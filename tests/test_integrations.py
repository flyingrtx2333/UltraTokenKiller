import json
from pathlib import Path

import pytest
import yaml

from ultratokenkiller.integrations import (
    HERMES_ALLOWLIST,
    HERMES_HOOK_COMMAND,
    HERMES_HOOK_START,
    CodexAdapter,
    HermesAdapter,
    START,
)


def test_codex_enable_is_idempotent_and_disable_preserves_user_config(tmp_path: Path):
    root = tmp_path / "codex"
    root.mkdir()
    config = root / "config.toml"
    config.write_text('model = "gpt-test"\nmodel_provider = "openai"\ndeveloper_instructions = "Keep my rule."\n[features]\napps = true\n', encoding="utf-8")
    adapter = CodexAdapter(root)
    adapter.enable(18788, tmp_path / "backups")
    adapter.enable(18788, tmp_path / "backups")
    text = config.read_text(encoding="utf-8")
    assert text.count(START) == 1
    assert 'base_url = "http://127.0.0.1:18788/v1"' in text
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib
    parsed = tomllib.loads(text)
    assert parsed["model_provider"] == "utk"
    assert "Keep my rule." in parsed["developer_instructions"]
    adapter.disable()
    restored = config.read_text(encoding="utf-8")
    assert START not in restored
    assert 'model = "gpt-test"' in restored
    assert 'model_provider = "openai"' in restored
    assert 'developer_instructions = "Keep my rule."' in restored
    assert 'apps = true' in restored


def test_hermes_refuses_non_openai_provider(tmp_path: Path):
    root = tmp_path / "hermes"
    root.mkdir()
    (root / "config.yaml").write_text("model:\n  provider: anthropic\n", encoding="utf-8")
    adapter = HermesAdapter(root)
    state = adapter.enable(18788, tmp_path / "backups")
    assert not state.supported
    assert START not in (root / "config.yaml").read_text(encoding="utf-8")


def test_hermes_enable_restores_existing_model_fields(tmp_path: Path):
    root = tmp_path / "hermes"
    root.mkdir()
    config = root / "config.yaml"
    original = "model:\n  provider: openai\n  default: gpt-test\n  coding_instructions: keep-this\ntools:\n  enabled: true\n"
    config.write_text(original, encoding="utf-8")
    adapter = HermesAdapter(root)
    assert adapter.enable(18788, tmp_path / "backups").enabled
    enabled = config.read_text(encoding="utf-8")
    assert enabled.count("model:") == 1
    assert "provider: openai" in enabled
    assert "provider: custom" not in enabled
    assert "default: gpt-test" in enabled
    adapter.disable()
    restored = config.read_text(encoding="utf-8")
    assert "provider: openai" in restored
    assert "coding_instructions: keep-this" in restored
    assert "enabled: true" in restored


def test_hermes_enable_preserves_provider_while_proxying_base_url(tmp_path: Path):
    root = tmp_path / "hermes"
    root.mkdir()
    config = root / "config.yaml"
    original = (
        "model:\n"
        "  provider: alibaba-cn\n"
        "  base_url: https://dashscope.aliyuncs.com/compatible-mode/v1\n"
        "  default: deepseek-v4-flash-0731\n"
    )
    config.write_text(original, encoding="utf-8")

    adapter = HermesAdapter(root)
    assert adapter.enable(18788, tmp_path / "backups").enabled
    enabled = yaml.safe_load(config.read_text(encoding="utf-8"))
    assert enabled["model"]["provider"] == "alibaba-cn"
    assert enabled["model"]["base_url"] == "http://127.0.0.1:18788/v1"

    adapter.disable()
    assert yaml.safe_load(config.read_text(encoding="utf-8")) == yaml.safe_load(original)


