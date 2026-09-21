"""Stable, non-secret identity for one UTK home directory."""
from __future__ import annotations

import hashlib
import os
import secrets
from pathlib import Path


def ensure_session_token(home: Path) -> str:
    """Return this home's broker token, creating it without replacing a peer."""
    home.mkdir(parents=True, exist_ok=True)
    path = home / "session-token"
    try:
        token = path.read_text(encoding="ascii").strip()
    except FileNotFoundError:
        token = secrets.token_urlsafe(32)
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            token = path.read_text(encoding="ascii").strip()
        else:
            with os.fdopen(descriptor, "w", encoding="ascii") as stream:
                stream.write(token)
    if not token:
        raise ValueError("UTK session token is empty")
    if os.name != "nt":
        os.chmod(path, 0o600)
    return token


def instance_id(token: str) -> str:
    """Derive a public instance identifier without exposing the broker token."""
    return hashlib.sha256(b"utk-instance-v1\0" + token.encode("ascii")).hexdigest()[:24]


def home_instance_id(home: Path) -> str | None:
    try:
        token = (home / "session-token").read_text(encoding="ascii").strip()
        return instance_id(token) if token else None
    except (FileNotFoundError, OSError, UnicodeError, ValueError):
        return None
