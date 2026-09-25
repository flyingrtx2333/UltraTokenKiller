import json
import threading

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from websockets.sync.server import serve

from ultratokenkiller.broker import broker_router
from ultratokenkiller.config import Settings
from ultratokenkiller.mcp import dispatch
from ultratokenkiller.proxy import create_proxy, request_class, websocket_proxy_policy


def test_websocket_proxy_policy_bypasses_loopback_only():
    assert websocket_proxy_policy("ws://127.0.0.1:9000/v1/responses") is None
    assert websocket_proxy_policy("ws://localhost:9000/v1/responses") is None
    assert websocket_proxy_policy("ws://[::1]:9000/v1/responses") is None
    assert websocket_proxy_policy("wss://api.openai.com/v1/responses") is True


def test_request_class_separates_model_probes_and_transport():
    assert request_class("POST", "v1/chat/completions") == "model"
    assert request_class("POST", "api/show") == "probe"
    assert request_class("GET", "v1/models") == "probe"
    assert request_class("POST", "health") == "transport"


def test_probe_does_not_consume_model_budget_or_count_as_model(tmp_path, monkeypatch):
    monkeypatch.setenv("UTK_MAX_MODEL_REQUESTS", "1")

    def upstream(request):
        if request.url.path.endswith("/api/show"):
            return httpx.Response(404, json={"error": {"type": "not_ollama"}})
        return httpx.Response(200, json={"choices": [], "usage": {"prompt_tokens": 3, "completion_tokens": 1}})

    with TestClient(create_proxy("https://example.test/v1", tmp_path, httpx.MockTransport(upstream))) as client:
        assert client.post("/api/show", json={"name": "model"}).status_code == 404
        assert client.post("/v1/chat/completions", json={"model": "m", "messages": []}).status_code == 200
        assert client.post("/v1/chat/completions", json={"model": "m", "messages": []}).status_code == 429

    events = Store(tmp_path / "metrics.sqlite3").events()
    assert [item["kind"] for item in events] == ["input", "transport"]
    probe = events[1]
    assert probe["metadata"]["request_class"] == "probe"
    assert probe["metadata"]["path"] == "/api/show"
    assert probe["metadata"]["error_category"] == "not_ollama"


def test_model_session_compresses_and_header_is_not_forwarded(tmp_path, monkeypatch):
    sent = []

    def compress(_self, text, session, hint=None, query=""):
        assert session == "hermes_bound"
        return {"content": "short", "saved_tokens": 20, "recovery_id": "abcdefghijklmnop"}

    monkeypatch.setattr("ultratokenkiller.proxy.BrokerClient.compress", compress)

    def upstream(request):
        sent.append(request)
        return httpx.Response(200, json={"choices": [], "usage": {"prompt_tokens": 4, "completion_tokens": 1}})

    recovered = "UTK_RETRIEVED_ORIGINAL\n" + ("keep" * 100)
    envelope = json.dumps({"output": "x" * 400, "stdout": recovered, "exit_code": 7, "error": None})
    payload = {"model": "m", "messages": [{"role": "tool", "content": envelope}]}
    with TestClient(create_proxy("https://example.test/v1", tmp_path, httpx.MockTransport(upstream))) as client:
        assert client.post("/v1/chat/completions", json={"model": "m", "messages": []},
                           headers={"x-utk-session-id": "hermes_bound"}).status_code == 200
        assert client.post("/v1/chat/completions", json=payload,
                           headers={"x-utk-session-id": "hermes_bound"}).status_code == 200

    assert "x-utk-session-id" not in sent[-1].headers
    messages = json.loads(sent[-1].content)["messages"]
    rendered = json.loads(next(item for item in messages if item.get("role") == "tool")["content"])
    assert rendered == {"output": "short", "stdout": recovered, "exit_code": 7, "error": None}
    event = Store(tmp_path / "metrics.sqlite3").events()[0]
    assert event["metadata"]["changed_tool_results"] == 1
    assert event["saved_tokens"] > 0
    assert event["metadata"]["estimator"].endswith("model_unmapped")
    assert event["metadata"]["token_estimate_exact_for_model"] is False
    assert event["metadata"]["estimated_saved_tokens_basis"] == "estimated_prompt_delta"
    assert event["metadata"]["cost_estimate_status"] == "unavailable_no_price_catalog"


