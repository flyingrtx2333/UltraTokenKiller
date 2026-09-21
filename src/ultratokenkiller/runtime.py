from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Sequence

import httpx

from .config import Settings, default_home
from .engines import compress_tool_output, estimate_tokens, supported_command
from .identity import ensure_session_token, home_instance_id
from .store import Store


def health(url: str, timeout: float = 1.0) -> bool:
    try:
        return httpx.get(url, timeout=timeout).is_success
    except httpx.HTTPError:
        return False


def headroom_health(settings: Settings, port: int | None = None, home: Path | None = None) -> bool:
    expected = home_instance_id(home or default_home())
    if not expected:
        return False
    try:
        response = httpx.get(
            f"http://{settings.host}:{port or settings.headroom_port}/health",
            timeout=1,
            trust_env=False,
        )
        payload = response.json()
        return (response.is_success and payload.get("engine") == "utk-native"
                and payload.get("instance_id") == expected)
    except (httpx.HTTPError, ValueError, AttributeError):
        return False


def headroom_ports(settings: Settings) -> list[int]:
    configured = [int(item["proxy_port"]) for item in settings.clients.values() if item.get("proxy_port")]
    return list(dict.fromkeys(configured or [settings.headroom_port]))


def service_health(settings: Settings, home: Path | None = None) -> bool:
    """Return true only when the listener belongs to the requested UTK home."""
    root = home or default_home()
    expected = home_instance_id(root)
    if not expected:
        return False
    try:
        response = httpx.get(
            f"http://{settings.host}:{settings.dashboard_port}/api/v1/health",
            timeout=1,
            trust_env=False,
        )
        return response.is_success and response.json().get("instance_id") == expected
    except (httpx.HTTPError, ValueError, AttributeError):
        return False


def start_processes(settings: Settings, home: Path | None = None) -> dict[str, int | str]:
    root = home or default_home()
    root.mkdir(parents=True, exist_ok=True)
    ensure_session_token(root)
    log = open(root / "service.log", "a", encoding="utf-8")
    env = os.environ.copy()
    env["UTK_HOME"] = str(root)
    env.update(settings.proxy_environment)
    result: dict[str, int | str] = {}
    instances = [item for item in settings.clients.values() if item.get("proxy_port")]
    if not instances:
        instances = [{"proxy_port": settings.headroom_port, "managed": settings.headroom_managed, "upstream_url": None}]
    for instance in {int(item["proxy_port"]): item for item in instances}.values():
        port = int(instance["proxy_port"])
        if not instance.get("managed", True) or headroom_health(settings, port, root):
            continue
        instance_env = env.copy()
        instance_env["UTK_UPSTREAM_URL"] = str(instance.get("upstream_url") or "https://api.openai.com/v1")
        instance_env["UTK_CLIENT"] = next((name for name, value in settings.clients.items() if value.get("proxy_port") == port), "unknown")
        command = [sys.executable, "-m", "uvicorn", "ultratokenkiller.proxy:create_proxy", "--factory", "--host", settings.host, "--port", str(port)]
        proc = _spawn(command, instance_env, log)
        (root / f"headroom-{port}.pid").write_text(str(proc.pid), encoding="ascii")
        result[f"native:{port}"] = proc.pid
    if not service_health(settings, root):
        command = [sys.executable, "-m", "ultratokenkiller.local_transport"]
        proc = _spawn(command, env, log)
        (root / "service.pid").write_text(str(proc.pid), encoding="ascii")
        result["service"] = proc.pid
    log.close()
    return result


def _spawn(command: Sequence[str], env: dict[str, str], log) -> subprocess.Popen:
    flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS if sys.platform == "win32" else 0
    return subprocess.Popen(command, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=log, creationflags=flags, start_new_session=sys.platform != "win32")


def stop_processes(home: Path | None = None) -> list[int]:
    root = home or default_home()
    stopped = []
    paths = [root / "service.pid", root / "headroom.pid", *root.glob("headroom-*.pid")]
    for path in paths:
        if not path.exists():
            continue
        try:
            pid = int(path.read_text(encoding="ascii"))
            os.kill(pid, signal.SIGTERM)
            stopped.append(pid)
        except (ValueError, ProcessLookupError, PermissionError):
            pass
        path.unlink(missing_ok=True)
    return stopped


