import json
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
    (["git", "commit", "-m", "message"], "git-action"),
    (["git", "push", "origin", "main"], "git-action"),
    (["git", "-C"], None),
])
def test_git_contracts(argv, kind):
    assert command_filter(argv) == kind


def test_commit_body_risks_and_identifiers_survive():
    original = "commit " + "a" * 40 + "\nAuthor: A <a@example.test>\nDate: today\n\n    change config\n\n    Do not delete config.v1.json.\n    Migration requires version 2, not 1.\n"
    result = compress_tool(original, "git-log")
    assert "Do not delete config.v1.json." in result
    assert "Migration requires version 2, not 1." in result
    assert "a" * 40 in result


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
    (["ls", "-la"], "file-list"),
    (["find", ".", "-name", "*.py"], "file-list"),
    (["find", ".", "-print0"], None),
    (["gh", "pr", "list"], "gh-human"),
    (["gh", "pr", "list", "--json", "number"], None),
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
    assert compress_tool('{"number":1}\n', "gh-human") == '{"number":1}\n'
    listing = "alpha.py          10\nbeta.py           20\n"
    compact = compress_tool(listing, "file-list")
    assert "alpha.py | 10" in compact and "beta.py | 20" in compact
    commit = "[main a1b2c3d] change\n 2 files changed, 10 insertions(+), 2 deletions(-)\n"
    assert "2 files changed | 10" in compress_tool(commit, "git-action")
    unknown = "remote helper emitted opaque result\n"
    assert compress_tool(unknown, "git-action") == unknown
