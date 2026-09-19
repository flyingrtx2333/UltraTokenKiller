from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import urllib.error
import zipfile
from pathlib import Path

from .config import default_home


HEADROOM_VERSION = "0.37.0"
RTK_RELEASE_API = "https://api.github.com/repos/rtk-ai/rtk/releases/latest"


def find_rtk(home: Path | None = None) -> str | None:
    name = "rtk.exe" if sys.platform == "win32" else "rtk"
    managed = (home or default_home()) / "bin" / name
    return str(managed) if managed.exists() else shutil.which("rtk")


def find_headroom() -> str | None:
    name = "headroom.exe" if sys.platform == "win32" else "headroom"
    adjacent = Path(sys.executable).parent / name
    return str(adjacent) if adjacent.exists() else shutil.which("headroom")


def ensure_headroom() -> tuple[bool, str]:
    existing = find_headroom()
    if existing:
        return True, existing
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", f"headroom-ai=={HEADROOM_VERSION}"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0, find_headroom() or (result.stderr.strip().splitlines()[-1] if result.stderr else "install failed")


def ensure_rtk(home: Path | None = None) -> tuple[bool, str]:
    existing = find_rtk(home)
    if existing:
        return True, existing
    root = home or default_home()
    try:
        request = urllib.request.Request(RTK_RELEASE_API, headers={"User-Agent": "UltraTokenKiller/0.1"})
        with urllib.request.urlopen(request, timeout=30) as response:
            release = json.load(response)
        asset_name = _rtk_asset_name()
        assets = {asset["name"]: asset["browser_download_url"] for asset in release["assets"]}
        if asset_name not in assets or "checksums.txt" not in assets:
            return False, f"No verified RTK asset for {platform.system()} {platform.machine()}"
        with tempfile.TemporaryDirectory(prefix="utk-rtk-") as temporary:
            temp = Path(temporary)
            archive = temp / asset_name
            checksums = temp / "checksums.txt"
            _download(assets[asset_name], archive)
            _download(assets["checksums.txt"], checksums)
            expected = _checksum_for(checksums.read_text(encoding="utf-8"), asset_name)
            actual = hashlib.sha256(archive.read_bytes()).hexdigest()
            if not expected or actual.lower() != expected.lower():
                return False, "RTK checksum verification failed"
            destination = root / "bin" / ("rtk.exe" if sys.platform == "win32" else "rtk")
            destination.parent.mkdir(parents=True, exist_ok=True)
            _extract_binary(archive, destination)
            if sys.platform != "win32":
                destination.chmod(destination.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        return True, str(destination)
    except (OSError, ValueError, KeyError, urllib.error.URLError) as error:
        return False, str(error)


def _rtk_asset_name() -> str:
    machine = platform.machine().lower()
    arm = machine in {"arm64", "aarch64"}
    if sys.platform == "win32" and not arm:
        return "rtk-x86_64-pc-windows-msvc.zip"
    if sys.platform == "darwin":
        return "rtk-aarch64-apple-darwin.tar.gz" if arm else "rtk-x86_64-apple-darwin.tar.gz"
    if sys.platform.startswith("linux"):
        return "rtk-aarch64-unknown-linux-gnu.tar.gz" if arm else "rtk-x86_64-unknown-linux-musl.tar.gz"
    raise ValueError(f"Unsupported RTK platform: {sys.platform}/{machine}")


def _download(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "UltraTokenKiller/0.1"})
    with urllib.request.urlopen(request, timeout=60) as source, destination.open("wb") as target:
        shutil.copyfileobj(source, target)


def _checksum_for(text: str, name: str) -> str | None:
    for line in text.splitlines():
        parts = line.strip().replace(" *", "  ").split()
        if len(parts) >= 2 and parts[-1].lstrip("*") == name:
            return parts[0]
    return None


def _extract_binary(archive: Path, destination: Path) -> None:
    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as package:
            member = next((item for item in package.infolist() if Path(item.filename).name == "rtk.exe"), None)
            if member is None:
                raise ValueError("RTK executable missing from archive")
            with package.open(member) as source, destination.open("wb") as target:
                shutil.copyfileobj(source, target)
        return
    with tarfile.open(archive, "r:gz") as package:
        member = next((item for item in package.getmembers() if item.isfile() and Path(item.name).name == "rtk"), None)
        if member is None:
            raise ValueError("RTK executable missing from archive")
        source = package.extractfile(member)
        if source is None:
            raise ValueError("RTK executable could not be extracted")
        with source, destination.open("wb") as target:
            shutil.copyfileobj(source, target)
