"""Pinned public model assets, SHA-256 verified before atomic activation."""
import hashlib
import json
import os
from importlib.resources import files
from pathlib import Path

import httpx

from .config import default_home


def model_manifest():
    return json.loads(files("ultratokenkiller").joinpath("data/text-model.json").read_text(encoding="utf-8"))


def model_directory(home=None):
    return (home or default_home()) / "assets" / "text-model"


def verify_assets(home=None):
    root = model_directory(home)
    manifest = model_manifest()
    for entry in manifest["files"]:
        path = root / entry["path"]
        if not path.is_file() or path.stat().st_size != entry["size"]:
            return False
        digest = hashlib.sha256()
        with path.open("rb") as file:
            for block in iter(lambda: file.read(1024*1024), b""):
                digest.update(block)
        if digest.hexdigest() != entry["sha256"]:
            return False
    return True


def install_assets(home=None):
    root = model_directory(home)
    manifest = model_manifest()
    with httpx.Client(timeout=httpx.Timeout(120, connect=30), follow_redirects=True) as client:
        for entry in manifest["files"]:
            relative = Path(entry["path"])
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("Unsafe asset path")
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() and target.stat().st_size == entry["size"] and hashlib.sha256(target.read_bytes()).hexdigest() == entry["sha256"]:
                continue
            import tempfile
            descriptor, filename = tempfile.mkstemp(dir=target.parent, suffix=".partial")
            temporary = Path(filename)
            try:
                digest = hashlib.sha256()
                size = 0
                url = f"https://huggingface.co/{manifest['repository']}/resolve/{manifest['revision']}/{entry['path']}"
                with os.fdopen(descriptor, "wb") as file, client.stream("GET", url) as response:
                    response.raise_for_status()
                    for block in response.iter_bytes(1024*1024):
                        size += len(block)
                        if size > entry["size"]:
                            raise ValueError("Asset exceeds declared size")
                        digest.update(block)
                        file.write(block)
                if size != entry["size"] or digest.hexdigest() != entry["sha256"]:
                    raise ValueError("Asset checksum mismatch")
                temporary.replace(target)
            finally:
                temporary.unlink(missing_ok=True)
    return verify_assets(home)
