import pytest

from ultratokenkiller.tool_filters import command_filter, compress_tool


@pytest.mark.parametrize(
    "argv, kind",
    [
        (["git", "status", "--short", "--branch"], "git-status"),
        (["git", "log", "-n", "20"], "git-log"),
        (["git", "diff", "HEAD~1", "--", "src/main.py"], "diff"),
        (["git", "add", "src/main.py"], "git-add"),
        (["git", "commit", "-m", "change"], "git-commit"),
        (["git", "push", "origin", "main"], "git-push"),
        (["git", "pull", "--ff-only"], "git-pull"),
        (["git", "fetch", "origin"], "git-fetch"),
        (["git", "checkout", "feature/x"], "git-checkout"),
        (["git", "switch", "feature/x"], "git-switch"),
        (["git", "branch", "--list"], "git-branch"),
        (["git", "stash", "push"], "git-stash"),
        (["git", "worktree", "list"], "git-worktree"),
    ],
)
def test_git_subcommands_have_specific_contracts(argv, kind):
    assert command_filter(argv) == kind


@pytest.mark.parametrize(
    "argv",
    [
        ["git", "status", "--porcelain=v2"],
        ["git", "log", "--oneline"],
        ["git", "log", "--graph"],
        ["git", "diff", "--stat"],
        ["git", "diff", "--word-diff"],
        ["git", "diff", "--ext-diff"],
    ],
)
def test_git_machine_or_user_selected_shapes_pass_through(argv):
    assert command_filter(argv) is None


def test_git_status_removes_only_instructional_hints():
    raw = (
        "On branch main\n"
        "Changes not staged for commit:\n"
        "  (use \"git add <file>...\" to update what will be committed)\n"
        "\tmodified:   src/main.py\n\n"
        "Untracked files:\n"
        "  (use \"git add <file>...\" to include in what will be committed)\n"
        "\tdocs/risk.md\n"
    )
    compact = compress_tool(raw, "git-status")
    assert "* main" in compact
    assert " M src/main.py" in compact
    assert "docs/risk.md" in compact
    assert "use \"git" not in compact


def test_git_commit_success_matches_fixed_rtk_hash_summary():
    raw = (
        "[main a1b2c3d] do not remove fallback\n"
        " 2 files changed, 10 insertions(+), 2 deletions(-)\n"
        " create mode 100644 docs/risk.md\n"
    )
    compact = compress_tool(raw, "git-commit")
    assert compact == "ok a1b2c3d\n"


@pytest.mark.parametrize(
    "kind, raw, expected",
    [
        ("git-pull", "Already up to date.\n", "ok (up-to-date)\n"),
        ("git-pull", "Fast-forward\n 3 files changed, 8 insertions(+), 1 deletion(-)\n", "ok 3 files +8 -1\n"),
        ("git-fetch", "From example.test/repo\n * [new branch] feature -> origin/feature\n", "ok fetched (1 new refs)\n"),
        ("git-checkout", "Switched to a new branch 'feature/x'\n", "ok feature/x (new)\n"),
        ("git-switch", "Already on 'main'\n", "ok main\n"),
        ("git-stash", "Saved working directory and index state WIP on main: a1b2 change\n", "ok stashed\n"),
    ],
)
def test_git_success_filters(kind, raw, expected):
    assert compress_tool(raw, kind) == expected


@pytest.mark.parametrize(
    "kind, raw",
    [
        ("git-add", "fatal: pathspec 'missing' did not match any files\n"),
        ("git-commit", "nothing to commit, working tree clean\n"),
        ("git-pull", "error: Your local changes would be overwritten\n"),
        ("git-fetch", "fatal: could not read from remote repository\n"),
        ("git-checkout", "error: pathspec 'missing' did not match\n"),
        ("git-stash", "No local changes to save\n"),
        ("git-push", "remote helper emitted opaque result\n"),
    ],
)
def test_git_failures_and_unknown_formats_are_unchanged(kind, raw):
    assert compress_tool(raw, kind) == raw
