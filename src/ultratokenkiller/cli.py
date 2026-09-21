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
from .identity import ensure_session_token
from .integrations import CodexAdapter, HermesAdapter
from .runtime import headroom_health, restart_managed_headrooms, run_command, service_health, start_processes, stop_processes
from .store import Store

app = typer.Typer(help="UltraTokenKiller 本地 Token 优化控制台", no_args_is_help=True)


@app.command()
def capabilities(
    json_output: bool = typer.Option(True, "--json/--no-json", help="输出机器可读 JSON；默认开启。"),
):
    """显示固定对标基线和真实验证状态。"""
    import json
    from .benchmark import capability_report
    report = capability_report()
    if json_output:
        typer.echo(json.dumps(report, ensure_ascii=False, indent=2))
        return
    summary = report["summary"]
    typer.echo(
        f"核心能力 {report['total_core_capabilities']} 项："
        f"上游对标 {summary['upstream_parity_passed']}，真实客户端 {summary['real_client_passed']}，"
        f"离线通过 {summary['offline_passed']}，待验证 {summary['implemented_unverified']}，"
        f"未实现 {summary['not_implemented']}"
    )
    typer.echo(
        f"命令契约已验证 {report['verified_command_contracts']} / 已审阅 {report['reviewed_command_contracts']}；"
        f"RTK 分母 {report['command_inventory_coverage_denominator']}："
        f"已映射 {report['command_inventory_status_counts'].get('contract_mapped', 0)}，"
        f"待验证 {report['command_inventory_status_counts'].get('unverified', 0)}"
    )
    full_counts = report["full_parity_upstream_counts"]
    verification_counts = report["full_parity_verification_summary"]
    typer.echo(
        f"完整三层核心分母 {report['full_parity_denominator']}："
        f"Headroom {full_counts['headroom']}，RTK {full_counts['rtk']}，"
        f"Caveman {full_counts['caveman']}；生态排除 {len(report['ecosystem_exclusions'])} 项"
    )
    typer.echo(
        f"统一状态：未实现 {verification_counts['not_implemented']} / "
        f"契约映射 {verification_counts['contract_mapped']} / "
        f"离线通过 {verification_counts['offline_passed']} / "
        f"固定上游部分 {verification_counts['fixed_upstream_partial_passed']} / "
        f"固定上游完整 {verification_counts['fixed_upstream_full_passed']} / "
        f"真实客户端 {verification_counts['real_client_passed']} / "
        f"资产未就绪 {verification_counts['asset_not_ready']}"
    )
    verification = report["verification"]
    typer.echo(
        f"完整清单源码当前 {verification['full_parity_source_current']} / "
        f"证据当前 {verification['full_parity_evidence_current']} / "
        f"证据文件存在 {verification['full_parity_evidence_present']}"
    )
    typer.echo(
        f"当前源码绑定 {verification['source_bound_capabilities']} 项；"
        f"真实客户端源码绑定 {verification['real_client_source_bound']} 项；"
        f"过期或未绑定 {len(verification['stale_capabilities'])} 项"
    )


@app.command("hermes-hook", hidden=True)
def hermes_hook_command():
    """Run the managed Hermes pre-tool hook over one stdin payload."""
    from .hermes_hook import main

    raise typer.Exit(main())


@app.command("assets")
def assets(action: str = typer.Argument("status")):
    """校验或安装锁定的本地推理模型。"""
    from .assets import install_assets, verify_assets
    if action not in {"status", "install"}:
        raise typer.BadParameter("action 必须是 status 或 install")
    ready = install_assets() if action == "install" else verify_assets()
    typer.echo("本地文本模型：已校验" if ready else "本地文本模型：未就绪")
    if not ready:
        raise typer.Exit(2)


