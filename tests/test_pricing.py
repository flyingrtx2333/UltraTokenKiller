from ultratokenkiller.pricing import (
    estimate_saved_input_cost,
    estimate_usage_cost,
    event_cost_estimates,
    load_price_catalog,
)
from ultratokenkiller.store import Store


def _prices():
    return {
        "hermes/provider/model-a": {
            "currency": "USD",
            "input_per_million": 0.15,
            "output_per_million": 0.60,
            "cache_mode": "none",
            "source": "https://provider.example/pricing",
            "checked_on": "2026-09-23",
        },
        "hermes/provider/model-b": {
            "currency": "USD",
            "input_per_million": 2.0,
            "output_per_million": 8.0,
            "cache_mode": "priced",
            "cached_input_per_million": 1.0,
            "source": "invoice-confirmed",
            "checked_on": "2026-09-23",
        },
    }


def test_exact_model_price_switch_and_unknown_model_are_not_conflated():
    catalog, status = load_price_catalog(_prices())
    assert status == "ready"

    first = estimate_usage_cost(catalog["hermes/provider/model-a"],
                                input_tokens=1_000_000, output_tokens=100_000, cached_tokens=0)
    second = estimate_usage_cost(catalog["hermes/provider/model-b"],
                                 input_tokens=1_000, output_tokens=100, cached_tokens=400)
    unknown = estimate_usage_cost(None, input_tokens=1000, output_tokens=100, cached_tokens=0)

    assert first["status"] == "estimated"
    assert first["amount"] == pytest.approx(0.21)
    assert second["status"] == "estimated"
    assert second["amount"] == pytest.approx(0.0024)
    assert unknown == {"status": "no_price"}


def test_cache_unknown_and_missing_usage_never_guess_a_cost():
    catalog, _ = load_price_catalog({
        "provider/uncertain": {
            "currency": "USD", "input_per_million": 1, "output_per_million": 2,
            "cache_mode": "unknown", "source": "provider pricing page", "checked_on": "2026-09-23",
        },
        "provider/cached": _prices()["hermes/provider/model-b"],
    })

    assert estimate_usage_cost(catalog["provider/uncertain"], input_tokens=10,
                               output_tokens=5, cached_tokens=0)["status"] == "cache_pricing_unknown"
    assert estimate_usage_cost(catalog["provider/cached"], input_tokens=10,
                               output_tokens=5, cached_tokens=None)["status"] == "cache_usage_missing"
    assert estimate_usage_cost(catalog["provider/cached"], input_tokens=None,
                               output_tokens=5, cached_tokens=0)["status"] == "usage_missing"


def test_saved_money_requires_known_no_cache_behavior():
    catalog, _ = load_price_catalog(_prices())
    no_cache = estimate_saved_input_cost(catalog["hermes/provider/model-a"], 500_000)
    cached = estimate_saved_input_cost(catalog["hermes/provider/model-b"], 500_000)

    assert no_cache["status"] == "estimated"
    assert no_cache["amount"] == pytest.approx(0.075)
    assert cached["status"] == "cache_effect_unknown"


def test_analytics_aggregates_cost_by_model_currency_and_time(tmp_path):
    _, status = load_price_catalog(_prices())
    store = Store(tmp_path / "metrics.sqlite3")
    event_metadata = lambda model, input_tokens, output_tokens, cached_tokens, saved_tokens: event_cost_estimates(
        _prices(), model, client="hermes", input_tokens=input_tokens, output_tokens=output_tokens,
        cached_tokens=cached_tokens, saved_tokens=saved_tokens,
    )
    store.add(kind="input", client="hermes", model="provider/model-a", success=True,
              input_tokens=1_000_000, output_tokens=100_000, cached_tokens=0, saved_tokens=500_000,
              metadata=event_metadata("provider/model-a", 1_000_000, 100_000, 0, 500_000))
    store.add(kind="input", client="hermes", model="provider/model-a", success=True,
              input_tokens=100_000, output_tokens=0, cached_tokens=0, saved_tokens=100_000,
              metadata=event_metadata("provider/model-a", 100_000, 0, 0, 100_000))
    store.add(kind="input", client="hermes", model="provider/model-b", success=True,
              input_tokens=1_000, output_tokens=100, cached_tokens=400, saved_tokens=500,
              metadata=event_metadata("provider/model-b", 1_000, 100, 400, 500))
    store.add(kind="input", client="hermes", model="provider/unknown", success=True,
              input_tokens=10, output_tokens=1, cached_tokens=0, saved_tokens=1,
              metadata=event_metadata("provider/unknown", 10, 1, 0, 1))

    result = store.analytics(24, status)
    models = {entry["name"]: entry for entry in result["by_model"]}

    assert result["price_catalog_status"] == "ready"
    assert result["estimated_cost_by_currency"]["USD"] == pytest.approx(0.2274)
    assert result["estimated_saved_cost_by_currency"]["USD"] == pytest.approx(0.09)
    assert models["provider/model-a"]["estimated_cost_by_currency"]["USD"] == pytest.approx(0.225)
    assert models["provider/model-a"]["estimated_saved_cost_by_currency"]["USD"] == pytest.approx(0.09)
    assert models["provider/model-b"]["estimated_saved_cost_by_currency"] == {}
    assert models["provider/unknown"]["estimated_cost_by_currency"] == {}
    assert sum(point["estimated_cost_by_currency"].get("USD", 0) for point in result["timeline"]) == pytest.approx(0.2274)


def test_event_cost_estimates_stay_separate_from_token_savings(tmp_path):
    store = Store(tmp_path / "metrics.sqlite3")
    metadata = event_cost_estimates(_prices(), "provider/model-a", client="hermes", input_tokens=1000,
                                    output_tokens=100, cached_tokens=0, saved_tokens=200)
    store.add(kind="input", client="hermes", model="provider/model-a", success=True,
              input_tokens=1000, output_tokens=100, cached_tokens=0, saved_tokens=200,
              metadata=metadata)

    event = store.events(1)[0]

    assert event["saved_tokens"] == 200
    assert event["metadata"]["estimated_cost"]["status"] == "estimated"
    assert event["metadata"]["estimated_saved_cost"]["status"] == "estimated"
    assert event["metadata"]["estimated_cost"]["amount"] != event["saved_tokens"]


def test_existing_event_estimates_are_not_repriced_by_a_later_catalog(tmp_path):
    store = Store(tmp_path / "metrics.sqlite3")
    snapshot = event_cost_estimates(_prices(), "provider/model-a", client="hermes", input_tokens=1000,
                                    output_tokens=100, cached_tokens=0, saved_tokens=200)
    store.add(kind="input", client="hermes", model="provider/model-a", success=True,
              input_tokens=1000, output_tokens=100, cached_tokens=0, saved_tokens=200,
              metadata=snapshot)

    result = store.analytics(24, catalog_status="not_configured")
    model = next(item for item in result["by_model"] if item["name"] == "provider/model-a")
    assert model["estimated_cost_by_currency"]["USD"] == pytest.approx(0.00021)
    assert result["price_catalog_status"] == "not_configured"


def test_invalid_price_rows_are_ignored_without_blocking_valid_models():
    raw = _prices() | {"bad": {"currency": "usd", "input_per_million": -1}}
    catalog, status = load_price_catalog(raw)
    assert set(catalog) == {"hermes/provider/model-a", "hermes/provider/model-b"}
    assert status == "partial"
import pytest
