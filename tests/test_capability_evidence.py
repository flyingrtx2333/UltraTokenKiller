from pathlib import Path

from ultratokenkiller.capabilities import (
    FULL_PARITY_STATES,
    _contract_fingerprint,
    _evidence_records,
    _full_item_fingerprint,
    _full_verification_status,
    _source_fingerprint,
    capability_report,
)


def test_source_fingerprint_changes_with_implementation(tmp_path):
    implementation = tmp_path / "src" / "feature.py"
    test = tmp_path / "tests" / "test_feature.py"
    implementation.parent.mkdir(parents=True)
    test.parent.mkdir(parents=True)
    implementation.write_text("VALUE = 1\n", encoding="utf-8")
    test.write_text("def test_value(): pass\n", encoding="utf-8")
    item = {"id": "feature", "implementation": ["src/feature.py"],
            "tests": ["tests/test_feature.py"], "verification": "offline_passed"}
    first = _source_fingerprint(tmp_path, item, "fixed-upstream")
    implementation.write_text("VALUE = 2\n", encoding="utf-8")
    assert first != _source_fingerprint(tmp_path, item, "fixed-upstream")


def test_capability_report_exposes_verification_binding():
    report = capability_report()
    assert report["schema_version"] == 4
    assert set(report["verification"]) >= {
        "ledger_present", "suite_passed", "source_bound_capabilities",
        "real_client_source_bound", "stale_capabilities",
    }
    assert all("offline_verification_current" in item for item in report["capabilities"])
    assert all("verification_current" in item for item in report["command_contracts"])


def test_contract_fingerprint_requires_reviewed_tests(tmp_path):
    (tmp_path / "src" / "ultratokenkiller").mkdir(parents=True)
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "ultratokenkiller" / "tool_filters.py").write_text("FILTER = 1\n")
    (tmp_path / "src" / "ultratokenkiller" / "processes.py").write_text("PROCESS = 1\n")
    (tmp_path / "tests" / "test_tool.py").write_text("def test_tool(): pass\n")
    contract = {"id": "tool", "reviewed": True, "tests": ["tests/test_tool.py"]}
    assert _contract_fingerprint(tmp_path, contract)
    contract["reviewed"] = False
    assert _contract_fingerprint(tmp_path, contract) is None


def test_evidence_fingerprints_are_stable_across_git_line_endings(tmp_path):
    implementation = tmp_path / "src" / "feature.py"
    test = tmp_path / "tests" / "test_feature.py"
    implementation.parent.mkdir(parents=True)
    test.parent.mkdir(parents=True)
    implementation.write_bytes(b"VALUE = 1\n")
    test.write_bytes(b"def test_value(): pass\n")
    item = {"id": "feature", "implementation": ["src/feature.py"],
            "tests": ["tests/test_feature.py"], "verification": "offline_passed"}
    lf_fingerprint = _source_fingerprint(tmp_path, item, "fixed-upstream")

    implementation.write_bytes(b"VALUE = 1\r\n")
    test.write_bytes(b"def test_value(): pass\r\n")

    assert _source_fingerprint(tmp_path, item, "fixed-upstream") == lf_fingerprint


def test_full_parity_items_share_one_evidence_bound_status_source():
    report = capability_report()

    assert report["schema_version"] == 4
    assert sum(report["full_parity_verification_summary"].values()) == 256
    assert set(report["full_parity_verification_summary"]) == set(FULL_PARITY_STATES)
    for item in report["full_parity_inventory"]:
        assert item["verification_status"] in FULL_PARITY_STATES
        assert len(item["source_fingerprint"] or "") in {0, 64}
        assert isinstance(item["source_current"], bool)
        assert isinstance(item["evidence_hashes"], list)
        assert isinstance(item["evidence_present"], bool)
        assert isinstance(item["evidence_current"], bool)
        assert isinstance(item["asset_ready"], bool)


def test_full_item_fingerprint_and_evidence_hash_change_with_source(tmp_path):
    implementation = tmp_path / "src" / "feature.py"
    test = tmp_path / "tests" / "test_feature.py"
    evidence = tmp_path / "docs" / "evidence.json"
    implementation.parent.mkdir(parents=True)
    test.parent.mkdir(parents=True)
    evidence.parent.mkdir(parents=True)
    implementation.write_text("VALUE = 1\n", encoding="utf-8")
    test.write_text("def test_value(): pass\n", encoding="utf-8")
    evidence.write_text('{"passed": true}\n', encoding="utf-8")
    item = {
        "id": "headroom.test.feature",
        "utk_implementation": ["src/feature.py"],
        "utk_tests": ["tests/test_feature.py"],
        "parity_evidence": ["docs/evidence.json"],
    }

    first = _full_item_fingerprint(tmp_path, item, "fixed-upstream")
    evidence_first = _evidence_records(tmp_path, item["parity_evidence"])
    implementation.write_text("VALUE = 2\n", encoding="utf-8")
    evidence.write_text('{"passed": false}\n', encoding="utf-8")

    assert first != _full_item_fingerprint(tmp_path, item, "fixed-upstream")
    assert evidence_first[0]["sha256"] != _evidence_records(
        tmp_path, item["parity_evidence"]
    )[0]["sha256"]


def test_full_status_requires_current_evidence_and_reports_missing_assets():
    item = {
        "implementation_status": "implemented",
        "parity_status": "fixed_upstream_suite_passed",
    }
    assert _full_verification_status(item, True, True, True, {}) == "fixed_upstream_full_passed"
    assert _full_verification_status(item, True, False, True, {}) == "offline_passed"
    assert _full_verification_status(item, True, True, False, {}) == "asset_not_ready"
