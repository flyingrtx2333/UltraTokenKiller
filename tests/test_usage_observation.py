from ultratokenkiller.proxy import UsageObserver
import pytest


@pytest.mark.parametrize("prefix", [b"data:", b"event: response.completed\n" + b"data:", b": keepalive\n\n" + b"data:"])
def test_missing_sse_mime_with_chunked_prefix_still_observes_usage(prefix):
    wire = prefix + b' {"type":"response.completed","response":{"usage":{"input_tokens":17,"output_tokens":3}}}\n\n'
    observer = UsageObserver(False)
    for byte in wire:
        observer.feed(bytes([byte]))
    observer.finish()
    assert observer.sse
    assert observer.usage == {"input_tokens": 17, "output_tokens": 3}
    assert observer.terminal_events == 1


def test_json_response_is_not_reinterpreted_as_sse():
    observer = UsageObserver(False)
    observer.feed(b'{"output":"data: private", "usage":{"input_tokens":8}}')
    observer.finish()
    assert not observer.sse
    assert observer.usage == {"input_tokens": 8}


def test_subscription_terminal_without_usage_remains_unknown():
    observer = UsageObserver(True)
    observer.feed(b'data: {"type":"response.completed","response":{"usage":null}}\n\n')
    observer.finish()
    assert observer.usage == {}
    assert observer.terminal_events == 1
    assert observer.usage_objects == 0
    assert not observer.disabled


def test_observation_counts_usage_without_keeping_response_body():
    observer = UsageObserver(True)
    observer.feed(b'data: {"type":"response.completed","response":{"usage":{"input_tokens":0,"output_tokens":2},"output":"private"}}\n\n')
    observer.finish()
    assert observer.usage == {"input_tokens": 0, "output_tokens": 2}
    assert observer.usage_objects == observer.terminal_events == 1
    assert observer.buffer == b""
    assert not observer.event_data
