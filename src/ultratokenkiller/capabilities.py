"""Evidence-backed capability inventory for the frozen parity target."""
from __future__ import annotations

import json
import hashlib
from collections import Counter
from importlib.resources import files
from pathlib import Path


STATES = ("not_implemented", "implemented_unverified", "offline_passed",
          "real_client_passed", "upstream_parity_passed")


def _exists(root: Path, value: str) -> bool:
    return (root / value).is_file()


def _fingerprint_bytes(path: Path) -> bytes:
    """Return Git-text-stable bytes for cross-platform evidence hashes."""
    return path.read_bytes().replace(b"\r\n", b"\n")


def _source_fingerprint(root: Path, item: dict, upstream_commit: str) -> str | None:
    """Bind a verification result to the exact implementation and tests."""
    paths = [*item.get("implementation", []),
             *(value.split("::", 1)[0] for value in item.get("tests", []))]
    if not paths or not all((root / value).is_file() for value in paths):
        return None
    digest = hashlib.sha256()
    digest.update(upstream_commit.encode("ascii"))
    digest.update(json.dumps(item, ensure_ascii=False, sort_keys=True).encode("utf-8"))
    for value in sorted(set(paths)):
        digest.update(value.replace("\\", "/").encode("utf-8"))
        digest.update(_fingerprint_bytes(root / value))
    return digest.hexdigest()


def _contract_fingerprint(root: Path, contract: dict) -> str | None:
    paths = ["src/ultratokenkiller/tool_filters.py", "src/ultratokenkiller/processes.py",
             *contract.get("implementation", []),
             *contract.get("tests", [])]
    if not contract.get("reviewed") or not all((root / value).is_file() for value in paths):
        return None
    digest = hashlib.sha256(json.dumps(contract, sort_keys=True).encode("utf-8"))
    for value in sorted(set(paths)):
        digest.update(value.encode("utf-8"))
        digest.update(_fingerprint_bytes(root / value))
    return digest.hexdigest()


