import asyncio
import copy
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from ultratokenkiller.broker import BrokerClient
from ultratokenkiller.compression import compress_content
from ultratokenkiller.config import Settings
from ultratokenkiller.prefix_guard import PrefixGuard, explicit_cache_ttl
from ultratokenkiller.proxy import compress_request, create_proxy
from ultratokenkiller.recovery import RecoveryVault
from ultratokenkiller.store import Store


def _output(protocol, value, call_id, marker=None):
    if protocol == "chat":
        return {"role": "tool", "tool_call_id": call_id, "content": value}
    if protocol == "anthropic":
        block = {"type": "tool_result", "tool_use_id": call_id, "content": value}
        if marker:
            block["cache_control"] = marker
        return {"role": "user", "content": [block]}
    return {"type": "function_call_output", "call_id": call_id, "output": value}


def _value(protocol, item):
    return (item["content"][0]["content"] if protocol == "anthropic" else
            item["output"] if protocol == "responses" else item["content"])


@pytest.mark.parametrize("protocol", ["chat", "anthropic", "responses"])
def test_first_history_is_frozen_then_only_new_suffix_is_compressed(
    tmp_path, monkeypatch, protocol
):
    vault = RecoveryVault()
    monkeypatch.setattr(BrokerClient, "compress", lambda self, text, session, **kwargs: {
        "content": (result := compress_content(text, session=session, vault=vault,
                                               **kwargs)).content, **result.metadata()})
    guard = PrefixGuard()
    field = "input" if protocol == "responses" else "messages"
    marker = {"type": "ephemeral", "ttl": "1h"} if protocol == "anthropic" else None
    old = "\n".join(["INFO old result"] * 120)
    new = "\n".join(["INFO new result"] * 120)
    first = {"model": "test", field: [_output(protocol, old, "old", marker)]}
    if protocol == "anthropic":
        first["system"] = [{"type": "text", "text": "instructions",
                            "cache_control": marker}]

    async def transform(payload, frozen, cold, prefix):
        return await compress_request(payload, Settings(), tmp_path, "session", "test",
                                      frozen_message_count=frozen, allow_cold=cold,
                                      forwarded_prefix=prefix)

    async def run(payload):
        return await guard.process(payload, session="session", protocol=protocol,
                                   model="test", transform=transform)

    first_sent, first_meta = asyncio.run(run(first))
    assert first_sent == first
    assert first_meta["prefix_guard"]["reason"] == "first_seen"

    second = copy.deepcopy(first)
    second[field].append(_output(protocol, new, "new"))
    sent, meta = asyncio.run(run(second))
    assert sent[field][0] == first[field][0]
    assert _value(protocol, sent[field][1]) != new
    assert meta["prefix_guard"]["frozen_messages"] == 1
    assert meta["changed_tool_results"] == 1
    repeated, repeated_meta = asyncio.run(run(second))
    assert repeated == sent
    assert repeated_meta["prefix_guard"]["frozen_messages"] == 2
    assert repeated_meta["changed_tool_results"] == 0


def test_explicit_ttl_allows_cold_recompression_and_recovery(tmp_path, monkeypatch):
    now = [100.0]
    guard = PrefixGuard(clock=lambda: now[0])
    vault = RecoveryVault()

    def compress(self, text, session, **kwargs):
        result = compress_content(text, session=session, vault=vault, **kwargs)
        return {"content": result.content, **result.metadata()}

    monkeypatch.setattr(BrokerClient, "compress", compress)
    old = "\n".join(["INFO cached output"] * 120)
    payload = {"model": "test", "messages": [_output("anthropic", old, "old",
               {"type": "ephemeral", "ttl": "5m"})]}

    async def transform(source, frozen, cold, prefix):
        return await compress_request(source, Settings(), tmp_path, "cold-session",
                                      frozen_message_count=frozen, allow_cold=cold,
                                      forwarded_prefix=prefix)

    async def run():
        return await guard.process(payload, session="cold-session", protocol="anthropic",
                                   model="test", transform=transform)

    first, _ = asyncio.run(run())
    assert first == payload
    now[0] = 459.0
    warm, warm_meta = asyncio.run(run())
    assert warm == payload
    assert warm_meta["prefix_guard"]["cold"] is False
    now[0] = 820.0
    cold, cold_meta = asyncio.run(run())
    rendered = _value("anthropic", cold["messages"][0])
    assert cold_meta["prefix_guard"]["cold"] is True
    assert rendered != old
    handle = rendered.split("UTK retrieve: ", 1)[1].strip()
    assert vault.retrieve("cold-session", handle)["content"] == old


def test_unknown_ttl_mismatch_and_expired_state_fail_closed():
    now = [0.0]
    guard = PrefixGuard(clock=lambda: now[0], idle_seconds=100)

    async def transform(payload, frozen, cold, prefix):
        result = copy.deepcopy(payload)
        result["messages"][frozen:] = [{**item, "content": "changed"}
                                        for item in result["messages"][frozen:]]
        if prefix is not None:
            result["messages"][:len(prefix)] = copy.deepcopy(prefix)
        return result, {}

    async def run(payload):
        return await guard.process(payload, session="s", protocol="anthropic",
                                   model="m", transform=transform)

    marker = {"type": "ephemeral"}
    payload = {"system": [{"type": "text", "text": "private",
                            "cache_control": marker}],
               "messages": [{"role": "tool", "content": "old"}]}
    assert explicit_cache_ttl(payload) is None
    assert asyncio.run(run(payload))[0] == payload
    now[0] = 90.0
    continued = copy.deepcopy(payload)
    continued["messages"].append({"role": "tool", "content": "new"})
    output, meta = asyncio.run(run(continued))
    assert output["messages"][0]["content"] == "old"
    assert output["messages"][1]["content"] == "changed"
    assert meta["prefix_guard"]["cold"] is False
    changed_system = copy.deepcopy(continued)
    changed_system["system"][0]["text"] = "different"
    assert asyncio.run(run(changed_system))[1]["prefix_guard"]["reason"] == "prefix_mismatch"
    now[0] = 191.0
    assert asyncio.run(run(changed_system))[1]["prefix_guard"]["reason"] == "first_seen"


