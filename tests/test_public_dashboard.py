import importlib
import time

import pytest
from fastapi.testclient import TestClient

from ultratokenkiller.config import Settings
from ultratokenkiller.store import Store
from ultratokenkiller.pricing import event_cost_estimates


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
    public_service.store.add(kind="input", client="hermes", success=False,
                             metadata={"session_id": "private", "recovery_id": "handle", "upstream_status": 404})
    public_service.store.add(kind="tool", client="hermes", success=True,
                             metadata={"session_id": "private", "recovery_id": "handle", "original_bytes": 100, "rendered_bytes": 20})
    metadata = client.get("/api/v1/events").json()[0]["metadata"]
    assert metadata == {"original_bytes": 100, "rendered_bytes": 20}
    assert client.get("/api/v1/events").json()[1]["metadata"] == {"upstream_status": 404}


def test_feature_states_describe_observed_effect_not_only_configuration(public_service):
    client = TestClient(public_service.app)
    initial = client.get("/api/v1/status").json()["features"]
    assert initial == {"input": "waiting", "tools": "waiting", "response": "waiting"}

    public_service.store.add(
        kind="input", client="hermes", success=True, saved_tokens=12,
        metadata={"changed_tool_results": 1, "response_style_applied": False},
    )
    public_service.store.add(
        kind="tool", client="hermes", success=True, saved_tokens=8,
        metadata={"optimized": True},
    )
    observed = client.get("/api/v1/status").json()["features"]
    assert observed["input"] == "active"
    assert observed["tools"] == "active"
    assert observed["response"] == "skipped"


def test_public_event_exposes_only_safe_request_diagnostics(public_service):
    public_service.store.add(
        kind="input", client="hermes", success=False,
        metadata={
            "request_class": "model", "path": "/v1/chat/completions",
            "error_category": "invalid_request", "estimator": "tiktoken:o200k_base:model_unmapped",
            "token_estimate_exact_for_model": False,
            "estimated_saved_tokens_basis": "estimated_prompt_delta",
            "cost_estimate_status": "unavailable_no_price_catalog", "session_id": "secret",
            "recovery_id": "secret-handle",
            "candidate_tool_results": 2,
            "tool_skip_reasons": {"already_compressed": 1, "secret-session": "private text"},
            "image_skip_reasons": {"text_dense_or_diagram": 1, "secret-session": "private text"},
        },
    )
    event = TestClient(public_service.app, base_url="http://42.194.159.81:19187").get(
        "/api/v1/events"
    ).json()[0]
    assert event["metadata"] == {
        "request_class": "model", "path": "/v1/chat/completions",
        "error_category": "invalid_request",
        "estimator": "tiktoken:o200k_base:model_unmapped",
        "token_estimate_exact_for_model": False,
        "estimated_saved_tokens_basis": "estimated_prompt_delta",
        "cost_estimate_status": "unavailable_no_price_catalog",
        "candidate_tool_results": 2,
        "tool_skip_reasons": {"already_compressed": 1},
        "image_skip_reasons": {"text_dense_or_diagram": 1},
    }


def test_public_compression_failure_shows_safe_reason_only(public_service):
    public_service.store.add(
        kind="input", client="hermes", success=True,
        metadata={"compression_fallback": "compression_timeout", "session_id": "private"},
    )
    client = TestClient(public_service.app, base_url="http://42.194.159.81:19187")
    assert client.get("/api/v1/status").json()["features"]["input"] == "error"
    assert client.get("/api/v1/events").json()[0]["metadata"] == {
        "compression_fallback": "compression_timeout"
    }

    public_service.store.add(
        kind="input", client="hermes", success=True,
        metadata={"compression_fallback": {"detail": "private exception text"}},
    )
    assert client.get("/api/v1/events").json()[0]["metadata"] == {}


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


def test_failed_applied_response_style_is_reported_as_error(public_service):
    public_service.settings.caveman = "lite"
    public_service.store.add(
        kind="input",
        client="hermes",
        success=False,
        metadata={"response_style_applied": True, "error_category": "invalid_request_error"},
    )

    status = TestClient(public_service.app).get("/api/v1/status").json()

    assert status["features"]["response"] == "error"


def test_public_metrics_include_safe_chart_aggregates(public_service):
    public_service.store.add(
        kind="input", client="hermes", model="model-a", success=True,
        input_tokens=10, output_tokens=2, saved_tokens=3,
        metadata={"secret": "never expose"},
    )

    payload = TestClient(public_service.app, base_url="http://42.194.159.81:19187").get(
        "/api/v1/metrics?hours=24"
    ).json()

    assert payload["analytics"]["by_model"][0]["name"] == "model-a"
    assert payload["analytics"]["timeline"]
    assert "secret" not in str(payload["analytics"])


def test_public_events_show_money_estimates_without_price_sources_or_secrets(public_service):
    public_service.settings.model_pricing = {
        "hermes/model-a": {
            "currency": "USD",
            "input_per_million": 1,
            "output_per_million": 2,
            "cache_mode": "none",
            "source": "private-price-source-with-sensitive-query?token=secret",
            "checked_on": "2026-09-23",
        }
    }
    metadata = {"secret": "request content must stay hidden"}
    metadata.update(event_cost_estimates(
        public_service.settings.model_pricing, "model-a", client="hermes", input_tokens=1000,
        output_tokens=100, cached_tokens=0, saved_tokens=200,
    ))
    public_service.store.add(
        kind="input", client="hermes", model="model-a", success=True,
        input_tokens=1000, output_tokens=100, cached_tokens=0, saved_tokens=200,
        metadata=metadata,
    )

    response = TestClient(public_service.app, base_url="http://42.194.159.81:19187").get("/api/v1/events")
    quote = response.json()[0]["metadata"]["estimated_cost"]
    saved_quote = response.json()[0]["metadata"]["estimated_saved_cost"]

    assert quote["status"] == "estimated"
    assert quote["currency"] == "USD"
    assert quote["amount"] == pytest.approx(0.0012)
    assert saved_quote["amount"] == pytest.approx(0.0002)
    assert "source" not in quote
    assert "secret" not in str(response.json())
