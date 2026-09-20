"""Generate a fixed-upstream reference package in an isolated subprocess.

The current fixture suite exercises Headroom-style input compression. RTK and
Caveman checkouts are verified and recorded, but receive zero cases until their
dedicated captured-output and paired-response suites land. This distinction is
part of the result so a completed package cannot be mistaken for three-layer
parity.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from importlib.resources import files
from pathlib import Path
from typing import Any

from .benchmark import fixtures


_HEADROOM_CHILD = r"""
import json
import sys
import hashlib
import importlib.metadata

import headroom
import headroom._core as headroom_core
from headroom import compress

payload = json.load(sys.stdin)
outputs = {}
engines = {}
for case in payload["cases"]:
    result = compress(
        [{"role": "user", "content": case["content"]}],
        model="gpt-4o",
        compress_user_messages=True,
        protect_recent=0,
        protect_analysis_context=False,
        min_tokens_to_compress=1,
        kompress_model="disabled",
    )
    content = result.messages[0].get("content", case["content"])
    if not isinstance(content, str):
        raise TypeError(f"Headroom returned non-text content for {case['name']}")
    outputs[case["name"]] = content
    engines[case["name"]] = {
        "component": "headroom",
        "tokens_before": result.tokens_before,
        "tokens_after": result.tokens_after,
        "transforms": list(result.transforms_applied),
    }
def digest(path):
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()

json.dump({
    "outputs": outputs,
    "engines": engines,
    "runtime": {
        "version": importlib.metadata.version("headroom-ai"),
        "python_module_sha256": digest(headroom.__file__),
        "native_module_sha256": digest(headroom_core.__file__),
    },
}, sys.stdout, ensure_ascii=False)
"""


def _lock() -> dict[str, dict[str, Any]]:
    return json.loads(
        files("ultratokenkiller").joinpath("data/upstream-lock.json").read_text(encoding="utf-8")
    )


def _git_head(path: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError(f"Reference checkout is not a readable Git repository: {path}")
    return result.stdout.strip()


def verify_checkouts(checkouts: dict[str, Path]) -> dict[str, str]:
    lock = _lock()
    expected_names = set(lock)
    if set(checkouts) != expected_names:
        raise ValueError(f"Reference checkouts must be exactly: {', '.join(sorted(expected_names))}")
    heads: dict[str, str] = {}
    for name in sorted(expected_names):
        path = Path(checkouts[name]).resolve()
        if not path.is_dir():
            raise ValueError(f"Missing {name} reference checkout: {path}")
        head = _git_head(path)
        expected = lock[name]["commit"]
        if head != expected:
            raise ValueError(f"{name} checkout is {head}, expected frozen commit {expected}")
        heads[name] = head
    return heads


def _headroom_outputs(checkout: Path, python: Path) -> dict[str, Any]:
    cases = [{"name": name, "content": content} for name, content, _ in fixtures()]
    result = subprocess.run(
        [str(python), "-I", "-X", "utf8", "-c", _HEADROOM_CHILD, str(checkout.resolve())],
        input=json.dumps({"cases": cases}, ensure_ascii=False),
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "PYTHONUTF8": "1"},
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()[-2000:]
        raise RuntimeError(f"Frozen Headroom runner failed: {detail}")
    try:
        data = json.loads(result.stdout)
    except ValueError as exc:
        raise RuntimeError("Frozen Headroom runner returned invalid JSON") from exc
    names = {name for name, _, _ in fixtures()}
    if set(data.get("outputs", {})) != names or set(data.get("engines", {})) != names:
        raise RuntimeError("Frozen Headroom runner returned an incomplete fixture set")
    try:
        import tomllib
    except ImportError:  # pragma: no cover - Python 3.10
        import tomli as tomllib
    project = tomllib.loads((checkout / "pyproject.toml").read_text(encoding="utf-8"))
    expected_version = project["project"]["version"]
    runtime = data.get("runtime", {})
    if runtime.get("version") != expected_version:
        raise RuntimeError(
            f"Headroom runtime is {runtime.get('version')}, expected checkout version {expected_version}"
        )
    if not all(runtime.get(key) for key in ("python_module_sha256", "native_module_sha256")):
        raise RuntimeError("Frozen Headroom runtime fingerprints are incomplete")
    return data


def generate_reference(
    *,
    headroom: Path,
    rtk: Path,
    caveman: Path,
    output: Path,
    python: Path | None = None,
) -> dict[str, Any]:
    """Run the deterministic input suite and atomically write its result package."""
    checkouts = {"headroom": Path(headroom), "rtk": Path(rtk), "caveman": Path(caveman)}
    heads = verify_checkouts(checkouts)
    runner = Path(python or sys.executable)
    if not runner.is_file():
        raise ValueError(f"Reference Python does not exist: {runner}")
    headroom_result = _headroom_outputs(checkouts["headroom"], runner)
    case_hashes = {
        name: hashlib.sha256(content.encode("utf-8")).hexdigest()
        for name, content, _ in fixtures()
    }
    result: dict[str, Any] = {
        "schema_version": 1,
        "generator": "utk-fixed-upstream-reference",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "suite_scope": "input-compression",
        "baselines": heads,
        "fixture_sha256": case_hashes,
        "outputs": headroom_result["outputs"],
        "engines": headroom_result["engines"],
        "runtime": {"headroom": headroom_result["runtime"]},
        "coverage": {"headroom": len(case_hashes), "rtk": 0, "caveman": 0},
        "live_model_calls": 0,
        "notes": [
            "RTK captured-output parity is not part of this input fixture suite.",
            "Caveman paired-response parity is not part of this input fixture suite.",
            "Headroom local ML compression is disabled; deterministic native transforms remain enabled.",
        ],
    }
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=output.parent, suffix=".tmp", delete=False
    ) as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temporary = Path(handle.name)
    try:
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    return result
