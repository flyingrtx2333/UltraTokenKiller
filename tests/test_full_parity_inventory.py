import json
from collections import Counter
from pathlib import Path

from scripts.generate_full_parity_inventory import generate
from ultratokenkiller.capabilities import capability_report


def test_full_parity_inventory_has_fixed_complete_denominator():
    report = generate()
    items = report["items"]

    assert report["core_denominator"] == 256
    assert len(items) == len({item["id"] for item in items})
    assert Counter(item["upstream"] for item in items) == {
        "headroom": 24,
        "rtk": 211,
        "caveman": 21,
    }
    assert all(item["core"] for item in items)
    assert all(item["upstream_evidence"] for item in items)
    assert all(item["implementation_status"] for item in items)
    assert all(item["parity_status"] for item in items)


def test_rtk_mapping_does_not_claim_variant_parity():
    report = json.loads(
        Path("src/ultratokenkiller/data/full-parity-inventory.json").read_text(encoding="utf-8")
    )
    rtk = [item for item in report["items"] if item["upstream"] == "rtk"]

    assert Counter(item["implementation_status"] for item in rtk) == {
        "contract_mapped": 60,
        "unverified": 151,
    }
    assert Counter(item["parity_status"] for item in rtk) == {
        "pending_fixed_upstream_variant_evidence": 197,
        "fixed_upstream_success_only": 11,
        "fixed_upstream_behavior_suite_windows": 2,
        "fixed_upstream_success_failure_windows": 1,
    }


def test_caveman_inventory_separates_policy_and_live_quality():
    report = json.loads(
        Path("src/ultratokenkiller/data/full-parity-inventory.json").read_text(encoding="utf-8")
    )
    caveman = [item for item in report["items"] if item["upstream"] == "caveman"]

    assert len([item for item in caveman if item["kind"] == "response_mode"]) == 7
    assert len([item for item in caveman if item["kind"] == "preservation_rule"]) == 7
    assert len([item for item in caveman if item["kind"] == "paired_quality_scenario"]) == 5
    assert len([item for item in caveman if item["kind"] == "structured_bypass"]) == 2
    assert all(
        item["parity_status"] == "authorization_required"
        for item in caveman if item["kind"] == "paired_quality_scenario"
    )


def test_exclusions_are_explicit_and_not_in_denominator():
    report = json.loads(
        Path("src/ultratokenkiller/data/full-parity-inventory.json").read_text(encoding="utf-8")
    )

    assert len(report["ecosystem_exclusions"]) == 6
    assert not {item["id"] for item in report["items"]}.intersection(
        item["id"] for item in report["ecosystem_exclusions"]
    )


def test_capability_report_exposes_full_parity_without_inflating_completion():
    report = capability_report(Path.cwd())

    assert report["full_parity_denominator"] == 256
    assert report["full_parity_upstream_counts"] == {
        "caveman": 21,
        "headroom": 24,
        "rtk": 211,
    }
    assert len(report["full_parity_inventory"]) == 256
    assert len(report["ecosystem_exclusions"]) == 6
    assert report["full_parity_implementation_counts"]["rtk"] == {
        "contract_mapped": 60,
        "unverified": 151,
    }
    assert report["full_parity_status_counts"]["rtk"] == {
        "fixed_upstream_success_only": 11,
        "fixed_upstream_behavior_suite_windows": 2,
        "fixed_upstream_success_failure_windows": 1,
        "pending_fixed_upstream_variant_evidence": 197,
    }
    assert report["full_parity_status_counts"]["caveman"]["authorization_required"] == 5
    assert report["full_parity_status_counts"]["headroom"] == {
        "fixed_upstream_sample_passed": 9,
        "fixed_upstream_suite_passed": 1,
        "not_individually_compared": 14,
    }
    assert "contract_mapped and passthrough do not count" in report["full_parity_note"]
