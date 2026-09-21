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
        "id": "git-status-worktree",
        "fixture": None,
        "program": None,
        "argv": ["git", "status"],
        "raw_argv": ["git", "status"],
        "kind": "git-status",
        "exit_code": 0,
        "setup_git_repo": True,
        "required": ["main", "tracked.txt", "untracked.txt"],
    },
    {
        "id": "git-log-default",
        "fixture": None,
        "program": None,
        "argv": ["git", "log"],
        "raw_argv": ["git", "log"],
        "kind": "git-log",
        "exit_code": 0,
        "setup_git_repo": True,
        "required": ["preserve migration guard", "initial fixture"],
    },
    {
        "id": "git-commit-success",
        "fixture": "git_commit_success_raw.txt",
        "program": "git",
        "argv": ["git", "commit", "-m", "preserve migration guard"],
        "kind": "git-commit",
        "exit_code": 0,
        "required": ["a1b2c3d"],
    },
    {
        "id": "git-add-success",
        "fixture": "git_add_success_raw.txt",
        "program": "git",
        "argv": ["git", "add", "tracked.txt"],
        "kind": "git-add",
        "exit_code": 0,
        "setup_git_repo": True,
        "setup_git_add": True,
        "captured_raw_only": True,
        "required": ["1 file changed", "1 insertion"],
    },
    {
        "id": "git-commit-failure",
        "fixture": "git_commit_failure_raw.txt",
        "program": "git",
        "argv": ["git", "commit", "-m", "empty"],
        "kind": "git-commit",
        "exit_code": 1,
        "required": ["nothing to commit", "working tree clean"],
    },
    {
        "id": "git-pull-success",
        "fixture": "git_pull_success_raw.txt",
        "program": "git",
        "argv": ["git", "pull", "--ff-only"],
        "kind": "git-pull",
        "exit_code": 0,
        "required": ["3", "10", "2"],
    },
    {
        "id": "git-pull-failure",
        "fixture": "git_pull_failure_raw.txt",
        "program": "git",
        "argv": ["git", "pull", "--ff-only"],
        "kind": "git-pull",
        "exit_code": 1,
        "required": ["local changes", "src/main.py", "Aborting"],
    },
    {
        "id": "git-checkout-success",
        "fixture": "git_checkout_success_raw.txt",
        "program": "git",
        "argv": ["git", "checkout", "-b", "feature/migration"],
        "kind": "git-checkout",
        "exit_code": 0,
        "required": ["feature/migration", "new"],
    },
    {
        "id": "git-checkout-failure",
        "fixture": "git_checkout_failure_raw.txt",
        "program": "git",
        "argv": ["git", "checkout", "missing-branch"],
        "kind": "git-checkout",
        "exit_code": 1,
        "required": ["missing-branch", "pathspec"],
    },
    {
        "id": "git-push-success",
        "fixture": "git_push_success_raw.txt",
        "program": "git",
        "argv": ["git", "push", "origin", "main"],
        "kind": "git-push",
        "exit_code": 0,
        "fixture_stderr": True,
        "required": ["example.test/repo.git", "main", "ok"],
    },
    {
        "id": "git-push-failure",
        "fixture": "git_push_failure_raw.txt",
        "program": "git",
        "argv": ["git", "push", "origin", "main"],
        "kind": "git-push",
        "exit_code": 1,
        "fixture_stderr": True,
        "required": ["rejected", "non-fast-forward", "failed to push"],
    },
    {
        "id": "git-fetch-success",
        "fixture": "git_fetch_success_raw.txt",
        "program": "git",
        "argv": ["git", "fetch", "origin"],
        "kind": "git-fetch",
        "exit_code": 0,
        "fixture_stderr": True,
        "required": ["fetched", "1", "new refs"],
    },
    {
        "id": "git-fetch-failure",
        "fixture": "git_fetch_failure_raw.txt",
        "program": "git",
        "argv": ["git", "fetch", "origin"],
        "kind": "git-fetch",
        "exit_code": 1,
        "fixture_stderr": True,
        "required": ["Could not resolve host", "example.test"],
    },
    {
        "id": "git-show-commit-diff",
        "fixture": None,
        "program": None,
        "argv": ["git", "show", "HEAD"],
        "raw_argv": ["git", "show", "HEAD"],
        "kind": "git-show",
        "exit_code": 0,
        "setup_git_repo": True,
        "required": ["preserve migration guard", "tracked.txt", "+beta"],
    },
    {
        "id": "git-branch-list",
        "fixture": "git_branch_list_raw.txt",
        "program": "git",
        "argv": ["git", "branch"],
        "kind": "git-branch",
        "exit_code": 0,
        "required": ["main", "feature/local", "feature/remote"],
    },
    {
        "id": "git-branch-write",
        "fixture": "git_branch_write_raw.txt",
        "program": "git",
        "argv": ["git", "branch", "-d", "obsolete"],
        "kind": "git-branch",
        "exit_code": 0,
        "required": ["ok"],
    },
    {
        "id": "git-branch-failure",
        "fixture": "git_branch_failure_raw.txt",
        "program": "git",
        "argv": ["git", "branch", "-d", "missing"],
        "kind": "git-branch",
        "exit_code": 1,
        "fixture_stderr": True,
        "required": ["missing", "not found"],
    },
    {
        "id": "git-stash-list",
        "fixture": "git_stash_list_raw.txt",
        "program": "git",
        "argv": ["git", "stash", "list"],
        "kind": "git-stash-list",
        "exit_code": 0,
        "required": ["stash@{0}", "preserve guard", "keep risk"],
    },
    {
        "id": "git-stash-show",
        "fixture": "git_stash_show_raw.txt",
        "program": "git",
        "argv": ["git", "stash", "show"],
        "kind": "git-stash-show",
        "exit_code": 0,
        "required": ["src/main.py", "docs/risk.md", "2 changed"],
    },
    {
        "id": "git-stash-push",
        "fixture": "git_stash_push_raw.txt",
        "program": "git",
        "argv": ["git", "stash", "push"],
        "kind": "git-stash",
        "exit_code": 0,
        "required": ["ok stashed"],
    },
    {
        "id": "git-stash-failure",
        "fixture": "git_stash_failure_raw.txt",
        "program": "git",
        "argv": ["git", "stash", "push", "-q"],
        "kind": "git-stash",
        "exit_code": 129,
        "fixture_stderr": True,
        "required": ["unknown switch", "usage"],
    },
    {
        "id": "git-worktree-list",
        "fixture": "git_worktree_list_raw.txt",
        "program": "git",
        "argv": ["git", "worktree", "list"],
        "kind": "git-worktree-list",
        "exit_code": 0,
        "required": ["C:/repo/main", "main", "feature/migration"],
    },
    {
        "id": "git-worktree-write",
        "fixture": "git_worktree_write_raw.txt",
        "program": "git",
        "argv": ["git", "worktree", "add", "C:/repo/feature"],
        "kind": "git-worktree",
        "exit_code": 0,
        "fixture_stderr": True,
        "required": ["ok"],
    },
    {
        "id": "git-worktree-failure",
        "fixture": "git_worktree_failure_raw.txt",
        "program": "git",
        "argv": ["git", "worktree", "add", "C:/repo/main"],
        "kind": "git-worktree",
        "exit_code": 128,
        "fixture_stderr": True,
        "required": ["already checked out", "C:/repo/main"],
    },
    {
        "id": "ls-human-long",
        "fixture": "ls_long_raw.txt",
        "program": "ls",
        "argv": ["ls", "-la", "."],
        "kind": "file-list-ls-long",
        "exit_code": 0,
        "required": ["src", "README file.md", "build.sh"],
    },
    {
        "id": "ls-unknown-locale",
        "fixture": "ls_unknown_locale_raw.txt",
        "program": "ls",
        "argv": ["ls", "."],
        "kind": "file-list-ls",
        "exit_code": 0,
        "required": ["README.md", "9月"],
    },
    {
        "id": "ls-failure",
        "fixture": "ls_failure_raw.txt",
        "program": "ls",
        "argv": ["ls", "missing"],
        "kind": "file-list-ls",
        "exit_code": 2,
        "required": ["missing", "No such file or directory"],
    },
    {
        "id": "tree-human",
        "fixture": "tree_human_raw.txt",
        "program": "tree",
        "argv": ["tree", "."],
        "kind": "file-list-tree",
        "exit_code": 0,
        "required": ["src", "main.py", "README.md"],
    },
    {
        "id": "tree-unknown-format",
        "fixture": "tree_unknown_raw.txt",
        "program": "tree",
        "argv": ["tree", "."],
        "kind": "file-list-tree",
        "exit_code": 0,
        "required": ["summary unavailable"],
    },
    {
        "id": "tree-failure",
        "fixture": "tree_failure_raw.txt",
        "program": "tree",
        "argv": ["tree", "missing"],
        "kind": "file-list-tree",
        "exit_code": 2,
        "required": ["missing", "No such file or directory"],
    },
    {
        "id": "find-human-paths",
        "fixture": "find_paths_raw.txt",
        "program": None,
        "argv": ["find", "*.py", "."],
        "kind": "file-list-find",
        "exit_code": 0,
        "setup_paths": True,
        "required": ["file_00.py", "file_19.py"],
    },
    {
        "id": "find-failure",
        "fixture": "find_failure_raw.txt",
        "program": None,
        "argv": ["find", "*.py", "./missing"],
        "kind": "file-list-find",
        "exit_code": 1,
        "required": ["missing", "No such file or directory"],
    },
    {
        "id": "read-numbered-source",
        "fixture": "native_sample.py",
        "program": None,
        "argv": ["read", "--line-numbers", "{fixture}"],
        "kind": "native-read",
        "exit_code": 0,
        "required": ["from pathlib import Path", "class Config", "load_config"],
    },
    {
        "id": "json-compact-values",
        "fixture": "native_data.json",
        "program": None,
        "argv": ["json", "{fixture}"],
        "kind": "native-json",
        "exit_code": 0,
        "required": ["enabled", "users", "alpha"],
    },
    {
        "id": "smart-python-summary",
        "fixture": "native_sample.py",
        "program": None,
        "argv": ["smart", "{fixture}"],
        "kind": "native-smart",
        "exit_code": 0,
        "required": ["Python", "pathlib"],
    },
    {
        "id": "rg-human-search",
        "fixture": "rg_human_search_raw.txt",
        "program": "rg",
        "argv": ["rg", "target", "."],
        "kind": "search",
        "exit_code": 0,
        "required": ["src/a.py", "target one", "src/b.py", "target four"],
    },
    {
        "id": "grep-human-search",
        "fixture": "grep_human_search_raw.txt",
        "program": "grep",
        "argv": ["grep", "target", "src/a.py", "src/b.py"],
        "kind": "search",
        "exit_code": 0,
        "required": ["src/a.py", "target one", "src/b.py", "target four"],
    },
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
    {
        "id": "bun-test-failure",
        "fixture": "bun_test_failures_raw.txt",
        "program": "bun",
        "argv": ["bun", "test"],
        "kind": "bun-test",
        "exit_code": 1,
        "required": ["t2 fails", "Expected: 3", "Received: 2"],
    },
    {
        "id": "deno-test-failure",
        "fixture": "deno_test_failures_raw.txt",
        "program": "deno",
        "argv": ["deno", "test"],
        "kind": "deno-test",
        "exit_code": 1,
        "required": ["plain assertion", "Values are not equal", "3 passed", "2 failed"],
    },
    {
        "id": "gradle-test-failure",
        "fixture": "gradlew_test_failed_raw.txt",
        "program": "gradle",
        "argv": ["gradlew", "test"],
        "kind": "gradle-test",
        "exit_code": 1,
        "required": ["testSubtraction FAILED", "expected:<3> but was:<-1>", "5 tests completed, 2 failed", "BUILD FAILED"],
    },
    {
        "id": "golangci-v2-issues",
        "fixture": "golangci_v2_issues_raw.json",
        "program": "golangci-lint",
        "argv": ["golangci-lint", "run"],
        "kind": "golangci",
        "exit_code": 1,
        "version_stdout": "golangci-lint has version 2.1.0 built with go1.24.0",
        "required": ["6 issues", "main.go", "errcheck", "ineffassign"],
    },
    {
        "id": "git-diff-multifile",
        "fixture": "diff/git_diff_multifile_raw.txt",
        "program": "git",
        "argv": ["git", "diff"],
        "kind": "diff",
        "exit_code": 0,
        "empty_first_args": ["config"],
        "empty_any_args": ["--no-patch"],
        "required": ["main.rs", "println!(\"2\")", "println!(\"five\")", "-- legacy column"],
    },
)


