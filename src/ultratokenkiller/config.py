from __future__ import annotations

import json
import os
import socket
import sys
import tempfile
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
    dashboard_host: str = "127.0.0.1"
    dashboard_port: int = 18787
    headroom_port: int = 18788
    profile: str = "safe"
    caveman: str = "lite"
    retention_days: int = 30
    auto_start: bool = True
    headroom_managed: bool = True
    clients: dict[str, dict[str, Any]] = field(default_factory=dict)
    proxy_environment: dict[str, str] = field(default_factory=dict)
    schema_version: int = 2
    tools_enabled: bool = True
    recovery_capacity_bytes: int = 256 * 1024 * 1024
    recovery_idle_seconds: int = 3600

    @classmethod
    def load(cls, home: Path | None = None) -> "Settings":
        path = (home or default_home()) / "config.json"
        values = json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else {}
        if values.get("schema_version", 1) not in {1, 2}:
            raise ValueError("Unsupported UTK configuration version")
        if values.get("schema_version") == 2:
            values = dict(values)
            input_config = values.get("input", {})
            values.update(profile=input_config.get("profile", "safe"),
                          headroom_port=input_config.get("port", 18788),
                          headroom_managed=input_config.get("managed", True),
                          caveman=values.get("response", {}).get("mode", "lite"),
                          tools_enabled=values.get("tools", {}).get("enabled", True))
        known = {key: values[key] for key in cls.__dataclass_fields__ if key in values}
        settings = cls(**known)
        if os.environ.get("UTK_DASHBOARD_PORT"):
            settings.dashboard_port = int(os.environ["UTK_DASHBOARD_PORT"])
        if os.environ.get("UTK_HEADROOM_PORT"):
            settings.headroom_port = int(os.environ["UTK_HEADROOM_PORT"])
        settings.validate()
        return settings

    def validate(self):
        if self.host != "127.0.0.1":
            raise ValueError("UTK only supports loopback listeners")
        if self.dashboard_host not in {"127.0.0.1", "0.0.0.0"}:
            raise ValueError("Dashboard host must be loopback or 0.0.0.0")
        if self.profile not in {"safe", "aggressive", "off"}:
            raise ValueError("Unknown input profile")
        if self.caveman not in {"lite", "full", "ultra", "off", "wenyan-lite", "wenyan-full", "wenyan-ultra"}:
            raise ValueError("Unknown response mode")
        if self.recovery_capacity_bytes <= 0 or self.recovery_idle_seconds <= 0:
            raise ValueError("Invalid recovery limits")
        if any(not 1 <= port <= 65535 for port in (self.dashboard_port, self.headroom_port)):
            raise ValueError("Invalid listener port")

    def public_config(self):
        data = asdict(self)
        data["schema_version"] = 2
        data["input"] = {"profile": data.pop("profile"), "port": data.pop("headroom_port"), "managed": data.pop("headroom_managed")}
        data["tools"] = {"enabled": data.pop("tools_enabled")}
        data["response"] = {"mode": data.pop("caveman")}
        return data

    def save(self, home: Path | None = None) -> Path:
        self.validate()
        root = home or default_home()
        root.mkdir(parents=True, exist_ok=True)
        path = root / "config.json"
        if path.exists():
            previous = json.loads(path.read_text(encoding="utf-8-sig"))
            if previous.get("schema_version", 1) == 1:
                backup = root / "config.v1.json"
                if not backup.exists():
                    backup.write_bytes(path.read_bytes())
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=root, suffix=".tmp", delete=False) as file:
            json.dump(self.public_config(), file, ensure_ascii=False, indent=2)
            temp = Path(file.name)
        try:
            temp.replace(path)
        finally:
            temp.unlink(missing_ok=True)
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
