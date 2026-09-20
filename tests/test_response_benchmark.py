import json

import pytest

from ultratokenkiller.response_benchmark import evaluate_pairs, plan_response_budget


def test_paired_response_report_checks_facts_and_omits_bodies(tmp_path):
    path = tmp_path / "pairs.json"
    path.write_text(json.dumps({"cases": [{
        "id": "review", "mode": "lite",
        "baseline": "The limit is 73 requests. Do not retry after HTTP 429. Extra repeated conclusion. Extra repeated conclusion.",
        "candidate": "Limit: 73 requests. Do not retry after HTTP 429.",
        "required": ["73", "Do not retry", "HTTP 429"], "forbidden": ["safe to retry"],
    }]}), encoding="utf-8")
    report = evaluate_pairs(path, "gpt-4o")
    assert report["all_correct"] and report["cases"][0]["reduction"] > 0
    assert "baseline" not in report["cases"][0] and "candidate" not in report["cases"][0]
    broken = json.loads(path.read_text())
    broken["cases"][0]["candidate"] = "Retry is fine."
    path.write_text(json.dumps(broken), encoding="utf-8")
    assert not evaluate_pairs(path)["all_correct"]


def test_response_pairs_reject_unknown_mode(tmp_path):
    path = tmp_path / "pairs.json"
    path.write_text('{"cases":[{"mode":"invented","baseline":"a","candidate":"b"}]}')
    with pytest.raises(ValueError, match="known mode"):
        evaluate_pairs(path)


def test_frozen_response_corpus_has_complete_coverage_and_explicit_budget():
    report = plan_response_budget(
        "src/ultratokenkiller/data/response-quality-corpus.json"
    )

    assert report["scenario_count"] == 5
    assert len(report["active_modes"]) == 6
    assert report["repetitions"] == 3
    assert report["required_model_requests"] == 180
    assert report["structured_bypass_cases"] == 2
    assert report["live_model_calls"] == 0
    assert report["status"] == "authorization_required"
