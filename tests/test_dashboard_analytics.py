from ultratokenkiller.store import Store


def test_chart_analytics_group_real_usage_without_content(tmp_path):
    store = Store(tmp_path / "metrics.sqlite3")
    store.add(
        kind="input",
        client="hermes",
        model="model-a",
        success=True,
        input_tokens=100,
        output_tokens=20,
        cached_tokens=15,
        saved_tokens=30,
        metadata={"private": "not returned"},
    )
    store.add(kind="tool", client="hermes", success=False, saved_tokens=40)

    analytics = store.analytics(24)

    assert analytics["granularity"] == "hour"
    assert len(analytics["timeline"]) == 24
    assert sum(point["consumed_tokens"] for point in analytics["timeline"]) == 120
    assert sum(point["saved_tokens"] for point in analytics["timeline"]) == 70
    model = analytics["by_model"][0]
    assert model == {
        "name": "model-a",
        "requests": 1,
        "consumed_tokens": 120,
        "saved_tokens": 30,
        "actual_input_tokens": 100,
        "actual_output_tokens": 20,
        "actual_cached_input_tokens": 15,
        "usage_observations": 1,
        "cache_usage_observations": 1,
        "estimated_cost_by_currency": {},
        "estimated_saved_cost_by_currency": {},
        "cost_estimate_statuses": {"price_not_recorded": 1},
    }
    assert sum(point["actual_input_tokens"] for point in analytics["timeline"]) == 100
    assert sum(point["actual_output_tokens"] for point in analytics["timeline"]) == 20
    assert sum(point["actual_cached_input_tokens"] for point in analytics["timeline"]) == 15
    assert analytics["measurement_basis"] == {
        "consumed_tokens": "provider_reported_usage",
        "saved_tokens": "estimated_prompt_delta",
        "money": "unavailable_no_price_catalog",
        "cached_input_tokens": "provider_reported_subset_of_input_tokens",
    }
    assert analytics["by_client"] == [
        {"name": "hermes", "requests": 1, "consumed_tokens": 120, "saved_tokens": 70}
    ]
    assert analytics["savings"] == [
        {"name": "input", "saved_tokens": 30},
        {"name": "tool", "saved_tokens": 40},
    ]
    assert analytics["outcomes"] == [
        {"name": "success", "count": 1},
        {"name": "failure", "count": 1},
    ]
    assert "private" not in str(analytics)


def test_week_and_month_use_daily_buckets(tmp_path):
    store = Store(tmp_path / "metrics.sqlite3")
    week = store.analytics(24 * 7)
    month = store.analytics(24 * 30)

    assert week["granularity"] == "day"
    assert len(week["timeline"]) == 7
    assert len(month["timeline"]) == 30


def test_analytics_aggregates_only_known_skip_reasons_and_usage_observations(tmp_path):
    store = Store(tmp_path / "metrics.sqlite3")
    store.add(
        kind="input", client="hermes", model="model-a", success=True,
        input_tokens=12,
        metadata={
            "tool_skip_reasons": {"already_compressed": 2, "no_tool_result": 1, "private-session": 8},
            "image_skip_reasons": {"text_dense_or_diagram": 3, "private-session": 9},
            "secret": "private prompt text",
        },
    )

    analytics = store.analytics(24)

    assert analytics["skip_reasons"] == [
        {"source": "image", "reason": "text_dense_or_diagram", "count": 3},
        {"source": "tool", "reason": "already_compressed", "count": 2},
        {"source": "tool", "reason": "no_tool_result", "count": 1},
    ]
    assert sum(point["usage_observations"] for point in analytics["timeline"]) == 1
    assert sum(point["cache_usage_observations"] for point in analytics["timeline"]) == 0
    assert "private" not in str(analytics)


def test_analytics_keeps_model_switches_and_missing_usage_distinct(tmp_path):
    store = Store(tmp_path / "metrics.sqlite3")
    store.add(kind="input", client="codex", model="model-a", success=True,
              input_tokens=90, output_tokens=10, cached_tokens=40, saved_tokens=8)
    store.add(kind="input", client="codex", model="model-a", success=True,
              input_tokens=50, output_tokens=5, saved_tokens=2)
    store.add(kind="input", client="codex", model="model-b", success=True,
              input_tokens=70, output_tokens=12, saved_tokens=4)
    store.add(kind="input", client="codex", model=None, success=False, saved_tokens=0)

    analytics = store.analytics(24)
    models = {item["name"]: item for item in analytics["by_model"]}
    assert models["model-a"]["actual_input_tokens"] == 140
    assert models["model-a"]["actual_output_tokens"] == 15
    assert models["model-a"]["actual_cached_input_tokens"] == 40
    assert models["model-a"]["usage_observations"] == 2
    assert models["model-a"]["cache_usage_observations"] == 1
    assert models["model-b"]["actual_input_tokens"] == 70
    assert models["model-b"]["actual_output_tokens"] == 12
    assert models["model-b"]["cache_usage_observations"] == 0
    assert models["unknown"]["usage_observations"] == 0
    assert sum(point["actual_input_tokens"] for point in analytics["timeline"]) == 210
    assert sum(point["actual_cached_input_tokens"] for point in analytics["timeline"]) == 40
