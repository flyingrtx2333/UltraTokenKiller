"""Execute each command once; compare compressors against the same captured bytes."""
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from ultratokenkiller.compression import compress_content
from ultratokenkiller.processes import execute
from ultratokenkiller.recovery import RecoveryVault
from ultratokenkiller.tool_filters import command_filter


@pytest.mark.skipif(not shutil.which("git"), reason="Git unavailable")
def test_actual_staged_git_diff_retains_changes_and_restores_once(tmp_path):
    def git(*args):
        return subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True)
    git("init", "-q")
    source = tmp_path / "example.py"
    lines = [f"# unchanged context {i}: preserve this detailed explanatory comment\n" for i in range(100)]
    source.write_text("".join(lines), encoding="utf-8")
    git("add", "example.py")
    git("-c", "user.name=UTK test", "-c", "user.email=utk@example.invalid", "commit", "-qm", "fixture")
    lines[50] = "threshold = 41  # do not round to 40\n"
    source.write_text("".join(lines), encoding="utf-8")
    git("add", "example.py")
    argv = ["git", "-C", str(tmp_path), "diff", "--cached", "--unified=100"]
    code, raw, fallback = execute(argv, capture=True, write=lambda _: pytest.fail("unexpected streaming"))
    assert code == 0 and fallback is None
    vault = RecoveryVault()
    result = compress_content(raw.decode("utf-8"), session="git", vault=vault, hint="tool:" + command_filter(argv))
    assert "+threshold = 41  # do not round to 40" in result.content
    assert result.saved_tokens > 0
    assert vault.retrieve("git", result.recovery_id)["content"].encode("utf-8") == raw


def test_actual_pytest_success_and_failure_keep_exit_semantics(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
    source = tmp_path / "test_fixture.py"
    source.write_text("import pytest\n@pytest.mark.parametrize('i', range(40))\ndef test_value(i):\n    assert i >= 0\n", encoding="utf-8")
    argv = [sys.executable, "-m", "pytest", "-v", "--color=no", "--confcutdir", str(tmp_path), str(source)]
    code, raw, _ = execute(argv, capture=True, write=lambda _: pytest.fail("unexpected streaming"))
    assert code == 0, raw.decode("utf-8", errors="replace")
    vault = RecoveryVault()
    result = compress_content(raw.decode("utf-8"), session="test", vault=vault, hint="tool:" + command_filter(argv))
    assert "40 passed" in result.content
    assert result.saved_tokens > 0
    assert vault.retrieve("test", result.recovery_id)["content"].encode("utf-8") == raw
    source.write_text("def test_failure():\n    assert 41 == 42, 'critical threshold mismatch'\n", encoding="utf-8")
    code, failed, _ = execute(argv, capture=True, write=lambda _: pytest.fail("unexpected streaming"))
    assert code == 1
    kept = compress_content(failed.decode("utf-8"), session="test", vault=vault, hint="tool:" + command_filter(argv))
    assert "critical threshold mismatch" in kept.content
    assert "41 == 42" in kept.content
