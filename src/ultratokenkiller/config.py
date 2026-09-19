from __future__ import annotations

import json
import os
import socket
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


def default_home() -> Path:
    override = os.environ.get("UTK_HOME")
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform == "win32":
        root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return root / "UltraTokenKiller"
    return Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state")) / "utk"


@dataclass
class Settings:
    host: str = "127.0.0.1"
    dashboard_port: int = 18787
    headroom_port: int = 18788
    profile: str = "safe"
    caveman: str = "lite"
    retention_days: int = 30
    auto_start: bool = True
    headroom_managed: bool = True
    clients: dict[str, dict[str, Any]] = field(default_factory=dict)
    proxy_environment: dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls, home: Path | None = None) -> "Settings":
        path = (home or default_home()) / "config.json"
        values = json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else {}
        known = {key: values[key] for key in cls.__dataclass_fields__ if key in values}
        settings = cls(**known)
        if os.environ.get("UTK_DASHBOARD_PORT"):
            settings.dashboard_port = int(os.environ["UTK_DASHBOARD_PORT"])
        if os.environ.get("UTK_HEADROOM_PORT"):
            settings.headroom_port = int(os.environ["UTK_HEADROOM_PORT"])
        return settings

    def save(self, home: Path | None = None) -> Path:
        root = home or default_home()
        root.mkdir(parents=True, exist_ok=True)
        path = root / "config.json"
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(path)
        return path


def choose_port(preferred: int, host: str = "127.0.0.1", excluded: set[int] | None = None) -> int:
    excluded = excluded or set()
    for port in range(preferred, min(preferred + 100, 65536)):
        if port in excluded:
            continue
        with socket.socket() as sock:
            try:
                sock.bind((host, port))
            except OSError:
                continue
            return port
    raise RuntimeError(f"No free local port found after {preferred}")
