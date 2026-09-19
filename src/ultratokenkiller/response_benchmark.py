"""Offline paired response-quality evaluation; reports no response bodies."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .token_count import count_text


MODES = {"off", "lite", "full", "ultra", "wenyan-lite", "wenyan-full", "wenyan-ultra"}


def evaluate_pairs(path: Path, model: str | None = None) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    cases = data.get("cases") if isinstance(data, dict) else None
    if not isinstance(cases, list) or not cases:
        raise ValueError("Response comparison requires a non-empty cases array")
    results = []
    for case in cases:
        if not isinstance(case, dict) or case.get("mode") not in MODES:
            raise ValueError("Each response case requires a known mode")
        baseline, candidate = case.get("baseline"), case.get("candidate")
        required, forbidden = case.get("required", []), case.get("forbidden", [])
        if not all(isinstance(value, str) for value in [baseline, candidate, *required, *forbidden]):
            raise ValueError("Response bodies and facts must be strings")
        before, after = count_text(baseline, model), count_text(candidate, model)
        kept = all(value in candidate for value in required)
        avoided = not any(value in candidate for value in forbidden)
        results.append({
            "id": str(case.get("id") or hashlib.sha256(baseline.encode()).hexdigest()[:16]),
            "mode": case["mode"], "baseline_sha256": hashlib.sha256(baseline.encode()).hexdigest(),
            "candidate_sha256": hashlib.sha256(candidate.encode()).hexdigest(),
            "baseline_tokens": before.value, "candidate_tokens": after.value,
            "reduction": max(0, before.value - after.value) / before.value if before.value else 0,
            "required_facts_preserved": kept, "forbidden_claims_absent": avoided,
            "correct": kept and avoided, "estimator": before.method,
        })
    return {"schema_version": 1, "status": "completed", "model": model,
            "cases": results, "all_correct": all(item["correct"] for item in results),
            "bodies_persisted": False, "live_model_calls": 0}