def test_mixed_tool_output_compresses_through_model_proxy_and_remains_recoverable(tmp_path, monkeypatch):
    from ultratokenkiller.compression import compress_content
    from ultratokenkiller.recovery import RecoveryVault

    vault = RecoveryVault()
    search = "\n".join(f"src/app.py:{n}:match {n}" for n in range(80))
    mixed = "Build output\n" + "\n".join(["INFO completed stage"] * 80)
    mixed += "\nERROR permission denied at src/app.py:42\n" + search

    def compress(_self, text, session, hint=None, query=""):
        result = compress_content(text, session=session, vault=vault, hint=hint, query=query)
        return {"content": result.content, "saved_tokens": result.saved_tokens,
                "recovery_id": result.recovery_id, "fallback": result.fallback}

    monkeypatch.setattr("ultratokenkiller.proxy.BrokerClient.compress", compress)
    sent = []

    def upstream(request):
        sent.append(request)
        return httpx.Response(200, json={"choices": [], "usage": {"prompt_tokens": 10, "completion_tokens": 1}})

    envelope = json.dumps({"output": mixed, "stdout": "already captured", "exit_code": 7, "error": None})
    payload = {"model": "m", "messages": [
        {"role": "user", "content": "Review the build output."},
        {"role": "tool", "content": envelope},
    ]}
    with TestClient(create_proxy("https://example.test/v1", tmp_path, httpx.MockTransport(upstream))) as client:
        assert client.post("/v1/chat/completions", json={"model": "m", "messages": []},
                           headers={"x-utk-session-id": "hermes_mixed"}).status_code == 200
        response = client.post("/v1/chat/completions", json=payload,
                               headers={"x-utk-session-id": "hermes_mixed"})
    assert response.status_code == 200

    assert "x-utk-session-id" not in sent[-1].headers
    forwarded = json.loads(sent[-1].content)
    tool_result = json.loads(next(item for item in forwarded["messages"] if item.get("role") == "tool")["content"])
    assert tool_result["exit_code"] == 7
    assert tool_result["error"] is None
    assert tool_result["stdout"] == "already captured"
    assert "Build output" in tool_result["output"]
    assert "ERROR permission denied at src/app.py:42" in tool_result["output"]
    assert "src/app.py\n" in tool_result["output"]
    assert "[UTK:" in tool_result["output"]
    handle = tool_result["output"].split("UTK retrieve: ", 1)[1].strip()
    assert vault.retrieve("hermes_mixed", handle)["content"] == mixed
    event = Store(tmp_path / "metrics.sqlite3").events()[0]
    assert event["metadata"]["changed_tool_results"] == 1
    assert event["saved_tokens"] > 0
from ultratokenkiller.recovery import RecoveryVault
from ultratokenkiller.store import Store


def test_anthropic_stream_accumulates_usage_and_preserves_headers(tmp_path):
    Settings(caveman="lite").save(tmp_path)
    sent = []
    stream = (b'event: message_start\ndata: {"type":"message_start","message":{"usage":{"input_tokens":20,"output_tokens":1,"cache_read_input_tokens":12}}}\n\n'
              b'event: message_delta\ndata: {"type":"message_delta","usage":{"output_tokens":7}}\n\n')
    def upstream(request):
        sent.append(request)
        return httpx.Response(200, content=stream, headers={"content-type": "text/event-stream"})
    with TestClient(create_proxy("https://example.test/v1", tmp_path, httpx.MockTransport(upstream))) as client:
        response = client.post("/v1/messages", headers={"x-api-key": "test-secret", "anthropic-version": "2023-06-01"},
                               json={"system": "keep this", "messages": [{"role": "user", "content": "hello"}]})
    assert response.content == stream
    assert sent[0].headers["x-api-key"] == "test-secret"
    payload = json.loads(sent[0].content)
    assert payload["system"].startswith("keep this")
    assert payload["messages"] == [{"role": "user", "content": "hello"}]
    event = Store(tmp_path / "metrics.sqlite3").events()[0]
    assert (event["input_tokens"], event["output_tokens"], event["cached_tokens"]) == (20, 7, 12)


