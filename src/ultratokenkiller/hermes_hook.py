"""Hermes pre-tool hook that routes safe supported commands through UTK."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
from typing import Any

from .tool_filters import command_filter


_SHELL_META = re.compile(r"(?:\r|\n|\|\||&&|[|;<>`]|\$\()")


def rewrite_payload(payload: object) -> dict[str, Any] | None:
    """Return a Hermes modify directive, or None when equivalence is uncertain."""
    if not isinstance(payload, dict) or payload.get("hook_event_name") != "pre_tool_call":
        return None
    if str(payload.get("tool_name", "")).lower() not in {"terminal", "shell"}:
        return None
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    command = tool_input.get("command")
    if not isinstance(command, str) or not command.strip() or _SHELL_META.search(command):
        return None
    try:
        argv = shlex.split(command, posix=os.name != "nt")
    except ValueError:
        return None
    if not argv or os.path.basename(argv[0]).lower() in {"utk", "utk.exe"}:
        return None
    if command_filter(argv) is None:
        return None

    session_seed = str(payload.get("session_id") or payload.get("profile") or "default")
    session = "hermes_" + hashlib.sha256(session_seed.encode("utf-8")).hexdigest()[:32]
    extra = payload.get("extra") if isinstance(payload.get("extra"), dict) else {}
    call_seed = "\0".join((session_seed, str(extra.get("tool_call_id", "")), command))
    hook_call_id = hashlib.sha256(call_seed.encode("utf-8")).hexdigest()
    wrapped = ["utk", "exec", "--session", session, "--hook-call-id", hook_call_id, "--", *argv]
    rendered = subprocess.list2cmdline(wrapped) if os.name == "nt" else shlex.join(wrapped)
    modified = dict(tool_input)
    modified["command"] = rendered
    return {"action": "modify", "args": modified}


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (OSError, ValueError, TypeError):
        print("{}")
        return 0
    directive = rewrite_payload(payload)
    print(json.dumps(directive or {}, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
