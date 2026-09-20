import hashlib
import json
from pathlib import Path

from ultratokenkiller.benchmark import (
    capability_report,
    fixtures,
    run_benchmark,
    run_benchmark_matrix,
    save_report,
)


def test_offline_report_is_metadata_only_and_honest():
    for mode in ("passthrough", "prototype", "native"):
        report = run_benchmark(mode)
        assert report["status"] == "completed"
        assert report["live_model_calls"] == 0
        assert report["parity_certified"] is False
        assert report["schema_version"] == 3
        assert len(report["implementation_fingerprint"]) == 64
        assert len(report["cases"]) >= 6
        assert all(item["required_facts_preserved"] for item in report["cases"])
        assert all("content" not in item["engine"] for item in report["cases"])
        assert all(item["peak_memory_bytes"] >= 0 for item in report["cases"])
    assert run_benchmark("upstream")["status"] == "unavailable"


def test_native_benchmark_is_deterministic_except_duration():
    first = run_benchmark("native", model="gpt-5.6-luna")
    second = run_benchmark("native", model="gpt-5.6-luna")
    for left, right in zip(first["cases"], second["cases"]):
        volatile = {"duration_ms", "peak_memory_bytes"}
        left = {key: value for key, value in left.items() if key not in volatile}
        right = {key: value for key, value in right.items() if key not in volatile}
        assert left == right


def test_fixed_reference_results_are_validated_before_comparison(tmp_path):
    base = run_benchmark("passthrough")
    cases = fixtures()
    reference = tmp_path / "reference.json"
    reference.write_text(json.dumps({
        "baselines": base["baselines"],
        "fixture_sha256": {name: hashlib.sha256(text.encode()).hexdigest() for name, text, _ in cases},
        "outputs": {name: text for name, text, _ in cases},
    }), encoding="utf-8")
    report = run_benchmark("upstream", reference=reference, model="gpt-4o")
    assert report["status"] == "completed"
    assert all(item["required_facts_preserved"] for item in report["cases"])
    assert all(item["estimator"].startswith("tiktoken:") for item in report["cases"])
    altered = json.loads(reference.read_text())
    altered["baselines"]["rtk"] = "wrong"
    reference.write_text(json.dumps(altered), encoding="utf-8")
    import pytest
    with pytest.raises(ValueError, match="baseline"):
        run_benchmark("upstream", reference=reference)


def test_inventory_does_not_claim_unreviewed_variants_complete():
    report = capability_report()
    assert report["discovered_command_variants"] > 100
    assert report["reviewed_command_contracts"] >= 10
    assert report["total_core_capabilities"] >= 30
    assert report["summary"]["implemented_unverified"] > 0
    assert report["summary"]["upstream_parity_passed"] == 0
    assert not report["parity_certified"]


def test_missing_source_evidence_downgrades_claims(tmp_path):
    report = capability_report(tmp_path)
    assert report["summary"]["not_implemented"] == report["total_core_capabilities"]


def test_latest_report_write_is_atomic_and_metadata_only(tmp_path):
    report = run_benchmark("native", model="gpt-4o")
    path = save_report(report, home=tmp_path)
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["status"] == "completed"
    assert not list(path.parent.glob("*.tmp"))
    assert all("content" not in case for case in stored["cases"])
    assert report["parity_certified"] is False


def test_four_route_matrix_keeps_missing_upstream_explicit():
    report = run_benchmark_matrix()

    assert report["status"] == "incomplete"
    assert report["route_order"] == ["passthrough", "prototype", "upstream", "native"]
    assert report["routes"]["upstream"]["status"] == "unavailable"
    assert report["live_model_calls"] == 0
    assert all(case["routes"]["upstream"]["status"] == "unavailable" for case in report["cases"])


def test_four_route_matrix_aligns_validated_reference(tmp_path):
    passthrough = run_benchmark("passthrough")
    fixture_rows = fixtures()
    reference = tmp_path / "reference.json"
    reference.write_text(json.dumps({
        "baselines": passthrough["baselines"],
        "fixture_sha256": {
            name: hashlib.sha256(content.encode("utf-8")).hexdigest()
            for name, content, _required in fixture_rows
        },
        "outputs": {name: content for name, content, _required in fixture_rows},
        "suite_scope": "input-compression",
        "coverage": {"headroom": len(fixture_rows), "rtk": 0, "caveman": 0},
        "generator": "test-fixed-upstream",
    }), encoding="utf-8")

    report = run_benchmark_matrix(reference=reference)

    assert report["status"] == "completed"
    assert report["live_model_calls"] == 0
    assert all(set(case["routes"]) == set(report["route_order"]) for case in report["cases"])
    assert all(case["routes"]["upstream"]["required_facts_preserved"] for case in report["cases"])


def test_native_route_rejects_recovery_marker_token_regression():
    report = run_benchmark("native")
    unknown = next(case for case in report["cases"] if case["case"] == "unknown-format")

    assert unknown["after_tokens"] <= unknown["before_tokens"]


def test_checked_in_four_route_evidence_is_complete_and_metadata_only():
    report = json.loads(
        Path("docs/evidence/four-route-matrix-20260920.json").read_text(encoding="utf-8")
    )

    assert report["status"] == "completed"
    assert report["route_order"] == ["passthrough", "prototype", "upstream", "native"]
    assert report["live_model_calls"] == 0
    assert report["baselines"] == {
        "headroom": "bc21c9370793f7e4aa94ac4c5d9a67a8d2dd0df9",
        "rtk": "0924356b4caba4989607227b7c8824d3d8098719",
        "caveman": "542442bab314973709f95b85b1ac0b3f6f5b5dc6",
    }
    assert len(report["cases"]) == len(fixtures())
    assert all(
        route["required_facts_preserved"]
        for case in report["cases"]
        for route in case["routes"].values()
    )
    unknown = next(case for case in report["cases"] if case["case"] == "unknown-format")
    assert unknown["routes"]["native"]["after_tokens"] <= unknown["routes"]["native"]["before_tokens"]

    def keys(value):
        if isinstance(value, dict):
            return set(value).union(*(keys(item) for item in value.values()))
        if isinstance(value, list):
            return set().union(*(keys(item) for item in value)) if value else set()
        return set()

    assert not {"original", "content", "outputs"}.intersection(keys(report))
