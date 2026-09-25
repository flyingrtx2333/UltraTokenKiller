"""Command-specific dispatch; unknown flags/formats are never guessed."""
import json
import re
from collections import Counter
from pathlib import Path


_LS_DATE = re.compile(
    r"\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}\s+(?:\d{4}|\d{2}:\d{2})\s+"
)


def _human_size(size: int) -> str:
    if size >= 1_048_576:
        return f"{size / 1_048_576:.1f}M"
    if size >= 1024:
        return f"{size / 1024:.1f}K"
    return f"{size}B"


def _octal_permissions(value: str) -> str | None:
    if len(value) < 10 or not value.isascii():
        return None
    bits = value.encode("ascii")
    triplets = ((1, 2, 3), (4, 5, 6), (7, 8, 9))
    result = []
    for read, write, execute in triplets:
        result.append(str((4 if bits[read] == 114 else 0) + (2 if bits[write] == 119 else 0)
                          + (1 if bits[execute] in b"xst" else 0)))
    special = (4 if bits[3] in b"sS" else 0) + (2 if bits[6] in b"sS" else 0) + (1 if bits[9] in b"tT" else 0)
    return (str(special) if special else "") + "".join(result)


def _compress_ls(text: str, show_long: bool) -> str:
    entries: list[tuple[bool, str, int, str | None]] = []
    meaningful = 0
    for line in text.splitlines():
        if not line or line.startswith("total "):
            continue
        meaningful += 1
        match = _LS_DATE.search(line)
        if not match:
            # A locale, error, or output format we cannot prove equivalent.
            if line.rstrip().endswith((" .", " ..")):
                continue
            return text
        before = line[:match.start()].split()
        if len(before) < 4 or len(before[0]) < 10:
            return text
        name = line[match.end():]
        if name in {".", ".."}:
            continue
        size = next((int(value) for value in reversed(before) if value.isdigit()), None)
        if size is None:
            # Character and block devices can use major/minor values; preserve unknown shape.
            return text
        permissions = _octal_permissions(before[0]) if show_long else None
        if show_long and permissions is None:
            return text
        entries.append((before[0].startswith("d"), name, size, permissions))
    if not meaningful:
        return text
    if not entries:
        rendered = "(empty)"
    else:
        rendered_lines = []
        for is_dir, name, size, permissions in sorted(entries, key=lambda item: not item[0]):
            label = name + "/" if is_dir else name
            fields = ([permissions] if permissions else []) + [label]
            if not is_dir:
                fields.append(_human_size(size))
            rendered_lines.append("  ".join(fields))
        rendered = "\n".join(rendered_lines)
    return rendered if len(rendered) < len(text) else text


def _compress_tree(text: str) -> str:
    lines = text.splitlines()
    if not lines or "\x00" in text:
        return text
    summary = re.compile(r"^\s*\d+ director(?:y|ies),\s*\d+ files?\s*$")
    if not any(summary.match(line) for line in lines):
        return text
    rendered_lines = [line.rstrip() for line in lines if line.strip() and not summary.match(line)]
    if not rendered_lines:
        return text
    rendered = "\n".join(rendered_lines)
    return rendered if len(rendered) < len(text) else text


def _compress_find(text: str) -> str:
    paths = [line for line in text.splitlines() if line]
    if len(paths) < 3 or "\x00" in text:
        return text
    if any(line.startswith(("find:", "fd:")) or "\n" in line for line in paths):
        return text
    grouped: dict[str, list[str]] = {}
    for path in paths:
        normalized = path.replace("\\", "/")
        if normalized.endswith("/") or normalized in {".", ".."}:
            return text
        parent, separator, name = normalized.rpartition("/")
        if not name or any(character in name for character in "\r\n\x00"):
            return text
        grouped.setdefault(parent or ".", []).append(name)
    output = [f"{len(paths)} files in {len(grouped)} dirs:", ""]
    for parent in sorted(grouped):
        files = grouped[parent]
        output.append(f"{parent}/ {' '.join(files)}")
    rendered = "\n".join(output)
    return rendered if len(rendered) < len(text) else text


_HOST_OUTPUT_FLAGS = {
    "--json", "--jq", "--template", "--web", "--output", "-F", "--paginate",
}


def _host_output_requested(args: list[str]) -> bool:
    return any(
        value in _HOST_OUTPUT_FLAGS
        or value.startswith(("--json=", "--jq=", "--template=", "--output="))
        for value in args
    )


def _hosting_kind(name: str, args: list[str]) -> str | None:
    if _host_output_requested(args):
        return None
    routed_args = list(args)
    if name == "glab":
        while len(routed_args) >= 2 and routed_args[0] in {"-R", "--repo", "-g", "--group"}:
            routed_args = routed_args[2:]
    if len(routed_args) < 2:
        return None
    route = tuple(routed_args[:2])
    if name == "gh":
        return {
            ("pr", "list"): "hosting-list",
            ("pr", "view"): "hosting-view",
            ("pr", "checks"): "hosting-checks",
            ("pr", "status"): "hosting-checks",
            ("issue", "list"): "hosting-list",
            ("issue", "view"): "hosting-view",
            ("run", "list"): "hosting-list",
            ("run", "view"): "hosting-view",
            ("repo", "view"): "hosting-view",
        }.get(route)
    if name == "glab":
        return {
            ("mr", "list"): "hosting-list",
            ("mr", "view"): "hosting-view",
            ("issue", "list"): "hosting-list",
            ("issue", "view"): "hosting-view",
            ("ci", "list"): "hosting-list",
            ("ci", "status"): "hosting-checks",
            ("pipeline", "list"): "hosting-list",
            ("pipeline", "status"): "hosting-checks",
            ("release", "list"): "hosting-list",
            ("release", "view"): "hosting-view",
        }.get(route)
    return None


