import copy

import pytest

from ultratokenkiller.codex_hook_trust import approve_session_hook, scoped_trust


def discovered():
    base = {"enabled": True, "handlerType": "command", "isManaged": False,
            "eventName": "preToolUse", "matcher": "^Bash$", "source": "user",
            "trustStatus": "untrusted", "currentHash": "sha256:other"}
    return {"data": [{"errors": [], "hooks": [
        {**base, "source": "sessionFlags", "key": "C:/<session-flags>/config.toml:pre_tool_use:0:0",
         "command": "utk hook codex", "currentHash": "sha256:utk"},
        {**base, "key": "headroom-key", "command": "C:/Python/Scripts/headroom.EXE init hook ensure --profile init-user --marker headroom-init-codex"},
        {**base, "key": "user-hook", "command": "user-check", "trustStatus": "trusted"},
        {**base, "key": "unreviewed-hook", "command": "unreviewed-check"},
        {**base, "key": "managed-hook", "command": "admin-check", "isManaged": True, "trustStatus": "managed"},
    ]}]}


def test_trust_only_exact_utk_definition_preserve_other_trust_and_policy():
    original = discovered()
    before = copy.deepcopy(original)
    state = scoped_trust(original)["hooks.state"]
    assert original == before
    assert state["C:/<session-flags>/config.toml:pre_tool_use:0:0"] == {"enabled": True, "trusted_hash": "sha256:utk"}
    assert state["headroom-key"]["enabled"] is False
    assert state["user-hook"]["trusted_hash"] == "sha256:other"
    assert "trusted_hash" not in state["unreviewed-hook"]
    assert "managed-hook" not in state


@pytest.mark.parametrize("managed,command", [
    (True, "headroom init hook ensure --profile init-user --marker headroom-init-codex"),
    (False, "headroom unknown-command"),
])
def test_never_disable_managed_or_unrecognized_headroom_hooks(managed, command):
    response = discovered()
    response["data"][0]["hooks"][1].update(isManaged=managed, command=command)
    with pytest.raises(ValueError, match="prevents automatic"):
        scoped_trust(response)


def test_confirmation_failure_stops_launch(monkeypatch, tmp_path):
    monkeypatch.setattr("ultratokenkiller.codex_hook_trust.list_hooks", lambda *a, **k: discovered())
    with pytest.raises(ValueError, match="did not confirm"):
        approve_session_hook(["codex"], {}, tmp_path)
