"""Command-specific dispatch; unknown flags/formats are never guessed."""
import json
import re
from collections import Counter
from pathlib import Path


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
        if args == ["status"]:
            return "git-status"
        if args == ["log"] or len(args) == 3 and args[:2] == ["log", "-n"] and args[2].isdigit():
            return "git-log"
        if args and args[0] == "diff" and all(
            x in {"--cached", "--staged"} or re.fullmatch(r"(?:--unified=|-U)\d{1,6}", x)
            for x in args[1:]
        ):
            return "diff"
        if args and args[0] in {"add", "commit", "push", "pull", "fetch", "checkout", "switch", "branch", "stash", "worktree"}:
            return "git-action"
        return None
    if name in {"rg", "grep"}:
        if not any(x in {
            "-l", "--files-with-matches", "--files", "--count", "-c",
            "-v", "--invert-match", "--only-matching", "-o", "--vimgrep",
            "--heading", "--count-matches", "--files-without-match",
        } for x in args):
            return "search"
        return None
    if name in {"ls", "tree", "find", "fd"}:
        if any(x in {"-print0", "--print0", "-0", "--json"} for x in args):
            return None
        return "file-list"
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
        kept = [line for line in lines if line.strip() and not line.startswith('  (use "git ')]
        return "\n".join(kept)+"\n"
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
            message = "\n".join(line[4:] if line.startswith("    ") else line for line in body.splitlines())
            output.append(header+"\n"+message+"\n")
        return "\n".join(output)
    if kind == "git-action":
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
    if kind == "file-list":
        if not lines or any("\x00" in line for line in lines):
            return text
        rendered = "\n".join(re.sub(r"[ \t]{2,}", " | ", line.rstrip()) for line in lines)
        return rendered + ("\n" if text.endswith("\n") else "")
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