def test_chat_completions_stream_is_byte_preserved_and_usage_recorded(tmp_path):
    stream = (
        b'data: {"choices":[{"index":0,"delta":{"content":"answer"}}]}\n\n'
        b'data: {"choices":[],"usage":{"prompt_tokens":17,"completion_tokens":3}}\n\n'
        b"data: [DONE]\n\n"
    )

    def upstream(request):
        assert request.url.path == "/v1/chat/completions"
        assert json.loads(request.content)["stream"] is True
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=stream)

    with TestClient(create_proxy(
        "https://example.test/v1", tmp_path, httpx.MockTransport(upstream)
    )) as client:
        response = client.post("/v1/chat/completions", json={
            "model": "gpt-4o",
            "stream": True,
            "stream_options": {"include_usage": True},
            "messages": [{"role": "user", "content": "hello"}],
        })

    assert response.status_code == 200
    assert response.content == stream
    event = Store(tmp_path / "metrics.sqlite3").events()[0]
    assert event["success"] is True
    assert (event["input_tokens"], event["output_tokens"]) == (17, 3)


def test_http_200_sse_error_is_classified_as_model_failure(tmp_path):
    stream = b'event: error\ndata: {"type":"error","error":{"type":"upstream_error"}}\n\n'

    def upstream(request):
        return httpx.Response(200, content=stream, headers={"content-type": "text/event-stream"})

    with TestClient(create_proxy("https://example.test/v1", tmp_path, httpx.MockTransport(upstream))) as client:
        response = client.post("/v1/chat/completions", json={"model": "m", "messages": []})
    assert response.status_code == 200
    assert response.content == stream
    event = Store(tmp_path / "metrics.sqlite3").events()[0]
    assert event["success"] is False
    assert event["metadata"]["error_category"] == "upstream_stream_error"


def test_websocket_text_binary_and_usage(tmp_path):
    seen = []
    def upstream(socket):
        seen.append(socket.request.headers.get("Authorization"))
        for message in socket:
            if isinstance(message, bytes):
                socket.send(message)
            else:
                socket.send('{"type":"response.completed","response":{"usage":{"input_tokens":4,"output_tokens":2}}}')
    with serve(upstream, "127.0.0.1", 0) as server:
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        port = server.socket.getsockname()[1]
        with TestClient(create_proxy(f"http://127.0.0.1:{port}/v1", tmp_path)) as client:
            with client.websocket_connect("/v1/responses", headers={"Authorization": "Bearer opaque"}) as socket:
                socket.send_bytes(b"binary\x00")
                assert socket.receive_bytes() == b"binary\x00"
                socket.send_text('{"type":"response.create"}')
                assert json.loads(socket.receive_text())["type"] == "response.completed"
        server.shutdown()
        worker.join(timeout=5)
    assert seen == ["Bearer opaque"]
    assert Store(tmp_path / "metrics.sqlite3").events()[0]["output_tokens"] == 2


