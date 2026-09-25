import json
from pathlib import Path
import pytest
from ultratokenkiller.compression import _json_compact
from ultratokenkiller.tool_filters import command_filter, compress_tool


@pytest.mark.parametrize("argv,kind", [
    (["git", "--no-pager", "-C", "directory with spaces", "diff", "--cached"], "diff"),
    (["git", "-C", "/tmp/repo", "status"], "git-status"),
    (["git", "diff", "--staged"], "diff"),
    (["git", "-c", "diff.external=other", "diff"], None),
    (["git", "diff", "--binary"], None),
    (["git", "status", "--porcelain=v2"], None),
    (["git", "commit", "-m", "message"], "git-commit"),
    (["git", "push", "origin", "main"], "git-push"),
    (["git", "-C"], None),
])
def test_git_contracts(argv, kind):
    assert command_filter(argv) == kind


def test_commit_body_risks_and_identifiers_survive():
    original = "commit " + "a" * 40 + "\nAuthor: A <a@example.test>\nDate: today\n\n    change config\n\n    Do not delete config.v1.json.\n    Migration requires version 2, not 1.\n"
    result = compress_tool(original, "git-log")
    assert "Do not delete config.v1.json." in result
    assert "Migration requires version 2, not 1." in result
    assert "a" * 10 in result


@pytest.mark.parametrize("kind,text", [("diff", "unknown\n indented information\n"), ("git-log", "unknown log format"), ("search", "file without numbered hits")])
def test_unknown_formats_unchanged(kind, text):
    assert compress_tool(text, kind) == text


def test_json_preserves_minority_status_boolean_and_unit():
    rows = [{"state": "ready", "enabled": True, "unit": "ms"} for _ in range(100)]
    rows[40] = {"state": "pending", "enabled": False, "unit": "s"}
    result = json.loads(_json_compact(json.dumps(rows)))
    assert rows[40] in result
    assert len(result) < len(rows)


@pytest.mark.parametrize("argv,kind", [
    (["ls", "-la"], "file-list-ls-long"),
    (["find", ".", "-name", "*.py"], "file-list-find"),
    (["find", ".", "-print0"], None),
    (["gh", "pr", "list"], "hosting-list"),
    (["gh", "pr", "view", "42"], "hosting-view"),
    (["gh", "pr", "checks", "42"], "hosting-checks"),
    (["gh", "pr", "list", "--json", "number"], None),
    (["gh", "pr", "view", "42", "--web"], None),
    (["glab", "mr", "list"], "hosting-list"),
    (["glab", "-R", "owner/repo", "mr", "list"], "hosting-list"),
    (["glab", "mr", "view", "42"], "hosting-view"),
    (["glab", "mr", "list", "-F", "json"], None),
    (["gt", "log"], "gt-log"),
    (["gt", "log", "short"], None),
    (["gt", "submit"], "gt-submit"),
    (["gt", "status"], "git-status"),
    (["gt", "branch"], None),
    (["rspec"], "generic-test"),
    (["dotnet", "test"], "generic-test"),
    (["mvn", "verify"], "generic-test"),
    (["phpstan", "analyse"], "diagnostics"),
    (["npm", "install"], "package"),
    (["npm", "view", "x", "--json"], None),
    (["aws", "sts", "get-caller-identity"], "cloud-human"),
    (["aws", "sts", "get-caller-identity", "--output", "json"], None),
])
def test_additional_command_contracts(argv, kind):
    assert command_filter(argv) == kind


def test_additional_filters_keep_failures_and_machine_shapes():
    assert compress_tool("10 examples, 0 failures\nnoise\n", "generic-test") == "10 examples, 0 failures\n"
    failure = "10 examples, 1 failure\nERROR do not retry\n"
    assert compress_tool(failure, "generic-test") == failure
    assert compress_tool('{"unexpected":1}\n', "hosting-view") == '{"unexpected":1}\n'
    listing = "alpha.py          10\nbeta.py           20\n"
    compact = compress_tool(listing, "file-list-ls-long")
    assert compact == listing
    commit = "[main a1b2c3d] change\n 2 files changed, 10 insertions(+), 2 deletions(-)\n"
    assert compress_tool(commit, "git-commit") == "ok a1b2c3d\n"
    unknown = "remote helper emitted opaque result\n"
    assert compress_tool(unknown, "git-push") == unknown


def test_pytest_expected_failure_outcomes_keep_reasons_and_counts():
    fixture = Path(__file__).parent / "fixtures" / "rtk_reference" / "pytest_xfail_xpass_raw.txt"
    raw = fixture.read_text(encoding="utf-8")
    result = compress_tool(raw, "pytest")
    assert "XFAIL tests/test_math.py::test_division - known bug #42" in result
    assert "XPASS tests/test_math.py::test_rounding - unexpected behavior change" in result
    assert "2 passed, 1 xfailed, 1 xpassed" in result
    assert len(result) < len(raw)


def test_pytest_collection_errors_and_unknown_output_pass_through():
    collection_error = (
        "============================= test session starts =============================\n"
        "collected 0 items / 1 error\n\n"
        "==================================== ERRORS ====================================\n"
        "ERROR collecting tests/test_auth.py\n"
        "ImportError while importing test module tests/test_auth.py\n"
        "E   ModuleNotFoundError: No module named 'auth'\n"
        "=========================== 1 error in 0.12s =============================\n"
    )
    assert compress_tool(collection_error, "pytest") == collection_error
    unknown = "plugin changed its output format\nopaque details\n"
    assert compress_tool(unknown, "pytest") == unknown


def test_hosting_filters_preserve_identifiers_states_and_failure_text():
    listing = json.dumps([
        {"number": 42, "title": "Preserve migration guard", "state": "OPEN", "author": {"login": "dev"}},
        {"number": 41, "title": "Do not delete config", "state": "MERGED", "author": {"login": "ops"}},
    ], indent=2) + "\n"
    result = compress_tool(listing, "hosting-list")
    assert "[open] | #42 | Preserve migration guard | (dev)" in result
    assert "[merged] | #41 | Do not delete config | (ops)" in result

    view = json.dumps({
        "iid": 7, "title": "Keep tenant check", "state": "opened",
        "author": {"username": "reviewer"}, "web_url": "https://gitlab.example/mr/7",
        "description": "Do not bypass tenant validation.",
    }, indent=2) + "\n"
    rendered = compress_tool(view, "hosting-view")
    for fact in ("7", "Keep tenant check", "opened", "reviewer", "https://gitlab.example/mr/7", "Do not bypass"):
        assert fact in rendered

    failure = "HTTP 403: authentication required; do not retry with another account\n"
    assert compress_tool(failure, "hosting-list") == failure


def test_graphite_filters_keep_branch_and_pr_facts_and_unknown_shapes():
    log = "◉  abc1234 feat/auth 2d ago dev@example.com\n│  preserve auth guard\n│\n~\n"
    compact = compress_tool(log, "gt-log")
    assert "abc1234" in compact and "feat/auth" in compact and "preserve auth guard" in compact
    assert "dev@example.com" not in compact

    submit = "Pushing objects...\nPushed branch feat/auth\nCreated pull request #42 for feat/auth: https://example/pull/42\n"
    compact_submit = compress_tool(submit, "gt-submit")
    assert "feat/auth" in compact_submit and "#42" in compact_submit and "https://example/pull/42" in compact_submit

    unknown = "Graphite changed its output schema\nopaque detail\n"
    assert compress_tool(unknown, "gt-sync") == unknown