def _compact_host_list(text: str) -> str:
    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        payload = None
    if isinstance(payload, list):
        rows = []
        for item in payload:
            if not isinstance(item, dict):
                return text
            if item.get("number") is not None:
                identifier = f"#{item['number']}"
            elif item.get("iid") is not None:
                identifier = f"!{item['iid']}"
            else:
                identifier = item.get("id")
            title = item.get("title", item.get("name", item.get("displayTitle")))
            state = item.get("state", item.get("status", item.get("conclusion")))
            author = item.get("author", item.get("user"))
            if isinstance(author, dict):
                author = author.get("login", author.get("username", author.get("name")))
            if identifier is None and title is None:
                return text
            if state not in (None, ""):
                normalized_state = str(state).lower()
                normalized_state = "open" if normalized_state == "opened" else normalized_state
                state = f"[{normalized_state}]"
            fields = [str(value) for value in (state, identifier, title, f"({author})" if author else None) if value not in (None, "")]
            rows.append(" | ".join(fields))
        rendered = "\n".join(rows) + ("\n" if text.endswith("\n") else "")
        return rendered if len(rendered) < len(text) else text

    lines = text.splitlines()
    known_header = bool(lines) and re.search(r"\b(?:STATE|STATUS|TITLE|NAME|ID|NUMBER|BRANCH)\b", lines[0], re.I)
    tabular_rows = len(lines) >= 2 and all("\t" in line for line in lines)
    if not known_header and not tabular_rows:
        return text
    rendered = "\n".join(re.sub(r"(?:\t+| {2,})", " | ", line.rstrip()) for line in lines)
    rendered += "\n" if text.endswith("\n") else ""
    return rendered if len(rendered) < len(text) else text


def _compact_host_view(text: str) -> str:
    try:
        item = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        item = None
    if not isinstance(item, dict):
        return text
    identifier = item.get("number", item.get("iid", item.get("id")))
    title = item.get("title", item.get("name", item.get("displayTitle")))
    if identifier is None and title is None:
        return text
    author = item.get("author", item.get("user"))
    if isinstance(author, dict):
        author = author.get("login", author.get("username", author.get("name")))
    lines = []
    for value in (
        identifier,
        title,
        item.get("state", item.get("status")),
        author,
        item.get("mergeable", item.get("merge_status")),
        item.get("source_branch", item.get("headRefName")),
        item.get("target_branch", item.get("baseRefName")),
        item.get("url", item.get("web_url")),
    ):
        if value not in (None, ""):
            lines.append(str(value))
    labels = item.get("labels")
    if isinstance(labels, list):
        label_names = [value.get("name") if isinstance(value, dict) else value for value in labels]
        label_names = [str(value) for value in label_names if value]
        if label_names:
            lines.append("labels: " + ", ".join(label_names))
    body = item.get("body", item.get("description"))
    if isinstance(body, str) and body.strip():
        lines.extend(("", body.strip()))
    rendered = "\n".join(lines) + ("\n" if text.endswith("\n") else "")
    return rendered if len(rendered) < len(text) else text


def _compact_host_checks(text: str) -> str:
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    if not lines or not any(re.search(r"\b(?:pass|fail|pending|success|queued|running|cancel)\w*\b", line, re.I) for line in lines):
        return text
    rendered = "\n".join(re.sub(r"(?:\t+| {2,})", " | ", line) for line in lines)
    rendered += "\n" if text.endswith("\n") else ""
    return rendered if len(rendered) < len(text) else text


def _compact_gt_log(text: str) -> str:
    def is_node(line: str) -> bool:
        stripped = line.lstrip("│| ")
        return bool(stripped) and stripped[0] in "◉○◯◆●@*"

    if not any(is_node(line) for line in text.splitlines()):
        return text
    rendered = []
    entries = 0
    for line in text.strip().splitlines():
        if is_node(line):
            entries += 1
        if entries > 5:
            break
        line = re.sub(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "", line)
        rendered.append(line.rstrip()[:120])
    if entries > 5:
        rendered.append("... more entries")
    result = "\n".join(rendered)
    return result if len(result) < len(text) else text


