from ultratokenkiller.tool_filters import compress_tool


def test_pytest_failure_keeps_name_error_location_and_counts():
    raw = """=== test session starts ===
tests/test_users.py .F [100%]
______________________ test_rejects_empty ______________________
>       assert '' == 'anonymous'
E       AssertionError: assert '' == 'anonymous'
tests/test_users.py:10: AssertionError
FAILED tests/test_users.py::test_rejects_empty - AssertionError
=================== 1 failed, 1 passed in 0.01s ===================
"""
    result = compress_tool(raw, "pytest")
    assert "test_rejects_empty" in result
    assert "AssertionError" in result
    assert "tests/test_users.py:10" in result
    assert "1 failed, 1 passed" in result
    assert "test session starts" not in result


def test_typescript_pretty_diagnostics_drop_source_excerpts():
    raw = """src/index.ts:1:7 - error TS2322: Type 'string' is not assignable to type 'number'.
1 const value: number = 'bad';
        ~~~~~
src/index.ts:4:8 - error TS2322: Another mismatch.
Found 2 errors in the same file, starting at: src/index.ts:1
"""
    result = compress_tool(raw, "diagnostics")
    assert result.count("TS2322") == 2
    assert "Found 2 errors" in result
    assert "const value" not in result


def test_typescript_pretty_diagnostics_strip_ansi_before_parsing():
    raw = (
        "src/index.ts:1:7 - \x1b[91merror\x1b[0m\x1b[90m TS2322: \x1b[0mBad type.\n"
        "Found 1 error in src/index.ts:1\n"
    )
    result = compress_tool(raw, "diagnostics")
    assert "TS2322" in result
    assert "Found 1 error" in result
    assert "\x1b[" not in result


def test_maven_failure_keeps_test_cause_counts_and_build_status():
    raw = """[INFO] Scanning projects...
[ERROR] Tests run: 1, Failures: 1, Errors: 0, Skipped: 0 <<< FAILURE! -- in example.FailTest
[ERROR] example.FailTest.breaks -- Time elapsed: 0.1 s <<< FAILURE!
org.opentest4j.AssertionFailedError: expected: <1> but was: <2>
[ERROR] Failures:
[ERROR]   FailTest.breaks:25 expected: <1> but was: <2>
[ERROR] Tests run: 10, Failures: 1, Errors: 0, Skipped: 0
[INFO] BUILD FAILURE
[ERROR] Failed to execute goal plugin:test: There are test failures.
"""
    result = compress_tool(raw, "generic-test")
    assert "FailTest.breaks" in result
    assert "expected: <1>" in result
    assert "Tests run: 10" in result
    assert "BUILD FAILURE" in result
    assert "Scanning projects" not in result
