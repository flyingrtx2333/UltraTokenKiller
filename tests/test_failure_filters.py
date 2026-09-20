import json

from ultratokenkiller.tool_filters import command_filter, compress_tool


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


def test_new_test_and_lint_commands_use_specific_filters():
    assert command_filter(["bun", "test"]) == "bun-test"
    assert command_filter(["deno", "test"]) == "deno-test"
    assert command_filter(["gradlew", "testDebugUnitTest"]) == "gradle-test"
    assert command_filter(["golangci-lint", "run"]) == "golangci"


def test_specific_filters_leave_structured_verbose_and_watch_modes_alone():
    assert command_filter(["bun", "test", "--watch"]) is None
    assert command_filter(["deno", "test", "--reporter=junit"]) is None
    assert command_filter(["gradlew", "test", "--stacktrace"]) is None
    assert command_filter(["golangci-lint", "run", "--output.json.path=report.json"]) is None


def test_bun_failure_keeps_failures_causes_and_summary():
    raw = """bun test v1.2.20
1 | noisy source
error: expect(received).toBe(expected)
Expected: 3
Received: 2
at <anonymous> (/work/fails.test.ts:3:40)
✗ t2 fails [0.13ms]
2 pass
4 fail
Ran 6 tests across 1 file.
"""
    result = compress_tool(raw, "bun-test")
    assert "t2 fails" in result
    assert "Expected: 3" in result
    assert "Received: 2" in result
    assert "4 fail" in result
    assert "noisy source" not in result


def test_deno_failure_strips_ansi_and_keeps_diff_and_counts():
    raw = """plain assertion \x1b[31mFAILED\x1b[0m
plain assertion \x1b[38;5;245m=> ./fails_test.ts:2:6\x1b[0m
\x1b[31merror\x1b[0m: AssertionError: Values are not equal.
[Diff] Actual / Expected
-   1
+   2
\x1b[31mFAILED\x1b[0m | 3 passed | 2 failed (15ms)
"""
    result = compress_tool(raw, "deno-test")
    assert "plain assertion => ./fails_test.ts:2:6" in result
    assert "Values are not equal" in result
    assert "-   1" in result and "+   2" in result
    assert "3 passed | 2 failed" in result
    assert "\x1b[" not in result


def test_gradle_failure_keeps_user_frames_and_summary():
    raw = """> Task :app:test
com.example.CalculatorTest > subtract FAILED
    java.lang.AssertionError: expected:<3> but was:<-1>
        at org.junit.Assert.fail(Assert.java:89)
        at com.example.CalculatorTest.subtract(CalculatorTest.kt:25)
5 tests completed, 2 failed
BUILD FAILED in 22s
"""
    result = compress_tool(raw, "gradle-test")
    assert "subtract FAILED" in result
    assert "expected:<3> but was:<-1>" in result
    assert "CalculatorTest.subtract" in result
    assert "5 tests completed, 2 failed" in result
    assert "BUILD FAILED" in result
    assert "org.junit" not in result


def test_golangci_json_groups_issues_without_report_catalog():
    raw = json.dumps({
        "Issues": [
            {"FromLinter": "errcheck", "SourceLines": ["defer f.Close()"], "Pos": {"Filename": "main.go"}},
            {"FromLinter": "errcheck", "SourceLines": ["defer f.Close()"], "Pos": {"Filename": "main.go"}},
            {"FromLinter": "ineffassign", "SourceLines": ["v := 1"], "Pos": {"Filename": "util.go"}},
        ],
        "Report": {"Linters": [{"Name": f"linter-{index}"} for index in range(100)]},
    })
    result = compress_tool(raw, "golangci")
    assert "3 issues in 2 files" in result
    assert "errcheck (2x)" in result
    assert "main.go (2 issues)" in result
    assert "defer f.Close()" in result
    assert "linter-99" not in result


def test_new_specific_filters_pass_unknown_formats_through():
    for kind in ("bun-test", "deno-test", "gradle-test", "golangci"):
        raw = "unrecognized output\n"
        assert compress_tool(raw, kind) == raw


def test_git_diff_keeps_every_changed_line_and_location():
    raw = """diff --git a/main.rs b/main.rs
index 1111111..2222222 100644
--- a/main.rs
+++ b/main.rs
@@ -1,4 +1,4 @@
 fn main() {
-    println!("old");
+    println!("new");
 }
diff --git a/notes.md b/notes.md
index 3333333..4444444 100644
--- a/notes.md
+++ b/notes.md
@@ -1,2 +1,3 @@
 heading
+++ can also be content
"""
    result = compress_tool(raw, "diff")
    assert "main.rs" in result and "notes.md" in result
    assert "@@ -1,4 +1,4 @@" in result
    assert '-    println!("old");' in result
    assert '+    println!("new");' in result
    assert "+++ can also be content" in result
    assert "index 1111111" not in result