def test_websocket_compresses_response_create_and_budgets_model_calls_only(tmp_path, monkeypatch):
    from ultratokenkiller.compression import compress_content
    from ultratokenkiller.recovery import RecoveryVault

    Settings(caveman="off").save(tmp_path)
    monkeypatch.setenv("UTK_MAX_MODEL_REQUESTS", "2")
    vault = RecoveryVault()

    def compress(_self, text, session, hint=None, query=""):
        result = compress_content(text, session=session, vault=vault, hint=hint, query=query)
        return {"content": result.content, **result.metadata()}

    monkeypatch.setattr("ultratokenkiller.proxy.BrokerClient.compress", compress)
    seen = []
    upstream_headers = {}
    cancel_seen = threading.Event()
    original = "\n".join([*("INFO repeated tool output" for _ in range(100)),
                           "ERROR permission denied at src/app.py:42"])
    create_event = {
        "type": "response.create",
        "response": {
            "model": "gpt-4o",
            "input": [{"type": "function_call_output", "call_id": "call-1", "output": original}],
        },
    }

    def upstream(socket):
        upstream_headers.update(socket.request.headers)
        for message in socket:
            event = json.loads(message)
            seen.append(event)
            if event.get("type") == "response.create":
                socket.send(json.dumps({
                    "type": "response.completed",
                    "response": {"id": f"resp-{len(seen)}",
                                 "usage": {"input_tokens": 123, "output_tokens": 7}},
                }))
            elif event.get("type") == "response.cancel":
                cancel_seen.set()

    with serve(upstream, "127.0.0.1", 0) as server:
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        port = server.socket.getsockname()[1]
        with TestClient(create_proxy(f"http://127.0.0.1:{port}/v1", tmp_path)) as client:
            with client.websocket_connect(
                "/v1/responses",
                headers={"Authorization": "Bearer opaque", "x-utk-session-id": "ws-session"},
            ) as socket:
                socket.send_text(json.dumps({"type": "response.create", "response": {
                    "model": "gpt-4o", "input": []}}))
                assert json.loads(socket.receive_text())["type"] == "response.completed"
                socket.send_text(json.dumps(create_event))
                completed = json.loads(socket.receive_text())
                assert completed["type"] == "response.completed"
                for _ in range(40):
                    if any(event["metadata"].get("changed_tool_results")
                           for event in Store(tmp_path / "metrics.sqlite3").events()):
                        break
                    threading.Event().wait(0.05)
                socket.send_text(json.dumps({"type": "response.cancel", "response_id": "resp-1"}))
                assert cancel_seen.wait(timeout=5)
                socket.send_text(json.dumps(create_event))
                rejected = json.loads(socket.receive_text())
                assert rejected["type"] == "error"
                assert "budget exhausted" in rejected["error"]["message"]
        server.shutdown()
        worker.join(timeout=5)

    assert len(seen) == 3
    assert seen[0]["type"] == "response.create"
    forwarded_output = seen[1]["response"]["input"][0]["output"]
    assert forwarded_output != original
    assert "ERROR permission denied at src/app.py:42" in forwarded_output
    handle = forwarded_output.split("UTK retrieve: ", 1)[1].strip()
    assert vault.retrieve("ws-session", handle)["content"] == original
    assert seen[2]["type"] == "response.cancel"
    assert upstream_headers["authorization"] == "Bearer opaque"
    assert "x-utk-session-id" not in upstream_headers

    event = next(event for event in Store(tmp_path / "metrics.sqlite3").events()
                 if event["metadata"].get("changed_tool_results"))
    assert event["model"] == "gpt-4o"
    assert (event["input_tokens"], event["output_tokens"]) == (123, 7)
    assert event["saved_tokens"] > 0
    assert event["metadata"]["transport"] == "websocket"
    assert event["metadata"]["session_id"] != "ws-session"
    assert "ws-session" not in json.dumps(event)


def test_websocket_retries_transient_handshake_before_counting_model_request(tmp_path, monkeypatch):
    import websockets.asyncio.client

    Settings(caveman="off").save(tmp_path)
    monkeypatch.setenv("UTK_MAX_MODEL_REQUESTS", "1")
    real_connect = websockets.asyncio.client.connect
    connect_attempts = 0
    received = []

    async def flaky_connect(*args, **kwargs):
        nonlocal connect_attempts
        connect_attempts += 1
        if connect_attempts < 3:
            raise OSError("temporary upstream handshake failure")
        return await real_connect(*args, **kwargs)

    monkeypatch.setattr("websockets.asyncio.client.connect", flaky_connect)

    def upstream(socket):
        for message in socket:
            event = json.loads(message)
            if event.get("type") == "response.create":
                received.append(event)
                socket.send(json.dumps({
                    "type": "response.completed",
                    "response": {"usage": {"input_tokens": 5, "output_tokens": 1}},
                }))

    with serve(upstream, "127.0.0.1", 0) as server:
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        port = server.socket.getsockname()[1]
        with TestClient(create_proxy(f"http://127.0.0.1:{port}/v1", tmp_path)) as client:
            with client.websocket_connect("/v1/responses") as socket:
                socket.send_text(json.dumps({
                    "type": "response.create",
                    "response": {"model": "gpt-4o", "input": "first model call"},
                }))
                assert json.loads(socket.receive_text())["type"] == "response.completed"
                socket.send_text(json.dumps({
                    "type": "response.create",
                    "response": {"model": "gpt-4o", "input": "second model call"},
                }))
                blocked = json.loads(socket.receive_text())
                assert blocked["type"] == "error"
                assert "budget exhausted" in blocked["error"]["message"]
        server.shutdown()
        worker.join(timeout=5)

    assert connect_attempts == 3
    assert len(received) == 1
    event = Store(tmp_path / "metrics.sqlite3").events()[0]
    assert event["success"] is True


