"""Offline evidence runner. No network or model calls are implicit."""
from __future__ import annotations

import hashlib
import json
import time
from importlib.resources import files

from .compression import compress_content
from .engines import estimate_tokens
from .recovery import RecoveryVault


def fixtures():
    return [
        ("json-outlier", json.dumps([{"id": i, "value": 9000 if i == 50 else 10} for i in range(100)]), ["9000"]),
        ("log-failure", "\n".join("ERROR do not delete record 778" if i == 50 else f"INFO processing request {i}" for i in range(100)), ["ERROR do not delete record 778"]),
        ("python-signature", "def total(value: int) -> int:\n"+"    value += 1\n"*100+"    return value\n", ["def total(value: int) -> int:"]),
        ("search-location", "\n".join(f"src/very/long/path/source.py:{i}:symbol_{i}" for i in range(100)), ["99", "symbol_99"]),
        ("prose-negation", "Do not delete /data/patient.json. The limit is 73 requests.\n"*50, ["Do not", "/data/patient.json", "73"]),
        ("patch-change", "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1,101 +1,101 @@\n"+" context\n"*100+"-unsafe\n+safe\n", ["-unsafe", "+safe", "@@ -1,101 +1,101 @@"]),
    ]


def run_benchmark(mode="native"):
    if mode not in {"passthrough", "prototype", "native", "upstream"}:
        raise ValueError("Unknown benchmark mode")
    if mode == "upstream":
        return {"schema_version": 1, "mode": mode, "status": "not_run",
                "reason": "Isolated pinned upstream reference runner has not been validated", "cases": []}
    if mode == "prototype":
        from .baselines.native_v1 import compress_request
    reports = []
    for name, original, required in fixtures():
        vault = RecoveryVault()
        start = time.perf_counter()
        metadata = {}
        restored = True
        if mode == "native":
            result = compress_content(original, session="benchmark", vault=vault)
            rendered = result.content
            metadata = result.metadata()
            if result.recovery_id:
                restored = vault.retrieve("benchmark", result.recovery_id, limit=64000)["content"] == original
        elif mode == "prototype":
            payload, _ = compress_request({"input": [{"type": "function_call_output", "output": original},
                                                      {"type": "function_call_output", "output": "latest"}]})
            rendered = payload["input"][0]["output"]
        else:
            rendered = original
        before, after = estimate_tokens(original), estimate_tokens(rendered)
        reports.append({"case": name, "fixture_sha256": hashlib.sha256(original.encode()).hexdigest(),
                        "before_tokens": before, "after_tokens": after, "reduction": (before-after)/before if before else 0,
                        "required_facts_preserved": all(value in rendered for value in required),
                        "recoverable": restored, "duration_ms": (time.perf_counter()-start)*1000,
                        "engine": metadata, "estimator": "utf8_bytes_div_4"})
    return {"schema_version": 1, "mode": mode, "status": "completed", "cases": reports,
            "live_model_calls": 0, "parity_certified": False}


def capability_report():
    data = files("ultratokenkiller").joinpath("data")
    inventory = json.loads(data.joinpath("command-inventory.json").read_text(encoding="utf-8"))
    lock = json.loads(data.joinpath("upstream-lock.json").read_text(encoding="utf-8"))
    return {"schema_version": 1, "baselines": {k: v["commit"] for k, v in lock.items()},
            "discovered_command_variants": len(inventory), "reviewed_command_variants": 0,
            "parity_certified": False, "command_inventory": inventory,
            "input": {name: {"implemented": name not in {"image"},
                              "limitations": "English encoder, verified local assets and query required" if name == "text-model" else "",
                              "upstream_comparison": "not_run"}
                      for name in ["json", "log", "python", "javascript", "typescript", "go", "rust", "java", "c", "cpp", "perl", "diff", "search", "text-model", "image"]}}
