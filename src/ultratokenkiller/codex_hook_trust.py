"""Ask Codex for hook hashes and trust only UTK's exact definition for this process."""
from __future__ import annotations
import json
import os
from pathlib import Path
import queue
import shlex
import signal
import subprocess
import sys
import threading
import time

from .processes import WindowsJob


def list_hooks(executable, overrides, cwd, timeout=20):
    from .codex_session import toml_value
    command = list(executable) + ["app-server"]
    for key, value in overrides.items():
        command += ["-c", key + "=" + toml_value(value)]
    job = WindowsJob() if sys.platform == "win32" else None
    process = None
    reader = None
    responses = queue.Queue(maxsize=256)
    stop = threading.Event()
    try:
        process = subprocess.Popen(command, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, encoding="utf-8", errors="strict",
            creationflags=0x00000004 if job else 0, start_new_session=job is None)
        if job:
            job.attach_and_resume(process)
        def read():
            while not stop.is_set():
                line = process.stdout.readline(1024 * 1024)
                if not line:
                    return
                try:
                    value = json.loads(line)
                    responses.put(value, timeout=1)
                except (ValueError, queue.Full):
                    pass
        reader = threading.Thread(target=read, daemon=True)
        reader.start()
        deadline = time.monotonic() + timeout
        def send(value):
            process.stdin.write(json.dumps(value) + "\n")
            process.stdin.flush()
        def response(request_id):
            while time.monotonic() < deadline:
                try:
                    value = responses.get(timeout=min(1, max(.01, deadline - time.monotonic())))
                except queue.Empty:
                    if process.poll() is not None:
                        break
                    continue
                if value.get("id") == request_id:
                    if "error" in value:
                        raise ValueError("Codex hook inspection RPC failed")
                    return value["result"]
            raise ValueError("Codex hook inspection timed out; no model request was made")
        send({"id": 1, "method": "initialize", "params": {"clientInfo": {"name": "utk", "version": "0.1.0"},
              "capabilities": {"experimentalApi": True}}})
        response(1)
        send({"method": "initialized", "params": {}})
        send({"id": 2, "method": "hooks/list", "params": {"cwds": [str(Path(cwd).resolve())]}})
        return response(2)
    finally:
        stop.set()
        if process is not None:
            if job:
                job.terminate()
            else:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)
            if reader:
                reader.join(timeout=2)
            for stream in (process.stdin, process.stdout):
                if stream:
                    stream.close()
        if job:
            job.close()


def scoped_trust(response):
    hooks = [hook for entry in response.get("data", []) for hook in entry.get("hooks", [])]
    if any(entry.get("errors") for entry in response.get("data", [])):
        raise ValueError("Codex reported hook configuration errors")
    ours = [hook for hook in hooks if hook.get("source") == "sessionFlags"
            and hook.get("handlerType") == "command" and hook.get("command") == "utk hook codex"
            and hook.get("matcher") == "^Bash$" and hook.get("eventName") == "preToolUse"]
    if len(ours) != 1 or ours[0].get("isManaged") or not ours[0].get("currentHash"):
        raise ValueError("Exactly one identifiable UTK session hook is required")
    hook = ours[0]
    # A hook key contains filesystem paths and dots. Put it inside a TOML map;
    # Codex -c dotted-path parsing does not treat embedded quotes as path escapes.
    states = {}
    for existing in hooks:
        if existing.get("isManaged"):
            continue
        state = {"enabled": existing["enabled"]}
        if existing.get("trustStatus") == "trusted":
            state["trusted_hash"] = existing["currentHash"]
        states[existing["key"]] = state
    states[hook["key"]] = {"trusted_hash": hook["currentHash"], "enabled": True}
    # This known Headroom init hook rewrites Codex's global config on each tool call.
    # Disable only its exact definition in the UTK invocation; keep disk state intact.
    expected = ["init", "hook", "ensure", "--profile", "init-user", "--marker", "headroom-init-codex"]
    for other in hooks:
        try:
            args = shlex.split(other.get("command") or "", posix=False)
        except ValueError:
            continue
        if not args:
            continue
        executable = args[0].strip('"').replace("\\", "/").rsplit("/", 1)[-1].lower()
        if executable in {"headroom", "headroom.exe"}:
            if args[1:] != expected or other.get("isManaged"):
                raise ValueError("An unrecognized or managed Headroom hook prevents automatic native integration")
            states[other["key"]]["enabled"] = False
    return {"hooks.state": states}


def approve_session_hook(executable, overrides, cwd):
    trust = scoped_trust(list_hooks(executable, overrides, cwd))
    verified = list_hooks(executable, {**overrides, **trust}, cwd)
    hooks = [h for e in verified.get("data", []) for h in e.get("hooks", [])]
    for target, state in trust["hooks.state"].items():
        if state.get("trusted_hash"):
            if not any(h.get("key") == target and h.get("currentHash") == state["trusted_hash"]
                       and h.get("trustStatus") == "trusted" and h.get("enabled") == state["enabled"] for h in hooks):
                raise ValueError("Codex did not confirm scoped UTK hook trust")
        if state["enabled"] is False:
            if any(h.get("key") == target and h.get("enabled") for h in hooks):
                raise ValueError("Conflicting Headroom hook remained enabled")
    return trust