@pytest.mark.parametrize(
    ("failure_type", "expected_category"),
    [
        ("error", "upstream_websocket_error"),
        ("response.failed", "upstream_websocket_error"),
        ("response.incomplete", "upstream_incomplete"),
        ("response.cancelled", "upstream_cancelled"),
    ],
)
def test_websocket_non_success_event_is_recorded_without_error_body(
    tmp_path, failure_type, expected_category
):
    Settings(caveman="off").save(tmp_path)
    failure = {"type": failure_type}
    if failure_type == "error":
        failure["error"] = {"type": "invalid_request_error", "message": "secret upstream detail"}
    else:
        failure["response"] = {"id": "resp-failed", "usage": {"input_tokens": 20, "output_tokens": 0}}

    def upstream(socket):
        for message in socket:
            if json.loads(message).get("type") == "response.create":
                socket.send(json.dumps(failure))

    with serve(upstream, "127.0.0.1", 0) as server:
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        port = server.socket.getsockname()[1]
        with TestClient(create_proxy(f"http://127.0.0.1:{port}/v1", tmp_path)) as client:
            with client.websocket_connect("/v1/responses") as socket:
                socket.send_text(json.dumps({
                    "type": "response.create",
                    "response": {"model": "gpt-4o", "input": "hello"},
                }))
                assert json.loads(socket.receive_text()) == failure
        server.shutdown()
        worker.join(timeout=5)

    event = Store(tmp_path / "metrics.sqlite3").events()[0]
    assert event["success"] is False
    assert event["metadata"]["error_category"] == expected_category
    assert "secret upstream detail" not in json.dumps(event)


def test_websocket_failed_response_does_not_count_estimated_savings(tmp_path, monkeypatch):
    from ultratokenkiller.compression import compress_content
    from ultratokenkiller.recovery import RecoveryVault

    Settings(caveman="off").save(tmp_path)
    vault = RecoveryVault()
    original = "\n".join([*("INFO repeated tool output" for _ in range(100)), "ERROR permission denied at src/app.py:42"])
    sent = []

    def compress(_self, text, session, hint=None, query=""):
        result = compress_content(text, session=session, vault=vault, hint=hint, query=query)
        return {"content": result.content, **result.metadata()}

    monkeypatch.setattr("ultratokenkiller.proxy.BrokerClient.compress", compress)

    def upstream(socket):
        for message in socket:
            event = json.loads(message)
            if event.get("type") == "response.create":
                sent.append(event)
                if len(sent) == 1:
                    socket.send(json.dumps({"type": "response.completed", "response": {
                        "id": "primer", "usage": {"input_tokens": 1, "output_tokens": 1}}}))
                    continue
                socket.send(json.dumps({
                    "type": "response.failed",
                    "response": {"id": "resp-failed"},
                    "error": {"message": "secret upstream detail"},
                }))
                return

    with serve(upstream, "127.0.0.1", 0) as server:
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        port = server.socket.getsockname()[1]
        with TestClient(create_proxy(f"http://127.0.0.1:{port}/v1", tmp_path)) as client:
            with client.websocket_connect(
                "/v1/responses", headers={"x-utk-session-id": "failed-compress"}
            ) as socket:
                socket.send_text(json.dumps({"type": "response.create", "response": {
                    "model": "gpt-4o", "input": []}}))
                assert json.loads(socket.receive_text())["type"] == "response.completed"
                socket.send_text(json.dumps({
                    "type": "response.create",
                    "response": {
                        "model": "gpt-4o",
                        "input": [{"type": "function_call_output", "call_id": "call-1", "output": original}],
                    },
                }))
                assert json.loads(socket.receive_text())["type"] == "response.failed"
        server.shutdown()
        worker.join(timeout=5)

    forwarded = sent[1]["response"]["input"][0]["output"]
    assert forwarded != original
    handle = forwarded.split("UTK retrieve: ", 1)[1].strip()
    assert vault.retrieve("failed-compress", handle)["content"] == original
    event = Store(tmp_path / "metrics.sqlite3").events()[0]
    assert event["success"] is False
    assert event["saved_tokens"] == 0
    assert event["metadata"]["estimated_saved_tokens"] == 0
    assert "secret upstream detail" not in json.dumps(event)


