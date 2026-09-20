import json
from pathlib import Path

from ultratokenkiller.rtk_reference import CASES, compare_rtk_reference


def test_comparison_uses_captured_output_without_executing_commands(tmp_path: Path):
    records = {}
    for case in CASES:
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
    assert all(item["exit_code"] != 0 for item in report["cases"])
