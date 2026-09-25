"""Conservative, process-local protection for provider prompt-cache prefixes."""

import asyncio
import copy
import json
import time
from collections import OrderedDict
from dataclasses import dataclass


_TTL_SECONDS = {"5m": 300, "1h": 3600}


def explicit_cache_ttl(payload: dict) -> int | None:
    """Return only a TTL stated by the request; unknown markers are not guesses."""
    markers = []

    def scan(value):
        if isinstance(value, dict):
            marker = value.get("cache_control")
            if marker:
                markers.append(marker)
            for child in value.values():
                if isinstance(child, (dict, list)):
                    scan(child)
        elif isinstance(value, list):
            for child in value:
                scan(child)

    scan(payload.get("system"))
    scan(payload.get("messages", payload.get("input", [])))
    if not markers or any(not isinstance(marker, dict) or marker.get("ttl") not in _TTL_SECONDS
                          for marker in markers):
        return None
    return max(_TTL_SECONDS[marker["ttl"]] for marker in markers)


def _unmodified_history(state: "PrefixState") -> bool:
    """Cold rebuilds require the client history to still contain its original text."""
    if state.incoming != state.forwarded:
        return False
    serialized = json.dumps(state.incoming, ensure_ascii=False)
    return not any(marker in serialized for marker in (
        "UTK retrieve:", '"_utk_recovery"', "UTK original image:",
        "[UTK: read of ",
    ))


@dataclass
class PrefixState:
    envelope: dict
    incoming: list
    forwarded: list
    ttl_seconds: int | None
    touched: float
    size: int


class PrefixGuard:
    """Serialize each session and retain bounded snapshots of its forwarded prefix."""

    def __init__(self, *, clock=time.monotonic, max_sessions=128,
                 max_bytes=32 * 1024 * 1024, max_session_bytes=4 * 1024 * 1024,
                 idle_seconds=7200, margin_seconds=60):
        self.clock = clock
        self.max_sessions = max_sessions
        self.max_bytes = max_bytes
        self.max_session_bytes = max_session_bytes
        self.idle_seconds = idle_seconds
        self.margin_seconds = margin_seconds
        self.states: OrderedDict[tuple[str, str, str], PrefixState] = OrderedDict()
        self.used_bytes = 0
        self.locks = [asyncio.Lock() for _ in range(64)]

    def _prune(self, now):
        for key, state in list(self.states.items()):
            if now - state.touched >= self.idle_seconds:
                self.used_bytes -= self.states.pop(key).size

    def _remember(self, key, envelope, incoming, forwarded, ttl, now):
        size = len(json.dumps(incoming, ensure_ascii=False).encode("utf-8"))
        size += len(json.dumps(forwarded, ensure_ascii=False).encode("utf-8"))
        size += len(json.dumps(envelope, ensure_ascii=False).encode("utf-8"))
        old = self.states.pop(key, None)
        if old:
            self.used_bytes -= old.size
        if size > self.max_session_bytes or size > self.max_bytes:
            return False
        while self.states and (len(self.states) >= self.max_sessions
                               or self.used_bytes + size > self.max_bytes):
            _, evicted = self.states.popitem(last=False)
            self.used_bytes -= evicted.size
        self.states[key] = PrefixState(copy.deepcopy(envelope), copy.deepcopy(incoming),
                                       copy.deepcopy(forwarded),
                                       ttl, now, size)
        self.used_bytes += size
        return True

    async def process(self, payload, *, session, protocol, model, transform):
        """Call transform(payload, frozen_count, cold, forwarded_prefix)."""
        items = payload.get("messages", payload.get("input"))
        if not session or not isinstance(items, list):
            return await transform(payload, 0, False, None)
        key = (session, protocol, model if isinstance(model, str) else "")
        envelope = {name: value for name, value in payload.items()
                    if name not in {"messages", "input"}}
        async with self.locks[hash(key) % len(self.locks)]:
            now = self.clock()
            self._prune(now)
            previous = self.states.get(key)
            ttl = explicit_cache_ttl(payload)
            matched = 0
            if previous and previous.envelope == envelope:
                for old, new in zip(previous.incoming, items):
                    if old != new:
                        break
                    matched += 1
            append_only = bool(previous and matched == len(previous.incoming))
            ttl_expired = bool(append_only and previous.ttl_seconds is not None
                               and ttl == previous.ttl_seconds
                               and now - previous.touched > ttl + self.margin_seconds)
            cold = bool(ttl_expired and _unmodified_history(previous))
            if cold:
                frozen = 0
                reason = "explicit_ttl_expired"
                forwarded_prefix = None
            elif append_only:
                frozen = matched
                reason = "matched_prefix"
                forwarded_prefix = previous.forwarded[:matched]
            else:
                frozen = len(items)
                reason = "first_seen" if previous is None else "prefix_mismatch"
                forwarded_prefix = None
            result, metadata = await transform(payload, frozen, cold, forwarded_prefix)
            output_items = result.get("messages", result.get("input"))
            if isinstance(output_items, list):
                remembered = self._remember(key, envelope, items, output_items, ttl, now)
            else:
                remembered = False
            metadata["prefix_guard"] = {
                "reason": reason, "frozen_messages": frozen,
                "cold": cold, "ttl_seconds": ttl,
                "tracked": remembered,
            }
            if ttl_expired and not cold:
                metadata["prefix_guard"]["cold_fallback"] = "unrecoverable_history"
            elif ttl is None:
                metadata["prefix_guard"]["cold_fallback"] = "unknown_ttl"
            return result, metadata
