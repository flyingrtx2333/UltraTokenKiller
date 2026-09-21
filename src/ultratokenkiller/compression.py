"""Content-aware native compressors. Lossy output requires a live recovery vault."""
from __future__ import annotations

import ast
import json
import re
import statistics
from dataclasses import replace

from .contracts import CompressionResult
from .engines import estimate_tokens
from .recovery import RecoveryVault

CRITICAL = re.compile(r"\b(error|fail(?:ed|ure)?|fatal|exception|warning|denied|timeout|panic|security|vulnerability|not found|cannot|must not)\b", re.I)


def classify(text: str, hint: str | None = None) -> str:
    if hint == "image":
        return "image"
    if hint and hint.startswith("tool:"):
        return hint
    if hint in {"search", "diff", "log"}:
        return hint
    stripped = text.lstrip()
    try:
        value = json.loads(text)
        if isinstance(value, (dict, list)):
            return "json"
    except (ValueError, RecursionError):
        pass
    if stripped.startswith(("diff --git ", "--- ")) and "\n@@ " in text:
        return "diff"
    if hint and hint.startswith("code:"):
        return hint
    if re.search(r"(?m)^(?:async )?def \w+\(|^class \w+.*:", text):
        return "code:python"
    lines = text.splitlines()
    if len(lines) > 3 and sum(bool(re.search(r"\b(INFO|DEBUG|WARN|ERROR|TRACE|FATAL)\b", line)) for line in lines) >= len(lines) / 3:
        return "log"
    if len(lines) > 3 and sum(bool(re.match(r".+?:\d+(?::\d+)?:", line)) for line in lines) >= len(lines) * .8:
        return "search"
    table_lines = [line for line in lines if line.strip()]
    if len(table_lines) >= 4:
        columns = [len(line.split("|")) for line in table_lines]
        if min(columns) >= 3 and len(set(columns)) == 1:
            return "table"
    return "text"


def _table_compact(text: str) -> str:
    """Collapse only exact consecutive rows in a confidently parsed pipe table."""
    lines = text.splitlines()
    output: list[str] = []
    previous: str | None = None
    repeated = 0
    for line in lines:
        if line == previous:
            repeated += 1
            continue
        if repeated:
            output.append(f"[UTK: {repeated} repeated table rows omitted]")
            repeated = 0
        output.append(line)
        previous = line
    if repeated:
        output.append(f"[UTK: {repeated} repeated table rows omitted]")
    return "\n".join(output) + ("\n" if text.endswith("\n") else "")


