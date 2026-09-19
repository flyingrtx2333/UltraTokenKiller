import json
from io import StringIO

from ultratokenkiller.hermes_hook import main, rewrite_payload


def payload(command: str, tool_name: str = "terminal") -> dict:
    return {
        "hook_event_name": "pre_tool_call",
        "tool_name": tool_name,
        "tool_input": {"command": command, "timeout": 30},
        "session_id": "session-one",
        "profile": "default",
        "extra": {"tool_call_id": "call-one"},
    }


def test_rewrites_supported_terminal_command_with_correlation():
    directive = rewrite_payload(payload("git status"))
    assert directive is not None
    command = directive["args"]["command"]
    assert command.startswith("utk exec ")
    assert "--session hermes_" in command
    assert "--hook-call-id" in command
    assert command.endswith("-- git status")
    assert directive["args"]["timeout"] == 30


def test_hook_skips_unknown_complex_structured_and_already_wrapped_commands():
    assert rewrite_payload(payload("unknown-command --flag")) is None
    assert rewrite_payload(payload("git status | cat")) is None
    assert rewrite_payload(payload("git status", "browser")) is None
    assert rewrite_payload(payload("utk exec -- git status")) is None
    assert rewrite_payload({"hook_event_name": "post_tool_call"}) is None


def test_main_uses_noop_json_for_invalid_input(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", StringIO("not-json"))
    assert main() == 0
    assert json.loads(capsys.readouterr().out) == {}
