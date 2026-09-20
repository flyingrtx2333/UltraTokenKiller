import json
from pathlib import Path

from scripts.finalize_command_inventory import build_inventory
from ultratokenkiller.capabilities import capability_report


ROOT = Path(__file__).resolve().parents[1]


def _inputs():
    lock = json.loads((ROOT / "src/ultratokenkiller/data/upstream-lock.json").read_text(encoding="utf-8"))
    inventory = json.loads(
        (ROOT / "src/ultratokenkiller/data/command-inventory.json").read_text(encoding="utf-8")
    )
    contracts = json.loads(
        (ROOT / "src/ultratokenkiller/data/tool-contracts.json").read_text(encoding="utf-8")
    )
    return lock, inventory, contracts


def test_frozen_command_inventory_is_the_complete_review_denominator():
    lock, inventory, contracts = _inputs()

    rebuilt = build_inventory(lock, inventory, contracts)

    assert rebuilt == inventory
    assert len(inventory) == 211
    assert len({item["id"] for item in inventory}) == 211
    assert all(item["disposition"] == "core" for item in inventory)
    assert all(item["scope"] == "coverage_denominator" for item in inventory)
    assert all(item["source_url"].endswith(f"#L{item['source_line']}") for item in inventory)
    assert all(item["command_path"] for item in inventory)
    assert all(item["family"] for item in inventory)
    assert all(item["platforms"] == ["windows", "macos", "linux"] for item in inventory)


def test_nested_subcommand_parameters_are_preserved():
    lock, inventory, contracts = _inputs()
    rebuilt = build_inventory(lock, inventory, contracts)

    git = next(item for item in rebuilt if item["id"] == "tools.Commands.Git")
    assert git["command_path"] == ["git"]
    assert any(parameter["role"] == "subcommand" for parameter in git["parameters"])


def test_capability_report_exposes_the_final_command_denominator():
    report = capability_report(ROOT)

    assert report["discovered_command_variants"] == 211
    assert report["command_inventory_coverage_denominator"] == 211
    assert report["command_inventory_exclusions"] == 0
    assert sum(report["command_inventory_status_counts"].values()) == 211
    assert report["command_inventory_status_counts"]["unverified"] < 211
