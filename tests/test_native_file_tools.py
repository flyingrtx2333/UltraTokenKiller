import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ultratokenkiller.broker import broker_router
from ultratokenkiller.config import Settings
from ultratokenkiller.compression import pin_transformation
from ultratokenkiller.native_tools import execute_native_tool
from ultratokenkiller.recovery import RecoveryVault
from ultratokenkiller.runtime import run_command
from ultratokenkiller.tool_filters import command_filter


def test_json_compacts_values_and_keys_only_preserves_structure(tmp_path: Path):
    source = tmp_path / "data.json"
    payload = {
        "enabled": True,
        "users": [{"id": index, "name": f"user-{index}"} for index in range(12)],
    }
    source.write_text(json.dumps(payload), encoding="utf-8")

    compact = execute_native_tool(["json", str(source)])
    schema = execute_native_tool(["json", "--keys-only", str(source)])

    assert compact and compact.code == 0
    assert "enabled: true" in compact.rendered
    assert "... +11 more" in compact.rendered
    assert schema and "users:" in schema.rendered and "int" in schema.rendered
    assert "user-0" not in schema.rendered
    assert command_filter(["json", str(source)]) == "native-json"


def test_read_windows_and_numbers_without_losing_original(tmp_path: Path):
    source = tmp_path / "sample.py"
    source.write_text("one\ntwo\nthree\nfour\n", encoding="utf-8")

    head = execute_native_tool(["read", "--head-lines", "2", "-n", str(source)])
    tail = execute_native_tool(["read", "--tail-lines=2", str(source)])

    assert head and head.original == "one\ntwo\nthree\nfour\n"
    assert head.rendered == "1 │ one\n2 │ two\n"
    assert tail and tail.rendered == "three\nfour\n"
    assert command_filter(["read", str(source)]) == "native-read"


def test_smart_matches_frozen_two_line_heuristic_shape(tmp_path: Path):
    source = tmp_path / "sample.py"
    source.write_text(
        "from pathlib import Path\n\nclass Config:\n    pass\n\ndef load_config(path):\n    return Path(path)\n",
        encoding="utf-8",
    )

    result = execute_native_tool(["smart", "--model", "heuristic", str(source)])

    assert result and result.code == 0
    assert result.rendered.splitlines()[0] == "Python module (1 fn, 1 struct) - 7 lines"
    assert "uses: pathlib" in result.rendered
    assert "defines: load_config" in result.rendered
    assert command_filter(["smart", str(source)]) == "native-smart"


def test_native_tool_failures_are_explicit_and_do_not_fake_output(tmp_path: Path):
    missing = execute_native_tool(["read", str(tmp_path / "missing.txt")])
    wrong = tmp_path / "config.yaml"
    wrong.write_text("enabled: true\n", encoding="utf-8")
    non_json = execute_native_tool(["json", str(wrong)])

    assert missing and missing.code == 1 and "missing.txt" in missing.error
    assert non_json and non_json.code == 1 and "not a JSON file" in non_json.error
    assert missing.rendered == non_json.rendered == ""


def test_native_transform_is_recoverable_and_never_forced_when_too_short():
    original = "detailed line with required fact 73\n" * 20
    rendered = "required fact 73 retained\n"
    vault = RecoveryVault(handle_factory=lambda: "native-file-handle")

    result = pin_transformation(
        original, rendered, session="native", vault=vault, kind="smart"
    )

    assert result.recovery_id == "native-file-handle"
    assert vault.retrieve("native", result.recovery_id)["content"] == original

    short = pin_transformation(
        "fact 73\n", "fact\n", session="short", vault=vault, kind="read"
    )
    assert short.content == "fact 73\n"
    assert short.fallback == "not_smaller_or_memory_full"


def test_native_transform_broker_requires_local_auth_and_binds_session():
    vault = RecoveryVault(handle_factory=lambda: "broker-native-handle")
    app = FastAPI()
    app.include_router(broker_router(vault, "secret"))
    client = TestClient(app)
    body = {
        "session": "session-a",
        "original": "required fact 73 with supporting context\n" * 20,
        "rendered": "required fact 73\n",
        "kind": "smart",
    }

    assert client.post("/api/v1/internal/pin-transform", json=body).status_code == 403
    response = client.post(
        "/api/v1/internal/pin-transform",
        headers={"X-UTK-Token": "secret"},
        json=body,
    )

    assert response.status_code == 200
    handle = response.json()["recovery_id"]
    assert handle == "broker-native-handle"
    assert vault.retrieve("session-a", handle)["content"] == body["original"]


def test_native_runtime_does_not_emit_unrecoverable_lossy_output(
    tmp_path: Path, monkeypatch, capsys
):
    source = tmp_path / "data.json"
    original = json.dumps({"rows": [{"id": index} for index in range(30)]})
    source.write_text(original, encoding="utf-8")

    class Events:
        def add(self, **event):
            self.event = event

    monkeypatch.delenv("UTK_SESSION_ID", raising=False)
    monkeypatch.setattr("ultratokenkiller.runtime.Settings.load", lambda *args: Settings())
    events = Events()

    assert run_command(["json", str(source)], events) == 0
    assert capsys.readouterr().out == original
    assert events.event["metadata"]["fallback"] == "missing_session"
    assert events.event["metadata"]["optimized"] is False
