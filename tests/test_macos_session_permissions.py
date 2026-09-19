import copy

import pytest

from ultratokenkiller import codex_session


@pytest.fixture
def mac(monkeypatch, tmp_path):
    monkeypatch.setattr(codex_session.sys, "platform", "darwin")
    monkeypatch.setattr("ultratokenkiller.local_transport.broker_socket", lambda home: tmp_path / "broker.sock")
    return tmp_path


@pytest.mark.parametrize("trust,parent", [(None, ":read-only"), ("trusted", ":workspace"), ("untrusted", ":workspace")])
def test_implicit_filesystem_policy_and_user_preferences_are_preserved(mac, trust, parent):
    config = {"model": "chosen", "model_reasoning_effort": "high", "approval_policy": "on-request"}
    if trust:
        config["projects"] = {str(mac): {"trust_level": trust}}
    before = copy.deepcopy(config)
    values = codex_session.macos_broker_overrides(mac, mac / "subdir", "a"*32, config, ["exec", "task"])
    prefix = "permissions." + values["default_permissions"]
    assert values[prefix + ".extends"] == parent
    assert values["features.network_proxy"] is True
    assert values[prefix + ".network.domains"] == {}
    assert values[prefix + ".network.unix_sockets"] == {str(mac / "broker.sock"): "allow"}
    assert not {"model", "model_reasoning_effort", "approval_policy", "projects"} & values.keys()
    assert config == before


@pytest.mark.parametrize("config", [
    {"sandbox_mode": "workspace-write"}, {"sandbox_workspace_write": {"writable_roots": ["private"]}},
    {"features": {"network_proxy": True}}, {"default_permissions": "custom"}, {"profile": "custom"},
])
def test_unknown_policy_is_rejected_without_mutation(mac, config):
    before = copy.deepcopy(config)
    with pytest.raises(ValueError, match="not verified"):
        codex_session.macos_broker_overrides(mac, mac, "a"*32, config, [])
    assert config == before


@pytest.mark.parametrize("arguments", [
    ["--sandbox", "workspace-write"], ["-sworkspace-write"], ["-pmy-profile"],
    ["-c", 'features."network_proxy"=false'], ["--config=features={network_proxy=false}"],
    ["-cdefault_permissions=custom"], ["--config", '"sandbox_mode"="danger-full-access"'],
])
def test_permission_override_cannot_disable_proxy_while_leaving_network_open(mac, arguments):
    with pytest.raises(ValueError, match="cannot be combined"):
        codex_session.macos_broker_overrides(mac, mac, "a"*32, {}, arguments)


def test_policy_rejection_happens_before_services_start(mac, monkeypatch):
    monkeypatch.setattr(codex_session, "codex_executable", lambda: ["codex"])
    monkeypatch.setattr(codex_session, "validate_client", lambda *args: {"sandbox_mode": "read-only"})
    def forbidden(*args):
        raise AssertionError("No service or config mutation allowed")
    monkeypatch.setattr(codex_session, "ensure_route", forbidden)
    with pytest.raises(ValueError, match="not verified"):
        codex_session.launch(["exec", "-C", str(mac), "task"], mac / "utk")
