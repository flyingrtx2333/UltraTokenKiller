import hashlib
import json
import sys
from pathlib import Path

import pytest

from ultratokenkiller.benchmark import fixtures, run_benchmark
from ultratokenkiller.reference_runner import generate_reference, verify_checkouts


def test_verify_checkouts_rejects_moved_baseline(monkeypatch, tmp_path: Path):
    roots = {name: tmp_path / name for name in ("headroom", "rtk", "caveman")}
    for root in roots.values():
        root.mkdir()
    monkeypatch.setattr("ultratokenkiller.reference_runner._git_head", lambda path: "wrong")

    with pytest.raises(ValueError, match="expected frozen commit"):
        verify_checkouts(roots)


def test_generate_reference_records_partial_layer_coverage(monkeypatch, tmp_path: Path):
    roots = {name: tmp_path / name for name in ("headroom", "rtk", "caveman")}
    for root in roots.values():
        root.mkdir()
    baselines = run_benchmark("passthrough")["baselines"]
    monkeypatch.setattr(
        "ultratokenkiller.reference_runner._git_head",
        lambda path: baselines[path.name],
    )
    outputs = {name: content for name, content, _ in fixtures()}
    engines = {name: {"component": "headroom", "transforms": []} for name in outputs}
    monkeypatch.setattr(
        "ultratokenkiller.reference_runner._headroom_outputs",
        lambda checkout, python: {
            "outputs": outputs,
            "engines": engines,
            "runtime": {
                "version": "test",
                "python_module_sha256": "a",
                "native_module_sha256": "b",
            },
        },
    )
    output = tmp_path / "reference.json"

    result = generate_reference(
        headroom=roots["headroom"],
        rtk=roots["rtk"],
        caveman=roots["caveman"],
        output=output,
        python=Path(sys.executable),
    )

    assert result["coverage"] == {"headroom": len(outputs), "rtk": 0, "caveman": 0}
    assert result["live_model_calls"] == 0
    assert result["fixture_sha256"] == {
        name: hashlib.sha256(content.encode()).hexdigest() for name, content, _ in fixtures()
    }
    stored = json.loads(output.read_text(encoding="utf-8"))
    assert stored["outputs"] == outputs
    report = run_benchmark("upstream", reference=output)
    assert report["status"] == "completed"
    assert report["reference"]["suite_scope"] == "input-compression"
    assert report["reference"]["coverage"]["rtk"] == 0