@app.command()
def benchmark(mode: str = typer.Option("native", help="passthrough、prototype、native、upstream、matrix"),
              output: Path | None = typer.Option(None), live: bool = typer.Option(False),
              max_requests: int | None = typer.Option(None),
              reference: Path | None = typer.Option(None, help="固定上游隔离运行结果"),
              model: str | None = typer.Option(None, help="离线 token 计数对应模型"),
              response_pairs: Path | None = typer.Option(None, help="回答精简成对评测 JSON")):
    """离线对照评测；从不隐式调用模型。"""
    import json
    from .benchmark import run_benchmark, run_benchmark_matrix, save_report
    if live:
        if max_requests is None or max_requests <= 0:
            raise typer.BadParameter("真实评测必须设置正数 --max-requests")
        raise typer.BadParameter("真实模型评测运行器尚未验收；没有提交任何请求")
    try:
        if response_pairs:
            from .response_benchmark import evaluate_pairs
            report = evaluate_pairs(response_pairs, model)
        else:
            report = (
                run_benchmark_matrix(reference=reference, model=model)
                if mode == "matrix"
                else run_benchmark(mode, reference=reference, model=model)
            )
    except ValueError as error:
        raise typer.BadParameter(str(error)) from error
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    if report["status"] == "completed":
        save_report(report, "response" if response_pairs else "compression")
    typer.echo(rendered)
    if report["status"] != "completed":
        raise typer.Exit(2)


def _settings() -> tuple[Path, Settings]:
    root = default_home()
    return root, Settings.load(root)


