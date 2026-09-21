from ultratokenkiller.tool_filters import command_filter, compress_tool


def test_ls_long_matches_fixed_human_shape_and_preserves_facts():
    raw = (
        "total 16\n"
        "drwxr-xr-x  2 user  staff    64 Jan  1 12:00 src\n"
        "-rw-r--r--  1 user  staff  1234 Jan  1 12:00 README file.md\n"
        "-rwxr-xr-x  1 user  staff   500 Dec 25  2024 build.sh\n"
    )
    compact = compress_tool(raw, "file-list-ls-long")
    assert compact == "755  src/\n644  README file.md  1.2K\n755  build.sh  500B\n"


def test_ls_unknown_locale_and_failure_are_unchanged():
    localized = "-rw-r--r-- 1 user staff 1234 9月 21 12:00 README.md\n"
    failure = "ls: cannot access 'missing': No such file or directory\n"
    assert compress_tool(localized, "file-list-ls") == localized
    assert compress_tool(failure, "file-list-ls") == failure


def test_tree_only_removes_recognized_summary():
    raw = ".\n├── src\n│   └── main.py\n└── README.md\n\n1 directory, 2 files\n"
    assert compress_tool(raw, "file-list-tree") == ".\n├── src\n│   └── main.py\n└── README.md\n"
    unknown = ".\n+-- src\nsummary unavailable\n"
    assert compress_tool(unknown, "file-list-tree") == unknown


def test_find_groups_paths_without_losing_names():
    raw = "".join(f"src/components/feature/file_{index:02}.py\n" for index in range(20))
    compact = compress_tool(raw, "file-list-find")
    for fact in ("src/components/feature/", "file_00.py", "file_19.py"):
        assert fact in compact
    assert len(compact) < len(raw)


def test_find_failures_and_machine_or_mutating_actions_pass_through():
    failure = "find: missing: No such file or directory\n"
    assert compress_tool(failure, "file-list-find") == failure
    assert command_filter(["find", ".", "-print0"]) is None
    assert command_filter(["find", ".", "-delete"]) is None
    assert command_filter(["find", ".", "-exec", "cat", "{}", ";"]) is None
    assert command_filter(["tree", "-J"]) is None
    assert command_filter(["ls", "--format=commas"]) is None


def test_file_list_dispatch_is_command_specific():
    assert command_filter(["ls"]) == "file-list-ls"
    assert command_filter(["ls", "-la"]) == "file-list-ls-long"
    assert command_filter(["tree", "src"]) == "file-list-tree"
    assert command_filter(["fd", "py", "src"]) == "file-list-find"