def test_websocket_reconnect_after_upstream_interruption_is_not_replayed(tmp_path):
    Settings(caveman="off").save(tmp_path)
    received = []
    attempts = 0
    attempts_lock = threading.Lock()

    def upstream(socket):
        nonlocal attempts
        with attempts_lock:
            attempts += 1
            attempt = attempts
        for message in socket:
            event = json.loads(message)
            if event.get("type") != "response.create":
                continue
            received.append(event)
            if attempt == 1:
                socket.close(code=1011, reason="private upstream detail")
            else:
                socket.send(json.dumps({
                    "type": "response.completed",
                    "response": {"id": "resp-reconnected", "usage": {"input_tokens": 8, "output_tokens": 2}},
                }))
            return

    with serve(upstream, "127.0.0.1", 0) as server:
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        port = server.socket.getsockname()[1]
        with TestClient(create_proxy(f"http://127.0.0.1:{port}/v1", tmp_path)) as client:
            with client.websocket_connect("/v1/responses") as socket:
                socket.send_text(json.dumps({
                    "type": "response.create",
                    "response": {"model": "gpt-4o", "input": "first attempt"},
                }))
                with pytest.raises(WebSocketDisconnect):
                    socket.receive_text()

            with client.websocket_connect("/v1/responses") as socket:
                socket.send_text(json.dumps({
                    "type": "response.create",
                    "response": {"model": "gpt-4o", "input": "explicit reconnect"},
                }))
                assert json.loads(socket.receive_text())["type"] == "response.completed"
        server.shutdown()
        worker.join(timeout=5)

    assert attempts == 2
    assert len(received) == 2
    events = Store(tmp_path / "metrics.sqlite3").events(limit=10)
    interrupted = next(event for event in events if not event["success"])
    completed = next(event for event in events if event["success"])
    assert interrupted["metadata"]["error_category"] == "websocket_interrupted"
    assert interrupted["saved_tokens"] == 0
    assert completed["metadata"]["external_id"] == "resp-reconnected"
    assert "private upstream detail" not in json.dumps(events)


def test_broker_auth_recovery_and_browser_denied():
    vault = RecoveryVault()
    app = FastAPI()
    app.include_router(broker_router(vault, "local-secret"))
    client = TestClient(app)
    body = {"content": json.dumps([{"value": 1}]*100), "session": "a"}
    assert client.post("/api/v1/internal/compress", json=body).status_code == 403
    headers = {"X-UTK-Token": "local-secret"}
    result = client.post("/api/v1/internal/compress", headers=headers, json=body).json()
    assert result["recovery_id"]
    response = client.post("/api/v1/internal/retrieve", headers=headers, json={"session": "a", "handle": result["recovery_id"]})
    assert response.json()["content"] == body["content"]
    assert client.post("/api/v1/internal/retrieve", headers=headers, json={"session": "b", "handle": result["recovery_id"]}).status_code == 410
    headers["Origin"] = "http://127.0.0.1"
    assert client.post("/api/v1/internal/compress", headers=headers, json=body).status_code == 403


def test_mcp_does_not_accept_session_override():
    class Broker:
        def retrieve(self, session, handle, offset, limit):
            assert session == "bound-session"
            return {"content": "original"}
    message = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "utk_retrieve", "arguments": {"handle": "h", "session": "other"}}}
    assert dispatch(message, "bound-session", Broker())["result"]["content"]
    assert dispatch(message, "", Broker())["result"]["isError"]