def test_expired_ttl_does_not_rewrite_previously_compressed_history():
    now = [0.0]
    guard = PrefixGuard(clock=lambda: now[0])
    marker = {"type": "ephemeral", "ttl": "5m"}
    first = {"messages": [_output("anthropic", "old", "old", marker)]}
    second = copy.deepcopy(first)
    second["messages"].append(_output("anthropic", "new", "new"))

    async def transform(source, frozen, cold, prefix):
        result = copy.deepcopy(source)
        if prefix is not None:
            result["messages"][:len(prefix)] = copy.deepcopy(prefix)
        if frozen < len(result["messages"]):
            result["messages"][-1]["content"][0]["content"] = "compressed"
        return result, {}

    async def run(payload):
        return await guard.process(payload, session="s", protocol="anthropic",
                                   model="m", transform=transform)

    asyncio.run(run(first))
    asyncio.run(run(second))
    now[0] = 361.0
    result, meta = asyncio.run(run(second))
    assert _value("anthropic", result["messages"][1]) == "compressed"
    assert meta["prefix_guard"]["cold"] is False
    assert meta["prefix_guard"]["cold_fallback"] == "unrecoverable_history"


def test_cache_marker_protects_image_and_thinking_but_new_image_can_change(
    tmp_path, monkeypatch
):
    calls = []

    def compress(self, text, session, **kwargs):
        calls.append(text)
        return {"content": "data:image/png;base64,short", "recovery_id": "image-handle"}

    monkeypatch.setattr(BrokerClient, "compress", compress)
    old = {"role": "user", "content": [
        {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                      "data": "old-image"},
         "cache_control": {"type": "ephemeral", "ttl": "1h"}}]}
    thinking = {"role": "assistant", "content": [
        {"type": "thinking", "thinking": "opaque", "signature": "signed"}]}
    new = {"role": "user", "content": [
        {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                      "data": "new-image"}}]}
    payload = {"messages": [old, thinking, new]}
    result, meta = asyncio.run(compress_request(payload, Settings(), tmp_path, "s"))
    assert result["messages"][0] == old
    assert result["messages"][1] == thinking
    assert result["messages"][2]["content"][0]["source"]["data"] == "short"
    assert meta["changed_images"] == 1
    assert calls == ["data:image/png;base64,new-image"]


def test_capacity_and_concurrent_repeat_are_bounded():
    payload = {"messages": [{"role": "tool", "content": "large"}]}
    small = PrefixGuard(max_session_bytes=1)

    async def unchanged(source, frozen, cold, prefix):
        return source, {}

    _, meta = asyncio.run(small.process(payload, session="s", protocol="chat",
                                        model="m", transform=unchanged))
    assert meta["prefix_guard"]["tracked"] is False

    guard = PrefixGuard()
    calls = []

    async def change(source, frozen, cold, prefix):
        await asyncio.sleep(0.01)
        result = copy.deepcopy(source)
        if prefix is not None:
            result["messages"][:len(prefix)] = copy.deepcopy(prefix)
        if frozen < len(result["messages"]):
            calls.append(1)
            result["messages"][frozen]["content"] = "compressed"
        return result, {}

    async def run():
        await guard.process({"messages": []}, session="s", protocol="chat",
                            model="m", transform=change)
        return await asyncio.gather(*(guard.process(payload, session="s",
                                  protocol="chat", model="m", transform=change)
                                      for _ in range(2)))

    results = asyncio.run(run())
    assert results[0][0] == results[1][0]
    assert results[0][0]["messages"][0]["content"] == "compressed"
    assert len(calls) == 1


def test_proxy_keeps_existing_system_and_style_stable(tmp_path):
    Settings(caveman="lite").save(tmp_path)
    sent = []
    raw_bodies = []

    def upstream(request):
        raw_bodies.append(request.content)
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": []})

    first = {"model": "test", "messages": [
        {"role": "system", "content": "existing instruction"},
        {"role": "user", "content": "first"}]}
    second = copy.deepcopy(first)
    second["messages"].append({"role": "user", "content": "second"})
    first_body = json.dumps(first, ensure_ascii=False, indent=2).encode("utf-8")
    with TestClient(create_proxy("https://example.test/v1", tmp_path,
                                 httpx.MockTransport(upstream))) as client:
        headers = {"x-utk-session-id": "style-session"}
        assert client.post("/v1/chat/completions", content=first_body,
                           headers={**headers, "content-type": "application/json"}).status_code == 200
        Settings(caveman="full").save(tmp_path)
        assert client.post("/v1/chat/completions", json=second, headers=headers).status_code == 200
    assert sent[0] == first
    assert raw_bodies[0] == first_body
    assert sent[1] == second
    event = Store(tmp_path / "metrics.sqlite3").events()[0]
    assert event["metadata"]["response_style_applied"] is False
    assert event["metadata"]["response_style_skipped"] == "cache_prefix"
