"""Native equivalents for RTK file-inspection commands."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class NativeToolResult:
    code: int
    original: str
    rendered: str
    kind: str
    error: str = ""


def _option_value(args: list[str], names: set[str], default: int) -> tuple[int, list[str]]:
    remaining: list[str] = []
    value = default
    seen = False
    index = 0
    while index < len(args):
        item = args[index]
        matched = next((name for name in names if item.startswith(name + "=")), None)
        if item in names:
            if index + 1 >= len(args):
                raise ValueError(f"{item} requires a value")
            value = int(args[index + 1])
            seen = True
            index += 2
        elif matched:
            value = int(item.split("=", 1)[1])
            seen = True
            index += 1
        else:
            remaining.append(item)
            index += 1
    if seen and value < 0:
        raise ValueError("line and depth limits must be non-negative")
    return value, remaining


def _compact_json(value, depth: int, maximum: int, keys_only: bool) -> str:
    indent = "  " * depth
    if depth > maximum:
        return indent + "..."
    if isinstance(value, dict):
        lines = [indent + "{"]
        keys = sorted(value)
        for index, key in enumerate(keys[:21]):
            child = value[key]
            if keys_only:
                shown = _json_type(child, depth + 1, maximum)
            else:
                shown = _compact_json(child, depth + 1, maximum, False)
            if "\n" in shown:
                lines.append(f"{indent}  {key}:")
                lines.append(shown)
            else:
                lines.append(f"{indent}  {key}: {shown.strip()}")
            if index == 20 and len(keys) > 21:
                lines.append(f"{indent}  ... +{len(keys) - 21} more keys")
        lines.append(indent + "}")
        return "\n".join(lines)
    if isinstance(value, list):
        if not value:
            return indent + "[]"
        if keys_only:
            return f"{indent}[{_json_type(value[0], 0, maximum).strip()}] ({len(value)})"
        if len(value) > 5:
            first = _compact_json(value[0], depth + 1, maximum, False).strip()
            return f"{indent}[{first}, ... +{len(value) - 1} more]"
        children = [_compact_json(item, depth + 1, maximum, False).strip() for item in value]
        return indent + "[" + ", ".join(children) + "]"
    if isinstance(value, str):
        shown = value if len(value) <= 80 else value[:77] + "..."
        return indent + json.dumps(shown, ensure_ascii=False)
    if value is True:
        return indent + "true"
    if value is False:
        return indent + "false"
    if value is None:
        return indent + "null"
    return indent + str(value)


def _json_type(value, depth: int, maximum: int) -> str:
    indent = "  " * depth
    if depth > maximum:
        return indent + "..."
    if isinstance(value, dict):
        return _compact_json(value, depth, maximum, True)
    if isinstance(value, list):
        if not value:
            return indent + "[]"
        return f"{indent}[{_json_type(value[0], 0, maximum).strip()}] ({len(value)})"
    if isinstance(value, bool):
        return indent + "bool"
    if isinstance(value, int):
        return indent + "int"
    if isinstance(value, float):
        return indent + "float"
    if value is None:
        return indent + "null"
    return indent + "string"


def _read(args: list[str]) -> NativeToolResult:
    line_numbers = any(item in {"-n", "--line-numbers"} for item in args)
    args = [item for item in args if item not in {"-n", "--line-numbers"}]
    head, args = _option_value(args, {"--head-lines"}, -1)
    tail, args = _option_value(args, {"--tail-lines"}, -1)
    maximum, args = _option_value(args, {"-m", "--max-lines"}, -1)
    level = "none"
    if "-l" in args or "--level" in args:
        flag = "-l" if "-l" in args else "--level"
        index = args.index(flag)
        if index + 1 >= len(args):
            raise ValueError(f"{flag} requires a value")
        level = args[index + 1]
        args = args[:index] + args[index + 2:]
    if level not in {"none", "minimal", "aggressive"}:
        raise ValueError("level must be none, minimal, or aggressive")
    if not args:
        raise ValueError("read requires at least one file")
    blocks: list[str] = []
    originals: list[str] = []
    for name in args:
        path = Path(name)
        content = path.read_text(encoding="utf-8")
        originals.append(content)
        lines = content.splitlines(keepends=True)
        shown = content
        if head >= 0:
            shown = "".join(lines[:head])
        elif tail >= 0:
            shown = "".join(lines[-tail:]) if tail else ""
        elif maximum >= 0 and len(lines) > maximum:
            first = maximum // 2
            shown = "".join(lines[:first]) + f"[UTK: {len(lines) - maximum} middle lines omitted]\n" + "".join(lines[-(maximum-first):])
        elif level != "none":
            from .code_compression import summarize_code
            language = path.suffix.lower().lstrip(".")
            shown = summarize_code(content, language, query="")
        if line_numbers:
            shown_lines = shown.splitlines(keepends=True)
            width = len(str(len(shown_lines)))
            shown = "".join(
                f"{index:>{width}} │ {line}"
                for index, line in enumerate(shown_lines, 1)
            )
        blocks.append(shown)
    original = "".join(originals)
    rendered = "".join(blocks)
    return NativeToolResult(0, original, rendered, "read")


def _json(args: list[str]) -> NativeToolResult:
    keys_only = "--keys-only" in args
    args = [item for item in args if item != "--keys-only"]
    depth, args = _option_value(args, {"-d", "--depth"}, 5)
    if len(args) != 1:
        raise ValueError("json requires exactly one file")
    path = Path(args[0])
    if path.suffix.lower() in {".toml", ".yaml", ".yml", ".xml", ".csv", ".ini", ".env", ".txt"}:
        raise ValueError(f"{path} is not a JSON file; use read for non-JSON files")
    original = path.read_text(encoding="utf-8").lstrip("\ufeff")
    value = json.loads(original)
    rendered = _compact_json(value, 0, depth, keys_only) + "\n"
    if len(rendered) >= len(original):
        rendered = original
    return NativeToolResult(0, original, rendered, "json")


def _smart(args: list[str]) -> NativeToolResult:
    positional: list[str] = []
    index = 0
    while index < len(args):
        item = args[index]
        if item in {"-m", "--model"}:
            if index + 1 >= len(args):
                raise ValueError(f"{item} requires a value")
            if args[index + 1] != "heuristic":
                raise ValueError("only the frozen heuristic smart model is supported")
            index += 2
        elif item.startswith("--model="):
            if item.split("=", 1)[1] != "heuristic":
                raise ValueError("only the frozen heuristic smart model is supported")
            index += 1
        elif item == "--force-download":
            index += 1
        elif item.startswith("-"):
            raise ValueError(f"unknown smart option: {item}")
        else:
            positional.append(item)
            index += 1
    if len(positional) != 1:
        raise ValueError("smart requires exactly one file")
    path = Path(positional[0])
    original = path.read_text(encoding="utf-8")
    language = {".py": "Python", ".rs": "Rust", ".ts": "TypeScript", ".js": "JavaScript", ".go": "Go"}.get(path.suffix.lower(), "Code")
    functions = re.findall(r"(?m)^\s*(?:def|fn|function)\s+([A-Za-z_]\w*)", original)
    structures = re.findall(r"(?m)^\s*(?:class|struct|enum|interface)\s+([A-Za-z_]\w*)", original)
    imports = re.findall(r"(?m)^\s*(?:from|import|use)\s+([^\s;]+)", original)
    parts = []
    if functions:
        parts.append(f"{len(functions)} fn")
    if structures:
        parts.append(f"{len(structures)} struct")
    line1 = f"{language} {'module' if parts else 'code'} ({', '.join(parts)}) - {len(original.splitlines())} lines" if parts else f"{language} code ({len(original.splitlines())} lines)"
    details = []
    if imports:
        details.append("uses: " + ", ".join(dict.fromkeys(imports[:3])))
    if language == "Python" and "def __init__" in original:
        details.append("patterns: OOP")
    elif functions:
        details.append("defines: " + ", ".join(functions[:3]))
    rendered = line1 + "\n" + (" | ".join(details) if details else "General purpose code file") + "\n"
    return NativeToolResult(0, original, rendered, "smart")


def execute_native_tool(argv: list[str]) -> NativeToolResult | None:
    if not argv:
        return None
    name = Path(argv[0]).name.lower()
    handlers = {"read": _read, "json": _json, "smart": _smart}
    handler = handlers.get(name)
    if handler is None:
        return None
    try:
        return handler(argv[1:])
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as error:
        return NativeToolResult(1, "", "", name, f"utk {name}: {error}\n")
