"""Capture the packaged Textual dashboard against an isolated running service."""

from __future__ import annotations

import asyncio
from pathlib import Path

from ultratokenkiller.config import Settings
from ultratokenkiller.tui import Dashboard


async def main() -> None:
    output = Path(__file__).resolve().parents[1] / "docs" / "assets"
    output.mkdir(parents=True, exist_ok=True)
    app = Dashboard(Settings(host="127.0.0.1", dashboard_port=18797))
    async with app.run_test(size=(120, 45)) as pilot:
        await pilot.pause(1)
        app.save_screenshot(filename="terminal-dashboard.svg", path=str(output))


if __name__ == "__main__":
    asyncio.run(main())