def _write_emitter(
    directory: Path,
    program: str,
    fixture: Path,
    exit_code: int,
    version_stdout: str | None = None,
    empty_first_args: tuple[str, ...] = (),
    empty_any_args: tuple[str, ...] = (),
    stderr: bool = False,
) -> None:
    if os.name == "nt":
        target = directory / f"{program}.cmd"
        version_branch = ""
        if version_stdout:
            version_branch = (
                f'@if "%~1"=="--version" (\r\n'
                f'  @echo {version_stdout}\r\n'
                "  @exit /b 0\r\n"
                ")\r\n"
            )
        empty_branches = "".join(
            f'@if "%~1"=="{argument}" @exit /b 1\r\n'
            for argument in empty_first_args
        )
        empty_any_branches = "".join(
            f'@for %%A in (%*) do @if "%%~A"=="{argument}" @exit /b 0\r\n'
            for argument in empty_any_args
        )
        target.write_text(
            version_branch + empty_branches + empty_any_branches
            + f'@type "{fixture}"{" 1>&2" if stderr else ""}\r\n@exit /b {exit_code}\r\n',
            encoding="utf-8",
        )
        return
    target = directory / program
    version_branch = ""
    if version_stdout:
        escaped_version = version_stdout.replace("'", "'\\''")
        version_branch = (
            'if [ "$1" = "--version" ]; then\n'
            f"  printf '%s\\n' '{escaped_version}'\n"
            "  exit 0\n"
            "fi\n"
        )
    empty_branches = "".join(
        f"if [ \"$1\" = '{argument}' ]; then exit 1; fi\n"
        for argument in empty_first_args
    )
    empty_any_branches = "".join(
        f"for arg in \"$@\"; do [ \"$arg\" = '{argument}' ] && exit 0; done\n"
        for argument in empty_any_args
    )
    escaped_fixture = str(fixture).replace("'", "'\\''")
    target.write_text(
        f"#!/bin/sh\n{version_branch}{empty_branches}{empty_any_branches}"
        f"cat '{escaped_fixture}'{' >&2' if stderr else ''}\nexit {exit_code}\n",
        encoding="utf-8",
    )
    target.chmod(target.stat().st_mode | stat.S_IXUSR)


