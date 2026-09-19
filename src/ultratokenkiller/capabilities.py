"""Evidence-backed capability inventory for the frozen parity target."""
from __future__ import annotations

import json
from collections import Counter
from importlib.resources import files
from pathlib import Path


STATES = ("not_implemented", "implemented_unverified", "offline_passed",
          "real_client_passed", "upstream_parity_passed")


def _exists(root: Path, value: str) -> bool:
    return (root / value).is_file()


def capability_report(root: Path | None = None) -> dict:
    """Return only claims whose implementation and evidence still exist.

    The manifest states the intended verification level. Missing code, tests or
    evidence automatically downgrade a claim instead of leaving a stale badge.
    """
    candidate = Path(__file__).resolve().parents[2]
    project = root or (candidate if (candidate / "pyproject.toml").is_file() else None)
    data = files("ultratokenkiller").joinpath("data")
    lock = json.loads(data.joinpath("upstream-lock.json").read_text(encoding="utf-8"))
    manifest = json.loads(data.joinpath("capability-manifest.json").read_text(encoding="utf-8"))
    discovered = json.loads(data.joinpath("command-inventory.json").read_text(encoding="utf-8"))
    contracts = json.loads(data.joinpath("tool-contracts.json").read_text(encoding="utf-8"))
    seen: set[str] = set()
    rendered = []
    for item in manifest:
        identifier = item["id"]
        if identifier in seen:
            raise ValueError(f"Duplicate capability id: {identifier}")
        seen.add(identifier)
        intended = item["verification"]
        if intended not in STATES:
            raise ValueError(f"Unknown capability state: {intended}")
        implementation = item.get("implementation", [])
        tests = item.get("tests", [])
        evidence = item.get("evidence", [])
        code_present = bool(implementation) and (project is None or all(_exists(project, value) for value in implementation))
        tests_present = bool(tests) and (project is None or all(_exists(project, value.split("::", 1)[0]) for value in tests))
        evidence_present = bool(evidence) and (project is None or all(_exists(project, value) for value in evidence))
        state = intended
        if not code_present:
            state = "not_implemented"
        elif STATES.index(state) >= STATES.index("offline_passed") and not tests_present:
            state = "implemented_unverified"
        elif STATES.index(state) >= STATES.index("real_client_passed") and not evidence_present:
            state = "offline_passed"
        entry = dict(item)
        upstream = lock[item["upstream"]]
        source = item["source"]
        entry["source_url"] = (f"https://github.com/{upstream['repository']}/blob/{upstream['commit']}/{source}"
                               if not source.startswith("http") else source)
        entry.setdefault("input", "Capability-specific protocol or command input")
        entry.setdefault("exceptions", ["Unknown or low-confidence format passes through unchanged"])
        entry.setdefault("platforms", ["windows", "macos", "linux"])
        entry.update(status=state, code_present=code_present, tests_present=tests_present,
                     evidence_present=evidence_present)
        entry.pop("verification", None)
        rendered.append(entry)
    counts = Counter(item["status"] for item in rendered)
    reviewed = [item for item in contracts if item.get("reviewed")]
    parity = bool(rendered) and all(item["status"] == "upstream_parity_passed" for item in rendered)
    return {
        "schema_version": 2,
        "baselines": {key: value["commit"] for key, value in lock.items()},
        "summary": {state: counts.get(state, 0) for state in STATES},
        "total_core_capabilities": len(rendered),
        "discovered_command_variants": len(discovered),
        "reviewed_command_contracts": len(reviewed),
        "command_contract_coverage_denominator": None,
        "command_inventory_note": "Discovery enums and reviewed behavior contracts have different granularity; no percentage is claimed",
        "upstream_comparisons_missing": sum(item["status"] != "upstream_parity_passed" for item in rendered),
        "command_inventory": discovered,
        "command_contracts": contracts,
        "capabilities": rendered,
        "parity_certified": parity,
    }
