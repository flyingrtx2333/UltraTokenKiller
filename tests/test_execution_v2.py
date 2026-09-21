import sys
import subprocess

from ultratokenkiller.processes import execute, execute_channels
from ultratokenkiller.runtime import _git_add_summary
from ultratokenkiller.tool_filters import command_filter, compress_tool


def test_memory_overflow_streams_every_byte_without_disk():
    output = []
    code, captured, fallback = execute([sys.executable, "-c", "import sys; sys.stdout.buffer.write(b'x'*200000)"], capture=True, write=output.append, memory_limit=1000)
    assert code == 0
    assert captured is None
    assert fallback == "memory_limit_passthrough"
    assert b"".join(output) == b"x"*200000


def test_binary_and_exit_code_preserved():
    code, captured, fallback = execute([sys.executable, "-c", "import sys; sys.stdout.buffer.write(b'\\xff\\x00'); sys.exit(17)"], capture=True, write=lambda _: None)
    assert code == 17
    assert captured == b"\xff\x00"


def test_channel_capture_preserves_stdout_stderr_and_exit_code():
    code, stdout, stderr, fallback = execute_channels(
        [sys.executable, "-c", "import sys; print('result'); print('diagnostic', file=sys.stderr); sys.exit(9)"],
        capture=True,
        write_stdout=lambda _: None,
        write_stderr=lambda _: None,
    )
    assert code == 9
    assert stdout.strip() == b"result"
    assert stderr.strip() == b"diagnostic"
    assert fallback is None


def test_channel_memory_overflow_streams_each_channel_without_loss():
    stdout_parts = []
    stderr_parts = []
    code, stdout, stderr, fallback = execute_channels(
        [sys.executable, "-c", "import sys; sys.stdout.write('o'*2000); sys.stdout.flush(); sys.stderr.write('e'*2000)"],
        capture=True,
        write_stdout=stdout_parts.append,
        write_stderr=stderr_parts.append,
        memory_limit=1000,
    )
    assert code == 0
    assert stdout is None and stderr is None
    assert fallback == "memory_limit_passthrough"
    assert b"".join(stdout_parts) == b"o" * 2000
    assert b"".join(stderr_parts) == b"e" * 2000


def test_git_add_summary_reads_staged_state_without_repeating_add(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    source = tmp_path / "guard.txt"
    source.write_text("do not remove\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "guard.txt"], check=True)
    summary = _git_add_summary(["git", "-C", str(tmp_path), "add", "guard.txt"])
    assert summary.startswith(b"ok 1 file changed")
    assert b"1 insertion(+)" in summary


def test_machine_flags_and_unknown_formats_passthrough():
    assert command_filter(["git", "diff", "--binary"]) is None
    assert command_filter(["git", "log", "--format=json"]) is None
    assert command_filter(["rg", "--json", "x"]) is None
    assert command_filter(["git", "status"]) == "git-status"
    assert compress_tool("unrecognized format", "git-status") == "unrecognized format"


def test_success_summary_and_distinct_errors():
    output = "================ test session starts ================\ntest_one.py ................\n================ 16 passed in 1.0s ================\n"
    result = compress_tool(output, "pytest")
    assert "16 passed in 1.0s" in result
    assert len(result) < len(output)
    failure = "ERROR missing secret: do not retry\nfailed test: a\n"
    assert compress_tool(failure, "pytest") == failure
