from pathlib import Path

import scripts.generate_current_status as current_status
from scripts.generate_current_status import (
    BEGIN_MARKER,
    END_MARKER,
    collect_status,
    render_sections,
    synchronize_documents,
)


def test_current_status_uses_evidence_bound_runtime_report():
    status = collect_status(Path.cwd())

    report = current_status.capability_report(Path.cwd())
    assert status["total"] == report["total_core_capabilities"]
    assert status["summary"] == report["summary"]
    assert sum(status["summary"].values()) == status["total"]
    assert status["full_denominator"] == report["full_parity_denominator"]
    assert status["full"] == report["full_parity_verification_summary"]
    assert sum(status["full"].values()) == status["full_denominator"]
    assert status["rtk_evidence"] == sum(
        count for state, count in report["full_parity_status_counts"]["rtk"].items()
        if state != "pending_fixed_upstream_variant_evidence"
    )
    assert status["unverified"] == sorted(
        item["id"] for item in report["capabilities"]
        if item["status"] == "implemented_unverified"
    )


def test_rendered_sections_include_both_denominators_and_all_unverified_items():
    status = collect_status(Path.cwd())
    sections = render_sections(Path.cwd())

    assert set(sections) == {
        "docs/development-notes.md",
        "docs/capability-evidence-2026-09-20.md",
        "docs/current-status-and-roadmap.md",
    }
    for rendered in sections.values():
        assert "36 项" in rendered
        assert "256 项" in rendered
    evidence = sections["docs/capability-evidence-2026-09-20.md"]
    assert all(f"`{identifier}`" in evidence for identifier in status["unverified"])


def test_check_mode_detects_drift_without_writing_and_update_is_idempotent(tmp_path):
    relative = "docs/status.md"
    target = tmp_path / relative
    target.parent.mkdir(parents=True)
    original = f"before\n{BEGIN_MARKER}\nold\n{END_MARKER}\nafter\n"
    target.write_text(original, encoding="utf-8")
    sections = {relative: "new"}

    assert synchronize_documents(tmp_path, sections, check=True) == [target]
    assert target.read_text(encoding="utf-8") == original

    assert synchronize_documents(tmp_path, sections) == [target]
    updated = target.read_text(encoding="utf-8")
    assert f"{BEGIN_MARKER}\nnew\n{END_MARKER}" in updated
    assert synchronize_documents(tmp_path, sections, check=True) == []
    assert synchronize_documents(tmp_path, sections) == []


def test_check_cli_returns_nonzero_for_drift(monkeypatch):
    monkeypatch.setattr(
        current_status,
        "synchronize_documents",
        lambda *, check: [current_status.ROOT / "README.md"],
    )

    assert current_status.main(["--check"]) == 1
