import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from ultratokenkiller import codex_session
from ultratokenkiller.config import Settings
from ultratokenkiller.hooks import codex_event, rewrite_literal
from ultratokenkiller.integrations import CodexAdapter

try:
    import tomllib
except ImportError:
    import tomli as tomllib


def test_scoped_overrides_preserve_user_hooks_environment_and_model(tmp_path):
    original = {"model": "user-model", "model_reasoning_effort": "high",
                "approval_policy": "on-request", "hooks": {"PreToolUse": [{"matcher": "x", "hooks": []}]},
                "shell_environment_policy": {"set": {"CUSTOM": "keep"}}}
    before = copy.deepcopy(original)
    overrides, environment = codex_session.session_overrides(Settings(), tmp_path, "a" * 32, original)
    parsed = tomllib.loads("\n".join(key + "=" + codex_session.toml_value(value) for key, value in overrides.items()))
    assert original == before
    assert not {"model", "model_reasoning_effort", "approval_policy"} & overrides.keys()
    assert parsed["shell_environment_policy"]["set"]["CUSTOM"] == "keep"
    assert len(parsed["hooks"]["PreToolUse"]) == 1
    assert parsed["hooks"]["PreToolUse"][0]["hooks"][0]["command"] == "utk hook codex"
    assert environment["UTK_CLIENT"] == "codex"
    assert parsed["mcp_servers"]["utk_recovery"]["env"]["UTK_SESSION_ID"] == environment["UTK_SESSION_ID"]
    assert parsed["model_providers"][parsed["model_provider"]]["env_http_headers"] == {"X-UTK-Session-Id": "UTK_SESSION_ID"}


def test_mcp_name_collision_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="Existing utk_recovery"):
        codex_session.session_overrides(Settings(), tmp_path, "a" * 32, {"mcp_servers": {"utk_recovery": {}}})


def test_client_gate_preserves_config_and_rejects_unknown_version(tmp_path, monkeypatch):
    adapter = CodexAdapter(tmp_path)
    adapter.config.write_text('model="kept"\nmodel_provider="openai"\n', encoding="utf-8")
    (tmp_path / "auth.json").write_text('{"auth_mode":"chatgpt"}', encoding="utf-8")
    before = adapter.config.read_bytes()
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, "codex-cli 0.138.0"))
    assert codex_session.validate_client(adapter, ["codex"])["model"] == "kept"
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, "codex-cli 0.153.4"))
    assert codex_session.validate_client(adapter, ["codex"])["model"] == "kept"
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, "codex-cli 0.139.0"))
    with pytest.raises(ValueError, match="not been verified"):
        codex_session.validate_client(adapter, ["codex"])
    assert adapter.config.read_bytes() == before


def test_macos_finds_chatgpt_bundled_codex(monkeypatch):
    bundled = "/Applications/ChatGPT.app/Contents/Resources/codex"
    monkeypatch.setattr(codex_session.shutil, "which", lambda name: None)
    monkeypatch.setattr(codex_session.sys, "platform", "darwin")
    monkeypatch.setattr(Path, "is_file", lambda path: path.as_posix() == bundled)
    assert codex_session.codex_executable()[0].replace("\\", "/") == bundled


def test_hook_correlation_preserves_other_fields_and_rejects_external_helpers():
    event = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_use_id": "call-read",
             "tool_input": {"command": "rg -n --with-filename . calculator.py", "workdir": "/tmp", "timeout_ms": 3000}}
    updated = codex_event(event, "a" * 32)["hookSpecificOutput"]["updatedInput"]
    assert "--hook-call-id " + hashlib.sha256(b"call-read").hexdigest() in updated["command"]
    assert updated["workdir"] == "/tmp" and updated["timeout_ms"] == 3000
    assert rewrite_literal("rg -n --pre=program . file", "a" * 32) is None
    assert rewrite_literal("rg -n --hostname-bin=program . file", "a" * 32) is None


def test_real_hook_stdio_utf8_produces_valid_rewrite(monkeypatch):
    monkeypatch.setenv("UTK_SESSION_ID", "a" * 32)
    event = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_use_id": "call-中文",
             "tool_input": {"command": "git status", "description": "检查状态"}}
    result = subprocess.run([sys.executable, "-m", "ultratokenkiller.hooks"],
        input=json.dumps(event, ensure_ascii=False).encode("utf-8"), capture_output=True, check=True)
    updated = json.loads(result.stdout)["hookSpecificOutput"]["updatedInput"]
    assert updated["command"].startswith("utk exec --session ")
    assert updated["description"] == "检查状态"


def test_launcher_scopes_environment_and_uses_selected_directory(tmp_path, monkeypatch):
    seen = {}
    monkeypatch.setattr(codex_session, "codex_executable", lambda: ["codex"])
    monkeypatch.setattr(codex_session, "validate_client", lambda *a: {"model": "preserved"})
    monkeypatch.setattr(codex_session, "ensure_route", lambda *a: Settings())
    def trust(executable, overrides, cwd):
        seen["cwd"] = cwd
        return {"hooks.state": {"exact-hook": {"trusted_hash": "sha256:exact", "enabled": True}}}
    monkeypatch.setattr("ultratokenkiller.codex_hook_trust.approve_session_hook", trust)
    def launch(command, env):
        seen["command"] = command
        seen["environment"] = env
        return 7
    monkeypatch.setattr(subprocess, "call", launch)
    before = dict(os.environ)
    arguments = ["exec", "-C", str(tmp_path), "--model", "gpt-5.6-luna", "task"]
    assert codex_session.launch(arguments, tmp_path / "utk") == 7
    assert seen["cwd"] == tmp_path
    assert seen["command"][-len(arguments):] == arguments
    assert seen["environment"]["UTK_CLIENT"] == "codex"
    assert dict(os.environ) == before
