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
        if args and args[0] in {"add", "commit", "push", "pull", "fetch", "checkout", "switch", "branch", "stash", "worktree"}:
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
    if name == "gh" and args and args[0] in {"pr", "issue", "run", "repo"}:
        if any(x in {"--json", "--jq", "--template", "--web"} for x in args):
            return None
        return "gh-human"
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
        summary = next(
            (line.strip() for line in text.splitlines() if re.search(r"\bfiles? changed\b", line)),
            "",
        )
        rendered = f"ok {match.group(1)[:7]} {match.group(2)}"
        if summary:
            rendered += "\n" + re.sub(r",\s+", " | ", summary)
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
            rendered = "ok " + re.sub(r",\s+", " | ", summary)
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
    if kind in {"git-push", "git-branch", "git-worktree"}:
        from .compression import CRITICAL
        if not text or CRITICAL.search(text):
            return text
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
            summary = [line for line in lines if re.search(r"\b\d+ passed\b", line)]
            valid = bool(summary) and any("test session starts" in line or re.match(r"[.s]+\s*\[", line) for line in lines)
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
    if kind == "gh-human":
        if not lines or any(line.lstrip().startswith(("{", "[")) for line in lines):
            return text
        rendered = "\n".join(re.sub(r"[ \t]{2,}", " | ", line.rstrip()) for line in lines)
        return rendered + ("\n" if text.endswith("\n") else "")
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
