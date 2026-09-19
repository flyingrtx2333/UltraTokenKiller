from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from typing import Annotated

import httpx
import typer

from . import __version__
from . import autostart
from .config import Settings, choose_port, default_home
from .dependencies import ensure_headroom, ensure_rtk, find_headroom, find_rtk
from .integrations import CodexAdapter, HermesAdapter
from .runtime import headroom_health, restart_managed_headrooms, run_command, service_health, start_processes, stop_processes
from .store import Store

app = typer.Typer(help="UltraTokenKiller 本地 Token 优化控制台", no_args_is_help=True)


def _settings() -> tuple[Path, Settings]:
    root = default_home()
    return root, Settings.load(root)


@app.command()
def install(no_clients: bool = typer.Option(False, help="不接入已检测到的客户端"), no_autostart: bool = typer.Option(False, help="不启用登录自启"), skip_downloads: bool = typer.Option(False, help="不下载缺失的 Headroom 和 RTK")):
    """安装服务、选择端口并接入 Codex 和 Hermes。"""
    root = default_home()
    settings = Settings.load(root)
    existing_dashboard = settings.dashboard_port if service_health(settings) else None
    proxy_keys = ("HEADROOM_HTTP_PROXY", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY")
    settings.proxy_environment = {key: os.environ[key] for key in proxy_keys if os.environ.get(key)}
    if "HEADROOM_HTTP_PROXY" not in settings.proxy_environment and settings.proxy_environment.get("HTTP_PROXY"):
        settings.proxy_environment["HEADROOM_HTTP_PROXY"] = settings.proxy_environment["HTTP_PROXY"]
    Store(root / "metrics.sqlite3")
    typer.echo(f"数据目录: {root}")
    if not skip_downloads:
        headroom_ok, headroom_detail = ensure_headroom()
        rtk_ok, rtk_detail = ensure_rtk(root)
        typer.echo(f"Headroom: {'可用' if headroom_ok else '安装失败'} {headroom_detail}")
        typer.echo(f"RTK: {'可用' if rtk_ok else '安装失败'} {rtk_detail}")
    elif not find_headroom() or not find_rtk(root):
        typer.echo("已跳过依赖下载；缺失的压缩层会显示为不可用。")

    existing_headroom = next((port for port in dict.fromkeys((settings.headroom_port, 18787, 8787)) if _headroom_at(settings.host, port)), None)
    adapters = {"codex": CodexAdapter(), "hermes": HermesAdapter()}
    instances: dict[str, dict] = {}
    reserved = {existing_headroom} if existing_headroom else set()
    if not no_clients:
        for name, adapter in adapters.items():
            state = adapter.detect()
            if not state.detected or not state.supported:
                continue
            upstream = adapter.upstream_url()
            if not upstream:
                typer.echo(f"{name}: 无法确定当前提供商上游，保留原配置")
                continue
            shared = next((item for item in instances.values() if item["upstream_url"] == upstream), None)
            if shared:
                port, managed = shared["proxy_port"], shared["managed"]
            elif name == "codex" and existing_headroom:
                port, managed = existing_headroom, False
            else:
                port = choose_port(18788, excluded={int(value) for value in reserved if value})
                reserved.add(port)
                managed = True
            instances[name] = {"proxy_port": port, "upstream_url": upstream, "managed": managed}
    if instances:
        settings.clients = instances
        primary = instances.get("codex") or next(iter(instances.values()))
        settings.headroom_port = int(primary["proxy_port"])
        settings.headroom_managed = bool(primary["managed"])
    elif existing_headroom:
        settings.clients = {}
        settings.headroom_port = existing_headroom
        settings.headroom_managed = False
    else:
        settings.clients = {}
        settings.headroom_port = choose_port(18788)
        settings.headroom_managed = True
        reserved.add(settings.headroom_port)
    settings.dashboard_port = existing_dashboard or choose_port(18787, excluded={int(value) for value in reserved if value})
    settings.save(root)
    start_processes(settings, root)
    deadline = time.time() + 15
    while time.time() < deadline and not service_health(settings):
        time.sleep(.25)
    if not no_clients:
        for name, adapter in adapters.items():
            state = adapter.detect()
            instance = settings.clients.get(name)
            if state.detected and state.supported and instance:
                state = adapter.enable(int(instance["proxy_port"]), root / "backups", settings.caveman)
            typer.echo(f"{state.name}: {'已接入' if state.enabled else state.detail}")
    if not no_autostart:
        ok, detail = autostart.enable(root)
        settings.auto_start = ok
        settings.save(root)
        typer.echo(f"登录自启: {'已启用' if ok else '未启用'} {detail}")
    else:
        settings.auto_start = False
        settings.save(root)
    typer.echo(f"网页看板: http://{settings.host}:{settings.dashboard_port}/dashboard")


def _headroom_at(host: str, port: int) -> bool:
    try:
        health_response = httpx.get(f"http://{host}:{port}/health", timeout=2)
        stats_response = httpx.get(f"http://{host}:{port}/stats", timeout=2)
        return health_response.is_success and stats_response.is_success and "tokens" in stats_response.json()
    except (httpx.HTTPError, ValueError):
        return False


@app.command()
def doctor():
    """检查依赖、进程、配置和客户端接入。"""
    root, settings = _settings()
    checks = [
        ("配置", (root / "config.json").exists(), str(root / "config.json")),
        ("管理服务", service_health(settings), f"{settings.host}:{settings.dashboard_port}"),
        ("Headroom", headroom_health(settings), find_headroom() or "未找到"),
        ("RTK", find_rtk(root) is not None, find_rtk(root) or "未找到"),
    ]
    for name, ok, detail in checks:
        typer.echo(f"{'OK' if ok else 'FAIL'} {name}: {detail}")
    for adapter in (CodexAdapter(), HermesAdapter()):
        state = adapter.detect()
        typer.echo(f"{'OK' if state.enabled else 'INFO'} {state.name}: {state.detail}")
    if not all(item[1] for item in checks[:2]):
        raise typer.Exit(1)


@app.command()
def status():
    root, settings = _settings()
    typer.echo(f"UltraTokenKiller {__version__}")
    typer.echo(f"管理服务: {'在线' if service_health(settings) else '离线'}  http://{settings.host}:{settings.dashboard_port}")
    typer.echo(f"Headroom: {'在线' if headroom_health(settings) else '离线'}  :{settings.headroom_port}")
    typer.echo(f"档位: {settings.profile} / Caveman {settings.caveman}")


@app.command()
def start():
    root, settings = _settings()
    result = start_processes(settings, root)
    typer.echo("已启动" if result else "服务已在运行")


@app.command()
def stop():
    stopped = stop_processes()
    typer.echo(f"已停止 {len(stopped)} 个进程")


@app.command()
def enable(client: str = typer.Argument(..., help="codex 或 hermes")):
    root, settings = _settings()
    adapters = {"codex": CodexAdapter(), "hermes": HermesAdapter()}
    if client not in adapters:
        raise typer.BadParameter("client 必须是 codex 或 hermes")
    state = adapters[client].enable(settings.headroom_port, root / "backups", settings.caveman)
    typer.echo(f"{client}: {'已接入' if state.enabled else state.detail}")


@app.command()
def disable(client: str = typer.Argument(..., help="codex 或 hermes")):
    adapters = {"codex": CodexAdapter(), "hermes": HermesAdapter()}
    if client not in adapters:
        raise typer.BadParameter("client 必须是 codex 或 hermes")
    adapters[client].disable()
    typer.echo(f"{client}: 已移除 UTK 受管配置")


@app.command()
def profile(name: str = typer.Argument(..., help="safe、aggressive 或 off"), caveman: str | None = typer.Option(None)):
    root, settings = _settings()
    if name not in {"safe", "aggressive", "off"}:
        raise typer.BadParameter("未知档位")
    if caveman and caveman not in {"lite", "full", "ultra", "off"}:
        raise typer.BadParameter("未知 Caveman 档位")
    managed_values = [bool(item.get("managed", True)) for item in settings.clients.values()]
    profile_controlled = all(managed_values) if managed_values else settings.headroom_managed
    if name != settings.profile and not profile_controlled:
        raise typer.BadParameter("当前 Headroom 由外部服务管理，请在该服务中修改输入压缩档位")
    settings.profile = name
    if caveman:
        settings.caveman = caveman
    settings.save(root)
    if profile_controlled:
        restart_managed_headrooms(settings, root)
    typer.echo(f"档位: {settings.profile} / Caveman {settings.caveman}")


@app.command(context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def exec(ctx: typer.Context):
    """通过 RTK 运行命令；复杂 shell 语法安全透传。"""
    command = list(ctx.args)
    if command and command[0] == "--":
        command = command[1:]
    code = run_command(command, Store(default_home() / "metrics.sqlite3"))
    raise typer.Exit(code)


@app.command()
def dashboard():
    from .tui import Dashboard
    Dashboard(Settings.load()).run()


@app.command()
def web():
    _, settings = _settings()
    webbrowser.open(f"http://{settings.host}:{settings.dashboard_port}/dashboard")


@app.command()
def update():
    subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "ultratokenkiller"], check=False)


@app.command()
def uninstall(keep_data: bool = typer.Option(True, help="保留统计和备份")):
    for adapter in (CodexAdapter(), HermesAdapter()):
        adapter.disable()
    stop_processes()
    autostart.disable()
    root = default_home()
    if not keep_data and root.exists():
        shutil.rmtree(root)
    typer.echo("已移除客户端接入和登录自启。" + ("统计和备份已保留。" if keep_data else "本地数据已删除。"))


if __name__ == "__main__":
    app()
