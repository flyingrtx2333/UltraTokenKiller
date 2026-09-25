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


def test_rewrites_supported_terminal_command_with_correlation(tmp_path):
    executable = tmp_path / "UTK install with spaces" / "utk.exe"
    executable.parent.mkdir()
    executable.touch()
    directive = rewrite_payload(payload("git status"), executable=str(executable))
    assert directive is not None
    command = directive["args"]["command"]
    assert str(executable) in command
    assert " exec " in command
    assert "--session hermes_" in command
    assert "--hook-call-id" in command
    assert "--client hermes" in command
    assert command.endswith("-- git status")
    assert directive["args"]["timeout"] == 30


def test_hook_skips_unknown_complex_structured_and_already_wrapped_commands(tmp_path):
    executable = tmp_path / "utk"
    executable.touch()
    path = str(executable)
    assert rewrite_payload(payload("unknown-command --flag"), executable=path) is None
    assert rewrite_payload(payload("git status | cat"), executable=path) is None
    assert rewrite_payload(payload("git status", "browser"), executable=path) is None
    assert rewrite_payload(payload("utk exec -- git status"), executable=path) is None
    assert rewrite_payload({"hook_event_name": "post_tool_call"}, executable=path) is None


def test_hook_does_not_rewrite_when_utk_executable_is_missing():
    assert rewrite_payload(payload("git status"), executable="") is None


def test_hook_uses_own_entrypoint_when_terminal_path_lacks_utk(tmp_path, monkeypatch):
    executable = tmp_path / "UTK install with spaces" / "utk.exe"
    executable.parent.mkdir()
    executable.touch()
    monkeypatch.delenv("UTK_EXECUTABLE", raising=False)
    monkeypatch.setattr("sys.argv", [str(executable), "hermes-hook"])
    monkeypatch.setattr("ultratokenkiller.hermes_hook.shutil.which", lambda _: None)
    directive = rewrite_payload(payload("grep -n . example.txt"))
    assert directive is not None
    assert str(executable) in directive["args"]["command"]


def test_main_uses_noop_json_for_invalid_input(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", StringIO("not-json"))
    assert main() == 0
    assert json.loads(capsys.readouterr().out) == {}
