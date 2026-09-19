import asyncio
import copy
import json

import pytest

from ultratokenkiller.broker import BrokerClient
from ultratokenkiller.compression import compress_content
from ultratokenkiller.config import Settings
from ultratokenkiller.proxy import compress_request
from ultratokenkiller.recovery import RecoveryVault


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
