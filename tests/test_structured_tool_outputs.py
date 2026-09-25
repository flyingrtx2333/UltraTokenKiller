import asyncio
import copy
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from ultratokenkiller.broker import BrokerClient
from ultratokenkiller.compression import compress_content
from ultratokenkiller.config import Settings
from ultratokenkiller.proxy import CompressionBreaker, compress_request, create_proxy
from ultratokenkiller.recovery import RecoveryVault
from ultratokenkiller.store import Store


@pytest.mark.parametrize("kind", ["function_call_output", "custom_tool_call_output", "chat_tool", "anthropic_tool"])
def test_structured_outputs_preserve_media_ids_recovery_and_history(tmp_path, monkeypatch, kind):
    vault = RecoveryVault()
    original = json.dumps([{"value": 42}] * 100)
    def compress(self, text, session, **kwargs):
        result = compress_content(text, session=session, vault=vault)
        return {"content": result.content, **result.metadata()}
    monkeypatch.setattr(BrokerClient, "compress", compress)
    text = {"type": "input_text" if kind.endswith("output") else "text", "text": original}
    media = [{"type": "input_image", "image_url": "data:opaque"},
             {"type": "input_audio", "audio_url": "data:opaque-audio"},
             {"type": "encrypted_content", "encrypted_content": "opaque"}]
    if kind == "chat_tool":
        item = {"role": "tool", "tool_call_id": "call-1", "content": [text, *media]}
    elif kind == "anthropic_tool":
        item = {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "call-1", "content": [text, *media]}]}
    else:
        item = {"type": kind, "call_id": "call-1", "output": [text, *media]}
    payload = {"input": [item, {"role": "user", "content": "preserve my question"}]}
    before = copy.deepcopy(payload)
    result, meta = asyncio.run(compress_request(payload, Settings(), tmp_path, "session"))
    assert payload == before
    assert meta["changed_tool_results"] == 1
    assert meta["estimated_saved_tokens"] > 0
    out = result["input"][0]
    parts = out.get("output", out.get("content"))
    if kind == "anthropic_tool":
        parts = parts[0]["content"]
    assert parts[1:] == media
    assert result["input"][1] == payload["input"][1]
    restored = copy.deepcopy(result)
    selected = restored["input"][0]
    fields = selected.get("output", selected.get("content"))
    if kind == "anthropic_tool":
        fields = fields[0]["content"]
    fields[0]["text"] = original
    assert restored == before  # Call IDs, ordering and all other fields survive.
    handle = next(iter(vault.sessions["session"].entries))
    assert vault.retrieve("session", handle)["content"] == original
    repeated, _ = asyncio.run(compress_request(result, Settings(), tmp_path, "session"))
    assert repeated == result


def test_input_skip_reason_distinguishes_precompressed_from_missing_tool_result(tmp_path, monkeypatch):
    def compress(self, text, session, **kwargs):
        assert session == "hermes_bound"
        return {"content": text, "fallback": "already_compressed", "saved_tokens": 0}

    monkeypatch.setattr(BrokerClient, "compress", compress)
    precompressed = {"messages": [{"role": "tool", "content": "UTK retrieve: opaque-handle"}]}
    result, meta = asyncio.run(compress_request(precompressed, Settings(), tmp_path, "hermes_bound"))
    assert result == precompressed
    assert meta["candidate_tool_results"] == 1
    assert meta["tool_skip_reasons"] == {"already_compressed": 1}
    assert meta["estimated_saved_tokens"] == 0

    plain = {"messages": [{"role": "user", "content": "long ordinary message"}]}
    result, meta = asyncio.run(compress_request(plain, Settings(), tmp_path, "hermes_bound"))
    assert result == plain
    assert meta["candidate_tool_results"] == 0
    assert meta["tool_skip_reasons"] == {"no_tool_result": 1}


def test_hook_compression_is_not_counted_again_as_input_savings(tmp_path, monkeypatch):
    vault = RecoveryVault()
    original = json.dumps([{"value": 42}] * 100)
    hook_result = compress_content(original, session="hermes_bound", vault=vault)
    assert hook_result.saved_tokens > 0

    def compress(self, text, session, **kwargs):
        result = compress_content(text, session=session, vault=vault)
        return {"content": result.content, **result.metadata()}

    monkeypatch.setattr(BrokerClient, "compress", compress)
    payload = {"messages": [{"role": "tool", "content": hook_result.content}]}
    result, meta = asyncio.run(compress_request(payload, Settings(), tmp_path, "hermes_bound"))
    assert result == payload
    assert meta["tool_skip_reasons"] == {"already_compressed": 1}
    assert meta["estimated_saved_tokens"] == 0
    assert vault.retrieve("hermes_bound", hook_result.recovery_id)["content"] == original