@app.command()
def install(no_clients: bool = typer.Option(False, help="不接入已检测到的客户端"), no_autostart: bool = typer.Option(False, help="不启用登录自启"), skip_downloads: bool = typer.Option(False, help="兼容旧参数；原生引擎无需下载")):
    """安装服务、选择端口并接入 Codex 和 Hermes。"""
    root = default_home()
    settings = Settings.load(root)
    ensure_session_token(root)
    existing_dashboard = settings.dashboard_port if service_health(settings, root) else None
    proxy_keys = ("HEADROOM_HTTP_PROXY", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY")
    settings.proxy_environment = {key: os.environ[key] for key in proxy_keys if os.environ.get(key)}
    if "HEADROOM_HTTP_PROXY" not in settings.proxy_environment and settings.proxy_environment.get("HTTP_PROXY"):
        settings.proxy_environment["HEADROOM_HTTP_PROXY"] = settings.proxy_environment["HTTP_PROXY"]
    Store(root / "metrics.sqlite3")
    typer.echo(f"数据目录: {root}")
    typer.echo("UTK 原生输入压缩、工具输出压缩、回答精简引擎已内置。")
    existing_headroom = None
    adapters = {"codex": CodexAdapter(), "hermes": HermesAdapter()}
    instances: dict[str, dict] = {}
    reserved = {existing_headroom} if existing_headroom else set()
    if not no_clients:
        for name, adapter in adapters.items():
            state = adapter.detect()
            if not state.detected or not state.supported:
                continue
            upstream = adapter.upstream_url()
            previous = settings.clients.get(name, {})
            if state.enabled and previous.get("upstream_url"):
                upstream = previous["upstream_url"]
            from urllib.parse import urlparse
            if upstream and urlparse(upstream).hostname in {"127.0.0.1", "localhost", "::1"}:
                typer.echo(f"{name}: 当前上游是本地代理，请先恢复原始上游后接入，避免重复压缩")
                continue
            if not upstream:
                typer.echo(f"{name}: 无法确定当前提供商上游，保留原配置")
                continue
            shared = next((item for item in instances.values() if item["upstream_url"] == upstream), None)
            if shared:
                port, managed = shared["proxy_port"], shared["managed"]
            elif previous.get("proxy_port") and headroom_health(settings, int(previous["proxy_port"]), root):
                port, managed = int(previous["proxy_port"]), True
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
        settings.headroom_port = settings.headroom_port if headroom_health(settings, home=root) else choose_port(18788)
        settings.headroom_managed = True
        reserved.add(settings.headroom_port)
    settings.dashboard_port = existing_dashboard or choose_port(18787, excluded={int(value) for value in reserved if value})
    settings.save(root)
    start_processes(settings, root)
    deadline = time.time() + 15
    while time.time() < deadline and not service_health(settings, root):
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
        return health_response.is_success and stats_response.is_success and health_response.json().get("engine") == "utk-native"
    except (httpx.HTTPError, ValueError):
        return False


@app.command()
def doctor():
    """检查依赖、进程、配置和客户端接入。"""
    root, settings = _settings()
    checks = [
        ("配置", (root / "config.json").exists(), str(root / "config.json")),
        ("管理服务", service_health(settings, root), f"{settings.host}:{settings.dashboard_port}"),
        ("UTK 输入代理", headroom_health(settings, home=root), "utk-native"),
        ("UTK 工具压缩", True, "内置"),
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
    typer.echo(f"管理服务: {'在线' if service_health(settings, root) else '离线'}  http://{settings.host}:{settings.dashboard_port}")
    typer.echo(f"UTK 输入代理: {'在线' if headroom_health(settings, home=root) else '离线'}  :{settings.headroom_port}")
    typer.echo(f"档位: {settings.profile} / 回答精简 {settings.caveman}")


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
    if caveman and caveman not in {"lite", "full", "ultra", "off", "wenyan-lite", "wenyan-full", "wenyan-ultra"}:
        raise typer.BadParameter("未知 回答精简 档位")
    managed_values = [bool(item.get("managed", True)) for item in settings.clients.values()]
    profile_controlled = all(managed_values) if managed_values else settings.headroom_managed
    if name != settings.profile and not profile_controlled:
        raise typer.BadParameter("当前 UTK 输入代理 由外部服务管理，请在该服务中修改输入压缩档位")
    settings.profile = name
    if caveman:
        settings.caveman = caveman
    settings.save(root)
    typer.echo(f"档位: {settings.profile} / 回答精简 {settings.caveman}")


@app.command(context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def exec(ctx: typer.Context, session: str | None = typer.Option(None), hook_call_id: str | None = typer.Option(None)):
    """通过 UTK 工具压缩 运行命令；复杂 shell 语法安全透传。"""
    command = list(ctx.args)
    if command and command[0] == "--":
        command = command[1:]
    previous = os.environ.get("UTK_SESSION_ID")
    previous_call = os.environ.get("UTK_HOOK_CALL_ID")
    if hook_call_id:
        import re
        if not re.fullmatch(r"[a-f0-9]{64}", hook_call_id):
            raise typer.BadParameter("Invalid hook correlation identifier")
    if session:
        import re
        if not re.fullmatch(r"[A-Za-z0-9_-]{16,128}", session):
            raise typer.BadParameter("Invalid session identifier")
        os.environ["UTK_SESSION_ID"] = session
    try:
        if hook_call_id:
            os.environ["UTK_HOOK_CALL_ID"] = hook_call_id
        from .tool_events import ToolEventSink
        code = run_command(command, ToolEventSink())
    finally:
        if previous_call is None:
            os.environ.pop("UTK_HOOK_CALL_ID", None)
        else:
            os.environ["UTK_HOOK_CALL_ID"] = previous_call
        if previous is None:
            os.environ.pop("UTK_SESSION_ID", None)
        else:
            os.environ["UTK_SESSION_ID"] = previous
    raise typer.Exit(code)


@app.command("mcp")
def mcp_server():
    """启动会话隔离的原文查询 MCP stdio 服务。"""
    from .mcp import main
    main()


@app.command("codex", context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def codex(ctx: typer.Context):
    """启动自动绑定代理、只读命令钩子及原文查询的 Codex 新会话。"""
    from .codex_session import launch
    try:
        code = launch(list(ctx.args))
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1)
    raise typer.Exit(code)


@app.command("hook")
def hook(client: str = typer.Argument("codex")):
    """运行工具事件适配器；不会自动修改客户端配置。"""
    if client != "codex":
        raise typer.BadParameter("该客户端的事件格式尚未完成真实验收")
    from .hooks import main
    main()


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
