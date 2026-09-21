"""Build the fixed-version Headroom, RTK and Caveman parity denominator."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "src" / "ultratokenkiller" / "data"
OUTPUT = DATA / "full-parity-inventory.json"
DOCUMENT = ROOT / "docs" / "full-capability-parity-2026-09-21.md"


def load(name: str):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def upstream_url(repository: str, commit: str, path: str) -> str:
    return f"https://github.com/{repository}/blob/{commit}/{path}"


def headroom_items(manifest: list[dict], lock: dict) -> list[dict]:
    fixture_map = {
        "input.routing": ["all fixed input fixtures"],
        "input.json": ["json-outlier", "json-minority"],
        "input.table": ["unknown-format"],
        "input.logs": ["log-failure", "unicode-log", "log-trace"],
        "input.code.python": ["python-signature"],
        "input.code.multilanguage": ["typescript-signature"],
        "input.diff": ["patch-change"],
        "input.search": ["search-location"],
        "input.long_text_en": ["prose-negation", "long-identifier"],
    }
    result = []
    for row in (item for item in manifest if item["upstream"] == "headroom"):
        fixtures = fixture_map.get(row["id"], [])
        parity_status = "fixed_upstream_sample_passed" if fixtures else "not_individually_compared"
        if row["id"] == "benchmark.fixed_upstream":
            parity_status = "fixed_upstream_suite_passed"
        source = row["source"]
        result.append({
            "id": f"headroom.{row['id']}",
            "upstream": "headroom",
            "kind": "core_capability",
            "category": row["layer"],
            "capability": row["id"],
            "variant": None,
            "core": True,
            "platforms": ["windows", "macos", "linux"],
            "upstream_evidence": [{
                "commit": lock["commit"],
                "path": source,
                "url": upstream_url(lock["repository"], lock["commit"], source),
            }],
            "utk_implementation": row["implementation"],
            "utk_tests": row["tests"],
            "implementation_status": row["verification"],
            "parity_status": parity_status,
            "parity_evidence": (
                ["docs/evidence/four-route-matrix-20260920.json", *fixtures]
                if fixtures or row["id"] == "benchmark.fixed_upstream" else []
            ),
            "gap": None if parity_status != "not_individually_compared" else "Needs a fixed-upstream item-level comparison",
        })
    return result


def rtk_items(inventory: list[dict], lock: dict) -> list[dict]:
    result = []
    success_samples = {
        "tools.Commands.Read",
        "tools.Commands.Json",
        "tools.Commands.Smart",
        "tools.Commands.Grep",
        "tools.Commands.Rg",
    }
    behavior_windows = {"tools.Commands.Ls", "tools.Commands.Tree"}
    success_failure_windows = {"tools.Commands.Find"}
    for row in inventory:
        mapped = row.get("status") == "contract_mapped"
        success_sampled = row["id"] in success_samples
        behavior_sampled = row["id"] in behavior_windows
        success_failure_sampled = row["id"] in success_failure_windows
        result.append({
            "id": f"rtk.{row['id']}",
            "upstream": "rtk",
            "kind": "command_variant",
            "category": row["family"],
            "capability": " ".join(row["command_path"]),
            "variant": row["id"],
            "parameters": row["parameters"],
            "output_formats": row["output_formats"],
            "core": row["disposition"] == "core",
            "platforms": row["platforms"],
            "upstream_evidence": [{
                "commit": lock["commit"],
                "path": row["source"],
                "line": row["source_line"],
                "url": row["source_url"],
            }],
            "utk_contracts": row["contract_ids"],
            "implementation_status": "contract_mapped" if mapped else "unverified",
            "parity_status": (
                "fixed_upstream_success_only" if success_sampled
                else "fixed_upstream_behavior_suite_windows" if behavior_sampled
                else "fixed_upstream_success_failure_windows" if success_failure_sampled
                else "pending_fixed_upstream_variant_evidence"
            ),
            "parity_evidence": (
                ["docs/evidence/upstream-rtk-comparison-20260920.json"]
                if success_sampled or behavior_sampled or success_failure_sampled else []
            ),
            "gap": (
                "Success sample passed; fixed-upstream failure, unknown-format and applicable-platform evidence remain"
                if success_sampled
                else "Fixed-upstream success, failure and unknown-format samples passed on Windows; macOS and Linux evidence remain"
                if behavior_sampled
                else "Fixed-upstream success and failure samples passed on Windows; unknown-format, macOS and Linux evidence remain"
                if success_failure_sampled
                else "Mapped contract still needs success, failure and unknown-format fixed-upstream evidence"
                if mapped
                else "Needs a dedicated contract plus success, failure and unknown-format evidence"
            ),
        })
    return result


def caveman_items(manifest: list[dict], lock: dict) -> list[dict]:
    source = "plugins/caveman/skills/caveman/SKILL.md"
    evidence = [{
        "commit": lock["commit"],
        "path": source,
        "url": upstream_url(lock["repository"], lock["commit"], source),
    }]
    implementation = next(item for item in manifest if item["id"] == "response.modes")
    quality = next(item for item in manifest if item["id"] == "response.paired_quality")
    result = []
    modes = ["off", "lite", "full", "ultra", "wenyan-lite", "wenyan-full", "wenyan-ultra"]
    for mode in modes:
        result.append({
            "id": f"caveman.mode.{mode}", "upstream": "caveman", "kind": "response_mode",
            "category": "mode", "capability": mode, "variant": mode, "core": True,
            "platforms": ["windows", "macos", "linux"], "upstream_evidence": evidence,
            "utk_implementation": implementation["implementation"], "utk_tests": implementation["tests"],
            "implementation_status": implementation["verification"],
            "parity_status": "fixed_upstream_policy_passed",
            "parity_evidence": ["docs/evidence/upstream-caveman-policy-reference-20260920.json"],
            "gap": None,
        })
    rules = [
        "facts-and-errors", "negations-and-numbers", "language-preservation", "safety-clarity",
        "detail-override", "no-invented-abbreviations", "never-grow",
    ]
    for rule in rules:
        result.append({
            "id": f"caveman.rule.{rule}", "upstream": "caveman", "kind": "preservation_rule",
            "category": "rule", "capability": rule, "variant": None, "core": True,
            "platforms": ["windows", "macos", "linux"], "upstream_evidence": evidence,
            "utk_implementation": implementation["implementation"], "utk_tests": implementation["tests"],
            "implementation_status": implementation["verification"],
            "parity_status": "fixed_upstream_policy_passed",
            "parity_evidence": ["docs/evidence/upstream-caveman-policy-reference-20260920.json"],
            "gap": None,
        })
    corpus = load("response-quality-corpus.json")
    for scenario in corpus["scenarios"]:
        result.append({
            "id": f"caveman.quality.{scenario['id']}", "upstream": "caveman",
            "kind": "paired_quality_scenario", "category": "quality", "capability": scenario["kind"],
            "variant": None, "required_facts": scenario["required_facts"], "core": True,
            "platforms": ["windows", "macos", "linux"], "upstream_evidence": evidence,
            "utk_implementation": quality["implementation"], "utk_tests": quality["tests"],
            "implementation_status": quality["verification"],
            "parity_status": "authorization_required",
            "parity_evidence": ["docs/evidence/response-quality-budget-20260920.json"],
            "gap": "Needs authorized paired model responses for every active mode and three repetitions",
        })
    for bypass in corpus["structured_bypass"]:
        result.append({
            "id": f"caveman.bypass.{bypass['id']}", "upstream": "caveman",
            "kind": "structured_bypass", "category": "structured_output", "capability": bypass["kind"],
            "variant": None, "core": True, "platforms": ["windows", "macos", "linux"],
            "upstream_evidence": evidence, "utk_implementation": implementation["implementation"],
            "utk_tests": implementation["tests"], "implementation_status": implementation["verification"],
            "parity_status": "offline_passed",
            "parity_evidence": implementation["tests"], "gap": None,
        })
    return result


def exclusions(locks: dict) -> list[dict]:
    return [
        {"id": "headroom.hosted-service", "upstream": "headroom", "reason": "Cloud accounts and hosted control plane are outside the single-user local core scope"},
        {"id": "rtk.release-infrastructure", "upstream": "rtk", "reason": "Project CI, release automation and maintainer tooling are not runtime token-compression capabilities"},
        {"id": "caveman.cloud-backend", "upstream": "caveman", "reason": "Cloud accounts, billing and team administration are outside the local core scope"},
        {"id": "caveman.workflow-discovery", "upstream": "caveman", "reason": "Cross-workflow spend discovery is an ecosystem feature, not response compression"},
        {"id": "caveman.experiment-management", "upstream": "caveman", "reason": "Remote experiment lifecycle management is outside the fixed response-policy core"},
        {"id": "caveman.cost-analytics", "upstream": "caveman", "reason": "Hosted cost analytics is outside local response compression and quality evaluation"},
    ]


def render_markdown(payload: dict) -> str:
    lines = [
        "# UTK fixed-version full capability parity inventory", "",
        "Generated from machine-readable upstream evidence. Implementation status and fixed-upstream parity status are separate; passthrough never counts as parity.", "",
        "## Denominator", "",
        "| Upstream | Core items | Implementation states | Parity states |",
        "|---|---:|---|---|",
    ]
    for upstream in ("headroom", "rtk", "caveman"):
        rows = [item for item in payload["items"] if item["upstream"] == upstream]
        impl = Counter(item["implementation_status"] for item in rows)
        parity = Counter(item["parity_status"] for item in rows)
        lines.append(f"| {upstream.title()} | {len(rows)} | {dict(sorted(impl.items()))} | {dict(sorted(parity.items()))} |")
    lines += ["", f"Total core denominator: **{len(payload['items'])}**", "", "## Items", "",
              "| ID | Category | Capability | Implementation | Fixed-upstream parity | Gap |", "|---|---|---|---|---|---|"]
    for item in payload["items"]:
        gap = (item.get("gap") or "—").replace("|", "/")
        capability = str(item["capability"]).replace("|", "/")
        lines.append(f"| `{item['id']}` | {item['category']} | `{capability}` | {item['implementation_status']} | {item['parity_status']} | {gap} |")
    lines += ["", "## Explicit ecosystem exclusions", "", "| ID | Upstream | Reason |", "|---|---|---|"]
    for item in payload["ecosystem_exclusions"]:
        lines.append(f"| `{item['id']}` | {item['upstream']} | {item['reason']} |")
    return "\n".join(lines) + "\n"


def generate() -> dict:
    locks = load("upstream-lock.json")
    manifest = load("capability-manifest.json")
    items = [
        *headroom_items(manifest, locks["headroom"]),
        *rtk_items(load("command-inventory.json"), locks["rtk"]),
        *caveman_items(manifest, locks["caveman"]),
    ]
    payload = {
        "schema_version": 1,
        "fixed_commits": {name: value["commit"] for name, value in locks.items()},
        "core_denominator": len(items),
        "items": items,
        "ecosystem_exclusions": exclusions(locks),
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    DOCUMENT.write_text(render_markdown(payload), encoding="utf-8")
    return payload


if __name__ == "__main__":
    report = generate()
    counts = Counter(item["upstream"] for item in report["items"])
    print(f"wrote {OUTPUT} and {DOCUMENT}: {dict(sorted(counts.items()))}")
