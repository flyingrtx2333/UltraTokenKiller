from pathlib import Path

from ultratokenkiller.store import Store


def test_summary_keeps_savings_layers_separate(tmp_path: Path):
    store = Store(tmp_path / "metrics.sqlite3")
    store.add(kind="rtk", client="cli", success=True, saved_tokens=120, duration_ms=10)
    store.add(kind="headroom", client="codex", success=True, saved_tokens=300, input_tokens=900, output_tokens=40)
    summary = store.summary()
    assert summary["rtk_saved_tokens"] == 120
    assert summary["headroom_saved_tokens"] == 300
    assert "total_saved_tokens" not in summary

