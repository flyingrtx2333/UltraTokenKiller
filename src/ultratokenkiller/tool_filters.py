"""Command-specific dispatch; unknown flags/formats are never guessed."""
import re
from pathlib import Path


def command_filter(argv: list[str]) -> str | None:
    if not argv or any(x in {"|", "||", "&&", ";", ">", ">>", "<"} for x in argv):
        return None
    name = Path(argv[0]).stem.lower()
    args = argv[1:]
    machine = {"--json", "--porcelain", "--porcelain=v1", "--porcelain=v2", "--binary", "-z", "--null", "--raw", "--patch", "--no-textconv"}
    if any(x in machine or x.startswith(("--format=", "--pretty=", "--output=", "--junitxml=")) for x in args):
        return None
    if name == "git":
        if args == ["status"]:
            return "git-status"
        if args == ["log"] or len(args) == 3 and args[:2] == ["log", "-n"] and args[2].isdigit():
            return "git-log"
        if args == ["diff"]:
            return "diff"
        return None
    if name in {"rg", "grep"}:
        if any(x in {"-n", "--line-number"} for x in args) and not any(x in {"-l", "--files-with-matches", "--files", "--count", "-c", "-v", "--invert-match"} for x in args):
            return "search"
        return None
    if name == "pytest" and not any(x.startswith("--junit") for x in args):
        return "pytest"
    if name == "cargo" and args and args[0] == "test":
        return "cargo-test"
    if name == "go" and args and args[0] == "test" and "-json" not in args:
        return "go-test"
    if name in {"jest", "vitest"} and not any(x.startswith("--reporter") for x in args):
        return "js-test"
    if name in {"tsc", "ruff", "mypy", "eslint"}:
        return "diagnostics"
    if name in {"docker", "kubectl", "oc"} and args and args[0] in {"ps", "images", "get"} and not any(x in {"-o", "--output", "--format", "--watch", "-w"} for x in args):
        return "table"
    return None


def compress_tool(text: str, kind: str) -> str:
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
            subject = next((line.strip() for line in body.splitlines() if line.strip()), "")
            output.append(header+"\n    "+subject+"\n")
        return "\n".join(output)
    if kind in {"pytest", "cargo-test", "go-test", "js-test"}:
        from .compression import CRITICAL
        if CRITICAL.search(re.sub(r"\b0 (?:failed|failures|errors|warnings)\b", "", text)):
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
        else:
            summary = [line for line in lines if re.search(r"^\s*(Test Suites:|Tests:|Test Files|Tests\s+|Duration|Time:)", line)]
            valid = bool(summary) and ("PASS" in text or "passed" in text)
        return "\n".join(summary)+"\n" if valid else text
    if kind == "diagnostics":
        # Group exact duplicated diagnostic lines; never discard distinct failures.
        if not any(re.search(r"(?:error TS\d+|\b[A-Z]\d{3}\b|\berror:)", line) for line in lines):
            return text
        seen = {}
        for line in lines:
            seen[line] = seen.get(line, 0)+1
        return "\n".join(line+(f" [repeated {count} times]" if count > 1 else "") for line, count in seen.items())+"\n"
    if kind == "table":
        if not lines or not re.search(r"CONTAINER ID|^NAME\s+|^REPOSITORY\s+", lines[0]):
            return text
        # Retain every field and row, only compact column padding.
        return "\n".join(re.sub(r" {2,}", " | ", line.rstrip()) for line in lines)+"\n"
    return text
