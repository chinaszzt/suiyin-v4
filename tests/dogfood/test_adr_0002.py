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
    constitution_path = REPO_ROOT / "docs" / "sdd" / "constitution.md"
    assert constitution_path.exists(), f"missing constitution: {constitution_path}"

    content = constitution_path.read_text(encoding="utf-8")

    # 顶部 metadata Version 升 v0.2.1
    assert "**Version**: v0.2.1" in content, "constitution 顶部 metadata 必须 bump 到 v0.2.1"

    # §6b Q-C-2 关闭，引用 ADR-0002
    q_c_2_lines = [
        line for line in content.splitlines() if "Q-C-2" in line and "ADR-0002" in line
    ]
    assert q_c_2_lines, "§6b Q-C-2 行必须更新为引用 ADR-0002"
    assert any("已拍" in line for line in q_c_2_lines), "§6b Q-C-2 行必须标 '已拍'"

    # §9 Version History 表加 v0.2.1 行 (2026-05-24)
    version_table_lines = [
        line for line in content.splitlines()
        if line.startswith("| v0.2.1") and "2026-05-24" in line
    ]
    assert version_table_lines, "§9 Version History 表必须含 v0.2.1 / 2026-05-24 行"
