"""Conversation-local lifecycle detection for file reads."""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass


READ_NAMES = {"Read", "read"}
MUTATING_NAMES = {"Edit", "edit", "Write", "write"}


@dataclass(frozen=True)
class FileOperation:
    message_index: int
    call_id: str
    name: str
    path: str
    operation: str
    offset: int | None = None
    limit: int | None = None


@dataclass(frozen=True)
class ReadLifecycle:
    message_index: int
    call_id: str
    path: str
    state: str
    offset: int | None = None
    limit: int | None = None


def frozen_prefix_message_count(messages: list[dict]) -> int:
    """Keep all messages through the latest explicit provider cache marker fixed."""
    boundary = 0
    for index, message in enumerate(messages):
        if not isinstance(message, dict):
            continue
        if message.get("cache_control"):
            boundary = index + 1
        content = message.get("content")
        if isinstance(content, list) and any(
            isinstance(block, dict) and block.get("cache_control") for block in content
        ):
            boundary = index + 1
    return boundary


def _read_args(value) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except (ValueError, TypeError):
            return {}
    return {}


def _number(value) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _operation(message_index: int, call_id, name, arguments) -> FileOperation | None:
    if not isinstance(call_id, str) or not call_id or not isinstance(name, str):
        return None
    if name not in READ_NAMES | MUTATING_NAMES:
        return None
    args = _read_args(arguments)
    path = args.get("file_path") or args.get("path")
    if not isinstance(path, str) or not path:
        return None
    kind = "read" if name in READ_NAMES else "edit"
    return FileOperation(
        message_index,
        call_id,
        name,
        path,
        kind,
        _number(args.get("offset")) if kind == "read" else None,
        _number(args.get("limit")) if kind == "read" else None,
    )


def _build_operations(messages: list[dict]) -> dict[str, list[FileOperation]]:
    by_path: dict[str, list[FileOperation]] = defaultdict(list)
    for index, message in enumerate(messages):
        if not isinstance(message, dict):
            continue
        if message.get("role") == "assistant":
            for call in message.get("tool_calls") or []:
                if not isinstance(call, dict):
                    continue
                function = call.get("function") or {}
                if not isinstance(function, dict):
                    continue
                operation = _operation(index, call.get("id"), function.get("name"), function.get("arguments"))
                if operation:
                    by_path[operation.path].append(operation)
            content = message.get("content")
            if isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict) or block.get("type") != "tool_use":
                        continue
                    operation = _operation(index, block.get("id"), block.get("name"), block.get("input"))
                    if operation:
                        by_path[operation.path].append(operation)
        # Responses API function calls are individual input items rather than
        # assistant messages with tool_calls.
        if message.get("type") == "function_call":
            operation = _operation(index, message.get("call_id"), message.get("name"), message.get("arguments"))
            if operation:
                by_path[operation.path].append(operation)
    return by_path


def _read_covers(later: FileOperation, earlier: FileOperation) -> bool:
    if later.offset is None and later.limit is None:
        return True
    if earlier.offset is None and earlier.limit is None:
        return False
    later_start = later.offset or 0
    later_end = later_start + (later.limit or 2000)
    earlier_start = earlier.offset or 0
    earlier_end = earlier_start + (earlier.limit or 2000)
    return later_start <= earlier_start and later_end >= earlier_end


def classify_reads(
    messages: list[dict],
    *,
    frozen_message_count: int = 0,
    compress_superseded: bool = True,
) -> list[ReadLifecycle]:
    """Classify reads from tool-call order; never infer lifecycle across paths."""
    classifications = []
    for path, operations in _build_operations(messages).items():
        reads = [item for item in operations if item.operation == "read"]
        edits = [item for item in operations if item.operation == "edit"]
        for read in reads:
            state = "fresh"
            if read.message_index >= frozen_message_count:
                if any(edit.message_index > read.message_index for edit in edits):
                    state = "stale"
                elif compress_superseded and any(
                    later.message_index > read.message_index and _read_covers(later, read)
                    for later in reads
                ):
                    state = "superseded"
            classifications.append(
                ReadLifecycle(read.message_index, read.call_id, path, state, read.offset, read.limit)
            )
    return sorted(classifications, key=lambda item: (item.message_index, item.call_id))


def tool_output_text_fields(messages: list[dict]):
    """Yield (call id, object, key) for recognized textual tool-result fields."""
    for item in messages:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        if role == "tool" and isinstance(item.get("content"), str):
            yield item.get("tool_call_id", ""), item, "content"
        if item.get("type") in {"function_call_output", "custom_tool_call_output"} and isinstance(item.get("output"), str):
            yield item.get("call_id", ""), item, "output"
        content = item.get("content")
        if isinstance(content, list):
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "tool_result":
                    continue
                tool_content = block.get("content")
                if isinstance(tool_content, str):
                    yield block.get("tool_use_id", ""), block, "content"
                elif isinstance(tool_content, list):
                    for part in tool_content:
                        if isinstance(part, dict) and part.get("type") in {"text", "input_text"} and isinstance(part.get("text"), str):
                            yield block.get("tool_use_id", ""), part, "text"
