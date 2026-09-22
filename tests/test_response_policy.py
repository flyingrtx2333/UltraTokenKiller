import pytest

from ultratokenkiller.engines import apply_response_style


def test_chat_completions_uses_widely_supported_system_role():
    payload = {"messages": [{"role": "user", "content": "Be concise"}]}
    result = apply_response_style(payload, "lite", protocol="openai-chat")
    assert result["messages"][0]["role"] == "system"
    assert result["messages"][1:] == payload["messages"]


@pytest.mark.parametrize("mode", ["lite", "full", "ultra", "wenyan-lite", "wenyan-full", "wenyan-ultra"])
def test_policy_idempotent_preserves_fields(mode):
    payload = {"input": "Review this", "model": "chosen-model", "reasoning": {"effort": "high"}, "tools": [{"name": "keep"}]}
    first = apply_response_style(payload, mode)
    assert apply_response_style(first, mode) == first
    assert first["model"] == payload["model"]
    assert first["reasoning"] == payload["reasoning"]
    assert first["tools"] == payload["tools"]


def test_detailed_and_structured_answers_not_overridden():
    detailed = {"messages": [{"role": "user", "content": "请详细解释实现原理"}]}
    assert apply_response_style(detailed, "ultra") == detailed
    schema = {"input": "answer", "text": {"format": {"type": "json_schema", "schema": {"type": "object"}}}}
    assert apply_response_style(schema, "ultra") == schema


def test_anthropic_block_cache_metadata_untouched():
    payload = {"system": [{"type": "text", "text": "stable", "cache_control": {"type": "ephemeral"}}], "messages": []}
    first = apply_response_style(payload, "lite", protocol="anthropic")
    assert first["system"][0] == payload["system"][0]
    assert apply_response_style(first, "lite", protocol="anthropic") == first
