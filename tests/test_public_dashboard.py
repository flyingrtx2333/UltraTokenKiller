import importlib
import time

import pytest
from fastapi.testclient import TestClient

from ultratokenkiller.config import Settings
from ultratokenkiller.store import Store


@pytest.fixture
def public_service(tmp_path, monkeypatch):
    monkeypatch.setenv("UTK_HOME", str(tmp_path))
    settings = Settings.load(tmp_path)
    settings.dashboard_host = "0.0.0.0"
    settings.save(tmp_path)
    import ultratokenkiller.service as service
    service = importlib.reload(service)
    monkeypatch.setattr(service, "restart_managed_headrooms", lambda *_: None)
    yield service
    # Do not leak the opt-in public setting into other tests importing this module.
    settings.dashboard_host = "127.0.0.1"
    settings.save(tmp_path)
    importlib.reload(service)


def test_public_view_never_exposes_token_or_management(public_service):
    client = TestClient(public_service.app, base_url="http://42.194.159.81:19187")
    response = client.get("/api/v1/config")
    assert response.status_code == 200
    assert response.json()["session_token"] is None
    assert response.headers["cache-control"] == "no-store"
    headers = {"X-UTK-Token": public_service.session_token}
    assert client.patch("/api/v1/config", json={"profile": "off"}, headers=headers).status_code == 403
    assert client.post("/api/v1/clients/hermes/disable", headers=headers).status_code == 403
    assert client.get("/api/v1/recovery", headers=headers).status_code == 403
    assert client.get("/api/v1/capabilities").status_code == 403
    assert all("config_path" not in item for item in client.get("/api/v1/status").json()["clients"])
    public_service.store.add(kind="tool", client="hermes", success=True,
                             metadata={"session_id": "private", "recovery_id": "handle", "original_bytes": 100, "rendered_bytes": 20})
    metadata = client.get("/api/v1/events").json()[0]["metadata"]
    assert metadata == {"original_bytes": 100, "rendered_bytes": 20}


def test_spoofed_loopback_headers_do_not_grant_access(public_service):
    client = TestClient(public_service.app, base_url="http://127.0.0.1:19187")
    headers = {"X-Forwarded-For": "127.0.0.1", "X-Real-IP": "127.0.0.1"}
    assert client.get("/api/v1/config", headers=headers).json()["session_token"] is None


def test_local_management_remains_available(public_service):
    client = TestClient(public_service.app, base_url="http://127.0.0.1:19187", client=("127.0.0.1", 12345))
    token = client.get("/api/v1/config").json()["session_token"]
    assert token == public_service.session_token
    response = client.patch("/api/v1/config", json={"tools": {"enabled": False}}, headers={"X-UTK-Token": token})
    assert response.status_code == 200
    assert client.get("/api/v1/status").json()["rtk"] is False


def test_events_obey_time_window_and_exclude_transport(public_service):
    store = public_service.store
    store.add(kind="tool", client="hermes", success=True, saved_tokens=10)
    old = store.add(kind="input", client="hermes", success=True)
    store.add(kind="transport", client="cli", success=True)
    with store.connect() as db:
        db.execute("UPDATE events SET created_at=? WHERE id=?", (time.time() - 2 * 86400, old))
    client = TestClient(public_service.app)
    recent = client.get("/api/v1/events?hours=24").json()
    assert [item["kind"] for item in recent] == ["tool"]
    assert len(client.get("/api/v1/events?hours=168").json()) == 2
    assert client.get("/api/v1/events?hours=0").status_code == 422


def test_store_unfiltered_call_stays_compatible(tmp_path):
    store = Store(tmp_path / "metrics.sqlite3")
    store.add(kind="transport", client="cli", success=True)
    assert len(store.events()) == 1
