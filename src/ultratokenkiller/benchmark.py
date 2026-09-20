"""Offline evidence runner. No network or model calls are implicit."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import time
import tempfile
from importlib.resources import files
from pathlib import Path

from .compression import compress_content
from .engines import estimate_tokens
from .recovery import RecoveryVault
from .token_count import count_text
from .config import default_home


def fixtures():
    return [
        ("json-outlier", json.dumps([{"id": i, "value": 9000 if i == 50 else 10} for i in range(100)]), ["9000"]),
        ("log-failure", "\n".join("ERROR do not delete record 778" if i == 50 else f"INFO processing request {i}" for i in range(100)), ["ERROR do not delete record 778"]),
        ("python-signature", "def total(value: int) -> int:\n"+"    value += 1\n"*100+"    return value\n", ["def total(value: int) -> int:"]),
        ("search-location", "\n".join(f"src/very/long/path/source.py:{i}:symbol_{i}" for i in range(100)), ["99", "symbol_99"]),
        ("prose-negation", "Do not delete /data/patient.json. The limit is 73 requests.\n"*50, ["Do not", "/data/patient.json", "73"]),
        ("patch-change", "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1,101 +1,101 @@\n"+" context\n"*100+"-unsafe\n+safe\n", ["-unsafe", "+safe", "@@ -1,101 +1,101 @@"]),
        ("unicode-log", "\n".join([f"INFO 请求 {i} 完成" for i in range(80)] + ["ERROR 不得删除 病历-73.json"]), ["ERROR", "不得删除", "病历-73.json"]),
        ("unknown-format", "opaque record | preserve=all | code=73\n" * 4, ["preserve=all", "code=73"]),
        ("json-minority", json.dumps([{"state": "ready", "enabled": True}] * 60 + [{"state": "blocked", "enabled": False}]), ["blocked", "false"]),
        ("log-trace", "INFO ok\n" * 40 + "Traceback (most recent call last):\n  File \"worker.py\", line 73\nValueError: must not retry\n" + "INFO ok\n" * 40, ["worker.py", "73", "must not retry"]),
        ("typescript-signature", "export async function calculate(value: number): Promise<number> {\n" + "  value += 1;\n" * 100 + "  return value;\n}\n", ["calculate", "Promise<number>"]),
        ("long-identifier", "Do not rename CustomerAuthorizationRevocationHandler_v2. Limit: 128 MiB.\n" * 40, ["Do not", "CustomerAuthorizationRevocationHandler_v2", "128 MiB"]),
    ]


def fixture_options(name):
    return {
        "prose-negation": {"query": "patient data deletion limit"},
        "typescript-signature": {"hint": "code:typescript", "query": "calculate function signature"},
        "long-identifier": {"query": "CustomerAuthorizationRevocationHandler_v2 limit"},
    }.get(name, {})


def _reference_outputs(reference, cases, baselines):
    path = Path(reference or os.environ.get("UTK_REFERENCE_RESULTS", ""))
    if not path.is_file():
        return None, "Set --reference to a validated fixed-baseline result file", None
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("baselines") != baselines:
        raise ValueError("Reference result baseline does not match the frozen commits")
    outputs = data.get("outputs")
    if not isinstance(outputs, dict):
        raise ValueError("Reference result requires an outputs object")
    expected = {name: hashlib.sha256(original.encode()).hexdigest() for name, original, _ in cases}
    if data.get("fixture_sha256") != expected or set(outputs) != set(expected):
        raise ValueError("Reference fixtures differ from this benchmark revision")
    if not all(isinstance(value, str) for value in outputs.values()):
        raise ValueError("Reference outputs must be text")
    metadata = {
        "suite_scope": data.get("suite_scope", "legacy-unspecified"),
        "coverage": data.get("coverage"),
        "generator": data.get("generator", "legacy-manual"),
    }
    return outputs, None, metadata


def run_benchmark(mode="native", *, reference=None, model=None):
    if mode not in {"passthrough", "prototype", "native", "upstream"}:
        raise ValueError("Unknown benchmark mode")
    cases = fixtures()
    lock = json.loads(files("ultratokenkiller").joinpath("data/upstream-lock.json").read_text(encoding="utf-8"))
    baselines = {key: value["commit"] for key, value in lock.items()}
    reference_outputs = None
    reference_metadata = None
    if mode == "upstream":
        reference_outputs, reason, reference_metadata = _reference_outputs(reference, cases, baselines)
        if reference_outputs is None:
            return {"schema_version": 2, "mode": mode, "status": "unavailable",
                    "reason": reason, "baselines": baselines, "cases": [], "live_model_calls": 0,
                    "parity_certified": False}
    if mode == "prototype":
        from .baselines.native_v1 import compress_request
    reports = []
    for name, original, required in cases:
        digest = hashlib.sha256(name.encode("utf-8")).digest()[:16]
        stable_handle = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
        vault = RecoveryVault(handle_factory=lambda value=stable_handle: value)
        start = time.perf_counter()
        metadata = {}
        restored = True
        if mode == "native":
            result = compress_content(original, session="benchmark", vault=vault, **fixture_options(name))
            rendered = result.content
            metadata = result.metadata()
            if result.recovery_id:
                restored = vault.retrieve("benchmark", result.recovery_id, limit=64000)["content"] == original
        elif mode == "prototype":
            payload, _ = compress_request({"input": [{"type": "function_call_output", "output": original},
                                                      {"type": "function_call_output", "output": "latest"}]})
            rendered = payload["input"][0]["output"]
        elif mode == "upstream":
            rendered = reference_outputs[name]
        else:
            rendered = original
        before_count, after_count = count_text(original, model), count_text(rendered, model)
        before, after = before_count.value, after_count.value
        reports.append({"case": name, "fixture_sha256": hashlib.sha256(original.encode()).hexdigest(),
                        "before_tokens": before, "after_tokens": after, "reduction": (before-after)/before if before else 0,
                        "required_facts_preserved": all(value in rendered for value in required),
                        "recoverable": restored, "duration_ms": (time.perf_counter()-start)*1000,
                        "engine": metadata, "estimator": before_count.method,
                        "exact_for_model": before_count.exact_for_model})
    return {"schema_version": 2, "mode": mode, "status": "completed", "cases": reports,
            "baselines": baselines, "model": model, "live_model_calls": 0,
            "parity_certified": False, "reference": reference_metadata}


def save_report(report: dict, kind="compression", home=None) -> Path:
    if kind not in {"compression", "response"}:
        raise ValueError("Unknown benchmark report kind")
    root = Path(home or default_home()) / "reports"
    root.mkdir(parents=True, exist_ok=True)
    target = root / f"{kind}-latest.json"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=root, suffix=".tmp", delete=False) as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        temporary = Path(handle.name)
    try:
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return target


def capability_report(root=None):
    from .capabilities import capability_report as report
    return report(root)
