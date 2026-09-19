import subprocess
import sys
import time

import pytest

from ultratokenkiller.processes import run_owned


def test_owned_process_preserves_utf8_and_exit_code():
    code = "import sys; s=sys.stdin.buffer.read().decode('utf-8'); sys.stdout.buffer.write(s.encode('utf-8')); sys.stderr.write('diagnostic'); sys.exit(7)"
    result = run_owned([sys.executable, "-c", code], input="中文🪨", timeout=10)
    assert result.returncode == 7
    assert result.stdout == "中文🪨"
    assert result.stderr == "diagnostic"


def test_timeout_terminates_descendants_before_they_can_write(tmp_path):
    marker = tmp_path / "should-not-exist"
    child = f"import time,pathlib; time.sleep(2); pathlib.Path({str(marker)!r}).write_text('escaped')"
    parent = f"import subprocess,sys,time; subprocess.Popen([sys.executable,'-c',{child!r}]); print('started',flush=True); time.sleep(30)"
    with pytest.raises(subprocess.TimeoutExpired) as error:
        run_owned([sys.executable, "-c", parent], input="", timeout=0.7)
    assert "started" in error.value.output
    time.sleep(2)
    assert not marker.exists()