def _load_ledger(project: Path | None, data) -> dict:
    if project is not None:
        path = project / "src" / "ultratokenkiller" / "data" / "verification-ledger.json"
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    try:
        return json.loads(data.joinpath("verification-ledger.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"schema_version": 1, "suite_passed": False, "capabilities": {}}


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
    full_inventory = json.loads(
        data.joinpath("full-parity-inventory.json").read_text(encoding="utf-8")
    )
    ledger = _load_ledger(project, data)
    ledger_items = ledger.get("capabilities", {}) if isinstance(ledger, dict) else {}
    ledger_contracts = ledger.get("command_contracts", {}) if isinstance(ledger, dict) else {}
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
        fingerprint = (_source_fingerprint(project, item, lock[item["upstream"]]["commit"])
                       if project is not None else ledger_items.get(identifier, {}).get("source_fingerprint"))
        ledger_entry = ledger_items.get(identifier, {})
        offline_current = bool(ledger.get("suite_passed")) and bool(ledger_entry.get("offline_passed")) and bool(fingerprint) and ledger_entry.get("source_fingerprint") == fingerprint
        evidence_bound = bool(evidence_present and fingerprint and
                              ledger_entry.get("real_client_source_fingerprint") == fingerprint)
        upstream_bound = bool(evidence_present and fingerprint and
                              ledger_entry.get("upstream_source_fingerprint") == fingerprint)
        state = intended
        if not code_present:
            state = "not_implemented"
        elif STATES.index(state) >= STATES.index("offline_passed") and (not tests_present or not offline_current):
            state = "implemented_unverified"
        elif STATES.index(state) >= STATES.index("real_client_passed") and not evidence_bound:
            state = "offline_passed"
        elif state == "upstream_parity_passed" and not upstream_bound:
            state = "real_client_passed"
        entry = dict(item)
        upstream = lock[item["upstream"]]
        source = item["source"]
        entry["source_url"] = (f"https://github.com/{upstream['repository']}/blob/{upstream['commit']}/{source}"
                               if not source.startswith("http") else source)
        entry.setdefault("input", "Capability-specific protocol or command input")
        entry.setdefault("exceptions", ["Unknown or low-confidence format passes through unchanged"])
        entry.setdefault("platforms", ["windows", "macos", "linux"])
        entry.update(status=state, code_present=code_present, tests_present=tests_present,
                     evidence_present=evidence_present, source_fingerprint=fingerprint,
                     offline_verification_current=offline_current,
                     real_client_evidence_bound=evidence_bound,
                     upstream_evidence_bound=upstream_bound,
                     verification_stale=(intended in STATES[2:] and state != intended))
        entry.pop("verification", None)
        rendered.append(entry)
    counts = Counter(item["status"] for item in rendered)
    rendered_contracts = []
    for contract in contracts:
        entry = dict(contract)
        fingerprint = (_contract_fingerprint(project, contract) if project is not None
                       else ledger_contracts.get(contract["id"], {}).get("source_fingerprint"))
        current = bool(ledger.get("suite_passed") and fingerprint and
                       ledger_contracts.get(contract["id"], {}).get("source_fingerprint") == fingerprint)
        entry.update(source_fingerprint=fingerprint, verification_current=current,
                     evidence_status="offline_passed" if current else "implemented_unverified")
        rendered_contracts.append(entry)
    reviewed = [item for item in rendered_contracts if item.get("reviewed")]
    parity = bool(rendered) and all(item["status"] == "upstream_parity_passed" for item in rendered)
    inventory_core = [item for item in discovered if item.get("disposition") == "core"]
    inventory_status_counts = Counter(item.get("status", "unverified") for item in inventory_core)
    full_items = full_inventory["items"]
    full_upstream_counts = Counter(item["upstream"] for item in full_items)
    full_implementation_counts = {
        upstream: dict(sorted(Counter(
            item["implementation_status"] for item in full_items
            if item["upstream"] == upstream
        ).items()))
        for upstream in sorted(full_upstream_counts)
    }
    full_parity_status_counts = {
        upstream: dict(sorted(Counter(
            item["parity_status"] for item in full_items
            if item["upstream"] == upstream
        ).items()))
        for upstream in sorted(full_upstream_counts)
    }
    return {
        "schema_version": 3,
        "baselines": {key: value["commit"] for key, value in lock.items()},
        "summary": {state: counts.get(state, 0) for state in STATES},
        "total_core_capabilities": len(rendered),
        "discovered_command_variants": len(discovered),
        "command_inventory_coverage_denominator": len(inventory_core),
        "command_inventory_status_counts": dict(sorted(inventory_status_counts.items())),
        "command_inventory_exclusions": len(discovered) - len(inventory_core),
        "reviewed_command_contracts": len(reviewed),
        "verified_command_contracts": sum(item["verification_current"] for item in rendered_contracts),
        "command_contract_coverage_denominator": None,
        "command_inventory_note": "All frozen RTK variants are in the coverage denominator; only evidence-bound reviewed contracts count as verified",
        "full_parity_denominator": full_inventory["core_denominator"],
        "full_parity_upstream_counts": dict(sorted(full_upstream_counts.items())),
        "full_parity_implementation_counts": full_implementation_counts,
        "full_parity_status_counts": full_parity_status_counts,
        "full_parity_inventory": full_items,
        "ecosystem_exclusions": full_inventory["ecosystem_exclusions"],
        "full_parity_note": (
            "Implementation status and fixed-upstream parity status are independent; "
            "contract_mapped and passthrough do not count as parity passed"
        ),
        "upstream_comparisons_missing": sum(item["status"] != "upstream_parity_passed" for item in rendered),
        "command_inventory": discovered,
        "command_contracts": rendered_contracts,
        "capabilities": rendered,
        "parity_certified": parity,
        "verification": {
            "ledger_present": bool(ledger_items),
            "suite_passed": bool(ledger.get("suite_passed")),
            "generated_at": ledger.get("generated_at"),
            "source_bound_capabilities": sum(item["offline_verification_current"] for item in rendered),
            "real_client_source_bound": sum(item["real_client_evidence_bound"] for item in rendered),
            "stale_capabilities": [item["id"] for item in rendered if item["verification_stale"]],
        },
    }
