"""Content-aware native compressors. Lossy output requires a live recovery vault."""
from __future__ import annotations

import ast
import hashlib
import json
import re
import statistics
from dataclasses import replace

from .contracts import CompressionResult
from .engines import estimate_tokens
from .recovery import RecoveryVault
from .text_compression import _collapse_exact_line_runs

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
    if re.match(r"(?is)^<(?:!doctype\s+html|html\b|div\b|table\b|ul\b|ol\b|section\b|article\b)", stripped) and "</" in stripped:
        return "html"
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


def _html_compact(text: str) -> str:
    """Collapse only identical, self-contained HTML rows; preserve all other markup."""
    if re.search(r"(?i)<(?:script|style|pre|textarea|template)\b", text):
        return text
    lines = text.splitlines(keepends=True)
    output = []
    index = 0
    row = re.compile(r"\s*<(li|tr|p|div|span)\b[^>]*>.*?</\1>\s*", re.I)
    while index < len(lines):
        end = index + 1
        while end < len(lines) and lines[end] == lines[index]:
            end += 1
        count = end - index
        line = lines[index]
        if count >= 3 and row.fullmatch(line) and not CRITICAL.search(line):
            output.append(line)
            newline = "\r\n" if line.endswith("\r\n") else "\n"
            output.append(f"<!-- UTK: identical HTML row repeated {count - 1} more times -->{newline}")
        else:
            output.extend(lines[index:end])
        index = end
    candidate = "".join(output)
    return candidate if len(candidate) < len(text) else text


