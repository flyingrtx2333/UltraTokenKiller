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
        saved_tokens=30,
        metadata={"private": "not returned"},
    )
    store.add(kind="tool", client="hermes", success=False, saved_tokens=40)

    analytics = store.analytics(24)

    assert analytics["granularity"] == "hour"
    assert len(analytics["timeline"]) == 24
    assert sum(point["consumed_tokens"] for point in analytics["timeline"]) == 120
    assert sum(point["saved_tokens"] for point in analytics["timeline"]) == 70
    assert analytics["by_model"] == [
        {"name": "model-a", "requests": 1, "consumed_tokens": 120, "saved_tokens": 30}
    ]
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
