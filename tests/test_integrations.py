from pathlib import Path

from ultratokenkiller.integrations import CodexAdapter, HermesAdapter, START


def test_codex_enable_is_idempotent_and_disable_preserves_user_config(tmp_path: Path):
    root = tmp_path / "codex"
    root.mkdir()
    config = root / "config.toml"
    config.write_text('model = "gpt-test"\nmodel_provider = "openai"\ndeveloper_instructions = "Keep my rule."\n[features]\napps = true\n', encoding="utf-8")
    adapter = CodexAdapter(root)
    adapter.enable(18788, tmp_path / "backups")
    adapter.enable(18788, tmp_path / "backups")
    text = config.read_text(encoding="utf-8")
    assert text.count(START) == 1
    assert 'base_url = "http://127.0.0.1:18788/v1"' in text
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib
    parsed = tomllib.loads(text)
    assert parsed["model_provider"] == "utk"
    assert "Keep my rule." in parsed["developer_instructions"]
    adapter.disable()
    restored = config.read_text(encoding="utf-8")
    assert START not in restored
    assert 'model = "gpt-test"' in restored
    assert 'model_provider = "openai"' in restored
    assert 'developer_instructions = "Keep my rule."' in restored
    assert 'apps = true' in restored


def test_hermes_refuses_non_openai_provider(tmp_path: Path):
    root = tmp_path / "hermes"
    root.mkdir()
    (root / "config.yaml").write_text("model:\n  provider: anthropic\n", encoding="utf-8")
    adapter = HermesAdapter(root)
    state = adapter.enable(18788, tmp_path / "backups")
    assert not state.supported
    assert START not in (root / "config.yaml").read_text(encoding="utf-8")


def test_hermes_enable_restores_existing_model_fields(tmp_path: Path):
    root = tmp_path / "hermes"
    root.mkdir()
    config = root / "config.yaml"
    original = "model:\n  provider: openai\n  default: gpt-test\n  coding_instructions: keep-this\ntools:\n  enabled: true\n"
    config.write_text(original, encoding="utf-8")
    adapter = HermesAdapter(root)
    assert adapter.enable(18788, tmp_path / "backups").enabled
    enabled = config.read_text(encoding="utf-8")
    assert enabled.count("model:") == 1
    assert "provider: custom" in enabled
    assert "default: gpt-test" in enabled
    adapter.disable()
    restored = config.read_text(encoding="utf-8")
    assert "provider: openai" in restored
    assert "coding_instructions: keep-this" in restored
    assert "enabled: true" in restored
