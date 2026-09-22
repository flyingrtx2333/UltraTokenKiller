import json
import threading

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
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
        assert client.post("/v1/chat/completions", json=payload,
                           headers={"x-utk-session-id": "hermes_bound"}).status_code == 200

    assert "x-utk-session-id" not in sent[0].headers
    messages = json.loads(sent[0].content)["messages"]
    rendered = json.loads(next(item for item in messages if item.get("role") == "tool")["content"])
    assert rendered == {"output": "short", "stdout": recovered, "exit_code": 7, "error": None}
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
