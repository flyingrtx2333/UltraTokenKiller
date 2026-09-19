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
            yield Metric("RTK 节省", id="rtk")
        yield Label("正在连接本地服务…", id="state")
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
            values = {"requests": metrics["requests"], "input": metrics["input_tokens"], "output": metrics["output_tokens"], "rtk": metrics["rtk_saved_tokens"]}
            for name, value in values.items():
                widget = self.query_one(f"#{name}", Metric)
                widget.value = f"{value:,}"
                widget.refresh()
            self.query_one("#state", Label).update(
                f"Headroom {'在线' if status['headroom'] else '离线'} · RTK {'可用' if status['rtk'] else '缺失'} · {status['profile']} / {status['caveman']}"
            )
            table = self.query_one("#events", DataTable)
            table.clear()
            from datetime import datetime
            for item in events:
                table.add_row(datetime.fromtimestamp(item["created_at"]).strftime("%H:%M:%S"), item["kind"], item["client"], "成功" if item["success"] else "失败", f"{item.get('duration_ms') or 0} ms")
        except (httpx.HTTPError, KeyError, ValueError):
            self.query_one("#state", Label).update("服务未运行。执行 utk start 后重试。")

