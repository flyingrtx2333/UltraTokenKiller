import shutil

import pytest

from ultratokenkiller.coding_acceptance import prepare, prompt, verify


def test_prompt_uses_portable_search_command():
    assert "grep -n -H . calculator.py" in prompt()


@pytest.mark.skipif(not shutil.which("git"), reason="Git unavailable")
def test_fixture_is_large_enough_for_tool_output_compression(tmp_path):
    root = tmp_path / "task"
    prepare(root)
    source = (root / "calculator.py").read_text(encoding="utf-8")
    assert source.count("# Contract note ") == 220
    assert 12_000 <= len(source) <= 16_000
    raw_search = "".join(f"calculator.py:{i}:{line}\n" for i, line in enumerate(source.splitlines(), 1))
    assert len(raw_search) <= 32000
    assert "limit 32000" in prompt()


@pytest.mark.skipif(not shutil.which("git"), reason="Git unavailable")
def test_correct_fix_passes_but_test_tampering_does_not(tmp_path):
    root = tmp_path / "task"
    baseline = prepare(root)
    assert baseline["baseline_failed"] == 3
    path = root / "calculator.py"
    path.write_text(path.read_text(encoding="utf-8").replace("return numerator // denominator", "return -(-numerator // denominator)"), encoding="utf-8")
    assert verify(root, baseline)["passed"]
    tests = root / "test_calculator.py"
    tests.write_text(tests.read_text(encoding="utf-8") + "\n# tampered\n", encoding="utf-8")
    evidence = verify(root, baseline)
    assert not evidence["passed"]
    assert not evidence["tests_unchanged"]
