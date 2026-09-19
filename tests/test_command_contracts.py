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