def _setup_git_repo(root: Path) -> None:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "UTK Fixture",
        "GIT_AUTHOR_EMAIL": "utk@example.test",
        "GIT_COMMITTER_NAME": "UTK Fixture",
        "GIT_COMMITTER_EMAIL": "utk@example.test",
        "GIT_AUTHOR_DATE": "2024-01-02T03:04:05+00:00",
        "GIT_COMMITTER_DATE": "2024-01-02T03:04:05+00:00",
    }
    subprocess.run(["git", "init", "-b", "main"], cwd=root, env=env, check=True, capture_output=True)
    tracked = root / "tracked.txt"
    tracked.write_text("alpha\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.txt"], cwd=root, env=env, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial fixture"], cwd=root, env=env, check=True, capture_output=True)
    env["GIT_AUTHOR_DATE"] = "2024-01-03T03:04:05+00:00"
    env["GIT_COMMITTER_DATE"] = "2024-01-03T03:04:05+00:00"
    tracked.write_text("alpha\nbeta\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.txt"], cwd=root, env=env, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "preserve migration guard", "-m", "Do not remove config.v2."],
        cwd=root,
        env=env,
        check=True,
        capture_output=True,
    )
    tracked.write_text("alpha\nbeta\ngamma\n", encoding="utf-8")
    (root / "untracked.txt").write_text("risk must not be lost\n", encoding="utf-8")


