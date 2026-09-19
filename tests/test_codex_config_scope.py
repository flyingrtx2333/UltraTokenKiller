"""Offline Codex parser regression; never submit a model request."""
import os

import pytest

from ultratokenkiller.codex_session import session_command


@pytest.mark.parametrize("arguments", [["exec", "--oss"], ["exec", "--profile=x"],
    ["exec", "-px"], ["exec", "--local-provider", "ollama"]])
def test_provider_switch_is_rejected_before_startup(arguments, tmp_path, monkeypatch):
    from ultratokenkiller import codex_session
    monkeypatch.setattr(codex_session, "ensure_route", lambda *a: pytest.fail("must not start service"))
    with pytest.raises(ValueError, match="bypass"):
        codex_session.launch(arguments, tmp_path)


@pytest.mark.parametrize("failure", ["provider", "url", "recovery"])
def test_effective_config_mismatch_blocks_launch(tmp_path, monkeypatch, failure):
    from ultratokenkiller.codex_session import verify_session_config, session_overrides
    from ultratokenkiller.config import Settings
    values, _ = session_overrides(Settings(), tmp_path, "a" * 32)
    provider = values["model_provider"]
    config = {"model_provider": provider, "model_providers": {provider: {
        "base_url": values[f"model_providers.{provider}.base_url"]}},
        "mcp_servers": {"utk_recovery": {"command": values["mcp_servers.utk_recovery.command"],
        "env": values["mcp_servers.utk_recovery.env"]}}}
    if failure == "provider":
        config["model_provider"] = "headroom"
    elif failure == "url":
        config["model_providers"][provider]["base_url"] = "http://127.0.0.1:8788"
    else:
        config["mcp_servers"]["utk_recovery"]["env"] = {}
    monkeypatch.setattr("ultratokenkiller.codex_hook_trust.inspect_codex", lambda *a: {"config": config})
    with pytest.raises(ValueError, match="no model request"):
        verify_session_config(["codex"], session_command(["codex"], ["exec"], values), tmp_path, values)


def test_config_scopes_preserve_user_order_and_literal_tail():
    command = session_command(["codex"], ["-c", "model=old", "exec", "--config=model=new",
        "--", "-c", "literal prompt"], {"model_provider": "utk"})
    assert command == ["codex", "exec", "-c", "model=old", "-c", "model=new",
        "-c", 'model_provider="utk"', "--", "-c", "literal prompt"]


@pytest.mark.skipif(not os.environ.get("UTK_TEST_CODEX_EXECUTABLE"), reason="Installed Codex offline parser required")
def test_real_codex_resolves_managed_route_after_subcommand(tmp_path, monkeypatch):
    executable = os.environ["UTK_TEST_CODEX_EXECUTABLE"]
    (tmp_path / "config.toml").write_text('model_provider="openai"\n', encoding="utf-8")
    overrides = {
        "model_provider": "utk_offline",
        "model_providers.utk_offline.name": "UTK offline fixture",
        "model_providers.utk_offline.base_url": "http://127.0.0.1:1/v1",
        "model_providers.utk_offline.wire_api": "responses",
    }
    command = session_command([executable], ["-c", 'model_provider="openai"', "app-server",
        "-c", 'approval_policy="never"'], overrides)
    from ultratokenkiller.codex_hook_trust import inspect_codex
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    config = inspect_codex(command, tmp_path, "config/read", {"includeLayers": False})["config"]
    assert config["model_provider"] == "utk_offline"
    assert config["model_providers"]["utk_offline"]["base_url"] == "http://127.0.0.1:1/v1"