def _json_compact(text: str) -> str:
    value = json.loads(text)
    def visit(item):
        if isinstance(item, dict):
            return {key: visit(value) for key, value in item.items()}
        if not isinstance(item, list):
            return item
        if len(item) <= 12:
            return [visit(value) for value in item]
        keep = {0, 1, len(item)-2, len(item)-1}
        for i, row in enumerate(item):
            if CRITICAL.search(json.dumps(row, ensure_ascii=False)):
                keep.add(i)
        if all(isinstance(row, dict) for row in item):
            schemas = {}
            for i, row in enumerate(item):
                schema = tuple(sorted(row))
                if schema not in schemas:
                    schemas[schema] = i
                    keep.add(i)
            for key in set().union(*(row.keys() for row in item)):
                categories = {}
                for i, row in enumerate(item):
                    value = row.get(key)
                    if value is None or isinstance(value, (str, bool)):
                        categories.setdefault((type(value).__name__, value), i)
                if len(categories) <= min(32, len(item) // 2):
                    keep.update(categories.values())
                values = [(i, row[key]) for i, row in enumerate(item) if isinstance(row.get(key), (int, float)) and not isinstance(row.get(key), bool)]
                if len(values) < 5 or re.search(r"(^id$|_id$|timestamp|time$)", key):
                    continue
                median = statistics.median(v for _, v in values)
                mad = statistics.median(abs(v-median) for _, v in values)
                for i, number in values:
                    if (mad == 0 and number != median) or (mad > 0 and abs(number-median) > 6*mad):
                        keep.add(i)
        result = []
        omitted = 0
        for i, row in enumerate(item):
            if i in keep:
                if omitted:
                    result.append({"_utk_omitted_records": omitted})
                    omitted = 0
                result.append(visit(row))
            else:
                omitted += 1
        if omitted:
            result.append({"_utk_omitted_records": omitted})
        return result
    return json.dumps(visit(value), ensure_ascii=False, separators=(",", ":"))


def _log_compact(text: str) -> str:
    lines = text.splitlines()
    keep = set(range(min(1, len(lines)))) | set(range(max(0, len(lines)-1), len(lines)))
    for i, line in enumerate(lines):
        if CRITICAL.search(line) or line.startswith(("Traceback", "  File ", "Caused by:", "\tat ")):
            keep.update(range(max(0, i-1), min(len(lines), i+2)))
    seen = set()
    for i, line in enumerate(lines):
        template = re.sub(r"\b\d+(?:[.:/-]\d+)*\b", "#", line)
        if template not in seen:
            seen.add(template)
            keep.add(i)
    output = []
    removed = 0
    for i, line in enumerate(lines):
        if i in keep:
            if removed:
                output.append(f"[{removed} repeated]")
                removed = 0
            output.append(line)
        else:
            removed += 1
    if removed:
        output.append(f"[{removed} repeated]")
    return "\n".join(output) + ("\n" if text.endswith("\n") else "")


def _python_compact(text: str, query: str = "") -> str:
    tree = ast.parse(text)
    lines = text.splitlines(keepends=True)
    replacements = []
    def visit(node):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            if node.name and re.search(rf"\b{re.escape(node.name)}\b", query):
                return
            first = node.body[0]
            # Single-line functions and signatures sharing a body line are untouched.
            if first.lineno > node.lineno and len(node.body) > 1:
                start = first.lineno-1
                indent = re.match(r"\s*", lines[start])[0]
                replacements.append((start, node.end_lineno, indent+"pass  # UTK: body available through recovery\n"))
            return
        for child in ast.iter_child_nodes(node):
            visit(child)
    visit(tree)
    for start, end, replacement in reversed(sorted(replacements)):
        lines[start:end] = [replacement]
    result = "".join(lines)
    ast.parse(result)
    return result


def _diff_compact(text: str) -> str:
    if not text.startswith(("diff --git ", "--- ")) or "\n@@ " not in text:
        return text
    # Preserve all file/hunk headers and changed lines. Explicitly mark omitted context.
    output = []
    omitted = 0
    for line in text.splitlines(keepends=True):
        if line.startswith(" "):
            omitted += 1
            continue
        if omitted:
            output.append(f"[UTK: {omitted} context omitted; summary]\n")
            omitted = 0
        output.append(line)
    if omitted:
        output.append(f"[UTK: {omitted} context omitted; summary]\n")
    return "".join(output)


def _search_compact(text: str) -> str:
    lines = text.splitlines()
    groups: dict[str, list[tuple[str | None, str]]] = {}
    for line in lines:
        numbered = re.match(r"^(.*?):(\d+(?::\d+)?):(.*)$", line)
        if numbered:
            groups.setdefault(numbered[1], []).append((numbered[2], numbered[3]))
            continue
        # Frozen RTK also accepts grep/rg's captured human shape `path:text`.
        # Preserve the whole match text and group only an unambiguous path
        # prefix; drive letters are consumed before looking for the separator.
        plain = re.match(r"^((?:[A-Za-z]:[\\/])?[^:]+):(.*)$", line)
        if not plain or not plain[1].strip() or not plain[2]:
            return text
        groups.setdefault(plain[1], []).append((None, plain[2]))
    output = []
    for path, hits in groups.items():
        output.append(path)
        visible = hits
        omitted = 0
        if len(hits) > 20:
            visible = hits[:8] + hits[-8:]
            omitted = len(hits) - len(visible)
        for index, (location, content) in enumerate(visible):
            if omitted and index == 8:
                output.append(f"  [UTK: {omitted} middle hits omitted]")
            output.append(f"  {location + ': ' if location else ''}{content}")
    rendered = "\n".join(output) + ("\n" if text.endswith("\n") else "")
    return rendered if len(rendered) < len(text) else text


def compress_content(text: str, *, session: str, vault: RecoveryVault, profile="safe", hint=None, query="", home=None) -> CompressionResult:
    before = estimate_tokens(text)
    kind = classify(text, hint)
    plain = CompressionResult(text, kind, before, before)
    def unchanged(reason):
        return vault.pin_passthrough(session, replace(plain, fallback=reason))
    # A prior transform wins across profile switches, protecting an already sent prefix.
    previous = vault.lookup(session, text)
    if previous:
        return previous
    if vault.owns_rendering(session, text):
        return replace(plain, fallback="already_compressed")
    if profile == "off":
        return unchanged("disabled")
    processors = {"json": _json_compact, "log": _log_compact,
                  "diff": _diff_compact, "search": _search_compact,
                  "table": _table_compact}
    processor = processors.get(kind)
    if kind == "code:python":
        processor = lambda value: _python_compact(value, query)
    if kind == "text" and query:
        from .text_compression import summarize_text
        processor = lambda value: summarize_text(value, query, home=home, aggressive=profile == "aggressive")
    if kind.startswith("tool:"):
        from .tool_filters import compress_tool
        processor = lambda value: compress_tool(value, kind.split(":", 1)[1])
    if kind.startswith("code:") and kind != "code:python":
        from .code_compression import summarize_code
        processor = lambda value: summarize_code(value, kind.split(":", 1)[1], query=query)
    if kind == "image":
        from .image_compression import compress_data_url
        processor = lambda value: compress_data_url(value, query, profile == "aggressive")
    if processor is None:
        return unchanged("compressor_not_ready")
    try:
        candidate = processor(text)
        def make(handle):
            if kind == "json":
                content = json.dumps({"_utk_recovery": handle, "data": json.loads(candidate)}, ensure_ascii=False, separators=(",", ":"))
            elif kind == "image":
                content = candidate
            else:
                marker = f"UTK retrieve: {handle}"
                prefix = "# " if kind in {"code:python", "code:perl"} else "// " if kind.startswith("code:") else ""
                content = candidate.rstrip()+"\n"+prefix+marker+"\n"
            return CompressionResult(content, kind, before, estimate_tokens(content), recovery_id=handle,
                                     preserved=("original_available", "content_boundaries"))
        result = vault.put(session, text, make)
        return result or unchanged("not_smaller_or_memory_full")
    except Exception:
        return unchanged("compression_error")