def _run_case(binary: Path, checkout: Path, case: dict[str, Any]) -> dict[str, Any]:
    fixture = None
    raw = ""
    if case.get("fixture"):
        repository_fixture = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "rtk_reference" / case["fixture"]
        fixture = repository_fixture if repository_fixture.is_file() else checkout / "tests" / "fixtures" / case["fixture"]
        if not fixture.is_file():
            raise ValueError(f"Missing frozen RTK fixture: {case['fixture']}")
        raw = fixture.read_text(encoding="utf-8", errors="replace")
    with tempfile.TemporaryDirectory(prefix="utk-rtk-reference-") as temporary:
        root = Path(temporary)
        if case.get("setup_git_repo"):
            _setup_git_repo(root)
        if case.get("setup_git_add"):
            (root / "tracked.txt").write_text(
                "alpha\nbeta\ngamma\ndelta\n", encoding="utf-8"
            )
        if case.get("raw_argv") and not case.get("captured_raw_only"):
            direct = subprocess.run(
                case["raw_argv"], cwd=root, text=True, encoding="utf-8", errors="replace",
                capture_output=True, check=False,
            )
            raw = direct.stdout or direct.stderr
        if case.get("setup_paths"):
            for relative in raw.splitlines():
                target = root / Path(relative)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("fixture\n", encoding="utf-8")
        if case["program"]:
            _write_emitter(
                root,
                case["program"],
                fixture.resolve(),
                case["exit_code"],
                case.get("version_stdout"),
                tuple(case.get("empty_first_args", ())),
                tuple(case.get("empty_any_args", ())),
                bool(case.get("fixture_stderr")),
            )
        env = {
            **os.environ,
            "PATH": str(root) + os.pathsep + os.environ.get("PATH", ""),
            "HOME": str(root),
            "APPDATA": str(root / "appdata"),
            "LOCALAPPDATA": str(root / "localappdata"),
            "RTK_TEE": "0",
            "NO_COLOR": "1",
        }
        argv = [str(fixture.resolve()) if value == "{fixture}" and fixture else value for value in case["argv"]]
        process = subprocess.run(
            [str(binary), *argv],
            cwd=root,
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
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
        if case["kind"].startswith("native-"):
            from .native_tools import execute_native_tool
            with tempfile.TemporaryDirectory(prefix="utk-native-reference-") as temporary:
                fixture = Path(temporary) / Path(case["fixture"]).name
                fixture.write_text(raw, encoding="utf-8")
                argv = [str(fixture) if value == "{fixture}" else value for value in case["argv"]]
                native_result = execute_native_tool(argv)
                if native_result is None or native_result.code:
                    raise RuntimeError(f"UTK native reference failed for {case_id}")
                native = native_result.rendered
        else:
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
