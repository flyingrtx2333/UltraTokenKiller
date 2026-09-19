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
from .dependencies import find_headroom, find_rtk
from .store import Store


def health(url: str, timeout: float = 1.0) -> bool:
    try:
        return httpx.get(url, timeout=timeout).is_success
    except httpx.HTTPError:
        return False


def headroom_health(settings: Settings, port: int | None = None) -> bool:
    return health(f"http://{settings.host}:{port or settings.headroom_port}/health")


def headroom_ports(settings: Settings) -> list[int]:
    configured = [int(item["proxy_port"]) for item in settings.clients.values() if item.get("proxy_port")]
    return list(dict.fromkeys(configured or [settings.headroom_port]))


def service_health(settings: Settings) -> bool:
    return health(f"http://{settings.host}:{settings.dashboard_port}/api/v1/health")


def start_processes(settings: Settings, home: Path | None = None) -> dict[str, int | str]:
    root = home or default_home()
    root.mkdir(parents=True, exist_ok=True)
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
        if not instance.get("managed", True) or headroom_health(settings, port):
            continue
        headroom = find_headroom()
        if not headroom:
            result[f"headroom:{port}"] = "missing"
        else:
            profile_args = {"safe": ["--mode", "cache"], "aggressive": ["--mode", "token", "--target-ratio", "0.35"], "off": ["--no-optimize"]}[settings.profile]
            instance_env = env.copy()
            if instance.get("upstream_url"):
                instance_env["OPENAI_TARGET_API_URL"] = str(instance["upstream_url"])
            command = [headroom, "proxy", "--host", settings.host, "--port", str(port), *profile_args, "--no-telemetry"]
            proc = _spawn(command, instance_env, log)
            (root / f"headroom-{port}.pid").write_text(str(proc.pid), encoding="ascii")
            result[f"headroom:{port}"] = proc.pid
    if not service_health(settings):
        command = [sys.executable, "-m", "uvicorn", "ultratokenkiller.service:app", "--host", settings.host, "--port", str(settings.dashboard_port)]
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
    if not command:
        raise ValueError("A command is required after --")
    started = time.perf_counter()
    rtk = find_rtk()
    rewritten = None
    actual = command
    saved_before = _rtk_total_saved(rtk) if rtk else 0
    if rtk:
        check = subprocess.run([rtk, "rewrite", *command], capture_output=True, text=True)
        candidate = check.stdout.strip()
        if check.returncode == 0 and candidate and not _unsafe_shell(candidate):
            rewritten = candidate
            actual = [rtk, *command]
    proc = subprocess.run(actual)
    duration = int((time.perf_counter() - started) * 1000)
    saved_after = _rtk_total_saved(rtk) if rtk else 0
    store.add(kind="rtk", client="cli", success=proc.returncode == 0, duration_ms=duration, saved_tokens=max(0, saved_after - saved_before), metadata={"command": command[0], "optimized": bool(rewritten)})
    return proc.returncode


def _rtk_total_saved(executable: str) -> int:
    try:
        result = subprocess.run([executable, "gain", "--format", "json"], capture_output=True, text=True, timeout=2)
        return int(json.loads(result.stdout).get("summary", {}).get("total_saved", 0)) if result.returncode == 0 else 0
    except (OSError, subprocess.SubprocessError, ValueError, TypeError):
        return 0


def _unsafe_shell(value: str) -> bool:
    return any(token in value for token in ("|", ">", "<", ";", "&&", "||", "`", "$("))
