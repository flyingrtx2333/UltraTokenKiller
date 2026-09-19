"""Conservative tool hooks. Shell constructs that cannot be proven equivalent pass through."""
import json
import os
import re
import sys

from .tool_filters import command_filter


def safe_argv(command: str):
    # Deliberately accept only literal unquoted argv here. Pipes, substitutions, quoted
    # strings, Windows backslashes and expansion syntax need a verified shell parser.
    if not isinstance(command, str) or not re.fullmatch(r"[A-Za-z0-9_./:=+,@ -]+", command):
        return None
    args = command.split()
    if not args or args[0] in {"utk", "rtk", "headroom"}:
        return None
    return args


def rewrite_literal(command: str, session: str):
    if not re.fullmatch(r"[A-Za-z0-9_-]{16,128}", session or ""):
        return None
    args = safe_argv(command)
    if not args:
        return None
    kind = command_filter(args)
    if kind not in {"git-status", "git-log", "diff", "search"}:
        return None
    return f"utk exec --session {session} -- " + command


def codex_event(event: dict, session: str):
    if event.get("hook_event_name") != "PreToolUse":
        return {}
    tool = event.get("tool_name")
    inputs = event.get("tool_input")
    if tool not in {"Bash", "exec_command", "shell_command"} or not isinstance(inputs, dict):
        return {}
    key = "cmd" if tool == "exec_command" else "command"
    original = inputs.get(key)
    updated = rewrite_literal(original, session)
    if updated is None:
        return {}
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow",
                                   "updatedInput": {**inputs, key: updated}}}


def hermes_terminal(command: str, session: str) -> str:
    """Pure adapter for a verified Hermes terminal hook; no permissions are changed."""
    return rewrite_literal(command, session) or command


def main():
    try:
        event = json.load(sys.stdin)
        result = codex_event(event, os.environ.get("UTK_SESSION_ID", ""))
    except (ValueError, TypeError, AttributeError):
        result = {}
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
