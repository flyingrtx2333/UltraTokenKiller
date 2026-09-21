from types import SimpleNamespace

from ultratokenkiller.config import Settings
from ultratokenkiller.identity import ensure_session_token, home_instance_id, instance_id
from ultratokenkiller.runtime import headroom_health, service_health


class _Response:
    is_success = True

    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


def test_instance_id_is_stable_and_does_not_expose_token(tmp_path):
    token = ensure_session_token(tmp_path)
    public = home_instance_id(tmp_path)
    assert public == instance_id(token)
    assert len(public) == 24
    assert token not in public
    assert ensure_session_token(tmp_path) == token


def test_health_rejects_another_home_and_legacy_listener(tmp_path, monkeypatch):
    expected = instance_id(ensure_session_token(tmp_path))
    settings = Settings()
    calls = []

    def get(_url, **kwargs):
        calls.append(kwargs)
        return _Response({"status": "ok", "instance_id": "another-instance"})

    monkeypatch.setattr("ultratokenkiller.runtime.httpx.get", get)
    assert not service_health(settings, tmp_path)
    assert calls[-1]["trust_env"] is False

    monkeypatch.setattr(
        "ultratokenkiller.runtime.httpx.get",
        lambda *_args, **_kwargs: _Response({"status": "ok", "version": "old"}),
    )
    assert not service_health(settings, tmp_path)

    monkeypatch.setattr(
        "ultratokenkiller.runtime.httpx.get",
        lambda *_args, **_kwargs: _Response({"status": "ok", "instance_id": expected}),
    )
    assert service_health(settings, tmp_path)


def test_health_without_home_token_never_claims_listener(tmp_path, monkeypatch):
    called = False

    def get(*_args, **_kwargs):
        nonlocal called
        called = True
        return _Response({"status": "ok"})

    monkeypatch.setattr("ultratokenkiller.runtime.httpx.get", get)
    assert not service_health(Settings(), tmp_path)
    assert not headroom_health(Settings(), home=tmp_path)
    assert not called


def test_proxy_health_requires_same_home_identity(tmp_path, monkeypatch):
    expected = instance_id(ensure_session_token(tmp_path))
    settings = Settings()
    monkeypatch.setattr(
        "ultratokenkiller.runtime.httpx.get",
        lambda *_args, **_kwargs: _Response(
            {"status": "ok", "engine": "utk-native", "instance_id": expected}
        ),
    )
    assert headroom_health(settings, home=tmp_path)

    other = instance_id("different-token")
    monkeypatch.setattr(
        "ultratokenkiller.runtime.httpx.get",
        lambda *_args, **_kwargs: _Response(
            {"status": "ok", "engine": "utk-native", "instance_id": other}
        ),
    )
    assert not headroom_health(settings, home=tmp_path)