def _processor_for_kind(kind: str, query: str, home, profile: str):
    processors = {"json": _json_compact, "log": _log_compact, "html": _html_compact,
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
    return processor


_MIXED_PROTECTED = re.compile(
    r"(?ms)(^```[^\r\n]*\r?\n.*?^```[ \t]*(?:\r?\n|$)|"
    r"<system-reminder\b[^>]*>.*?</system-reminder>)", re.I)
_SEARCH_LINE = re.compile(r".+?:\d+(?::\d+)?:")
_LOG_LINE = re.compile(r"\b(INFO|DEBUG|WARN|ERROR|TRACE|FATAL)\b", re.I)
_SEARCH_CONTEXT_LINE = re.compile(r"\S+[-:]\d+[-:].+")


def _mixed_line_kind(line: str) -> str:
    stripped = line.strip()
    if _SEARCH_LINE.match(stripped) or _SEARCH_CONTEXT_LINE.match(stripped):
        return "search"
    if re.match(r"(?:\d{4}-\d\d-\d\d\S*\s+)?(?:INFO|DEBUG|WARN|ERROR|TRACE|FATAL)\b", stripped, re.I):
        return "log"
    if stripped.startswith("<") and re.match(r"</?[A-Za-z][^>]*>", stripped):
        return "html"
    if stripped.count("|") >= 2:
        return "table"
    return "text"


def _split_mixed_plain(chunk: str) -> list[tuple[str, str]]:
    if re.search(r"(?i)<(?:script|style|pre|textarea|template)\b", chunk):
        return [(chunk, "protected")]
    lines = chunk.splitlines(keepends=True)
    result: list[tuple[str, str]] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            result.append((line, "separator"))
            index += 1
            continue
        if line.lstrip().startswith(("[", "{")):
            # Decode once from a bounded prefix. Trying every successive line
            # made large non-JSON tool outputs quadratic to scan.
            source = "".join(lines[index:index + 1000])[:256_000]
            try:
                decoded, offset = json.JSONDecoder().raw_decode(source.lstrip())
                offset += len(source) - len(source.lstrip())
                line_end = source.find("\n", offset)
                if line_end < 0:
                    line_end = len(source)
                if line_end == len(source) and len(source) == 256_000:
                    raise ValueError("JSON boundary may be truncated")
                if isinstance(decoded, (dict, list)) and not source[offset:line_end].strip():
                    count = source[:line_end].count("\n") + 1
                    result.append(("".join(lines[index:index + count]), "section"))
                    index += count
                    continue
            except (ValueError, RecursionError):
                pass
        kind = _mixed_line_kind(line)
        end = index + 1
        while end < len(lines) and lines[end].strip() and _mixed_line_kind(lines[end]) == kind:
            end += 1
        result.append(("".join(lines[index:end]), "section"))
        index = end
    return result


def _compress_mixed_sections(text: str, query: str, home, profile: str) -> str | None:
    """Compress independently recognizable sections without changing protected boundaries."""
    parts: list[tuple[str, str]] = []
    for chunk in _MIXED_PROTECTED.split(text):
        if not chunk:
            continue
        if chunk.lower().startswith("<system-reminder"):
            parts.append((chunk, "protected"))
        elif chunk.startswith("```"):
            parts.append((chunk, "fence"))
        else:
            if re.search(r"(?m)^```|<system-reminder\b", chunk, re.I):
                return None  # An unclosed protected block must remain untouched.
            parts.extend(_split_mixed_plain(chunk))

    kinds = set()
    for value, role in parts:
        if role == "section" and value.strip():
            kinds.add(classify(value.strip()))
        elif role == "fence":
            kinds.add("code")
        elif role == "protected":
            kinds.add("protected")
    if len(kinds) < 2:
        return None

    rendered = []
    changed = False
    for value, role in parts:
        if role == "fence":
            lines = value.splitlines(keepends=True)
            language = lines[0].lstrip("`").strip().lower()
            body = "".join(lines[1:-1])
            processor = _processor_for_kind(f"code:{language}", query, home, profile)
            if language not in {"python", "javascript", "typescript", "tsx", "go", "rust", "java", "c", "cpp", "perl"}:
                processor = None
            if processor is not None and body.strip():
                try:
                    compact = processor(body)
                except Exception:
                    compact = body
                if body.endswith("\n") and not compact.endswith("\n"):
                    compact += "\n"
                if len(compact) < len(body):
                    value = lines[0] + compact + lines[-1]
                    changed = True
        elif role == "section" and value.strip():
            core = value.strip()
            kind = classify(core)
            lines = core.splitlines()
            if kind == "log" and not all(_LOG_LINE.search(line) for line in lines):
                kind = "text"
            if kind == "search" and not all(_SEARCH_LINE.match(line) for line in lines):
                kind = "text"
            processor = _processor_for_kind(kind, query, home, profile) if kind != "text" else None
            if kind == "text" and not CRITICAL.search(core):
                processor = _collapse_exact_line_runs
            if processor is not None:
                try:
                    compact = processor(core)
                except Exception:
                    compact = core
                if len(compact) < len(core):
                    prefix = value[:len(value) - len(value.lstrip())]
                    suffix = value[len(value.rstrip()):]
                    value = prefix + compact + suffix
                    changed = True
        rendered.append(value)
    return "".join(rendered) if changed else None


def _duplicate_reference(previous: CompressionResult, text: str) -> CompressionResult | None:
    if not previous.recovery_id:
        return None
    if previous.content_type == "json":
        reference = json.dumps(
            {"_utk_duplicate": True, "_utk_recovery": previous.recovery_id},
            separators=(",", ":"),
        )
    else:
        reference = f"UTK duplicate result; retrieve previous output with handle: {previous.recovery_id}"
    before = estimate_tokens(text)
    after = estimate_tokens(reference)
    if after >= before:
        return None
    return replace(
        previous,
        content=reference,
        before_tokens=before,
        after_tokens=after,
        fallback=None,
        preserved=("original_available", "previous_result_reference"),
    )


_REPEAT_PATH_OR_ID = re.compile(
    r"(?:\b[A-Z]:[\\/]|(?<!\w)(?:\.\.?[\\/]|[\w.-]+[\\/])[\w./-]+|\b[\w./-]+:\d+(?::\d+)?\b|\b(?:id|uuid|request[_ -]?id|trace[_ -]?id|session[_ -]?id|commit|hash)\s*[:=]\s*\S+|\b[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\b)",
    re.I,
)


def _repeat_line_is_safe(line: str) -> bool:
    value = line.strip()
    return bool(value) and not CRITICAL.search(value) and not _REPEAT_PATH_OR_ID.search(value)


def _repeated_segment_reference(text: str, *, session: str, vault: RecoveryVault, kind: str) -> CompressionResult | None:
    """Replace one sizeable exact, non-critical line span seen in this session."""
    if not session:
        return None
    lines = text.splitlines(keepends=True)
    if len(lines) < 4:
        return None

    # Index a bounded set of recent originals. Exact line equality and protected
    # anchors avoid fuzzy deletion of paths, IDs, line numbers, or failure details.
    windows: dict[bytes, list[tuple[str, list[str], int]]] = {}
    indexed = 0
    for handle, original in vault.recent_entries(session):
        source_lines = original.splitlines(keepends=True)
        for start in range(max(0, len(source_lines) - 3)):
            block = source_lines[start:start + 4]
            if sum(map(len, block)) > 12_000 or not all(_repeat_line_is_safe(line) for line in block):
                continue
            key = hashlib.sha256("".join(block).encode()).digest()
            candidates = windows.setdefault(key, [])
            if len(candidates) < 8:
                candidates.append((handle, source_lines, start))
            indexed += 1
            if indexed >= 8_192:
                break
        if indexed >= 8_192:
            break
    if not windows:
        return None

    best: tuple[int, int, str, int] | None = None
    scanned = 0
    for start in range(len(lines) - 3):
        block = lines[start:start + 4]
        if sum(map(len, block)) > 12_000 or not all(_repeat_line_is_safe(line) for line in block):
            continue
        candidates = windows.get(hashlib.sha256("".join(block).encode()).digest(), ())
        for handle, source_lines, source_start in candidates:
            if source_lines[source_start:source_start + 4] != block:
                continue
            left = 0
            while (
                start - left - 1 >= 0
                and source_start - left - 1 >= 0
                and lines[start - left - 1] == source_lines[source_start - left - 1]
                and _repeat_line_is_safe(lines[start - left - 1])
                and sum(map(len, lines[start - left - 1:start + 4])) <= 12_000
            ):
                left += 1
            right = 4
            while (
                start + right < len(lines)
                and source_start + right < len(source_lines)
                and lines[start + right] == source_lines[source_start + right]
                and _repeat_line_is_safe(lines[start + right])
                and sum(map(len, lines[start - left:start + right + 1])) <= 12_000
            ):
                right += 1
            char_count = sum(map(len, lines[start - left:start + right]))
            if char_count > (best[0] if best else 0):
                best = (char_count, start - left, handle, right + left)
        scanned += 1
        if scanned >= 8_192:
            break
    if not best:
        return None

    _characters, start, prior_handle, line_count = best
    end = start + line_count
    omitted = lines[start:end]
    newline = "\r\n" if any(line.endswith("\r\n") for line in omitted) else "\n"
    reference = (
        f"[UTK: {line_count} repeated lines omitted; recover the earlier output "
        f"with handle {prior_handle}]{newline}"
    )
    candidate = "".join(lines[:start]) + reference + "".join(lines[end:])
    before = estimate_tokens(text)

    def make(handle: str) -> CompressionResult:
        content = candidate.rstrip("\r\n") + f"\nUTK retrieve: {handle}\n"
        return CompressionResult(
            content,
            kind,
            before,
            estimate_tokens(content),
            recovery_id=handle,
            preserved=("original_available", "previous_segment_reference", "critical_lines"),
        )

    return vault.put(session, text, make)


def compress_content(text: str, *, session: str, vault: RecoveryVault, profile="safe", hint=None, query="", home=None) -> CompressionResult:
    before = estimate_tokens(text)
    kind = classify(text, hint)
    plain = CompressionResult(text, kind, before, before)
    def unchanged(reason):
        return vault.pin_passthrough(session, replace(plain, fallback=reason))
    # A prior transform wins across profile switches, protecting an already sent prefix.
    previous = vault.lookup(session, text)
    if previous:
        if profile != "off":
            duplicate = _duplicate_reference(previous, text)
            if duplicate is not None:
                return duplicate
        return previous
    if vault.owns_rendering(session, text):
        return replace(plain, fallback="already_compressed")
    if profile == "off":
        return unchanged("disabled")
    if hint is None and kind in {"text", "log", "search", "table"}:
        try:
            repeated = _repeated_segment_reference(text, session=session, vault=vault, kind=kind)
        except Exception:
            repeated = None
        if repeated is not None:
            return repeated
    processor = _processor_for_kind(kind, query, home, profile)
    if hint is None and kind != "json":
        try:
            mixed = _compress_mixed_sections(text, query, home, profile)
        except Exception:
            return unchanged("compression_error")
        if mixed is not None:
            kind = "mixed"
            processor = lambda value: mixed
        elif "```" in text or "<system-reminder" in text:
            return unchanged("compressor_not_ready")
    if processor is None:
        return unchanged("compressor_not_ready")
    try:
        if kind == "text" and re.search(r"[\u3400-\u9fff]", text):
            if not query:
                return unchanged("missing_query")
            from .text_compression import summarize_cjk_text_with_reason
            candidate, reason = summarize_cjk_text_with_reason(
                text, query, aggressive=profile == "aggressive"
            )
            if reason != "compressed":
                return unchanged(reason)
        elif kind == "image":
            from .image_compression import compress_data_url_with_reason
            candidate, reason = compress_data_url_with_reason(
                text, query, aggressive=profile == "aggressive"
            )
            if candidate == text:
                return unchanged(reason)
        else:
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


def pin_transformation(
    original: str,
    rendered: str,
    *,
    session: str,
    vault: RecoveryVault,
    kind: str,
) -> CompressionResult:
    """Attach a recovery handle to a deterministic native-tool transform."""
    before = estimate_tokens(original)
    plain = CompressionResult(original, kind, before, before)
    if not session:
        return replace(plain, fallback="missing_session")
    if rendered == original or not rendered:
        return vault.pin_passthrough(session, replace(plain, fallback="unchanged"))

    def make(handle: str) -> CompressionResult:
        content = rendered.rstrip() + f"\nUTK retrieve: {handle}\n"
        return CompressionResult(
            content,
            kind,
            before,
            estimate_tokens(content),
            recovery_id=handle,
            preserved=("original_available", "content_boundaries"),
        )

    result = vault.put(session, original, make)
    return result or vault.pin_passthrough(
        session, replace(plain, fallback="not_smaller_or_memory_full")
    )
