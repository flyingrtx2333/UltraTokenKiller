"""Run fixed RTK filters against captured, read-only command output."""
from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .reference_runner import _lock, _git_head
from .token_count import count_text
from .tool_filters import compress_tool


CASES = (
    {
        "id": "pytest-failure",
        "fixture": "uv_run_pytest_failure.txt",
        "program": "pytest",
        "argv": ["pytest"],
        "kind": "pytest",
        "exit_code": 1,
        "required": ["test_normalize_user_rejects_empty", "AssertionError", "1 failed"],
    },
    {
        "id": "typescript-pretty-errors",
        "fixture": "tsc_pretty_raw.txt",
        "program": "tsc",
        "argv": ["tsc"],
        "kind": "diagnostics",
        "exit_code": 2,
        "required": ["src/index.ts", "TS2322", "3 errors"],
    },
    {
        "id": "maven-test-failure",
        "fixture": "mvn_test_fail_slice_raw.txt",
        "program": "mvn",
        "argv": ["mvn", "test"],
        "kind": "generic-test",
        "exit_code": 1,
        "required": ["RtkInducedFailTest", "expected", "BUILD FAILURE"],
    },
)


def _write_emitter(directory: Path, program: str, fixture: Path, exit_code: int) -> None:
    if os.name == "nt":
        target = directory / f"{program}.cmd"
        target.write_text(f'@type "{fixture}"\r\n@exit /b {exit_code}\r\n', encoding="utf-8")
        return
    target = directory / program
    target.write_text(
        f"#!/bin/sh\ncat '{fixture}'\nexit {exit_code}\n",
        encoding="utf-8",
    )
    target.chmod(target.stat().st_mode | stat.S_IXUSR)


def _run_case(binary: Path, checkout: Path, case: dict[str, Any]) -> dict[str, Any]:
    fixture = checkout / "tests" / "fixtures" / case["fixture"]
    if not fixture.is_file():
        raise ValueError(f"Missing frozen RTK fixture: {case['fixture']}")
    raw = fixture.read_text(encoding="utf-8", errors="replace")
    with tempfile.TemporaryDirectory(prefix="utk-rtk-reference-") as temporary:
        root = Path(temporary)
        _write_emitter(root, case["program"], fixture.resolve(), case["exit_code"])
        env = {
            **os.environ,
            "PATH": str(root) + os.pathsep + os.environ.get("PATH", ""),
            "HOME": str(root),
            "APPDATA": str(root / "appdata"),
            "LOCALAPPDATA": str(root / "localappdata"),
            "RTK_TEE": "0",
            "NO_COLOR": "1",
        }
        process = subprocess.run(
            [str(binary), *case["argv"]],
            cwd=root,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
    rendered = process.stdout.strip() or process.stderr.strip()
    if not rendered:
        raise RuntimeError(f"Frozen RTK returned no output for {case['id']}")
    return {
        "raw": raw,
        "output": rendered,
        "exit_code": process.returncode,
        "raw_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
    }


def generate_rtk_reference(*, checkout: Path, binary: Path, output: Path) -> dict[str, Any]:
    checkout = Path(checkout).resolve()
    binary = Path(binary).resolve()
    expected = _lock()["rtk"]["commit"]
    head = _git_head(checkout)
    if head != expected:
        raise ValueError(f"rtk checkout is {head}, expected frozen commit {expected}")
    if not binary.is_file():
        raise ValueError(f"Missing fixed RTK binary: {binary}")
    records = {case["id"]: _run_case(binary, checkout, case) for case in CASES}
    result = {
        "schema_version": 1,
        "generator": "utk-fixed-rtk-captured-output",
        "baseline": expected,
        "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
        "live_model_calls": 0,
        "external_write_commands": 0,
        "cases": records,
    }
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".tmp")
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, output)
    return result


def compare_rtk_reference(reference: Path, model: str = "gpt-5.6-luna") -> dict[str, Any]:
    data = json.loads(Path(reference).read_text(encoding="utf-8"))
    cases_by_id = {case["id"]: case for case in CASES}
    reports = []
    for case_id, record in data["cases"].items():
        case = cases_by_id[case_id]
        raw = record["raw"]
        upstream = record["output"]
        native = compress_tool(raw, case["kind"])
        before = count_text(raw, model).value
        upstream_after = count_text(upstream, model).value
        native_after = count_text(native, model).value
        upstream_reduction = (before - upstream_after) / before if before else 0.0
        native_reduction = (before - native_after) / before if before else 0.0
        reports.append(
            {
                "case": case_id,
                "kind": case["kind"],
                "required_facts_upstream": all(value in upstream for value in case["required"]),
                "required_facts_utk": all(value in native for value in case["required"]),
                "upstream_reduction": upstream_reduction,
                "utk_reduction": native_reduction,
                "ratio": native_reduction / upstream_reduction if upstream_reduction > 0 else None,
                "exit_code": record["exit_code"],
            }
        )
    return {
        "schema_version": 1,
        "baseline": data["baseline"],
        "model": model,
        "case_count": len(reports),
        "live_model_calls": 0,
        "cases": reports,
    }
