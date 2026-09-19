"""Bounded in-memory recovery and stable per-session transformations."""
from __future__ import annotations

import hashlib
import secrets
import threading
import time
from dataclasses import dataclass, field

from .contracts import CompressionResult


class RecoveryUnavailable(LookupError):
    pass


@dataclass
class Session:
    touched: float
    entries: dict[str, tuple[str, CompressionResult]] = field(default_factory=dict)
    fingerprints: dict[str, str] = field(default_factory=dict)
    bytes: int = 0


class RecoveryVault:
    def __init__(self, capacity: int = 256 * 1024 * 1024, idle_seconds: float = 3600, clock=time.monotonic):
        if capacity <= 0 or idle_seconds <= 0:
            raise ValueError("Memory and expiry limits must be positive")
        self.capacity = capacity
        self.idle_seconds = idle_seconds
        self.clock = clock
        self.sessions: dict[str, Session] = {}
        self.used = 0
        self.lock = threading.RLock()

    def _prune(self):
        now = self.clock()
        for key in list(self.sessions):
            if now - self.sessions[key].touched >= self.idle_seconds:
                self.used -= self.sessions.pop(key).bytes

    def lookup(self, session: str, original: str) -> CompressionResult | None:
        with self.lock:
            self._prune()
            current = self.sessions.get(session)
            if current:
                current.touched = self.clock()
                key = current.fingerprints.get(hashlib.sha256(original.encode()).hexdigest())
                if key:
                    return current.entries[key][1]
        return None

    def put(self, session: str, original: str, factory) -> CompressionResult | None:
        """Atomically pin a transformation. Never evict active entries for space."""
        if not session:
            raise ValueError("A session is required")
        with self.lock:
            existing = self.lookup(session, original)
            if existing:
                return existing
            handle = secrets.token_urlsafe(24)
            result = factory(handle)
            # Conservatively charge Python Unicode storage and per-entry overhead.
            size = 4 * (len(original) + len(result.content)) + 2048
            if size > self.capacity - self.used or result.after_tokens >= result.before_tokens:
                return None
            current = self.sessions.setdefault(session, Session(self.clock()))
            current.touched = self.clock()
            current.entries[handle] = (original, result)
            current.fingerprints[hashlib.sha256(original.encode()).hexdigest()] = handle
            current.bytes += size
            self.used += size
            return result

    def retrieve(self, session: str, handle: str, offset: int = 0, limit: int = 32000) -> dict:
        if offset < 0 or not 1 <= limit <= 64000:
            raise ValueError("Invalid recovery range")
        with self.lock:
            self._prune()
            current = self.sessions.get(session)
            if not current or handle not in current.entries:
                raise RecoveryUnavailable("Original unavailable: expired, restarted, or wrong session")
            current.touched = self.clock()
            text = current.entries[handle][0]
            return {"content": text[offset:offset+limit], "offset": offset,
                    "total_characters": len(text), "next_offset": offset+limit if offset+limit < len(text) else None}

    def owns_rendering(self, session: str, text: str) -> bool:
        with self.lock:
            self._prune()
            current = self.sessions.get(session)
            if not current:
                return False
            current.touched = self.clock()
            return any(result.content == text for _, result in current.entries.values())

    def status(self):
        with self.lock:
            self._prune()
            return {"used_bytes": self.used, "capacity_bytes": self.capacity,
                    "sessions": len(self.sessions), "idle_seconds": self.idle_seconds, "storage": "memory-only"}