def test_hermes_hook_merge_approval_and_restore_are_scoped(tmp_path: Path):
    root = tmp_path / "hermes"
    root.mkdir()
    config = root / "config.yaml"
    original = (
        "model:\n  provider: openai\n"
        "hooks:\n  post_tool_call:\n    - command: user-audit\n"
        "tools:\n  enabled: true\n"
    )
    config.write_text(original, encoding="utf-8")
    allowlist = root / HERMES_ALLOWLIST
    allowlist.write_text(
        '{"approvals":[{"event":"post_tool_call","command":"user-audit"}]}\n',
        encoding="utf-8",
    )
    adapter = HermesAdapter(root)
    adapter.enable(18788, tmp_path / "backups")
    adapter.enable(18788, tmp_path / "backups")
    enabled = config.read_text(encoding="utf-8")
    parsed = yaml.safe_load(enabled)
    assert parsed["hooks"]["post_tool_call"] == [{"command": "user-audit"}]
    assert parsed["hooks"]["pre_tool_call"] == [
        {
            "matcher": "^(terminal|shell)$",
            "command": HERMES_HOOK_COMMAND,
            "timeout": 5,
            "fail_closed": False,
        }
    ]
    assert enabled.count(HERMES_HOOK_START) == 1
    assert enabled.count(HERMES_HOOK_COMMAND) == 1
    approvals = __import__("json").loads(allowlist.read_text(encoding="utf-8"))["approvals"]
    assert sum(entry.get("command") == HERMES_HOOK_COMMAND for entry in approvals) == 1
    assert any(entry.get("command") == "user-audit" for entry in approvals)

    adapter.disable()
    restored = config.read_text(encoding="utf-8")
    assert HERMES_HOOK_START not in restored
    assert "command: user-audit" in restored
    assert "provider: openai" in restored
    approvals = json.loads(allowlist.read_text(encoding="utf-8"))["approvals"]
    assert not any(entry.get("command") == HERMES_HOOK_COMMAND for entry in approvals)
    assert any(entry.get("command") == "user-audit" for entry in approvals)


def test_hermes_hook_appends_to_existing_event_and_restores_it(tmp_path: Path):
    root = tmp_path / "hermes"
    root.mkdir()
    config = root / "config.yaml"
    original = (
        "model:\n  provider: openai\n"
        "hooks:\n  pre_tool_call:\n"
        "    - matcher: write_file\n      command: user-policy\n"
    )
    config.write_text(original, encoding="utf-8")

    adapter = HermesAdapter(root)
    adapter.enable(18788, tmp_path / "backups")
    entries = yaml.safe_load(config.read_text(encoding="utf-8"))["hooks"]["pre_tool_call"]
    assert [entry["command"] for entry in entries] == ["user-policy", HERMES_HOOK_COMMAND]

    adapter.disable()
    assert yaml.safe_load(config.read_text(encoding="utf-8")) == yaml.safe_load(original)


def test_hermes_preserves_matching_user_approval(tmp_path: Path):
    root = tmp_path / "hermes"
    root.mkdir()
    (root / "config.yaml").write_text("model:\n  provider: openai\n", encoding="utf-8")
    allowlist = root / HERMES_ALLOWLIST
    user_entry = {
        "event": "pre_tool_call",
        "command": HERMES_HOOK_COMMAND,
        "approved_at": "user-owned",
        "script_mtime_at_approval": None,
    }
    allowlist.write_text(json.dumps({"approvals": [user_entry]}) + "\n", encoding="utf-8")

    adapter = HermesAdapter(root)
    adapter.enable(18788, tmp_path / "backups")
    adapter.disable()

    assert json.loads(allowlist.read_text(encoding="utf-8"))["approvals"] == [user_entry]


def test_invalid_hermes_allowlist_does_not_change_config(tmp_path: Path):
    root = tmp_path / "hermes"
    root.mkdir()
    config = root / "config.yaml"
    original = "model:\n  provider: openai\n"
    config.write_text(original, encoding="utf-8")
    (root / HERMES_ALLOWLIST).write_text("not-json", encoding="utf-8")

    with pytest.raises(ValueError, match="allowlist"):
        HermesAdapter(root).enable(18788, tmp_path / "backups")

    assert config.read_text(encoding="utf-8") == original