def test_warm_history_and_provider_cache_markers_remain_stable_across_turns(tmp_path, monkeypatch):
    vault = RecoveryVault()

    def compress(self, text, session, **kwargs):
        result = compress_content(text, session=session, vault=vault, **kwargs)
        return {"content": result.content, **result.metadata()}

    monkeypatch.setattr(BrokerClient, "compress", compress)
    first_original = json.dumps([{"result": f"record-{index}", "status": "ready"}
                                 for index in range(100)])
    system = [{"type": "text", "text": "Keep the cached instructions.",
               "cache_control": {"type": "ephemeral", "ttl": "1h"}}]
    thinking = {"type": "thinking", "thinking": "private reasoning", "signature": "opaque"}
    first_payload = {"model": "claude-test", "system": system, "messages": [
        {"role": "assistant", "content": [thinking, {"type": "text", "text": "tool call"}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1",
                                            "content": first_original,
                                            "cache_control": {"type": "ephemeral", "ttl": "1h"}}]},
    ]}

    first, _ = asyncio.run(compress_request(first_payload, Settings(), tmp_path, "warm-session"))
    old_result = first["messages"][1]["content"][0]["content"]
    assert old_result != first_original
    assert first["system"] == system
    assert first["messages"][0]["content"][0] == thinking
    assert first["messages"][1]["content"][0]["cache_control"] == {
        "type": "ephemeral", "ttl": "1h"
    }

    second_original = json.dumps([{"event": f"event-{index}", "state": "complete"}
                                  for index in range(100)])
    second_payload = copy.deepcopy(first)
    second_payload["messages"].append({"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "t2", "content": second_original,
         "cache_control": {"type": "ephemeral", "ttl": "1h"}}
    ]})
    second, metadata = asyncio.run(
        compress_request(second_payload, Settings(), tmp_path, "warm-session")
    )
    assert second["system"] == system
    assert second["messages"][0]["content"][0] == thinking
    assert second["messages"][1]["content"][0]["content"] == old_result
    assert second["messages"][1]["content"][0]["cache_control"] == {
        "type": "ephemeral", "ttl": "1h"
    }
    assert second["messages"][2]["content"][0]["content"] != second_original
    assert metadata["changed_tool_results"] == 1

    third_payload = copy.deepcopy(second)
    third_payload["messages"].append({"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "t3", "content": first_original}
    ]})
    third, third_metadata = asyncio.run(
        compress_request(third_payload, Settings(), tmp_path, "warm-session")
    )
    duplicate = json.loads(third["messages"][3]["content"][0]["content"])
    assert duplicate == {
        "_utk_duplicate": True,
        "_utk_recovery": json.loads(old_result)["_utk_recovery"],
    }
    assert third_metadata["changed_tool_results"] == 1
    assert third_metadata["estimated_saved_tokens"] > 0


@pytest.mark.parametrize("protocol", ["openai_chat", "anthropic", "responses"])
def test_warm_tool_prefix_stays_stable_when_new_provider_turn_is_compressed(
    tmp_path, monkeypatch, protocol
):
    vault = RecoveryVault()

    def compress(self, text, session, **kwargs):
        result = compress_content(text, session=session, vault=vault, **kwargs)
        return {"content": result.content, **result.metadata()}

    monkeypatch.setattr(BrokerClient, "compress", compress)
    original_prefix = json.dumps(
        [{"path": f"src/module-{index}.py", "status": "ready", "line": index}
         for index in range(120)],
        ensure_ascii=False,
    )
    new_output = json.dumps(
        [{"path": f"tests/case-{index}.py", "status": "passed", "line": index}
         for index in range(120)],
        ensure_ascii=False,
    )
    cache_marker = {"type": "ephemeral", "ttl": "1h"}

    def output(original, call_id, *, marker=False):
        if protocol == "openai_chat":
            return {"role": "tool", "tool_call_id": call_id, "content": original}
        if protocol == "anthropic":
            result = {"type": "tool_result", "tool_use_id": call_id, "content": original}
            if marker:
                result["cache_control"] = dict(cache_marker)
            return {"role": "user", "content": [result]}
        return {"type": "function_call_output", "call_id": call_id, "output": original}

    def text_of(item):
        if protocol == "openai_chat":
            return item["content"]
        if protocol == "anthropic":
            return item["content"][0]["content"]
        return item["output"]

    if protocol == "responses":
        first_payload = {"input": [output(original_prefix, "old-call", marker=True)]}
        field = "input"
    else:
        first_payload = {"messages": [output(original_prefix, "old-call", marker=True)]}
        field = "messages"

    first, _ = asyncio.run(
        compress_request(first_payload, Settings(), tmp_path, f"warm-{protocol}")
    )
    stable_prefix = text_of(first[field][0])
    assert stable_prefix != original_prefix

    continued = copy.deepcopy(first)
    continued[field].append(output(new_output, "new-call"))
    second, metadata = asyncio.run(
        compress_request(continued, Settings(), tmp_path, f"warm-{protocol}")
    )

    assert text_of(second[field][0]) == stable_prefix
    assert text_of(second[field][1]) != new_output
    assert metadata["changed_tool_results"] == 1
    assert metadata["estimated_saved_tokens"] > 0
    if protocol == "anthropic":
        assert second[field][0]["content"][0]["cache_control"] == cache_marker


