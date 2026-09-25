import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from ultratokenkiller.compression import compress_content
from ultratokenkiller.config import Settings
from ultratokenkiller.recovery import RecoveryUnavailable, RecoveryVault


def test_json_outlier_error_boundaries_and_full_recovery():
    rows = [{"latency": 10, "status": "ok", "id": i} for i in range(100)]
    rows[50]["latency"] = 9000
    rows[70]["status"] = "failed"
    original = json.dumps(rows)
    vault = RecoveryVault()
    result = compress_content(original, session="a", vault=vault)
    assert result.saved_tokens > 0
    compressed = json.loads(result.content)["data"]
    assert rows[0] in compressed and rows[-1] in compressed
    assert rows[50] in compressed and rows[70] in compressed
    assert vault.retrieve("a", result.recovery_id)["content"] == original
    with pytest.raises(RecoveryUnavailable):
        vault.retrieve("b", result.recovery_id)


def test_capacity_expiry_and_stable_rendering():
    now = [0]
    vault = RecoveryVault(capacity=100_000, idle_seconds=10, clock=lambda: now[0])
    original = "\n".join(
        [*(f"INFO processing request {i}" for i in range(100)), "INFO source src/module.py"]
    )
    first = compress_content(original, session="a", vault=vault)
    assert first.recovery_id
    assert "src/module.py" in first.content
    assert compress_content(original, session="a", vault=vault, profile="off").content == first.content
    assert compress_content(first.content, session="a", vault=vault).fallback == "already_compressed"
    now[0] = 11
    with pytest.raises(RecoveryUnavailable):
        vault.retrieve("a", first.recovery_id)
    assert vault.status()["used_bytes"] == 0
    tiny = RecoveryVault(capacity=16)
    assert compress_content(original, session="a", vault=tiny).content == original


def test_concurrent_sessions_and_restart_never_recover_other_conversation():
    vault = RecoveryVault()

    def compress_for(index):
        original = json.dumps([{"session": index, "value": n} for n in range(100)])
        result = compress_content(original, session=f"session-{index}", vault=vault)
        return index, original, result.recovery_id

    with ThreadPoolExecutor(max_workers=8) as pool:
        records = list(pool.map(compress_for, range(16)))

    for index, original, handle in records:
        assert handle
        assert vault.retrieve(f"session-{index}", handle)["content"] == original
        with pytest.raises(RecoveryUnavailable, match="wrong session"):
            vault.retrieve(f"session-{(index + 1) % 16}", handle)
    with pytest.raises(RecoveryUnavailable, match="restarted"):
        RecoveryVault().retrieve(f"session-{index}", handle)


def test_cross_turn_duplicate_uses_prior_recovery_handle_without_cross_session_sharing():
    vault = RecoveryVault()
    original = json.dumps([{"id": index, "path": "src/module.py", "status": "ready"}
                           for index in range(100)])
    first = compress_content(original, session="dedup-a", vault=vault)
    repeated = compress_content(original, session="dedup-a", vault=vault)

    assert first.recovery_id
    assert repeated.recovery_id == first.recovery_id
    assert repeated.content != first.content
    reference = json.loads(repeated.content)
    assert reference == {"_utk_duplicate": True, "_utk_recovery": first.recovery_id}
    assert repeated.saved_tokens > 0
    assert vault.retrieve("dedup-a", first.recovery_id)["content"] == original

    other_session = compress_content(original, session="dedup-b", vault=vault)
    assert other_session.recovery_id != first.recovery_id
    assert "_utk_duplicate" not in other_session.content
    assert vault.retrieve("dedup-b", other_session.recovery_id)["content"] == original


def test_cross_turn_reference_requires_a_live_session_index():
    now = [0.0]
    vault = RecoveryVault(idle_seconds=10, clock=lambda: now[0])
    original = json.dumps([{"id": index, "path": "src/module.py", "state": "ready"}
                           for index in range(100)])
    first = compress_content(original, session="live", vault=vault)
    assert first.recovery_id
    assert "_utk_duplicate" in compress_content(original, session="live", vault=vault).content

    now[0] = 11
    expired = compress_content(original, session="live", vault=vault)
    assert expired.recovery_id and expired.recovery_id != first.recovery_id
    assert "_utk_duplicate" not in expired.content
    with pytest.raises(RecoveryUnavailable, match="expired"):
        vault.retrieve("live", first.recovery_id)

    restarted = compress_content(original, session="live", vault=RecoveryVault())
    assert restarted.recovery_id
    assert "_utk_duplicate" not in restarted.content

    no_session = compress_content(original, session="", vault=vault)
    assert no_session.content == original
    assert no_session.recovery_id is None


