import pytest

from ultratokenkiller.hooks import codex_event, hermes_terminal, rewrite_literal

SESSION = "a"*32


def test_non_shell_tool_with_command_field_is_not_rewritten():
    event = {"hook_event_name": "PreToolUse", "tool_name": "other_tool",
             "tool_input": {"command": "git status"}}
    assert codex_event(event, SESSION) == {}


@pytest.mark.parametrize("command", ["git status | cat", "git diff > patch", 'rg -n "foo bar" .', "git status; exit", "utk exec -- git status", "git status && echo hi", "git diff $(whoami)"])
def test_unsafe_commands_not_rewritten(command):
    assert rewrite_literal(command, SESSION) is None


@pytest.mark.parametrize("command", ["git push", "git commit -m change", "git pull --ff-only", "git fetch origin"])
def test_literal_git_write_commands_use_managed_wrapper(command):
    rewritten = rewrite_literal(command, SESSION)
    assert rewritten is not None
    assert rewritten.endswith("-- " + command)


def test_codex_preserves_workdir_and_timeout():
    event = {"hook_event_name": "PreToolUse", "tool_name": "exec_command", "tool_input": {"cmd": "git status", "workdir": "repo", "yield_time_ms": 1000}}
    result = codex_event(event, SESSION)["hookSpecificOutput"]["updatedInput"]
    assert result["workdir"] == "repo"
    assert result["yield_time_ms"] == 1000
    assert result["cmd"].endswith("-- git status")
    assert codex_event(event, "") == {}


def test_codex_rewrites_unknown_command_tool_but_ignores_non_commands():
    event = {"hook_event_name": "PreToolUse", "tool_name": "command_execution",
             "tool_use_id": "call", "tool_input": {"command": "grep -n -H . calculator.py"}}
    updated = codex_event(event, SESSION)["hookSpecificOutput"]["updatedInput"]["command"]
    assert updated.startswith("utk exec --session ")
    assert "--hook-call-id " in updated
    assert codex_event({"hook_event_name": "PreToolUse", "tool_name": "Read", "tool_input": {}}, SESSION) == {}


def test_hermes_unknown_syntax_preserved():
    assert hermes_terminal("git status | cat", SESSION) == "git status | cat"
    assert hermes_terminal("git status", SESSION).startswith("utk exec --session")
