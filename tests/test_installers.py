from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_shell_installer_stages_validates_and_rolls_back():
    text = (ROOT / "scripts/install.sh").read_text(encoding="utf-8")
    assert "venv.new" in text and "venv.previous" in text
    assert "capabilities >/dev/null" in text
    assert "assets install" in text
    assert "previous runtime restored" in text


def test_powershell_installer_checks_absolute_targets_and_rolls_back():
    text = (ROOT / "scripts/install.ps1").read_text(encoding="utf-8")
    assert "GetFullPath" in text and "StartsWith" in text
    assert "venv.new" in text and "venv.previous" in text
    assert "assets install" in text
    assert "previous runtime restored" in text
