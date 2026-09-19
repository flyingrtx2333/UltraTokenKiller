import sys

from ultratokenkiller.dependencies import _checksum_for, _rtk_asset_name


def test_checksum_parser_accepts_standard_format():
    assert _checksum_for("abc123  rtk-x86_64-pc-windows-msvc.zip\n", "rtk-x86_64-pc-windows-msvc.zip") == "abc123"


def test_current_platform_has_rtk_asset():
    name = _rtk_asset_name()
    assert name.startswith("rtk-")
    assert name.endswith((".zip", ".tar.gz"))
