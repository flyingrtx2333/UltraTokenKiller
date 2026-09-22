from pathlib import Path

from ultratokenkiller.config import Settings, choose_port


def test_public_dashboard_does_not_expose_model_proxy(tmp_path):
    import pytest
    settings = Settings(dashboard_host="0.0.0.0")
    settings.save(tmp_path)
    loaded = Settings.load(tmp_path)
    assert loaded.dashboard_host == "0.0.0.0"
    assert loaded.host == "127.0.0.1"
    with pytest.raises(ValueError):
        Settings(host="0.0.0.0").validate()
    with pytest.raises(ValueError):
        Settings(dashboard_host="untrusted.example").validate()


def test_settings_round_trip(tmp_path: Path):
    settings = Settings(dashboard_port=19001, caveman="full")
    settings.save(tmp_path)
    loaded = Settings.load(tmp_path)
    assert loaded.dashboard_port == 19001
    assert loaded.caveman == "full"


def test_choose_port_skips_excluded():
    port = choose_port(29101, excluded={29101})
    assert port != 29101
