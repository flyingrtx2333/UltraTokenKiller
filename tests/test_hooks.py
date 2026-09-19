import pytest

from ultratokenkiller.hooks import codex_event, hermes_terminal, rewrite_literal

SESSION = "a"*32


@pytest.mark.parametrize("command", ["git status | cat", "git diff > patch", 'rg -n "foo bar" .', "git status; exit", "git push", "git commit -m change", "utk exec -- git status", "git status && echo hi", "git diff $(whoami)"])
def test_unsafe_and_write_commands_not_rewritten(command):
    assert rewrite_literal(command, SESSION) is None


def test_codex_preserves_workdir_and_timeout():
    event = {"hook_event_name": "PreToolUse", "tool_name": "exec_command", "tool_input": {"cmd": "git status", "workdir": "repo", "yield_time_ms": 1000}}
    result = codex_event(event, SESSION)["hookSpecificOutput"]["updatedInput"]
    assert result["workdir"] == "repo"
    assert result["yield_time_ms"] == 1000
    assert result["cmd"].endswith("-- git status")
    assert codex_event(event, "") == {}


def test_hermes_unknown_syntax_preserved():
    assert hermes_terminal("git status | cat", SESSION) == "git status | cat"
    assert hermes_terminal("git status", SESSION).startswith("utk exec --session")
