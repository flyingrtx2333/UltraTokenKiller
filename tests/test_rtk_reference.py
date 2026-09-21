import json
from pathlib import Path

from ultratokenkiller.rtk_reference import CASES, compare_rtk_reference


def test_comparison_uses_captured_output_without_executing_commands(tmp_path: Path):
    records = {}
    for case in CASES:
        if case["kind"].startswith("native-"):
            raw = (
                Path("tests/fixtures/rtk_reference") / case["fixture"]
            ).read_text(encoding="utf-8")
        else:
            raw = "\n".join(case["required"]) + "\n" + ("noise\n" * 100)
        records[case["id"]] = {
            "raw": raw,
            "output": "\n".join(case["required"]),
            "exit_code": case["exit_code"],
            "raw_sha256": "fixture",
        }
    path = tmp_path / "reference.json"
    path.write_text(
        json.dumps({"baseline": "fixed", "cases": records}),
        encoding="utf-8",
    )

    report = compare_rtk_reference(path)

    assert report["case_count"] == len(CASES)
    assert report["live_model_calls"] == 0
    assert all(item["required_facts_upstream"] for item in report["cases"])
    assert {item["case"]: item["exit_code"] for item in report["cases"]} == {
        case["id"]: case["exit_code"] for case in CASES
    }


def test_git_add_reference_uses_captured_probe_and_one_fixed_execution():
    case = next(case for case in CASES if case["id"] == "git-add-success")

    assert case["fixture"] == "git_add_success_raw.txt"
    assert case["setup_git_repo"] is True
    assert case["setup_git_add"] is True
    assert case["captured_raw_only"] is True
    assert case["argv"] == ["git", "add", "tracked.txt"]
