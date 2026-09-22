import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import yaml

from ultratokenkiller.integrations import (
    HERMES_ALLOWLIST,
    HERMES_HOOK_COMMAND,
    HERMES_HOOK_START,
    HERMES_PLUGIN_NAME,
    CodexAdapter,
    HermesAdapter,
    START,
)


def test_codex_enable_is_idempotent_and_disable_preserves_user_config(tmp_path: Path):
    root = tmp_path / "codex"
    root.mkdir()
    config = root / "config.toml"
    config.write_text(
        'model = "gpt-test"\nmodel_provider = "openai"\n'
        'developer_instructions = "Keep my rule."\n[features]\napps = true\n',
        encoding="utf-8",
    )
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
    assert not (root / "plugins" / HERMES_PLUGIN_NAME).exists()


def test_hermes_enable_restores_existing_model_fields(tmp_path: Path):
    root = tmp_path / "hermes"
    root.mkdir()
    config = root / "config.yaml"
    original = (
        "model:\n  provider: openai\n  default: gpt-test\n"
        "  coding_instructions: keep-this\ntools:\n  enabled: true\n"
    )
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
    assert enabled["plugins"]["enabled"] == [HERMES_PLUGIN_NAME]
    adapter.disable()
    assert yaml.safe_load(config.read_text(encoding="utf-8")) == yaml.safe_load(original)


def test_hermes_plugin_merge_install_and_restore_are_scoped(tmp_path: Path):
    root = tmp_path / "hermes"
    root.mkdir()
    config = root / "config.yaml"
    original = (
        "model:\n  provider: openai\n"
        "plugins:\n  enabled:\n    - user-plugin\n"
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

    parsed = yaml.safe_load(config.read_text(encoding="utf-8"))
    assert parsed["plugins"]["enabled"] == ["user-plugin", HERMES_PLUGIN_NAME]
    assert parsed["hooks"]["post_tool_call"] == [{"command": "user-audit"}]
    plugin_dir = root / "plugins" / HERMES_PLUGIN_NAME
    assert (plugin_dir / "__init__.py").is_file()
    assert (plugin_dir / "plugin.yaml").is_file()
    assert HERMES_HOOK_START not in config.read_text(encoding="utf-8")
    approvals = json.loads(allowlist.read_text(encoding="utf-8"))["approvals"]
    assert approvals == [{"event": "post_tool_call", "command": "user-audit"}]

    adapter.disable()
    restored = yaml.safe_load(config.read_text(encoding="utf-8"))
    assert restored["plugins"]["enabled"] == ["user-plugin"]
    assert restored["hooks"]["post_tool_call"] == [{"command": "user-audit"}]
    assert not (plugin_dir / "__init__.py").exists()
    assert not (plugin_dir / "plugin.yaml").exists()


def test_hermes_enable_migrates_legacy_managed_hook_only(tmp_path: Path):
    root = tmp_path / "hermes"
    root.mkdir()
    config = root / "config.yaml"
    config.write_text(
        "model:\n  provider: openai\n"
        "hooks:\n  pre_tool_call:\n"
        "    - matcher: write_file\n      command: user-policy\n"
        f"    {HERMES_HOOK_START}\n"
        "    - matcher: \"^(terminal|shell)$\"\n"
        f"      command: \"{HERMES_HOOK_COMMAND}\"\n"
        "      timeout: 5\n      fail_closed: false\n"
        "    # <<< ultratokenkiller hermes hook <<<\n",
        encoding="utf-8",
    )
    allowlist = root / HERMES_ALLOWLIST
    allowlist.write_text(
        json.dumps(
            {
                "approvals": [
                    {"event": "pre_tool_call", "command": HERMES_HOOK_COMMAND, "managed_by": "utk"},
                    {"event": "pre_tool_call", "command": "user-policy", "managed_by": "user"},
                ]
            }
        ),
        encoding="utf-8",
    )

    HermesAdapter(root).enable(18788, tmp_path / "backups")
    parsed = yaml.safe_load(config.read_text(encoding="utf-8"))
    assert [entry["command"] for entry in parsed["hooks"]["pre_tool_call"]] == ["user-policy"]
    assert parsed["plugins"]["enabled"] == [HERMES_PLUGIN_NAME]
    approvals = json.loads(allowlist.read_text(encoding="utf-8"))["approvals"]
    assert approvals == [{"event": "pre_tool_call", "command": "user-policy", "managed_by": "user"}]


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


def test_invalid_hermes_allowlist_is_ignored_by_plugin_install(tmp_path: Path):
    root = tmp_path / "hermes"
    root.mkdir()
    config = root / "config.yaml"
    config.write_text("model:\n  provider: openai\n", encoding="utf-8")
    allowlist = root / HERMES_ALLOWLIST
    allowlist.write_text("not-json", encoding="utf-8")

    state = HermesAdapter(root).enable(18788, tmp_path / "backups")

    assert state.enabled
    assert allowlist.read_text(encoding="utf-8") == "not-json"
    assert yaml.safe_load(config.read_text(encoding="utf-8"))["plugins"]["enabled"] == [HERMES_PLUGIN_NAME]


def test_installed_hermes_plugin_resolves_utk_and_fails_open(tmp_path: Path, monkeypatch):
    root = tmp_path / "hermes"
    root.mkdir()
    (root / "config.yaml").write_text("model:\n  provider: openai\n", encoding="utf-8")
    HermesAdapter(root).enable(18788, tmp_path / "backups")
    plugin_path = root / "plugins" / HERMES_PLUGIN_NAME / "__init__.py"
    spec = importlib.util.spec_from_file_location("utk_hermes_plugin_test", plugin_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module.shutil, "which", lambda name: "/opt/utk" if name == "utk" else None)
    callbacks = {}

    class Context:
        def register_hook(self, event, callback):
            callbacks[event] = callback

    module.register(Context())
    assert set(callbacks) == {"pre_tool_call"}

    def successful_run(argv, **kwargs):
        assert argv == ["/opt/utk", "hermes-hook"]
        payload = json.loads(kwargs["input"])
        assert payload["tool_input"]["command"] == "git status"
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"action": "modify", "args": {"command": "utk exec -- git status", "timeout": 30}}),
            stderr="",
        )

    monkeypatch.setattr(module.subprocess, "run", successful_run)
    args = {"command": "git status", "timeout": 30}
    directive = callbacks["pre_tool_call"](tool_name="terminal", args=args, session_id="session-one")
    assert args["command"] == "utk exec -- git status"
    assert directive == {
        "action": "modify",
        "args": {"command": "utk exec -- git status", "timeout": 30},
    }

    def failing_run(*_args, **_kwargs):
        raise OSError("missing")

    monkeypatch.setattr(module.subprocess, "run", failing_run)
    original = {"command": "git status"}
    callbacks["pre_tool_call"](tool_name="terminal", args=original)
    assert original == {"command": "git status"}
