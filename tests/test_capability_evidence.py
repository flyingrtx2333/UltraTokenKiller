from pathlib import Path

from ultratokenkiller.capabilities import _contract_fingerprint, _source_fingerprint, capability_report


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
    assert report["schema_version"] == 3
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
