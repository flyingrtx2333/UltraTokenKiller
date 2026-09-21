import importlib

from fastapi.testclient import TestClient


def test_management_writes_require_session_token(tmp_path, monkeypatch):
    monkeypatch.setenv("UTK_HOME", str(tmp_path))
    import ultratokenkiller.service as service
    service = importlib.reload(service)
    monkeypatch.setattr(service, "restart_managed_headrooms", lambda *_: None)
    client = TestClient(service.app)
    health = client.get("/api/v1/health")
    assert health.status_code == 200
    assert len(health.json()["instance_id"]) == 24
    assert service.session_token not in health.text
    assert client.patch("/api/v1/config", json={"profile": "off"}).status_code == 403
    config = client.get("/api/v1/config").json()
    response = client.patch("/api/v1/config", json={"profile": "off"}, headers={"X-UTK-Token": config["session_token"]})
    assert response.status_code == 200
    assert response.json()["profile"] == "off"
    assert client.get("/api/v1/benchmarks/latest").status_code == 404