def test_broker_failure_is_reported_without_changing_tool_output(tmp_path, monkeypatch):
    def unavailable(self, text, session, **kwargs):
        return {"content": text, "fallback": "broker_unavailable", "saved_tokens": 0}

    monkeypatch.setattr(BrokerClient, "compress", unavailable)
    payload = {"messages": [{"role": "tool", "content": "diagnostic details"}]}
    result, meta = asyncio.run(compress_request(payload, Settings(), tmp_path, "hermes_bound"))
    assert result == payload
    assert meta["tool_skip_reasons"] == {"broker_unavailable": 1}
    assert meta["compression_fallback"] == "broker_unavailable"


def test_unexpected_compressor_error_preserves_tool_status_envelope(tmp_path, monkeypatch):
    def broken(self, text, session, **kwargs):
        raise RuntimeError("secret diagnostic details")

    monkeypatch.setattr(BrokerClient, "compress", broken)
    content = json.dumps({"exit_code": 17, "stdout": "important output", "stderr": "fatal: denied"})
    payload = {"messages": [{"role": "tool", "content": content}]}
    result, meta = asyncio.run(compress_request(payload, Settings(), tmp_path, "bound"))
    assert result == payload
    assert meta["estimated_saved_tokens"] == 0
    assert meta["tool_skip_reasons"] == {"compression_error": 1}
    assert meta["compression_fallback"] == "compression_error"
    assert "secret" not in json.dumps(meta)


def test_unexpected_image_compressor_error_preserves_image(tmp_path, monkeypatch):
    def broken(self, text, session, **kwargs):
        raise RuntimeError("secret diagnostic details")

    monkeypatch.setattr(BrokerClient, "compress", broken)
    payload = {"messages": [{"role": "user", "content": [
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,YWJj"}}
    ]}]}
    result, meta = asyncio.run(compress_request(payload, Settings(), tmp_path, "bound"))
    assert result == payload
    assert meta["changed_images"] == 0
    assert meta["tool_skip_reasons"] == {}
    assert meta["image_skip_reasons"] == {"compression_error": 1}
    assert meta["compression_fallback"] == "compression_error"
    assert "secret" not in json.dumps(meta)


def test_slow_compression_forwards_original_request(tmp_path, monkeypatch):
    calls = []

    async def slow(*args):
        calls.append(1)
        await asyncio.sleep(0.1)

    monkeypatch.setattr("ultratokenkiller.proxy.compress_request", slow)
    monkeypatch.setattr("ultratokenkiller.proxy.INPUT_COMPRESSION_TIMEOUT_SECONDS", 0.01)
    sent = []

    def upstream(request):
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": []})

    payload = {"model": "test-model", "messages": [{"role": "user", "content": "keep exact"}]}
    with TestClient(create_proxy("https://example.test/v1", tmp_path, httpx.MockTransport(upstream))) as client:
        response = client.post("/v1/chat/completions", json=payload, headers={"x-utk-session-id": "bound"})
    assert response.status_code == 200
    assert sent == [payload]
    assert calls == [1]
    event = Store(tmp_path / "metrics.sqlite3").events()[0]
    assert event["metadata"]["compression_fallback"] == "compression_timeout"


def test_repeated_compression_failures_open_local_circuit(tmp_path, monkeypatch):
    calls = []

    async def broken(*args):
        calls.append(1)
        raise RuntimeError("private details")

    monkeypatch.setattr("ultratokenkiller.proxy.compress_request", broken)
    sent = []

    def upstream(request):
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": []})

    payload = {"model": "test-model", "messages": [{"role": "user", "content": "keep exact"}]}
    with TestClient(create_proxy("https://example.test/v1", tmp_path, httpx.MockTransport(upstream))) as client:
        for _ in range(4):
            assert client.post("/v1/chat/completions", json=payload).status_code == 200
    assert sent == [payload] * 4
    assert len(calls) == 3
    events = Store(tmp_path / "metrics.sqlite3").events()
    assert events[0]["metadata"]["compression_fallback"] == "compression_circuit_open"
    assert events[0]["model"] == "test-model"
    assert all(event["metadata"]["compression_fallback"] == "compression_error" for event in events[1:])


def test_compression_circuit_recovers_after_cooldown(monkeypatch):
    now = [100.0]
    monkeypatch.setattr("ultratokenkiller.proxy.time.monotonic", lambda: now[0])
    breaker = CompressionBreaker(threshold=2, cooldown_seconds=30)
    breaker.failure()
    assert not breaker.is_open()
    breaker.failure()
    assert breaker.is_open()
    now[0] = 131.0
    assert not breaker.is_open()
    breaker.success()
    breaker.failure()
    assert not breaker.is_open()
