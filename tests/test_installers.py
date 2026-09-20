from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_shell_installer_stages_validates_and_rolls_back():
    text = (ROOT / "scripts/install.sh").read_text(encoding="utf-8")
    assert 'uv_version="0.12.17"' in text
    assert "Runtime helper checksum mismatch" in text
    assert "uv-aarch64-apple-darwin.tar.gz" in text
    assert "UTK_UV_ARCHIVE" in text
    assert "/opt/homebrew/bin/uv" in text
    assert 'venv --python 3.11 --seed' in text
    assert "UTK_INSTALL_NO_CLIENTS" in text
    assert "UTK_INSTALL_NO_AUTOSTART" in text
    assert 'UTK_HOME="$utk_root"' in text
    assert "venv.new" in text and "venv.previous" in text
    assert "capabilities >/dev/null" in text
    assert "assets install" in text
    assert "previous runtime restored" in text


    assert 'old_prefix = b"#!" + sys.argv[2].encode() + b"/"' in text
    assert "if data.startswith(old_prefix):" in text
    assert 'if [ -z "${UTK_UV_ARCHIVE:-}" ]; then' in text


def test_powershell_installer_checks_absolute_targets_and_rolls_back():
    text = (ROOT / "scripts/install.ps1").read_text(encoding="utf-8")
    assert "GetFullPath" in text and "StartsWith" in text
    assert "venv.new" in text and "venv.previous" in text
    assert "assets install" in text
    assert "previous runtime restored" in text
