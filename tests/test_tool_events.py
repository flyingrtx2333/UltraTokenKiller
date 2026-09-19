import sqlite3

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ultratokenkiller.broker import broker_router
from ultratokenkiller.recovery import RecoveryVault
from ultratokenkiller.store import Store
from ultratokenkiller.tool_events import ToolEventSink


def event():
    return {"kind": "tool", "client": "codex", "success": True, "duration_ms": 10,
            "saved_tokens": 100, "metadata": {"command": "rg", "optimized": True,
            "engine": "utk-native", "estimator": "utf8_bytes_div_4", "filter": "search",
            "execution_id": "a" * 32, "session_id": "b" * 64}}


def test_broker_records_metadata_once_and_rejects_bodies(tmp_path):
    app = FastAPI()
    app.include_router(broker_router(RecoveryVault(), "secret", tmp_path))
    client = TestClient(app)
    headers = {"X-UTK-Token": "secret"}
    path = "/api/v1/internal/tool-events"
    assert client.post(path, json=event()).status_code == 403
    assert client.post(path, json=event(), headers={**headers, "Origin": "http://evil.test"}).status_code == 403
    assert client.post(path, json=event(), headers=headers).status_code == 200
    assert client.post(path, json=event(), headers=headers).status_code == 200
    records = Store(tmp_path / "metrics.sqlite3").events(100)
    assert len(records) == 1
    assert records[0]["input_tokens"] is None
    bad = event()
    bad["metadata"]["prompt"] = "private body"
    assert client.post(path, json=bad, headers=headers).status_code == 422
    assert b"private body" not in (tmp_path / "metrics.sqlite3").read_bytes()


def test_failed_metrics_do_not_change_command_result(tmp_path, monkeypatch):
    monkeypatch.delenv("UTK_SESSION_ID", raising=False)
    def fail(*args, **kwargs):
        raise sqlite3.OperationalError("disk I/O error")
    monkeypatch.setattr(Store, "add", fail)
    assert ToolEventSink(tmp_path).add(**event()) is None


def test_active_session_never_opens_sqlite_from_command(tmp_path, monkeypatch):
    monkeypatch.setenv("UTK_SESSION_ID", "test-session")
    def fail(*args, **kwargs):
        raise AssertionError("command process must not open SQLite")
    monkeypatch.setattr(Store, "__init__", fail)
    assert ToolEventSink(tmp_path).add(**event()) is None
