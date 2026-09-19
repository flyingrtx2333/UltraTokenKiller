import sys

from ultratokenkiller.processes import execute
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
