from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

from .config import default_home


TASK_NAME = "UltraTokenKiller"


def enable(home: Path | None = None) -> tuple[bool, str]:
    root = home or default_home()
    root.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, "-m", "ultratokenkiller.cli", "start"]
    if sys.platform == "win32":
        executable = f'"{command[0]}" -m ultratokenkiller.cli start'
        result = subprocess.run(
            ["schtasks", "/Create", "/TN", TASK_NAME, "/SC", "ONLOGON", "/TR", executable, "/F"],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0, (result.stdout or result.stderr).strip()
    if sys.platform == "darwin":
        path = Path.home() / "Library" / "LaunchAgents" / "dev.ultratokenkiller.service.plist"
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "Label": "dev.ultratokenkiller.service",
            "ProgramArguments": command,
            "RunAtLoad": True,
            "KeepAlive": False,
            "EnvironmentVariables": {"UTK_HOME": str(root)},
        }
        path.write_bytes(plistlib.dumps(data))
        result = subprocess.run(["launchctl", "load", "-w", str(path)], capture_output=True, text=True)
        return result.returncode == 0, (result.stdout or result.stderr or str(path)).strip()
    systemctl = shutil.which("systemctl")
    if systemctl:
        directory = Path.home() / ".config" / "systemd" / "user"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "utk.service"
        path.write_text(
            "[Unit]\nDescription=UltraTokenKiller\nAfter=network.target\n\n"
            "[Service]\nType=oneshot\nRemainAfterExit=yes\n"
            f"Environment=UTK_HOME={root}\nExecStart={sys.executable} -m ultratokenkiller.cli start\n"
            f"ExecStop={sys.executable} -m ultratokenkiller.cli stop\n\n"
            "[Install]\nWantedBy=default.target\n",
            encoding="utf-8",
        )
        subprocess.run([systemctl, "--user", "daemon-reload"], capture_output=True)
        result = subprocess.run([systemctl, "--user", "enable", "--now", "utk.service"], capture_output=True, text=True)
        return result.returncode == 0, (result.stdout or result.stderr or str(path)).strip()
    return False, "No supported user service manager was found"


def disable() -> tuple[bool, str]:
    if sys.platform == "win32":
        result = subprocess.run(["schtasks", "/Delete", "/TN", TASK_NAME, "/F"], capture_output=True, text=True)
        return result.returncode == 0, (result.stdout or result.stderr).strip()
    if sys.platform == "darwin":
        path = Path.home() / "Library" / "LaunchAgents" / "dev.ultratokenkiller.service.plist"
        subprocess.run(["launchctl", "unload", "-w", str(path)], capture_output=True)
        path.unlink(missing_ok=True)
        return True, str(path)
    systemctl = shutil.which("systemctl")
    if systemctl:
        result = subprocess.run([systemctl, "--user", "disable", "--now", "utk.service"], capture_output=True, text=True)
        return result.returncode == 0, (result.stdout or result.stderr).strip()
    return False, "No supported user service manager was found"

