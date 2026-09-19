from pathlib import Path

from ultratokenkiller.config import Settings, choose_port


def test_settings_round_trip(tmp_path: Path):
    settings = Settings(dashboard_port=19001, caveman="full")
    settings.save(tmp_path)
    loaded = Settings.load(tmp_path)
    assert loaded.dashboard_port == 19001
    assert loaded.caveman == "full"


def test_choose_port_skips_excluded():
    port = choose_port(29101, excluded={29101})
    assert port != 29101

