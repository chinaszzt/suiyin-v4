"""Dogfood T-001: ADR-0002 + constitution v0.2.1 验证.

按 dogfood/T-001/spec.md §5 AC. 测试名 prefix `test_AC_101_` / `test_AC_102_`
由 C4 parser (Fork G) 识别为 covering AC-101 / AC-102.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_AC_101_adr_0002_exists_with_template_structure() -> None:
    adr_path = REPO_ROOT / "docs" / "sdd" / "adrs" / "0002-python-tech-stack.md"
    assert adr_path.exists(), f"missing ADR file: {adr_path}"

    content = adr_path.read_text(encoding="utf-8")
    assert "Python 3.11+" in content, "ADR-0002 必须含 'Python 3.11+'"
    assert "## Status" in content, "ADR-0002 必须有 '## Status' 段"
    assert "Accepted" in content, "ADR-0002 Status 必须是 Accepted"
    # 决策含与 shell / Bun / Go 候选对比
    assert "Shell" in content, "ADR-0002 应对比 Shell 候选"
    assert "Bun" in content, "ADR-0002 应对比 Bun 候选"
    assert "Go" in content, "ADR-0002 应对比 Go 候选"


def test_AC_102_constitution_bumped_to_v0_2_1() -> None:
    """AC-102 timeline-stable 版: 验"v0.2.1 这个 release 发生过", 不验"current = v0.2.1".

    PR #27 把 constitution 升到 v0.2.2 后, 原来 assert "**Version**: v0.2.1" 失败.
    Dogfood test 是历史 audit, 不应阻塞后续 constitution bump. 改写为 version history
    + Q-C-2 状态 (这些是历史事实, 不会被后续 bump 抹掉).
    """
    constitution_path = REPO_ROOT / "docs" / "sdd" / "constitution.md"
    assert constitution_path.exists(), f"missing constitution: {constitution_path}"

    content = constitution_path.read_text(encoding="utf-8")

    # §6b Q-C-2 关闭，引用 ADR-0002 (timeline-stable: 一旦关就不会再 reopen)
    q_c_2_lines = [
        line for line in content.splitlines() if "Q-C-2" in line and "ADR-0002" in line
    ]
    assert q_c_2_lines, "§6b Q-C-2 行必须更新为引用 ADR-0002"
    assert any("已拍" in line for line in q_c_2_lines), "§6b Q-C-2 行必须标 '已拍'"

    # §9 Version History 表加 v0.2.1 行 (2026-05-24) — historical record, 永远在
    version_table_lines = [
        line for line in content.splitlines()
        if line.startswith("| v0.2.1") and "2026-05-24" in line
    ]
    assert version_table_lines, "§9 Version History 表必须含 v0.2.1 / 2026-05-24 行"

    # 不再 assert 顶部 metadata version (会被 v0.2.2 等后续 bump 失效).
    # Dogfood AC 的语义是 "v0.2.1 bump 发生过", 由 version history 表证, 而非
    # current metadata snapshot.
