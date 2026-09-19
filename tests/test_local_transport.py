import json
import os
import socket
import subprocess
import sys
import time

import httpx
import pytest

from ultratokenkiller.broker import BrokerClient
from ultratokenkiller.config import Settings, choose_port
from ultratokenkiller.local_transport import bind_broker_socket, broker_socket
from ultratokenkiller.recovery import RecoveryUnavailable
from ultratokenkiller.tool_events import ToolEventSink
from ultratokenkiller.store import Store


@pytest.mark.skipif(os.name == "nt", reason="Unix socket transport")
def test_shared_http_and_socket_vault_auth_events_and_cleanup(tmp_path, monkeypatch):
    settings = Settings(dashboard_port=choose_port(19870))
    settings.save(tmp_path)
    env = {**os.environ, "UTK_HOME": str(tmp_path)}
    proc = subprocess.Popen([sys.executable, "-m", "ultratokenkiller.local_transport"], env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    broker = BrokerClient(tmp_path)
    path = broker_socket(tmp_path)
    try:
        with httpx.Client(trust_env=False, timeout=1) as tcp:
            for _ in range(100):
                if proc.poll() is not None:
                    pytest.fail("Broker exited during startup")
                try:
                    if tcp.get(broker.url + "/api/v1/health").is_success:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(.05)
            else:
                pytest.fail("Broker did not become ready")
            assert path.stat().st_mode & 0o777 == 0o600
            original = json.dumps([{"id": i, "value": "constant-value"} for i in range(100)])
            compressed = broker.compress(original, "session-one")
            handle = compressed["recovery_id"]
            assert handle
            # UDS and TCP must reach the SAME in-memory original.
            response = tcp.post(broker.url + "/api/v1/internal/retrieve", headers=broker.headers(),
                                json={"session": "session-one", "handle": handle})
            assert response.json()["content"] == original
            with pytest.raises(RecoveryUnavailable):
                broker.retrieve("session-other", handle)
            with broker.client() as uds:
                assert uds.post(broker.url + "/api/v1/internal/retrieve", json={}).status_code == 403
            monkeypatch.setenv("UTK_SESSION_ID", "session-one")
            event = dict(kind="tool", client="codex", success=True, duration_ms=1, saved_tokens=5,
                         metadata=dict(command="grep", optimized=True, engine="utk-native",
                                       estimator="utf8_bytes_div_4", filter="search", execution_id="a"*32))
            assert ToolEventSink(tmp_path).add(**event) is not None
            ToolEventSink(tmp_path).add(**event)
            assert len(Store(tmp_path / "metrics.sqlite3").events()) == 1
            assert original.encode() not in (tmp_path / "metrics.sqlite3").read_bytes()
    finally:
        proc.terminate()
        proc.wait(timeout=10)
    assert not path.exists()


@pytest.mark.skipif(os.name == "nt", reason="Unix socket transport")
def test_socket_never_replaces_files_or_live_listeners(tmp_path):
    path = broker_socket(tmp_path)
    path.parent.mkdir(mode=0o700, exist_ok=True)
    path.write_text("preserve")
    try:
        with pytest.raises(PermissionError):
            bind_broker_socket(tmp_path)
        assert path.read_text() == "preserve"
    finally:
        path.unlink()
    listener = bind_broker_socket(tmp_path)
    try:
        with pytest.raises(OSError, match="already active"):
            bind_broker_socket(tmp_path)
    finally:
        listener.close()
    # A closed stale socket can be replaced, without changing its path.
    listener = bind_broker_socket(tmp_path)
    listener.close()
    path.unlink()