def test_cross_turn_duplicate_segments_are_recoverable_and_keep_critical_lines():
    shared = [f"INFO cache phase step-{index:02} verified stable" for index in range(40)]

    def output(batch):
        return "\n".join(
            [*shared, *([f"INFO {batch} background task completed safely"] * 80),
             "INFO source src/module.py:42", "ERROR request failed; preserve this failure"]
        )

    vault = RecoveryVault()
    first_text = output("first")
    first = compress_content(first_text, session="partial-dedup", vault=vault)
    assert first.recovery_id

    second_text = output("second")
    second = compress_content(second_text, session="partial-dedup", vault=vault)
    assert second.recovery_id
    assert "40 repeated lines omitted" in second.content
    assert first.recovery_id in second.content
    assert "src/module.py:42" in second.content
    assert "ERROR request failed; preserve this failure" in second.content
    assert second.saved_tokens > 0
    assert vault.retrieve("partial-dedup", second.recovery_id)["content"] == second_text
    assert vault.retrieve("partial-dedup", first.recovery_id)["content"] == first_text

    isolated = compress_content(second_text, session="another-session", vault=vault)
    assert "repeated lines omitted" not in isolated.content
    assert isolated.recovery_id
    assert vault.retrieve("another-session", isolated.recovery_id)["content"] == second_text


def test_cross_turn_duplicate_segments_do_not_use_expired_restarted_or_missing_indexes():
    shared = [f"INFO cache phase step-{index:02} verified stable" for index in range(40)]
    original = "\n".join([*shared, *(["INFO worker heartbeat stable"] * 80)])
    previous = "\n".join([*shared, *(["INFO old worker idle"] * 80)])
    now = [0.0]
    vault = RecoveryVault(idle_seconds=10, clock=lambda: now[0])
    assert compress_content(previous, session="expiry", vault=vault).recovery_id

    now[0] = 11
    expired = compress_content(original, session="expiry", vault=vault)
    restarted_vault = RecoveryVault()
    restarted = compress_content(original, session="expiry", vault=restarted_vault)
    no_session = compress_content(original, session="", vault=vault)
    for result in (expired, restarted):
        assert "repeated lines omitted" not in result.content
        assert result.recovery_id
    assert vault.retrieve("expiry", expired.recovery_id)["content"] == original
    assert restarted_vault.retrieve("expiry", restarted.recovery_id)["content"] == original
    assert no_session.content == original
    assert no_session.recovery_id is None


def test_mixed_sections_preserve_order_unknown_text_and_recovery():
    intro = "Review src/app.py:42 before changing the deployment."
    structured = json.dumps([{"id": n, "status": "ok", "latency": 12} for n in range(100)])
    logs = "\n".join(["INFO running health check"] * 80 + ["ERROR request failed at src/app.py:42"])
    unknown = "<custom-widget data-id=\"security\">Keep this exact text.</custom-widget>"
    original = "\n\n".join((intro, structured, logs, unknown))
    vault = RecoveryVault()
    result = compress_content(original, session="bound", vault=vault)
    assert result.content_type == "mixed"
    assert result.saved_tokens > 0
    assert intro in result.content
    assert "ERROR request failed at src/app.py:42" in result.content
    assert unknown in result.content
    assert result.content.index(intro) < result.content.index("ERROR request failed") < result.content.index(unknown)
    assert vault.retrieve("bound", result.recovery_id)["content"] == original


def test_mixed_content_with_code_fence_is_passed_through_until_boundaries_are_safe():
    original = "Intro\n\n```python\n" + "\n".join(["ERROR = 'not a log'"] * 40) + "\n```\n\nEnd"
    result = compress_content(original, session="bound", vault=RecoveryVault())
    assert result.content == original
    assert result.fallback == "compressor_not_ready"


