import json

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
    original = "\n".join(f"INFO processing request {i}" for i in range(100))
    first = compress_content(original, session="a", vault=vault)
    assert first.recovery_id
    assert compress_content(original, session="a", vault=vault, profile="off").content == first.content
    assert compress_content(first.content, session="a", vault=vault).fallback == "already_compressed"
    now[0] = 11
    with pytest.raises(RecoveryUnavailable):
        vault.retrieve("a", first.recovery_id)
    assert vault.status()["used_bytes"] == 0
    tiny = RecoveryVault(capacity=16)
    assert compress_content(original, session="a", vault=tiny).content == original


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