def _compact_gt_action(text: str, kind: str) -> str:
    stripped = text.strip()
    if not stripped:
        return text
    if kind == "gt-submit":
        facts = [line.strip() for line in stripped.splitlines() if re.search(r"\b(?:Pushed branch|pull request #\d+)\b", line, re.I)]
        if not facts:
            return text
        result = "\n".join(facts)
    elif kind == "gt-sync":
        synced = [line for line in stripped.splitlines() if re.search(r"\bSynced(?: branch| with remote)\b", line, re.I)]
        deleted = []
        for line in stripped.splitlines():
            match = re.search(r"\bDeleted branch [`\"']?([A-Za-z0-9/_.+@-]+)", line, re.I)
            if match:
                deleted.append(match.group(1))
        if not synced and not deleted:
            return text
        parts = []
        if synced:
            parts.append(f"{len(synced)} synced")
        if deleted:
            parts.append(f"{len(deleted)} deleted ({', '.join(deleted)})")
        result = "ok sync: " + ", ".join(parts)
    elif kind == "gt-restack":
        branches = [line for line in stripped.splitlines() if re.search(r"\b(?:Restacked|Rebased) branch\b", line, re.I)]
        if not branches:
            return text
        result = f"ok restacked {len(branches)} branches"
    else:
        created = next((re.search(r"\bCreated branch [`\"']?([A-Za-z0-9/_.+@-]+)", line, re.I) for line in stripped.splitlines() if re.search(r"\bCreated branch\b", line, re.I)), None)
        if created is None:
            return text
        result = f"ok created {created.group(1)}"
    result += "\n" if text.endswith("\n") else ""
    return result if len(result) < len(text) else text


def command_filter(argv: list[str]) -> str | None:
    if not argv or any(x in {"|", "||", "&&", ";", ">", ">>", "<"} for x in argv):
        return None
    name = Path(argv[0]).stem.lower()
    args = argv[1:]
    if re.fullmatch(r"python(?:3(?:\.\d+)?)?", name) and args[:2] == ["-m", "pytest"]:
        return command_filter(["pytest", *args[2:]])
    machine = {"--json", "--porcelain", "--porcelain=v1", "--porcelain=v2", "--binary", "-z", "--null", "--raw", "--patch", "--no-textconv"}
    if any(x in machine or x.startswith(("--format=", "--pretty=", "--output=", "--junitxml=")) for x in args):
        return None
    if name in {"read", "json", "smart"}:
        return f"native-{name}"
    if name == "git":
        # These global flags preserve the selected command's output schema.
        # Arbitrary -c configuration and external diff programs stay unsupported.
        while args:
            if args[0] == "--no-pager":
                args = args[1:]
            elif args[0] == "-C" and len(args) >= 3:
                args = args[2:]
            else:
                break
        if args and args[0] == "status":
            # Machine-readable status is rejected by the global shape guard above.  Human
            # status variants keep the same semantic sections and can be filtered safely.
            return "git-status"
        if args and args[0] == "log" and not any(
            value in {"--oneline", "--graph", "--stat", "--shortstat", "--numstat", "--name-only", "--name-status"}
            or value.startswith(("--date=", "--decorate="))
            for value in args[1:]
        ):
            # Custom formats are rejected by the global guard.  The remaining default and
            # oneline forms are handled independently by the log filter.
            return "git-log"
        if args and args[0] == "diff":
            raw_shapes = {
                "--stat", "--shortstat", "--numstat", "--name-only", "--name-status",
                "--summary", "--check", "--quiet", "--exit-code", "--word-diff",
                "--color-words", "--dirstat", "--ext-diff",
            }
            if not any(
                value in raw_shapes
                or value.startswith(("--stat=", "--numstat=", "--word-diff=", "--dirstat="))
                for value in args[1:]
            ):
                return "diff"
        if args and args[0] == "show":
            show_args = args[1:]
            raw_show = {
                "--stat", "--shortstat", "--numstat", "--name-only", "--name-status",
                "--summary", "--check", "--quiet", "--format", "--pretty",
            }
            if not any(
                value in raw_show
                or value.startswith(("--format=", "--pretty=", "--stat=", "--numstat="))
                or (":" in value and not value.startswith("--"))
                for value in show_args
            ):
                return "git-show"
        if args and args[0] == "stash":
            if args[1:2] == ["list"]:
                return "git-stash-list"
            if args[1:2] == ["show"]:
                if any(value in {"-p", "--patch", "--word-diff"} or value.startswith("--word-diff=") for value in args[2:]):
                    return "diff" if not any(value.startswith("--word-diff") for value in args[2:]) else None
                return "git-stash-show"
            return "git-stash"
        if args and args[0] == "worktree":
            return "git-worktree-list" if len(args) == 1 or args[1] == "list" else "git-worktree"
        if args and args[0] in {"add", "commit", "push", "pull", "fetch", "checkout", "switch", "branch"}:
            return "git-" + args[0]
        return None
    if name in {"rg", "grep"}:
        if not any(x in {
            "-l", "--files-with-matches", "--files", "--count", "-c",
            "-v", "--invert-match", "--only-matching", "-o", "--vimgrep",
            "--heading", "--count-matches", "--files-without-match",
        } for x in args):
            return "search"
        return None
    if name == "ls":
        if any(x in {"-0", "--zero", "--dired", "--hyperlink", "--json"}
               or x.startswith(("--format=", "--quoting-style=")) for x in args):
            return None
        long_listing = any(
            x in {"--full-time", "--format=long", "--format=verbose"}
            or x.startswith("-") and not x.startswith("--") and any(flag in x[1:] for flag in "lgno")
            for x in args
        )
        return "file-list-ls-long" if long_listing else "file-list-ls"
    if name == "tree":
        if any(x in {"-J", "-X", "--xml", "--json", "-H", "--fromfile"} for x in args):
            return None
        return "file-list-tree"
    if name in {"find", "fd"}:
        unsafe_actions = {
            "-print0", "--print0", "-0", "--json", "-printf", "-fprintf", "-fprint",
            "-fprint0", "-exec", "-execdir", "-ok", "-okdir", "-delete", "-ls", "--exec",
            "--exec-batch", "-x", "-X",
        }
        if any(x in unsafe_actions for x in args):
            return None
        return "file-list-find"
    if name in {"gh", "glab"}:
        return _hosting_kind(name, args)
    if name == "gt" and args:
        if args[0] in {"status", "diff", "show", "add", "commit", "push", "pull", "fetch", "checkout", "switch", "stash", "worktree"}:
            return command_filter(["git", *args])
        if args[0] == "log" and args[1:2] != ["short"]:
            return "gt-log"
        if args[0] in {"submit", "sync", "restack", "create"}:
            return "gt-" + args[0]
        return None
    if name == "pytest" and not any(x.startswith("--junit") for x in args):
        return "pytest"
    if name == "cargo" and args and args[0] == "test":
        return "cargo-test"
    if name == "go" and args and args[0] == "test" and "-json" not in args:
        return "go-test"
    if name in {"jest", "vitest"} and not any(x.startswith("--reporter") for x in args):
        return "js-test"
    structured_test_output = any(
        value == "--reporter"
        or value.startswith("--reporter=")
        or value.startswith("--junit-path")
        for value in args
    )
    watch_mode = any(value in {"--watch", "--watch-all"} for value in args)
    if name == "bun" and args[:1] == ["test"] and not structured_test_output and not watch_mode:
        return "bun-test"
    if name == "deno" and args[:1] == ["test"] and not structured_test_output and not watch_mode:
        return "deno-test"
    if name in {"gradle", "gradlew"} and any(
        part == "test" or "test" in part.lower() for part in args
    ) and not any(value in {"--stacktrace", "--info", "--debug", "--full-stacktrace"} for value in args):
        return "gradle-test"
    if name == "golangci-lint" and args == ["run"]:
        return "golangci"
    if name in {"bun", "deno"} and args[:1] == ["test"]:
        return None
    if name in {"gradle", "gradlew"} and any(
        part == "test" or "test" in part.lower() for part in args
    ):
        return None
    if name == "golangci-lint" and "run" in args:
        return None
    if name in {"rspec", "phpunit", "pest", "paratest"}:
        return "generic-test"
    if name in {"dotnet", "mvn", "mvnw", "gradle", "gradlew", "sbt", "rake", "bun", "deno"} and any(
            part in {"test", "check", "verify"} for part in args):
        return "generic-test"
    if name in {"tsc", "ruff", "mypy", "eslint"}:
        return "diagnostics"
    if name in {"golangci-lint", "rubocop", "phpstan", "sqlfluff", "pylint", "clang-tidy"}:
        return "diagnostics"
    if name in {"npm", "pnpm", "yarn", "pip", "pip3", "uv", "composer", "bundle"} and args:
        if any(x in {"--json", "--parseable", "--silent"} for x in args):
            return None
        return "package"
    if name in {"docker", "kubectl", "oc"} and args and args[0] in {"ps", "images", "get"} and not any(x in {"-o", "--output", "--format", "--watch", "-w"} for x in args):
        return "table"
    if name == "aws" and args and not any(x in {"--output", "--query"} or x.startswith(("--output=", "--query=")) for x in args):
        return "cloud-human"
    return None


