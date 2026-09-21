from ultratokenkiller.compression import _search_compact
from ultratokenkiller.tool_filters import command_filter, compress_tool


def test_frozen_rtk_human_search_shape_groups_files_and_keeps_matches():
    raw = (
        "src/a.py:target one with enough explanatory content\n"
        "src/a.py:target two with enough explanatory content\n"
        "src/b.py:target three with enough explanatory content\n"
        "src/b.py:target four with enough explanatory content\n"
    )

    result = compress_tool(raw, "search")

    assert result == (
        "src/a.py\n"
        "  target one with enough explanatory content\n"
        "  target two with enough explanatory content\n"
        "src/b.py\n"
        "  target three with enough explanatory content\n"
        "  target four with enough explanatory content\n"
    )


def test_search_preserves_numbered_locations_and_windows_drive_paths():
    raw = (
        "C:\\work\\a.py:12:target: detail\n"
        "C:\\work\\a.py:18:second target\n"
    )

    result = _search_compact(raw)

    assert "C:\\work\\a.py" in result
    assert "12: target: detail" in result
    assert "18: second target" in result


def test_search_unknown_and_machine_shapes_pass_through():
    unknown = "binary-ish output without a file separator\n"
    failure = "rg: missing/path: IO error: path not found\n"

    assert _search_compact(unknown) == unknown
    assert _search_compact(failure) == failure
    assert command_filter(["rg", "--json", "target", "."]) is None
    assert command_filter(["rg", "--count", "target", "."]) is None
    assert command_filter(["grep", "-v", "target", "a.txt"]) is None


def test_search_commands_accept_frozen_default_human_invocation():
    assert command_filter(["rg", "target", "src"]) == "search"
    assert command_filter(["grep", "target", "a.txt", "b.txt"]) == "search"
