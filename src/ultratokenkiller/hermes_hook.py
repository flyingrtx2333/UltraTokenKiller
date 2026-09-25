"""Hermes pre-tool hook that routes safe supported commands through UTK."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from .tool_filters import command_filter


_SHELL_META = re.compile(r"(?:\r|\n|\|\||&&|[|;<>`]|\$\()")


def _resolve_utk_executable() -> str | None:
    candidates = [os.environ.get("UTK_EXECUTABLE"), sys.argv[0], shutil.which("utk")]
    names = ("utk.exe", "utk") if os.name == "nt" else ("utk",)
    candidates.extend(str(Path(sys.executable).with_name(name)) for name in names)
    for candidate in candidates:
        if candidate and Path(candidate).name.lower() in names and Path(candidate).is_file():
            return str(Path(candidate).resolve())
    return None


def rewrite_payload(payload: object, *, executable: str | None = None) -> dict[str, Any] | None:
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
    executable = executable if executable is not None else _resolve_utk_executable()
    if not executable or not Path(executable).is_file():
        return None

    session_seed = str(payload.get("session_id") or payload.get("profile") or "default")
    session = "hermes_" + hashlib.sha256(session_seed.encode("utf-8")).hexdigest()[:32]
    extra = payload.get("extra") if isinstance(payload.get("extra"), dict) else {}
    call_seed = "\0".join((session_seed, str(extra.get("tool_call_id", "")), command))
    hook_call_id = hashlib.sha256(call_seed.encode("utf-8")).hexdigest()
    wrapped = [
        str(Path(executable).resolve()), "exec", "--session", session, "--hook-call-id", hook_call_id,
        "--client", "hermes", "--", *argv,
    ]
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