def compress_tool(text: str, kind: str) -> str:
    if kind == "diff":
        lines = text.splitlines()
        if not lines or not lines[0].startswith("diff --git ") or not any(line.startswith("@@ ") for line in lines):
            return text
        output = ["Changes:"]
        current_file: str | None = None
        additions = deletions = 0
        in_hunk = False

        def finish_file() -> None:
            nonlocal additions, deletions
            if current_file is not None:
                output.append(f"  +{additions} -{deletions}")
            additions = deletions = 0

        for line in lines:
            if line.startswith("diff --git "):
                finish_file()
                match = re.match(r"diff --git a/(.+) b/(.+)$", line)
                if not match:
                    return text
                current_file = match.group(2)
                output.extend(["", current_file])
                in_hunk = False
            elif line.startswith("@@ "):
                output.append(line)
                in_hunk = True
            elif in_hunk and line.startswith("+"):
                output.append(line)
                additions += 1
            elif in_hunk and line.startswith("-"):
                output.append(line)
                deletions += 1
            elif in_hunk and line.startswith("\\ No newline at end of file"):
                output.append(line)
        finish_file()
        rendered = "\n".join(output).strip() + "\n"
        return rendered if len(rendered) < len(text) else text
    if kind == "search":
        from .compression import _search_compact
        return _search_compact(text)
    lines = text.splitlines()
    if kind == "git-status":
        if not lines or not lines[0].startswith(("On branch ", "HEAD detached ")):
            return text
        # In-progress operations carry instructions whose omission can change the next safe
        # action.  Keep those states in their human form and only remove generic hints.
        state_words = ("rebase in progress", "currently rebasing", "unmerged paths", "cherry-picking", "currently reverting", "currently bisecting")
        if any(word in text.lower() for word in state_words):
            kept = [line for line in lines if line.strip() and not line.lstrip().startswith('(use "git ')]
            return "\n".join(kept) + ("\n" if text.endswith("\n") else "")
        branch = lines[0].removeprefix("On branch ") if lines[0].startswith("On branch ") else lines[0]
        output = [f"* {branch}"]
        section = ""
        status_map = {
            "modified": "M", "new file": "A", "deleted": "D", "renamed": "R",
            "copied": "C", "both modified": "U", "added by us": "U",
            "deleted by us": "U", "deleted by them": "U", "both added": "U",
        }
        for line in lines[1:]:
            stripped = line.strip()
            if stripped.startswith("Changes to be committed:"):
                section = "staged"
            elif stripped.startswith("Changes not staged for commit:"):
                section = "unstaged"
            elif stripped.startswith("Untracked files:"):
                section = "untracked"
            elif stripped.startswith("Unmerged paths:"):
                section = "unmerged"
            elif not stripped or stripped.startswith(("(use \"git ", "no changes added", "nothing added")):
                continue
            elif section == "untracked" and not stripped.startswith("("):
                output.append(f"?? {stripped}")
            elif ":" in stripped and section in {"staged", "unstaged", "unmerged"}:
                label, path = (part.strip() for part in stripped.split(":", 1))
                code = status_map.get(label)
                if code and path:
                    output.append((f"{code}  " if section == "staged" else f" {code} ") + path)
        if len(output) == 1 and "working tree clean" in text:
            output.append("clean - nothing to commit")
        rendered = "\n".join(output) + ("\n" if text.endswith("\n") else "")
        return rendered if len(rendered) < len(text) else text
    if kind == "git-log":
        commits = re.split(r"(?m)(?=^commit [0-9a-f]{40}(?:\s|$))", text)
        if len(commits) < 2 or commits[0].strip():
            return text
        output = []
        for block in commits[1:]:
            header, separator, body = block.partition("\n\n")
            if not separator or "\nAuthor:" not in header or "\nDate:" not in header:
                return text
            # Bodies can carry migration instructions, negation and risk.
            message_lines = [line[4:] if line.startswith("    ") else line for line in body.splitlines()]
            while message_lines and not message_lines[-1]:
                message_lines.pop()
            if not message_lines:
                return text
            author = next(line.removeprefix("Author:").strip() for line in header.splitlines() if line.startswith("Author:"))
            commit_hash = header.splitlines()[0].split()[1]
            subject, *rest = message_lines
            entry = f"{commit_hash[:10]} {subject} | {author}"
            if rest:
                entry += "\n" + "\n".join(rest)
            output.append(entry)
        rendered = "\n\n".join(output) + ("\n" if text.endswith("\n") else "")
        return rendered if len(rendered) < len(text) else text
    if kind == "git-show":
        commits = re.split(r"(?m)(?=^commit [0-9a-f]{40}(?:\s|$))", text)
        if len(commits) != 2 or commits[0].strip():
            return text
        header_and_body, marker, patch = commits[1].partition("\ndiff --git ")
        if not marker:
            return text
        header, separator, body = header_and_body.partition("\n\n")
        if not separator or "\nAuthor:" not in header:
            return text
        commit_hash = header.splitlines()[0].split()[1]
        author = next(line.removeprefix("Author:").strip() for line in header.splitlines() if line.startswith("Author:"))
        messages = [line[4:] if line.startswith("    ") else line for line in body.splitlines()]
        messages = [line for line in messages if line]
        if not messages:
            return text
        compact_patch = compress_tool("diff --git " + patch, "diff")
        if compact_patch == "diff --git " + patch:
            return text
        rendered = f"{commit_hash[:10]} {messages[0]} | {author}\n\n{compact_patch}"
        return rendered if len(rendered) < len(text) else text
    if kind == "git-add":
        # Successful git add is normally silent.  Any text is actionable diagnostic output.
        return text
    if kind == "git-commit":
        from .compression import CRITICAL
        if not text or CRITICAL.search(text):
            return text
        match = re.search(r"(?m)^\[[^\]]*\b([0-9a-f]{7,64})\]\s+(.+)$", text)
        if not match:
            return text
        rendered = f"ok {match.group(1)[:7]}"
        rendered += "\n" if text.endswith("\n") else ""
        return rendered if len(rendered) < len(text) else text
    if kind == "git-pull":
        from .compression import CRITICAL
        if not text or CRITICAL.search(text):
            return text
        if re.search(r"Already up[ -]to[ -]date", text, re.I):
            return "ok (up-to-date)\n" if text.endswith("\n") else "ok (up-to-date)"
        summary = next(
            (line.strip() for line in text.splitlines() if re.search(r"\bfiles? changed\b", line)),
            None,
        )
        if summary:
            files = re.search(r"(\d+) files? changed", summary)
            insertions = re.search(r"(\d+) insertions?\(\+\)", summary)
            deletions = re.search(r"(\d+) deletions?\(-\)", summary)
            rendered = "ok"
            if files:
                rendered += f" {files.group(1)} files"
                rendered += f" +{insertions.group(1) if insertions else '0'}"
                rendered += f" -{deletions.group(1) if deletions else '0'}"
            return rendered + ("\n" if text.endswith("\n") else "")
        return text
    if kind == "git-fetch":
        from .compression import CRITICAL
        if not text or CRITICAL.search(text):
            return text
        refs = sum(1 for line in text.splitlines() if "->" in line or "[new " in line)
        if not refs:
            return text
        rendered = f"ok fetched ({refs} new refs)"
        return rendered + ("\n" if text.endswith("\n") else "")
    if kind in {"git-checkout", "git-switch"}:
        from .compression import CRITICAL
        if not text or CRITICAL.search(text):
            return text
        patterns = (
            (r"Switched to a new branch ['\"]?([^'\"\r\n]+)", "ok {0} (new)"),
            (r"Switched to branch ['\"]?([^'\"\r\n]+)", "ok {0}"),
            (r"Already on ['\"]?([^'\"\r\n]+)", "ok {0}"),
            (r"HEAD is now at\s+([0-9a-f]+)", "ok HEAD {0}"),
        )
        for pattern, template in patterns:
            match = re.search(pattern, text)
            if match:
                rendered = template.format(match.group(1))
                return rendered + ("\n" if text.endswith("\n") else "")
        return text
    if kind == "git-stash":
        from .compression import CRITICAL
        if not text or CRITICAL.search(text):
            return text
        if "No local changes" in text:
            return text
        if re.search(r"Saved working directory|Saved index state", text):
            return "ok stashed\n" if text.endswith("\n") else "ok stashed"
        return text
    if kind == "git-stash-list":
        if not lines or not all(re.match(r"^stash@\{\d+\}:\s+", line) for line in lines):
            return text
        rendered_lines = []
        for line in lines:
            index, rest = line.split(": ", 1)
            message = rest.split(": ", 1)[-1]
            rendered_lines.append(f"{index}: {message}")
        rendered = "\n".join(rendered_lines)
        return rendered if len(rendered) < len(text) else text
    if kind == "git-stash-show":
        file_rows = []
        summary = ""
        for line in lines:
            stripped = line.strip()
            match = re.match(r"^(.+?)\s+\|\s+(Bin|\d+)(.*)$", stripped)
            if match:
                suffix = " (binary)" if match.group(2) == "Bin" else f" {match.group(2)}"
                if "+" in match.group(3):
                    suffix += " +"
                if "-" in match.group(3):
                    suffix += "-"
                file_rows.append(match.group(1).strip() + suffix)
            elif re.search(r"\bfiles? changed\b", stripped):
                summary = stripped.replace("files changed", "changed").replace("file changed", "changed").replace("insertions(+)", "+").replace("insertion(+)", "+").replace("deletions(-)", "-").replace("deletion(-)", "-").replace(",", "")
            elif stripped:
                return text
        if not file_rows:
            return text
        rendered = "\n".join(file_rows + ([summary] if summary else [])) + ("\n" if text.endswith("\n") else "")
        return rendered if len(rendered) < len(text) else text
    if kind == "git-worktree-list":
        if not lines or not all(len(line.split()) >= 3 for line in lines if line.strip()):
            return text
        rendered = "\n".join(" ".join(line.split()) for line in lines if line.strip())
        rendered += "\n" if text.endswith("\n") else ""
        return rendered if len(rendered) < len(text) else text
    if kind == "git-push":
        if not text or re.search(r"(?im)^(?:error:|fatal:|.*\[rejected\])", text):
            return text
        noise = (
            "Enumerating objects:", "Counting objects:", "Compressing objects:",
            "Writing objects:", "Delta compression using", "Total ",
        )
        kept = [line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith(noise)]
        destination = None
        for line in kept:
            match = re.search(r" -> (\S+)", line)
            if match:
                destination = match.group(1)
                break
        if "Everything up-to-date" in text:
            kept.append("ok (up-to-date)")
        elif destination:
            kept.append(f"ok {destination}")
        else:
            return text
        rendered = "\n".join(kept) + ("\n" if text.endswith("\n") else "")
        return rendered if len(rendered) < len(text) else text
    if kind == "git-branch":
        from .compression import CRITICAL
        if not text or CRITICAL.search(text):
            return text
        if re.search(r"(?m)^(?:Deleted branch|branch '.+' set up to track)", text):
            return "ok\n" if text.endswith("\n") else "ok"
        if not all(line.startswith(("* ", "  ", "+ ", "remotes/")) for line in lines if line.strip()):
            return text
        current = ""
        local = []
        remote = []
        for line in lines:
            stripped = line.strip()
            if line.startswith("* "):
                current = line[2:].strip()
            elif stripped.startswith("remotes/"):
                value = stripped.split("/", 2)[-1]
                if not value.startswith("HEAD ") and value not in remote:
                    remote.append(value)
            elif stripped:
                local.append(stripped.removeprefix("+ "))
        if not current:
            return text
        rendered_lines = [f"* {current}", *(f"  {name}" for name in local)]
        remote_only = [name for name in remote if name != current and name not in local]
        if remote_only:
            rendered_lines.append(f"  remote-only ({len(remote_only)}):")
            rendered_lines.extend(f"    {name}" for name in remote_only[:20])
        rendered = "\n".join(rendered_lines) + ("\n" if text.endswith("\n") else "")
        return rendered if len(rendered) < len(text) else text
    if kind == "git-worktree":
        from .compression import CRITICAL
        if not text or CRITICAL.search(text):
            return text
        if re.search(r"(?m)^(?:Preparing worktree|HEAD is now at|Removing worktree)", text):
            return "ok\n" if text.endswith("\n") else "ok"
        known = re.search(r"(?m)^(?:\[[^\]]+ [0-9a-f]+\]|To |From |Updating |Fast-forward|Already up.to.date|Everything up.to.date|Saved working directory|Switched to|Your branch is)", text)
        if not known:
            return text
        rendered_lines: list[str] = []
        for line in text.splitlines():
            compact = re.sub(r"[ \t]{2,}", " | ", line.strip())
            compact = re.sub(
                r", (?=\d+ (?:files? changed|insertions?\(\+\)|deletions?\(-\)))",
                " | ",
                compact,
                count=1,
            )
            rendered_lines.append(compact)
        rendered = "\n".join(rendered_lines)
        rendered += "\n" if text.endswith("\n") else ""
        return rendered if len(rendered) <= len(text) else text
    if kind == "bun-test":
        cleaned = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", text)
        kept = []
        for line in cleaned.splitlines():
            stripped = line.strip()
            if (
                stripped.startswith("✗ ")
                or (stripped.startswith("error:") and "logged between real failures" not in stripped)
                or stripped.startswith(("Expected:", "Received:", "at <anonymous>"))
                or re.fullmatch(r"\d+ (?:pass|skip|todo|fail)", stripped)
                or stripped.startswith("Ran ")
            ):
                kept.append(stripped)
        rendered = "\n".join(dict.fromkeys(kept))
        return rendered + "\n" if rendered else text
    if kind == "deno-test":
        cleaned = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", text)
        kept = []
        for line in cleaned.splitlines():
            stripped = line.strip()
            if (
                re.search(r"=> \./.+:\d+:\d+$", stripped)
                or stripped.startswith("error: AssertionError:")
                or stripped == "[Diff] Actual / Expected"
                or re.match(r"^[+-]\s+\S", stripped)
                or re.match(r"^FAILED\s*\|\s*\d+ passed\s*\|\s*\d+ failed", stripped)
            ):
                kept.append(stripped)
        rendered = "\n".join(dict.fromkeys(kept))
        return rendered + "\n" if rendered else text
    if kind == "gradle-test":
        kept = []
        for line in text.splitlines():
            stripped = line.strip()
            if (
                (" FAILED" in line and not stripped.startswith("BUILD"))
                or re.search(r"(?:AssertionError|NotImplementedError|Exception|Error):", stripped)
                or (
                    re.match(r"at (?:[A-Za-z_]\w*\.)+[A-Za-z_]\w*\([^)]*:\d+\)$", stripped)
                    and not stripped.startswith(("at org.", "at java.", "at kotlin.", "at sun.", "at jdk."))
                )
                or re.match(r"^\d+ tests completed, \d+ failed$", stripped)
                or stripped.startswith("BUILD FAILED")
            ):
                kept.append(stripped)
        rendered = "\n".join(dict.fromkeys(kept))
        return rendered + "\n" if rendered else text
    if kind == "golangci":
        try:
            payload = json.loads(text)
            issues = payload["Issues"]
            if not isinstance(issues, list) or not issues:
                return text
            linters = Counter(item["FromLinter"] for item in issues)
            files = Counter(item["Pos"]["Filename"] for item in issues)
            output = [f"golangci-lint: {len(issues)} issues in {len(files)} files", "Top linters:"]
            output.extend(f"  {name} ({count}x)" for name, count in linters.most_common())
            output.append("Top files:")
            for filename, count in files.most_common():
                output.append(f"  {filename} ({count} issues)")
                file_issues = [item for item in issues if item["Pos"]["Filename"] == filename]
                for linter, linter_count in Counter(item["FromLinter"] for item in file_issues).most_common(3):
                    output.append(f"    {linter} ({linter_count})")
                    first = next(item for item in file_issues if item["FromLinter"] == linter)
                    source = first.get("SourceLines") or []
                    if source:
                        output.append(f"      → {source[0].strip()[:80]}")
            return "\n".join(output) + "\n"
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return text
    if kind in {"pytest", "cargo-test", "go-test", "js-test", "generic-test"}:
        from .compression import CRITICAL
        has_failure = bool(CRITICAL.search(re.sub(r"\b0 (?:failed|failures|errors|warnings)\b", "", text)))
        if kind == "pytest" and (
            re.search(r"^ERROR (?:collecting|at setup|at teardown)\b", text, re.M)
            or re.search(r"\b[1-9]\d* errors?\b", text)
            or "Interrupted:" in text
        ):
            # Collection and fixture errors can have no FAILED line. Keep their
            # traceback and summary intact until this shape has its own parser.
            return text
        if has_failure and kind == "pytest":
            kept = [
                line for line in lines
                if re.match(r"^_+\s+.+\s+_+$", line)
                or re.match(r"^(?:E\s+|>\s+|FAILED\s+)", line)
                or re.search(r"\.py:\d+:\s+(?:AssertionError|[A-Za-z]+Error)", line)
                or re.search(r"\b\d+ failed(?:, \d+ passed)?\b", line)
            ]
            rendered = "\n".join(dict.fromkeys(kept))
            return rendered + "\n" if rendered else text
        if has_failure and kind == "generic-test" and "BUILD FAILURE" in text:
            kept = [
                line for line in lines
                if "<<< FAILURE" in line
                or re.search(r"(?:AssertionFailedError|AssertionError|Exception|Error):", line)
                or re.match(r"^\[ERROR\]\s+(?:Failures:|Tests run:|\S+\.(?:\S+):\d+|Failed to execute goal)", line)
                or "BUILD FAILURE" in line
            ]
            rendered = "\n".join(dict.fromkeys(kept))
            return rendered + "\n" if rendered else text
        if has_failure:
            return text
        if kind == "pytest":
            summary = [line for line in lines if re.search(r"\b\d+ (?:passed|skipped|xfailed|xpassed)\b", line)]
            valid = bool(summary) and any("test session starts" in line or re.match(r"[.s]+\s*\[", line) for line in lines)
            if valid:
                outcomes = [line for line in lines if line.startswith(("XFAIL ", "XPASS "))]
                rendered = "\n".join([*outcomes, summary[-1]]) + "\n"
                return rendered if len(rendered) < len(text) else text
        elif kind == "cargo-test":
            summary = [line for line in lines if line.startswith("test result: ok.")]
            valid = bool(summary)
        elif kind == "go-test":
            summary = [line for line in lines if line.startswith(("ok\t", "?\t", "ok  ", "?   "))]
            valid = bool(summary) and all(line.startswith(("ok", "?", "=== RUN", "--- PASS", "PASS")) or not line.strip() for line in lines)
        elif kind == "js-test":
            summary = [line for line in lines if re.search(r"^\s*(Test Suites:|Tests:|Test Files|Tests\s+|Duration|Time:)", line)]
            valid = bool(summary) and ("PASS" in text or "passed" in text)
        else:
            summary = [line for line in lines if re.search(
                r"(?:\b\d+ examples?, \d+ failures?\b|\bTests run: \d+.*Failures: 0\b|\bBUILD SUCCESS(?:FUL)?\b|\b\d+ tests?, \d+ assertions?, 0 failures?\b|\bOK \(\d+ tests?\))",
                line, re.I)]
            valid = bool(summary)
        return "\n".join(summary)+"\n" if valid else text
    if kind == "diagnostics":
        # Group exact duplicated diagnostic lines; never discard distinct failures.
        diagnostic_lines = [re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", line) for line in lines]
        if not any(re.search(r"(?:error TS\d+|\b[A-Z]\d{3}\b|\berror:)", line) for line in diagnostic_lines):
            return text
        typescript = [
            line for line in diagnostic_lines
            if re.search(r"(?:^|\s)error TS\d+:", line)
            or re.search(r"^Found \d+ errors?", line)
        ]
        if typescript:
            return "\n".join(dict.fromkeys(typescript)) + "\n"
        seen = {}
        for line in diagnostic_lines:
            seen[line] = seen.get(line, 0)+1
        return "\n".join(line+(f" [repeated {count} times]" if count > 1 else "") for line, count in seen.items())+"\n"
    if kind == "table":
        if not lines or not re.search(r"CONTAINER ID|^NAME\s+|^REPOSITORY\s+", lines[0]):
            return text
        # Retain every field and row, only compact column padding.
        return "\n".join(re.sub(r" {2,}", " | ", line.rstrip()) for line in lines)+"\n"
    if kind in {"file-list-ls", "file-list-ls-long"}:
        return _compress_ls(text, show_long=kind.endswith("-long"))
    if kind == "file-list-tree":
        return _compress_tree(text)
    if kind == "file-list-find":
        return _compress_find(text)
    if kind == "hosting-list":
        return _compact_host_list(text)
    if kind == "hosting-view":
        return _compact_host_view(text)
    if kind == "hosting-checks":
        return _compact_host_checks(text)
    if kind == "gt-log":
        return _compact_gt_log(text)
    if kind in {"gt-submit", "gt-sync", "gt-restack", "gt-create"}:
        return _compact_gt_action(text, kind)
    if kind == "package":
        from .compression import CRITICAL
        if CRITICAL.search(re.sub(r"\b0 (?:errors?|warnings?|vulnerabilities)\b", "", text)):
            return text
        kept = [line for line in lines if line.strip() and not re.match(r"^[\s\-\\|/]+$", line)]
        rendered = "\n".join(kept) + ("\n" if text.endswith("\n") else "")
        return rendered if len(rendered) < len(text) else text
    if kind == "cloud-human":
        if not lines or not any("|" in line for line in lines):
            return text
        rendered = "\n".join(re.sub(r"\s*\|\s*", " | ", line.strip()) for line in lines if line.strip("+- "))
        return rendered + ("\n" if text.endswith("\n") else "")
    return text
