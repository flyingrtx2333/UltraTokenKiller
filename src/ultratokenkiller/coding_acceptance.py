"""Small real Git/code/test task. Only synthetic source files persist on disk."""
from __future__ import annotations
import hashlib
import os
from pathlib import Path
import subprocess
import sys


def git(root, *arguments):
    return subprocess.run(["git", "-C", str(root), "-c", "core.autocrlf=false", "-c", "core.hooksPath=" + str(root / ".hooks"),
        *arguments], capture_output=True, check=True, encoding="utf-8", timeout=20).stdout


def run_tests(root):
    return subprocess.run([sys.executable, "-m", "pytest", "-q", "--confcutdir", str(root), "test_calculator.py"],
        cwd=root, env={**os.environ, "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}, capture_output=True,
        encoding="utf-8", errors="replace", timeout=30)


def prepare(root: Path):
    root.mkdir(parents=True, exist_ok=False)
    (root / ".hooks").mkdir()
    source = "# UTK_RECOVERY_PROOF\n" + "".join(
        f"# Contract note {i}: keep ceil_div API and tests unchanged.\n"
        for i in range(220))
    source += ('\ndef ceil_div(numerator: int, denominator: int) -> int:\n'
               '    """Return the smallest integer >= numerator / denominator. Denominator must be positive."""\n'
               '    if denominator <= 0:\n'
               '        raise ValueError("denominator must be positive")\n'
               '    return numerator // denominator\n')
    test = ('import pytest\nfrom calculator import ceil_div\n'
            '@pytest.mark.parametrize("n,d,expected", [(5,2,3),(0,3,0),(-5,2,-2),(6,2,3),(17,5,4)])\n'
            'def test_ceiling(n,d,expected):\n    assert ceil_div(n,d) == expected\n'
            '@pytest.mark.parametrize("d", [0,-1])\n'
            'def test_invalid_denominator(d):\n    with pytest.raises(ValueError):\n        ceil_div(5,d)\n')
    (root / "calculator.py").write_text(source, encoding="utf-8")
    (root / "test_calculator.py").write_text(test, encoding="utf-8")
    (root / ".gitignore").write_text("__pycache__/\n.pytest_cache/\n", encoding="utf-8")
    git(root, "-c", "init.templateDir=", "init", "-q")
    git(root, "add", "calculator.py", "test_calculator.py", ".gitignore")
    git(root, "-c", "user.name=UTK acceptance", "-c", "user.email=utk@example.invalid",
        "commit", "--no-gpg-sign", "-qm", "Acceptance fixture")
    baseline = run_tests(root)
    if baseline.returncode != 1 or "3 failed, 4 passed" not in baseline.stdout:
        raise RuntimeError("Coding fixture baseline did not fail as expected; no model request permitted")
    return {"source_hash": hashlib.sha256((root / "calculator.py").read_bytes()).hexdigest(),
            "test_hash": hashlib.sha256((root / "test_calculator.py").read_bytes()).hexdigest(),
            "baseline_failed": 3, "baseline_passed": 4}


def verify(root, baseline):
    source = hashlib.sha256((root / "calculator.py").read_bytes()).hexdigest()
    tests = hashlib.sha256((root / "test_calculator.py").read_bytes()).hexdigest()
    status = git(root, "status", "--porcelain").splitlines()
    result = run_tests(root)
    checks = {"source_changed": source != baseline["source_hash"],
              "tests_unchanged": tests == baseline["test_hash"],
              "only_target_changed": status == [" M calculator.py"],
              "tests_exit_code": result.returncode,
              "seven_tests_passed": result.returncode == 0 and "7 passed" in result.stdout}
    checks["passed"] = all(checks[key] for key in ("source_changed", "tests_unchanged", "only_target_changed", "seven_tests_passed"))
    return checks


def prompt():
    return (
        "Fix calculator.py so ceil_div follows its documented mathematical ceiling contract, preserving its API and denominator validation. "
        "Do not edit tests or any other file. You have exactly three tool rounds and then a final answer. "
        "Round 1: one shell call with exactly: grep -n -H . calculator.py\n"
        "Use the raw command; the installed UTK hook wraps it automatically. "
        "Round 2: call utk_retrieve with the handle from the result, offset 0, limit 16000. Read the recovered source. "
        "Round 3: ONE shell call containing a script that edits calculator.py, runs python -m pytest -q, "
        "and then runs git diff -- calculator.py. Do not use apply_patch or split this script into separate tool calls. "
        "After the tests pass and the diff shows only the intended fix, answer exactly UTK_REAL_RECOVERY_OK. "
        "If a step fails, report it and stop. Do not explore other files, spawn agents, or change model."
    )
