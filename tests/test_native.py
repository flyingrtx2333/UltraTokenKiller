import json
import sys

import httpx
from fastapi.testclient import TestClient

from ultratokenkiller.config import Settings
from ultratokenkiller.engines import compress_request, compact_repetitions, supported_command, response_instruction
from ultratokenkiller.proxy import create_proxy, UsageObserver
from ultratokenkiller.runtime import run_command
from ultratokenkiller.store import Store


def test_input_preserves_instructions_latest_tool_and_multimodal():
    repeated = "building dependency alpha beta gamma delta\n" * 50
    payload = {"instructions": "Preserve all requirements", "input": [
        {"role": "user", "content": [{"type": "input_image", "image_url": "data:abc"}]},
        {"type": "function_call_output", "call_id": "a", "output": repeated},
        {"type": "function_call_output", "call_id": "b", "output": repeated}]}
    result, metrics = compress_request(payload)
    assert result["instructions"] == payload["instructions"]
    assert result["input"][0] == payload["input"][0]
    assert result["input"][-1] == payload["input"][-1]
    assert result["input"][1]["call_id"] == "a"
    assert metrics["estimated_saved_tokens"] > 0
    assert payload["input"][1]["output"] == repeated
    assert compress_request(payload, "off")[0] == payload


def test_errors_and_structured_results_preserved():
    error = "ERROR: something broke here\n" * 100
    assert compact_repetitions(error) == error
    structured = "{\n" + '"value": 42,\n' * 100 + "}"
    payload = {"messages": [{"role": "tool", "content": structured}, {"role": "tool", "content": "latest"}]}
    assert compress_request(payload)[0] == payload


def test_command_allowlist():
    assert supported_command(["git", "diff", "--stat"])
    assert not supported_command(["git", "diff", "--binary"])
    assert not supported_command(["rg", "--json", "foo"])
    assert not supported_command(["bash", "-c", "git status | cat"])
    assert not supported_command(["git", "status", "--porcelain"])
    assert response_instruction("off") == ""


def test_command_exit_status_and_working_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    store = Store(tmp_path / "metrics.sqlite3")
    code = run_command([sys.executable, "-c", "from pathlib import Path; Path('proof').write_text('ok'); raise SystemExit(7)"], store)
    assert code == 7
    assert (tmp_path / "proof").read_text() == "ok"
    assert store.events()[0]["success"] is False
    assert store.events()[0]["kind"] == "tool"


def test_native_stream_auth_usage_and_no_body_storage(tmp_path):
    Settings(caveman="off").save(tmp_path)
    observed = []
    wire = b'data: {"type":"response.completed","response":{"usage":{"input_tokens":123,"output_tokens":7,"input_tokens_details":{"cached_tokens":100}}}}\n\ndata: [DONE]\n\n'
    def upstream(request):
        observed.append(request)
        return httpx.Response(200, content=wire, headers={"content-type": "text/event-stream"})
    app = create_proxy("https://example.test/backend-api/codex", tmp_path, httpx.MockTransport(upstream))
    with TestClient(app) as client:
        result = client.post("/v1/responses", json={"input": "private-prompt", "model": "test"}, headers={"Authorization": "Bearer temporary", "chatgpt-account-id": "account"})
    assert result.content == wire
    assert str(observed[0].url) == "https://example.test/backend-api/codex/responses"
    assert observed[0].headers["authorization"] == "Bearer temporary"
    assert observed[0].headers["chatgpt-account-id"] == "account"
    event = Store(tmp_path / "metrics.sqlite3").events()[0]
    assert (event["input_tokens"], event["output_tokens"], event["cached_tokens"]) == (123, 7, 100)
    assert "private-prompt" not in json.dumps(event)
    assert "temporary" not in json.dumps(event)


def test_upstream_errors_not_retried_and_usage_unknown(tmp_path):
    calls = []
    def upstream(request):
        calls.append(request)
        return httpx.Response(429, json={"error": "limited"}, headers={"retry-after": "30"})
    with TestClient(create_proxy("https://example.test/v1", tmp_path, httpx.MockTransport(upstream))) as client:
        response = client.post("/v1/responses", json={"input": "hello"})
    assert response.status_code == 429
    assert response.headers["retry-after"] == "30"
    assert len(calls) == 1
    event = Store(tmp_path / "metrics.sqlite3").events()[0]
    assert event["input_tokens"] is None
    assert event["success"] is False


def test_optimizer_exception_forwards_original_bytes(tmp_path, monkeypatch):
    import ultratokenkiller.proxy as proxy
    def fail(*args):
        raise RuntimeError("optimizer failed")
    monkeypatch.setattr(proxy, "compress_request", fail)
    observed = []
    def upstream(request):
        observed.append(request.content)
        return httpx.Response(200, json={})
    original = b'{ "input": "keep byte spacing" }'
    with TestClient(create_proxy("https://example.test/v1", tmp_path, httpx.MockTransport(upstream))) as client:
        assert client.post("/v1/responses", content=original).status_code == 200
    assert observed == [original]


def test_usage_observer_split_frames():
    observer = UsageObserver(True)
    for chunk in [b'data: {"usa', b'ge":{"prompt_tokens":15,"completion_tokens":2}}\r', b'\n\n']:
        observer.feed(chunk)
    assert observer.usage["input_tokens"] == 15


def test_real_git_status_keeps_paths(tmp_path, monkeypatch, capfd):
    import shutil
    import subprocess
    import pytest
    if not shutil.which("git"):
        pytest.skip("Git unavailable")
    monkeypatch.chdir(tmp_path)
    subprocess.run(["git", "init", "-q"], check=True)
    (tmp_path / "important-file.txt").write_text("keep me")
    store = Store(tmp_path / "metrics.sqlite3")
    assert run_command(["git", "status"], store) == 0
    output = capfd.readouterr().out
    assert "important-file.txt" in output
    assert not any(line.startswith('  (use "git add ') for line in output.splitlines())
    assert store.events()[0]["metadata"]["engine"] == "utk-native"


def test_style_toggle_and_chat_usage(tmp_path):
    settings = Settings(caveman="ultra")
    settings.save(tmp_path)
    observed = []
    def upstream(request):
        observed.append(json.loads(request.content))
        return httpx.Response(200, json={"usage": {"prompt_tokens": 12, "completion_tokens": 3}})
    with TestClient(create_proxy("https://example.test/v1", tmp_path, httpx.MockTransport(upstream))) as client:
        payload = {"messages": [{"role": "user", "content": "hello"}]}
        client.post("/v1/chat/completions", json=payload)
        settings.caveman = "off"
        settings.save(tmp_path)
        client.post("/v1/chat/completions", json=payload)
    assert observed[0]["messages"][0]["role"] == "developer"
    assert observed[1] == payload
    assert Store(tmp_path / "metrics.sqlite3").events()[0]["input_tokens"] == 12
