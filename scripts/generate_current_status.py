"""Synchronize current capability status blocks in maintained documentation."""
from __future__ import annotations

import argparse
from collections.abc import Mapping
from pathlib import Path

from ultratokenkiller.capabilities import capability_report


ROOT = Path(__file__).resolve().parents[1]
BEGIN_MARKER = "<!-- BEGIN GENERATED CURRENT STATUS -->"
END_MARKER = "<!-- END GENERATED CURRENT STATUS -->"


def collect_status(root: Path = ROOT) -> dict:
    """Return the evidence-bound status values used by maintained docs."""
    report = capability_report(root)
    summary = report["summary"]
    full = report["full_parity_verification_summary"]
    full_by_upstream = report["full_parity_verification_counts"]
    parity_by_upstream = report["full_parity_status_counts"]
    implementation_by_upstream = report["full_parity_implementation_counts"]
    unverified = sorted(
        item["id"]
        for item in report["capabilities"]
        if item["status"] == "implemented_unverified"
    )
    rtk_parity = parity_by_upstream["rtk"]
    rtk_evidence = sum(
        value
        for state, value in rtk_parity.items()
        if state != "pending_fixed_upstream_variant_evidence"
    )
    return {
        "total": report["total_core_capabilities"],
        "summary": summary,
        "full_denominator": report["full_parity_denominator"],
        "full": full,
        "full_by_upstream": full_by_upstream,
        "parity_by_upstream": parity_by_upstream,
        "implementation_by_upstream": implementation_by_upstream,
        "rtk_evidence": rtk_evidence,
        "unverified": unverified,
    }


def _high_level_line(status: dict) -> str:
    summary = status["summary"]
    return (
        f"高层产品能力共 **{status['total']} 项**："
        f"**{summary['offline_passed']} 项**证据有效并离线通过，"
        f"**{summary['implemented_unverified']} 项**已实现但当前证据待重新验证，"
        f"**{summary['real_client_passed']} 项**拥有当前源码绑定的实机通过证据。"
    )


def _full_line(status: dict) -> str:
    full = status["full"]
    return (
        f"完整三层核心分母共 **{status['full_denominator']} 项**："
        f"固定上游完整通过 {full['fixed_upstream_full_passed']} 项、"
        f"部分通过 {full['fixed_upstream_partial_passed']} 项、"
        f"离线通过 {full['offline_passed']} 项、"
        f"仅完成契约映射 {full['contract_mapped']} 项、"
        f"资产未就绪 {full['asset_not_ready']} 项、"
        f"未实现 {full['not_implemented']} 项。"
    )


def render_readme_status(status: dict) -> str:
    headroom = status["parity_by_upstream"]["headroom"]
    rtk_impl = status["implementation_by_upstream"]["rtk"]
    caveman = status["parity_by_upstream"]["caveman"]
    return "\n".join([
        _high_level_line(status),
        "",
        _full_line(status),
        "",
        (
            f"- Headroom：24 项；固定上游完整 {headroom['fixed_upstream_suite_passed']} 项、"
            f"部分样例 {headroom['fixed_upstream_sample_passed']} 项、"
            f"{headroom['not_individually_compared']} 项待逐项对照。"
        ),
        (
            f"- RTK：211 项；{status['rtk_evidence']} 项已有固定上游不同级别证据、"
            f"{rtk_impl['contract_mapped']} 项已映射契约、"
            f"{rtk_impl['unverified']} 项未实现；契约映射和安全透传不算完整对标。"
        ),
        (
            "- Caveman：21 项；"
            f"{caveman['fixed_upstream_policy_passed']} 项固定策略对照、"
            f"{caveman['offline_passed']} 项结构化绕过离线通过、"
            f"{caveman['authorization_required']} 个真实回答质量场景等待独立 180 次授权。"
        ),
    ])


def render_evidence_status(status: dict) -> str:
    unverified = "\n".join(f"- `{identifier}`" for identifier in status["unverified"])
    return "\n".join([
        _high_level_line(status),
        "",
        _full_line(status),
        "",
        "“已实现”表示实现文件和测试入口仍存在；“当前已验证”还要求完整测试账本、实现与测试源码指纹以及相关证据哈希全部匹配。代码或证据变化后，状态会保守降级，不沿用旧结论。",
        "",
        f"当前 {len(status['unverified'])} 项已实现但证据待重新验证：",
        "",
        unverified,
    ])


def render_roadmap_status(status: dict) -> str:
    by_upstream = status["full_by_upstream"]
    return "\n".join([
        _high_level_line(status),
        "",
        _full_line(status),
        "",
        "按上游拆分的证据绑定状态：",
        "",
        (
            "- Headroom："
            f"{by_upstream['headroom']['fixed_upstream_full_passed']} 项固定上游完整通过、"
            f"{by_upstream['headroom']['offline_passed']} 项离线通过、"
            f"{by_upstream['headroom']['asset_not_ready']} 项资产未就绪。"
        ),
        (
            "- RTK："
            f"{by_upstream['rtk']['fixed_upstream_partial_passed']} 项固定上游部分通过、"
            f"{by_upstream['rtk']['contract_mapped']} 项仅完成契约映射、"
            f"{by_upstream['rtk']['not_implemented']} 项未实现。"
        ),
        (
            "- Caveman："
            f"{by_upstream['caveman']['fixed_upstream_full_passed']} 项固定上游完整通过、"
            f"{by_upstream['caveman']['offline_passed']} 项离线通过。"
        ),
    ])


def render_sections(root: Path = ROOT) -> dict[str, str]:
    status = collect_status(root)
    return {
        "docs/development-notes.md": render_readme_status(status),
        "docs/capability-evidence-2026-09-20.md": render_evidence_status(status),
        "docs/current-status-and-roadmap.md": render_roadmap_status(status),
    }


def replace_generated_block(text: str, replacement: str) -> str:
    if text.count(BEGIN_MARKER) != 1 or text.count(END_MARKER) != 1:
        raise ValueError("document must contain exactly one generated current-status block")
    start = text.index(BEGIN_MARKER) + len(BEGIN_MARKER)
    end = text.index(END_MARKER, start)
    if end < start:
        raise ValueError("generated current-status markers are out of order")
    newline = "\r\n" if text[start:start + 2] == "\r\n" else "\n"
    rendered = replacement.replace("\n", newline)
    return f"{text[:start]}{newline}{rendered}{newline}{text[end:]}"


def synchronize_documents(
    root: Path = ROOT,
    sections: Mapping[str, str] | None = None,
    *,
    check: bool = False,
) -> list[Path]:
    """Update generated blocks, or return drift without writing in check mode."""
    rendered_sections = dict(render_sections(root) if sections is None else sections)
    drifted: list[Path] = []
    for relative, rendered in rendered_sections.items():
        path = root / relative
        raw = path.read_bytes()
        current = raw.decode("utf-8")
        expected = replace_generated_block(current, rendered)
        if expected == current:
            continue
        drifted.append(path)
        if not check:
            path.write_bytes(expected.encode("utf-8"))
    return drifted


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="report stale generated blocks without modifying documentation",
    )
    args = parser.parse_args(argv)
    drifted = synchronize_documents(check=args.check)
    if args.check and drifted:
        for path in drifted:
            print(f"stale: {path.relative_to(ROOT)}")
        return 1
    for path in drifted:
        print(f"updated: {path.relative_to(ROOT)}")
    if not drifted:
        print("current-status documentation is up to date")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
