import hashlib

from ultratokenkiller import assets


def test_verification_requires_size_and_hash(tmp_path, monkeypatch):
    content = b"safe weights fixture"
    manifest = {"files": [{"path": "model.bin", "size": len(content), "sha256": hashlib.sha256(content).hexdigest()}]}
    monkeypatch.setattr(assets, "model_manifest", lambda: manifest)
    assert assets.verify_assets(tmp_path) is False
    root = assets.model_directory(tmp_path)
    root.mkdir(parents=True)
    (root / "model.bin").write_bytes(content)
    assert assets.verify_assets(tmp_path) is True
    (root / "model.bin").write_bytes(b"X"*len(content))
    assert assets.verify_assets(tmp_path) is False