def restart_managed_headrooms(settings: Settings, home: Path | None = None) -> None:
    root = home or default_home()
    managed_ports = {
        int(item["proxy_port"])
        for item in settings.clients.values()
        if item.get("proxy_port") and item.get("managed", True)
    }
    if not settings.clients and settings.headroom_managed:
        managed_ports.add(settings.headroom_port)
    for port in managed_ports:
        path = root / f"headroom-{port}.pid"
        if not path.exists() and port == settings.headroom_port:
            path = root / "headroom.pid"
        if path.exists():
            try:
                os.kill(int(path.read_text(encoding="ascii")), signal.SIGTERM)
            except (ValueError, ProcessLookupError, PermissionError):
                pass
            path.unlink(missing_ok=True)
    start_processes(settings, root)


def run_command(command: list[str], store: Store) -> int:
    import hashlib
    import uuid
    from .broker import BrokerClient
    from .processes import execute
    from .tool_filters import command_filter
    if not command:
        raise ValueError("A command is required after --")
    settings = Settings.load()
    started = time.perf_counter()
    kind = command_filter(command) if settings.tools_enabled else None
    saved = 0
    metadata = {"command": Path(command[0]).name, "optimized": False, "engine": "utk-native",
                "estimator": "utf8_bytes_div_4", "filter": kind, "execution_id": uuid.uuid4().hex}
    if os.environ.get("UTK_SESSION_ID"):
        metadata["session_id"] = hashlib.sha256(os.environ["UTK_SESSION_ID"].encode()).hexdigest()
    if os.environ.get("UTK_HOOK_CALL_ID"):
        metadata["tool_call_id"] = os.environ["UTK_HOOK_CALL_ID"]
    from .native_tools import execute_native_tool
    native = execute_native_tool(command)
    if native is not None:
        code = native.code
        fallback = None
        rendered = native.rendered
        if native.error:
            _write_stderr(native.error.encode("utf-8"))
        elif native.original:
            session = os.environ.get("UTK_SESSION_ID", "")
            if not settings.tools_enabled:
                rendered = native.original
                fallback = "disabled"
            elif native.rendered != native.original and session:
                result = BrokerClient().pin_transform(
                    native.original, native.rendered, session, native.kind
                )
                rendered = result["content"]
                saved = result.get("saved_tokens", 0)
                fallback = result.get("fallback")
                metadata["recovery_id"] = result.get("recovery_id")
            elif native.rendered != native.original:
                rendered = native.original
                fallback = "missing_session"
            metadata["optimized"] = rendered != native.original
            _write_stdout(rendered.encode("utf-8"))
        metadata["fallback"] = fallback
        client_name = os.environ.get("UTK_CLIENT", "cli")
        if client_name not in {"codex", "hermes", "cli"}:
            client_name = "cli"
        store.add(
            kind="tool",
            client=client_name,
            success=code == 0,
            duration_ms=int((time.perf_counter() - started) * 1000),
            saved_tokens=saved,
            metadata=metadata,
        )
        return code
    code, raw, fallback = execute(command, capture=bool(kind), write=_write_stdout)
    if raw is not None:
        rendered = raw
        try:
            original = raw.decode("utf-8")
            session = os.environ.get("UTK_SESSION_ID", "")
            if session:
                hint = kind if kind in {"diff", "search", "log"} else "tool:"+kind
                result = BrokerClient().compress(original, session, hint=hint)
                rendered = result["content"].encode("utf-8")
                saved = result.get("saved_tokens", 0)
                metadata["optimized"] = rendered != raw
                metadata["recovery_id"] = result.get("recovery_id")
                fallback = result.get("fallback")
            elif kind == "git-status":
                # Removing Git's fixed instructional boilerplate remains available without recovery.
                rendered = compress_tool_output(command, original).encode("utf-8")
                saved = max(0, estimate_tokens(original)-estimate_tokens(rendered.decode("utf-8")))
                metadata["optimized"] = rendered != raw
            else:
                fallback = "missing_session"
        except (UnicodeDecodeError, ValueError, OSError):
            rendered = raw
            fallback = "encoding_or_compression_error"
        _write_stdout(rendered)
    metadata["fallback"] = fallback
    client_name = os.environ.get("UTK_CLIENT", "cli")
    if client_name not in {"codex", "hermes", "cli"}:
        client_name = "cli"
    store.add(kind="tool", client=client_name, success=code == 0,
              duration_ms=int((time.perf_counter()-started)*1000), saved_tokens=saved, metadata=metadata)
    return code


def _write_stdout(data: bytes):
    target = getattr(sys.stdout, "buffer", None)
    if target is not None:
        target.write(data)
        target.flush()
    else:
        sys.stdout.write(data.decode("utf-8", errors="replace"))
        sys.stdout.flush()


def _write_stderr(data: bytes):
    target = getattr(sys.stderr, "buffer", None)
    if target is not None:
        target.write(data)
        target.flush()
    else:
        sys.stderr.write(data.decode("utf-8", errors="replace"))
        sys.stderr.flush()
