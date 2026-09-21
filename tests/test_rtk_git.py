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
        (["git", "show", "HEAD"], "git-show"),
        (["git", "stash", "list"], "git-stash-list"),
        (["git", "stash", "show"], "git-stash-show"),
        (["git", "stash", "show", "-p"], "diff"),
        (["git", "worktree", "list"], "git-worktree-list"),
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
        ["git", "show", "--stat"],
        ["git", "show", "HEAD:README.md"],
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


def test_git_push_removes_progress_but_keeps_remote_result():
    raw = (
        "Enumerating objects: 5, done.\n"
        "Counting objects: 100% (5/5), done.\n"
        "Writing objects: 100% (3/3), done.\n"
        "To https://example.test/repo.git\n"
        "   abc1234..def5678  main -> main\n"
    )
    compact = compress_tool(raw, "git-push")
    assert "Enumerating objects" not in compact
    assert "https://example.test/repo.git" in compact
    assert "main -> main" in compact
    assert compact.endswith("ok main\n")


def test_git_branch_list_groups_remote_only_branches():
    raw = "* main\n  feature/local\n  remotes/origin/HEAD -> origin/main\n  remotes/origin/main\n  remotes/origin/feature/remote\n"
    compact = compress_tool(raw, "git-branch")
    assert "* main" in compact
    assert "feature/local" in compact
    assert "remote-only (1)" in compact
    assert "feature/remote" in compact
    assert "origin/HEAD" not in compact


def test_git_stash_list_and_stat_have_dedicated_filters():
    listing = "stash@{0}: WIP on main: a1b2c3d preserve guard\nstash@{1}: On feature: f6e5d4c keep risk\n"
    assert compress_tool(listing, "git-stash-list") == "stash@{0}: a1b2c3d preserve guard\nstash@{1}: f6e5d4c keep risk"
    stat = " src/main.py | 10 ++++++++--\n docs/risk.md | 2 ++\n 2 files changed, 10 insertions(+), 2 deletions(-)\n"
    compact = compress_tool(stat, "git-stash-show")
    assert "src/main.py 10 +-" in compact
    assert "docs/risk.md 2 +" in compact
    assert "2 changed 10 + 2 -" in compact


def test_git_show_compacts_header_and_patch():
    raw = (
        "commit " + "a" * 40 + "\nAuthor: A <a@example.test>\nDate: today\n\n"
        "    preserve migration guard\n\n"
        "diff --git a/src/main.py b/src/main.py\n"
        "index 1111111..2222222 100644\n--- a/src/main.py\n+++ b/src/main.py\n"
        "@@ -1,2 +1,2 @@\n-old\n+new\n context\n"
    )
    compact = compress_tool(raw, "git-show")
    assert "aaaaaaaaaa preserve migration guard" in compact
    assert "A <a@example.test>" in compact
    assert "src/main.py" in compact
    assert "-old" in compact and "+new" in compact
    assert " context" not in compact


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


def test_git_add_compacts_staged_stat_probe_without_losing_counts():
    raw = (
        " tracked.txt | 1 +\n"
        " 1 file changed, 1 insertion(+)\n"
        " 1 file changed, 1 insertion(+)\n"
    )

    compact = compress_tool(raw, "git-add")

    assert "tracked.txt" in compact
    assert "1 file changed" in compact
    assert "1 insertion" in compact
