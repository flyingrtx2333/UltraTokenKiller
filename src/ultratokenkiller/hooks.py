"""Conservative tool hooks. Shell constructs that cannot be proven equivalent pass through."""
import json
import os
import re
import sys
import hashlib

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
    if kind not in {"diff", "search"} and not kind.startswith("git-"):
        return None
    if kind == "search":
        allowed = {"-n", "--line-number", "--with-filename", "-H", "-i", "--ignore-case", "-F", "--fixed-strings", "--"}
        if any(arg.startswith("-") and arg not in allowed for arg in args[1:]):
            return None
    return f"utk exec --session {session} -- " + command


def codex_event(event: dict, session: str):
    if event.get("hook_event_name") != "PreToolUse":
        return {}
    tool = event.get("tool_name")
    if tool not in {"Bash", "shell", "shell_command", "exec_command", "functions.exec_command", "functions.shell", "functions.shell_command", "command_execution"}:
        return {}
    inputs = event.get("tool_input")
    if not isinstance(inputs, dict):
        return {}
    key = "cmd" if isinstance(inputs.get("cmd"), str) else "command"
    if not isinstance(inputs.get(key), str):
        return {}
    original = inputs.get(key)
    updated = rewrite_literal(original, session)
    if updated is None:
        return {}
    call_id = event.get("tool_use_id")
    if isinstance(call_id, str) and call_id:
        digest = hashlib.sha256(call_id.encode("utf-8")).hexdigest()
        updated = updated.replace(" -- ", " --hook-call-id " + digest + " -- ", 1)
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow",
                                   "updatedInput": {**inputs, key: updated}}}


def hermes_terminal(command: str, session: str) -> str:
    """Pure adapter for a verified Hermes terminal hook; no permissions are changed."""
    return rewrite_literal(command, session) or command


def main():
    try:
        stream = getattr(sys.stdin, "buffer", sys.stdin)
        raw = stream.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise ValueError("Hook input exceeds budget")
        event = json.loads(raw)
        result = codex_event(event, os.environ.get("UTK_SESSION_ID", ""))
    except (ValueError, TypeError, AttributeError):
        result = {}
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