def test_mixed_code_fence_compresses_body_without_breaking_fence_or_neighbors():
    body = "def parse_record(value):\n" + "".join(f"    step_{n} = value + {n}\n" for n in range(80)) + "    return value\n"
    original = "Read src/parser.py:18\n\n```python\n" + body + "```\n\nKeep the warning: ERROR permission denied."
    vault = RecoveryVault()
    result = compress_content(original, session="bound", vault=vault)
    assert result.content_type == "mixed"
    assert result.saved_tokens > 0
    assert "Read src/parser.py:18" in result.content
    assert "```python\ndef parse_record(value):" in result.content
    assert "pass  # UTK: body available through recovery" in result.content
    assert "\n```\n\n" in result.content
    assert "Keep the warning: ERROR permission denied." in result.content
    assert vault.retrieve("bound", result.recovery_id)["content"] == original


def test_unclosed_mixed_code_fence_stays_original():
    original = "Intro\n\n```python\n" + "\n".join("INFO should not be parsed" for _ in range(40))
    result = compress_content(original, session="bound", vault=RecoveryVault())
    assert result.content == original
    assert result.fallback == "compressor_not_ready"


def test_mixed_html_rows_shrink_but_errors_and_unknown_mark_up_stay_visible():
    html = "<ul>\n" + "<li>healthy worker</li>\n" * 80 + "<li>ERROR access denied</li>\n</ul>"
    original = "Scan the web result.\n\n" + html + "\n\nUnknown <custom id='x'>must stay</custom>."
    vault = RecoveryVault()
    result = compress_content(original, session="bound", vault=vault)
    assert result.content_type == "mixed"
    assert result.saved_tokens > 0
    assert "<li>healthy worker</li>" in result.content
    assert "identical HTML row repeated 79 more times" in result.content
    assert "<li>ERROR access denied</li>" in result.content
    assert "Unknown <custom id='x'>must stay</custom>." in result.content
    assert vault.retrieve("bound", result.recovery_id)["content"] == original


def test_html_with_script_is_not_summarized_as_markup():
    original = "<html>\n<script>\n" + "const key = 42;\n" * 80 + "</script>\n</html>"
    result = compress_content(original, session="bound", vault=RecoveryVault())
    assert result.content == original


def test_fixed_upstream_mixed_boundaries_without_blank_lines_preserve_facts():
    # Based on Headroom bc21c937 tests/test_mixed_content_sections.py's adjacent sections.
    search = "\n".join(f"src/app.py:{n}:match {n}" for n in range(1, 81))
    structured = json.dumps([{"id": n, "status": "ok"} for n in range(80)])
    original = "Intro text\n```python\nprint('x')\n```\n" + structured + "\n" + search
    vault = RecoveryVault()
    result = compress_content(original, session="bound", vault=vault)
    assert result.content_type == "mixed"
    assert result.saved_tokens > 0
    assert "Intro text\n```python\nprint('x')\n```" in result.content
    assert "src/app.py\n" in result.content
    assert "  1: match 1" in result.content
    assert "  80: match 80" in result.content
    assert result.content.index("Intro text") < result.content.index("src/app.py\n")
    assert vault.retrieve("bound", result.recovery_id)["content"] == original


def test_invalid_json_banner_and_search_context_are_never_misrouted_to_prose():
    banner = "[harness: do not drop this security warning.]"
    search = "src/main.py-40-    context before\nsrc/main.py:42:def process(items):\nsrc/main.py-43-    context after"
    original = "Intro\n" + banner + "\n" + search + "\nTrailing prose"
    result = compress_content(original, session="bound", vault=RecoveryVault(), query="summarize")
    assert banner in result.content
    assert search in result.content
    assert "Trailing prose" in result.content


def test_case_insensitive_protected_block_is_not_compressed():
    protected = "<SYSTEM-REMINDER>\n" + "INFO keep this exact\n" * 80 + "</SYSTEM-REMINDER>"
    search = "\n".join(f"src/main.py:{n}:match {n}" for n in range(80))
    original = protected + "\n" + search
    vault = RecoveryVault()
    result = compress_content(original, session="bound", vault=vault)
    assert result.saved_tokens > 0
    assert protected in result.content
    assert vault.retrieve("bound", result.recovery_id)["content"] == original


