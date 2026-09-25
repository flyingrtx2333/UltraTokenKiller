import asyncio
import json
import re

from ultratokenkiller.config import Settings
from ultratokenkiller.proxy import compress_request
from ultratokenkiller.compression import pin_transformation
from ultratokenkiller.read_lifecycle import classify_reads, frozen_prefix_message_count
from ultratokenkiller.recovery import RecoveryVault


def read_call(call_id, path, *, offset=None, limit=None):
    args = {"file_path": path}
    if offset is not None:
        args["offset"] = offset
    if limit is not None:
        args["limit"] = limit
    return {
        "role": "assistant",
        "tool_calls": [{"id": call_id, "type": "function", "function": {
            "name": "Read", "arguments": json.dumps(args),
        }}],
    }


def edit_call(call_id, path, name="Edit"):
    return {
        "role": "assistant",
        "tool_calls": [{"id": call_id, "type": "function", "function": {
            "name": name, "arguments": json.dumps({"file_path": path}),
        }}],
    }


def test_read_edit_reread_marks_only_the_old_version_stale():
    content = "source line\n" * 100
    messages = [
        read_call("read-1", "src/app.py"),
        {"role": "tool", "tool_call_id": "read-1", "content": content},
        edit_call("edit-1", "src/app.py"),
        {"role": "tool", "tool_call_id": "edit-1", "content": "updated"},
        read_call("read-2", "src/app.py"),
        {"role": "tool", "tool_call_id": "read-2", "content": content + "new\n"},
    ]

    states = {item.call_id: item.state for item in classify_reads(messages)}

    assert states == {"read-1": "stale", "read-2": "fresh"}


def test_lifecycle_pass_replaces_old_result_and_keeps_current_read_and_metadata(tmp_path, monkeypatch):
    old = "old source context\n" * 80
    current = "new source context\n" * 80
    vault = RecoveryVault()
    payload = {"messages": [
        read_call("r1", "src/app.py"),
        {"role": "tool", "tool_call_id": "r1", "content": old,
         "metadata": {"origin": "test"}},
        edit_call("e1", "src/app.py", "Write"),
        {"role": "tool", "tool_call_id": "e1", "content": "written"},
        read_call("r2", "src/app.py"),
        {"role": "tool", "tool_call_id": "r2", "content": current},
    ]}

    class Broker:
        def __init__(self):
            self.pinned = []
            self.compressed = []

        def pin_transform(self, original, rendered, session, kind):
            self.pinned.append((original, session, kind))
            result = pin_transformation(original, rendered, session=session, vault=vault, kind=kind)
            return {"content": result.content, "saved_tokens": result.saved_tokens,
                    "recovery_id": result.recovery_id}

        def compress(self, text, session, **kwargs):
            self.compressed.append(text)
            return {"content": text, "fallback": "not_smaller_or_memory_full", "saved_tokens": 0}

    broker = Broker()
    monkeypatch.setattr("ultratokenkiller.proxy.BrokerClient", lambda _root=None: broker)
    result, metadata = asyncio.run(compress_request(payload, Settings(), tmp_path, "session-1", "gpt-test"))

    assert "stale" in result["messages"][1]["content"]
    recovered_handle = re.search(r"UTK retrieve: ([^\s]+)", result["messages"][1]["content"]).group(1)
    assert vault.retrieve("session-1", recovered_handle)["content"] == old
    assert result["messages"][5]["content"] == current
    assert result["messages"][1]["metadata"] == {"origin": "test"}
    assert broker.pinned == [(old, "session-1", "read_lifecycle_stale")]
    assert broker.compressed == ["written"]
    assert metadata["read_lifecycle"]["reads_stale"] == 1
    assert metadata["read_lifecycle"]["reads_fresh"] == 1
    assert metadata["read_lifecycle"]["transformed"] == 1
    assert metadata["changed_tool_results"] == 1


def test_small_stale_read_is_left_untouched(tmp_path, monkeypatch):
    payload = {"messages": [
        read_call("r1", "src/app.py"),
        {"role": "tool", "tool_call_id": "r1", "content": "short result"},
        edit_call("e1", "src/app.py"),
    ]}

    class Broker:
        def pin_transform(self, *_args, **_kwargs):
            raise AssertionError("small outputs should not be pinned")

        def compress(self, text, *_args, **_kwargs):
            return {"content": text, "fallback": "not_smaller_or_memory_full", "saved_tokens": 0}

    monkeypatch.setattr("ultratokenkiller.proxy.BrokerClient", lambda _root=None: Broker())
    result, metadata = asyncio.run(compress_request(payload, Settings(), tmp_path, "session-1", "gpt-test"))

    assert result["messages"][1]["content"] == "short result"
    assert metadata["read_lifecycle"]["skipped_small"] == 1
    assert metadata["read_lifecycle"]["transformed"] == 0


def test_later_read_only_supersedes_a_range_it_fully_covers():
    messages = [
        read_call("partial", "src/a.py", offset=100, limit=50),
        read_call("covering", "src/a.py", offset=90, limit=100),
        read_call("disjoint", "src/a.py", offset=250, limit=50),
        read_call("other-file", "src/b.py", offset=100, limit=50),
        edit_call("edit-b", "src/b.py"),
    ]

    states = {item.call_id: item.state for item in classify_reads(messages)}

    assert states == {
        "partial": "superseded",
        "covering": "fresh",
        "disjoint": "fresh",
        "other-file": "stale",
    }


def test_full_read_covers_partial_but_partial_read_does_not_cover_full():
    messages = [
        read_call("partial", "src/a.py", offset=20, limit=10),
        read_call("full", "src/a.py"),
        read_call("full-first", "src/b.py"),
        read_call("partial-later", "src/b.py", offset=20, limit=10),
    ]

    states = {item.call_id: item.state for item in classify_reads(messages)}

    assert states == {
        "partial": "superseded",
        "full": "fresh",
        "full-first": "fresh",
        "partial-later": "fresh",
    }


def test_explicit_cache_prefix_is_not_rewritten():
    messages = [
        read_call("r1", "src/app.py"),
        {"role": "tool", "tool_call_id": "r1", "content": "cached", "cache_control": {"type": "ephemeral"}},
        edit_call("e1", "src/app.py"),
    ]

    assert frozen_prefix_message_count(messages) == 2
    assert classify_reads(messages, frozen_message_count=2)[0].state == "fresh"


def test_anthropic_and_responses_tool_shapes_are_recognized():
    messages = [
        {"role": "assistant", "content": [
            {"type": "tool_use", "id": "a-read", "name": "Read", "input": {"path": "src/a.py"}}
        ]},
        {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "a-read", "content": "x" * 600}
        ]},
        {"type": "function_call", "call_id": "r-write", "name": "Write",
         "arguments": json.dumps({"path": "src/a.py"})},
        {"type": "function_call_output", "call_id": "r-write", "output": "done"},
    ]

    classifications = classify_reads(messages)

    assert [(item.call_id, item.state) for item in classifications] == [("a-read", "stale")]
