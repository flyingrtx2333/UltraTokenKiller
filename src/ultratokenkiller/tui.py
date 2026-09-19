from __future__ import annotations

import httpx
from textual.app import App, ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import DataTable, Footer, Header, Label, Static

from .config import Settings


class Metric(Static):
    def __init__(self, label: str, value: str = "—", **kwargs):
        super().__init__(**kwargs)
        self.label = label
        self.value = value

    def render(self) -> str:
        return f"[dim]{self.label}[/dim]\n[bold]{self.value}[/bold]"


class Dashboard(App):
    CSS = """
    Screen { background: #0d1218; color: #e7edf3; }
    #metrics { height: 6; }
    Metric { width: 1fr; margin: 0 1; padding: 1 2; background: #151d26; border-left: tall #25c2a0; }
    #state { margin: 1 2; }
    #readiness { margin: 0 2 1 2; color: #aebdca; }
    DataTable { margin: 0 2; height: 1fr; }
    """
    BINDINGS = [("q", "quit", "退出"), ("r", "refresh", "刷新")]

    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="metrics"):
            yield Metric("请求", id="requests")
            yield Metric("输入 Token", id="input")
            yield Metric("输出 Token", id="output")
            yield Metric("工具压缩估算", id="rtk")
        yield Label("正在连接本地服务…", id="state")
        yield Label("正在读取能力证据", id="readiness")
        yield DataTable(id="events")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#events", DataTable)
        table.add_columns("时间", "类型", "客户端", "结果", "耗时")
        self.set_interval(5, self.refresh_data)
        self.refresh_data()

    def action_refresh(self) -> None:
        self.refresh_data()

    def refresh_data(self) -> None:
        base = f"http://{self.settings.host}:{self.settings.dashboard_port}/api/v1"
        try:
            with httpx.Client(timeout=2) as client:
                status = client.get(f"{base}/status").json()
                metrics = client.get(f"{base}/metrics").json()["local"]
                events = client.get(f"{base}/events?limit=20").json()
                capabilities = client.get(f"{base}/capabilities").json()
                recovery = client.get(f"{base}/recovery/status").json()
                compression_report = client.get(f"{base}/benchmarks/latest?kind=compression")
                response_report = client.get(f"{base}/benchmarks/latest?kind=response")
            values = {"requests": metrics["requests"], "input": metrics["input_tokens"], "output": metrics["output_tokens"], "rtk": metrics["rtk_saved_tokens"]}
            for name, value in values.items():
                widget = self.query_one(f"#{name}", Metric)
                widget.value = "未知" if value is None else f"{value:,}"
                widget.refresh()
            self.query_one("#state", Label).update(
                f"输入代理 {'在线' if status['headroom'] else '离线'} · 内置工具压缩 {'可用' if status['rtk'] else '不可用'} · {status['profile']} / {status['caveman']}"
            )
            summary = capabilities["summary"]
            reports = f"压缩对照 {'已有' if compression_report.is_success else '未运行'} / 回答评测 {'已有' if response_report.is_success else '未运行'}"
            self.query_one("#readiness", Label).update(
                f"能力 {capabilities['total_core_capabilities']} 项：对标 {summary['upstream_parity_passed']}，真实 {summary['real_client_passed']}，离线 {summary['offline_passed']}，待验证 {summary['implemented_unverified']}，未实现 {summary['not_implemented']} · "
                f"命令契约 {capabilities['reviewed_command_contracts']} / 发现 {capabilities['discovered_command_variants']}（发现数不作分母）· {reports} · 原文内存 {recovery['used_bytes'] / 1048576:.1f}/{recovery['capacity_bytes'] / 1048576:.0f} MiB"
            )
            table = self.query_one("#events", DataTable)
            table.clear()
            from datetime import datetime
            for item in events:
                table.add_row(datetime.fromtimestamp(item["created_at"]).strftime("%H:%M:%S"), item["kind"], item["client"], "成功" if item["success"] else "失败", f"{item.get('duration_ms') or 0} ms")
        except (httpx.HTTPError, KeyError, ValueError):
            self.query_one("#state", Label).update("服务未运行。执行 utk start 后重试。")