def test_large_unclosed_json_like_section_is_left_intact():
    unclosed = "[\n" + '{"id": 1, "warning": "must not drop"},\n' * 7000
    original = unclosed + "Trailing prose"
    result = compress_content(original, session="bound", vault=RecoveryVault())
    assert unclosed in result.content
    assert "Trailing prose" in result.content


def test_multiline_json_with_brackets_in_strings_keeps_following_section():
    structured = '[\n  {"path": "a]b", "message": "keep {literal} braces"},\n  {"path": "c"}\n]'
    search = "\n".join(f"src/main.py:{n}:match {n}" for n in range(80))
    original = "Intro\n" + structured + "\n" + search
    vault = RecoveryVault()
    result = compress_content(original, session="bound", vault=vault)
    assert result.saved_tokens > 0
    assert "a]b" in result.content
    assert "keep {literal} braces" in result.content
    assert "src/main.py\n" in result.content
    assert vault.retrieve("bound", result.recovery_id)["content"] == original


def test_mixed_plain_text_only_collapses_exact_repetitions():
    prose = "A steady worker completed the task.\n" * 80
    warning = "ERROR permission denied.\n"
    search = "\n".join(f"src/main.py:{n}:match {n}" for n in range(80))
    original = prose + warning + search
    vault = RecoveryVault()
    result = compress_content(original, session="bound", vault=vault)
    assert result.saved_tokens > 0
    assert "identical line repeated" in result.content
    assert warning in result.content
    assert vault.retrieve("bound", result.recovery_id)["content"] == original


def test_interleaved_table_html_plain_and_failure_facts_keep_their_order():
    plain = "Routine status line.\n" * 60
    table = "| id | state |\n| --- | --- |\n" + "| 1 | ready |\n" * 40
    table += "| 2 | ERROR denied |\n"
    html = "<ul>\n" + "<li>healthy worker</li>\n" * 40
    html += "<li>ERROR permission denied</li>\n</ul>"
    original = plain + table + html
    vault = RecoveryVault()
    result = compress_content(original, session="bound", vault=vault)
    assert result.content_type == "mixed"
    assert result.saved_tokens > 0
    assert "identical line repeated" in result.content
    assert "repeated table rows omitted" in result.content
    assert "identical HTML row repeated" in result.content
    assert "| 2 | ERROR denied |" in result.content
    assert "<li>ERROR permission denied</li>" in result.content
    assert result.content.index("Routine status line") < result.content.index("| id | state |")
    assert result.content.index("| id | state |") < result.content.index("<ul>")
    assert vault.retrieve("bound", result.recovery_id)["content"] == original


def test_python_valid_and_search_locations():
    import ast
    code = "def important(value: int) -> int:\n" + "    value += 1\n" * 100 + "    return value\n"
    vault = RecoveryVault()
    result = compress_content(code, session="a", vault=vault)
    ast.parse(result.content)
    assert "def important(value: int) -> int:" in result.content
    assert vault.retrieve("a", result.recovery_id)["content"] == code
    search = "\n".join(f"src/very/long/path/important.py:{i}:value {i}" for i in range(100))
    result = compress_content(search, session="a", vault=vault)
    assert result.saved_tokens > 0
    assert "99: value 99" in result.content


def test_config_migration_idempotent_preserves_backup(tmp_path):
    old = {"profile": "off", "caveman": "full", "headroom_port": 19991}
    (tmp_path / "config.json").write_text(json.dumps(old))
    settings = Settings.load(tmp_path)
    settings.save(tmp_path)
    saved = json.loads((tmp_path / "config.json").read_text())
    assert saved["schema_version"] == 2
    assert saved["input"]["port"] == 19991
    assert saved["response"]["mode"] == "full"
    assert "caveman" not in saved
    settings.save(tmp_path)
    assert json.loads((tmp_path / "config.v1.json").read_text()) == old
    assert Settings.load(tmp_path).profile == "off"
