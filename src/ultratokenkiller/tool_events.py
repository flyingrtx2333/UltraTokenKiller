"""Body-free tool telemetry; the daemon owns SQLite when a session is active."""
from __future__ import annotations

import os
import sqlite3
from typing import Annotated, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field

from .config import default_home


RecoveryId = Annotated[str, Field(max_length=128, pattern=r"^[A-Za-z0-9_-]+$")]


class ToolMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    command: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.+-]+$")
    optimized: bool
    engine: Literal["utk-native"]
    estimator: Literal["utf8_bytes_div_4"]
    filter: str | None = Field(default=None, max_length=64, pattern=r"^[a-z0-9:_-]+$")
    execution_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    session_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    tool_call_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    recovery_id: RecoveryId | None = None
    recovery_ids: dict[Literal["stdout", "stderr"], RecoveryId] | None = None
    optimized_channels: list[Literal["stdout", "stderr"]] | None = None
    fallback: str | None = Field(default=None, max_length=64, pattern=r"^[a-z0-9:_-]+$")


class ToolEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    kind: Literal["tool"]
    client: Literal["cli", "codex", "hermes"]
    success: bool
    duration_ms: int = Field(ge=0)
    saved_tokens: int = Field(ge=0)
    metadata: ToolMetadata


class ToolEventSink:
    def __init__(self, home=None):
        self.home = home or default_home()

    def add(self, **event):
        """Metric failures cannot turn a successful command into a failed one."""
        try:
            if os.environ.get("UTK_SESSION_ID"):
                from .broker import BrokerClient
                broker = BrokerClient(self.home)
                with broker.client(timeout=3) as client:
                    response = client.post(broker.url + "/api/v1/internal/tool-events",
                                           headers=broker.headers(), json=event)
                    response.raise_for_status()
                    return response.json()["id"]
            from .store import Store
            return Store(self.home / "metrics.sqlite3").add(**event)
        except (OSError, sqlite3.Error, httpx.HTTPError, ValueError, KeyError):
            return None
