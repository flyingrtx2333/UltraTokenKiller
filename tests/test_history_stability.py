import json

from ultratokenkiller.compression import compress_content
from ultratokenkiller.recovery import RecoveryVault


def test_passthrough_history_remains_identical_after_enabling_compression():
    vault = RecoveryVault()
    original = json.dumps([{"value": "repeated"}] * 100)
    first = compress_content(original, session="s", vault=vault, profile="off")
    second = compress_content(original, session="s", vault=vault, profile="safe")
    assert second == first
    assert not second.recovery_id
    # New content can still be compressed.
    assert compress_content(original + " ", session="s", vault=vault).recovery_id


def test_metadata_exhaustion_freezes_new_lossy_results_until_idle():
    now = [0.0]
    vault = RecoveryVault(capacity=2200, idle_seconds=10, clock=lambda: now[0])
    compress_content("first", session="s", vault=vault, profile="off")
    compress_content("second", session="s", vault=vault, profile="off")
    assert vault.status()["new_compression_frozen"]
    now[0] = 9
    original = json.dumps([{"x": "y"}] * 30)
    assert not compress_content(original, session="other", vault=vault).recovery_id
    now[0] = 11
    assert vault.status()["new_compression_frozen"]
    assert vault.status()["used_bytes"] <= 2200
    now[0] = 20
    assert not vault.status()["new_compression_frozen"]


def test_passthrough_fingerprints_do_not_retain_bodies():
    vault = RecoveryVault()
    original = "private original body" * 1000
    compress_content(original, session="s", vault=vault, profile="off")
    assert all(value.content == "" for value in vault.sessions["s"].passthroughs.values())
    assert vault.status()["used_bytes"] < len(original)


def test_tool_search_and_diff_dispatch_are_recoverable():
    search = "".join(f"a/very/long/repeated/path/file.py:{i}:hit\n" for i in range(100))
    diff = "diff --git a/a b/a\n--- a/a\n+++ b/a\n@@ -1,100 +1,100 @@\n" + " context line\n" * 100 + "-old\n+new\n"
    vault = RecoveryVault()
    for kind, original in [("search", search), ("diff", diff)]:
        result = compress_content(original, session="s", vault=vault, hint="tool:" + kind)
        assert result.after_tokens < result.before_tokens
        assert vault.retrieve("s", result.recovery_id)["content"] == original
        if kind == "diff":
            assert "-old\n+new" in result.content
        else:
            assert "99: hit" in result.content
