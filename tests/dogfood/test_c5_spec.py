"""Dogfood T-002: C5 AI Reviewer spec 验证.

按 dogfood/T-002/spec.md §5 AC. 测试名 prefix `test_AC_201_` .. `test_AC_208_`
由 C4 parser (Fork G) 识别为 covering AC-201 .. AC-208.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SPEC_PATH = REPO_ROOT / "docs" / "sdd" / "components" / "c5-ai-reviewer.md"


def _spec_text() -> str:
    assert SPEC_PATH.exists(), f"missing c5-ai-reviewer.md: {SPEC_PATH}"
    return SPEC_PATH.read_text(encoding="utf-8")


_CHAPTER_RE = re.compile(r"^## \d+\. ")


def _section_text(content: str, heading: str) -> str:
    """提取 `## N. Title` ... 下一个 chapter heading (`## N. ...`) 之间的正文.

    注意: 必须用 chapter heading 正则识别终结, 不能用 `startswith('## ')`,
    因为 §4 AI Prompt Template 内嵌的 `## Your Role` / `## Input` 等 markdown
    subheader 会被误判为下一个 chapter (导致 section 被错截).
    """
    lines = content.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.strip() == heading:
            start = i + 1
            break
    assert start is not None, f"heading not found: {heading}"
    end = len(lines)
    for j in range(start, len(lines)):
        if _CHAPTER_RE.match(lines[j]):
            end = j
            break
    return "\n".join(lines[start:end])


def test_AC_201_c5_spec_exists_with_8_sections() -> None:
    content = _spec_text()
    expected = [
        "## 0. Type",
        "## 1. Purpose",
        "## 2. Public API",
        "## 3. Behavior Contract",
        "## 4. AI Prompt Template",
        "## 5. Acceptance Criteria",
        "## 6. Open Questions",
        "## 7. Implementation Notes",
    ]
    # 严格按 component-spec-template.md 顺序
    indices = [content.find(h) for h in expected]
    for h, idx in zip(expected, indices):
        assert idx != -1, f"missing section: {h}"
    assert indices == sorted(indices), (
        f"sections not in template order: {list(zip(expected, indices))}"
    )


def test_AC_202_type_is_imperative() -> None:
    content = _spec_text()
    type_section = _section_text(content, "## 0. Type")
    # §0 必须标"自建组件 (imperative ...)"
    assert "自建组件" in type_section, "§0 Type 必须含 '自建组件'"
    assert "imperative" in type_section, "§0 Type 必须含 'imperative' 字样"
    # 必须勾选自建组件 (而非行为契约)
    assert re.search(r"\[x\][^\n]*自建组件", type_section), (
        "§0 Type 必须勾选 [x] 自建组件"
    )


def test_AC_203_public_api_has_3_yaml_blocks_and_verdict_findings() -> None:
    content = _spec_text()
    api_section = _section_text(content, "## 2. Public API")
    # 至少 3 个 ```yaml``` block (Input / Output / Error)
    yaml_blocks = re.findall(r"```yaml\b.*?```", api_section, flags=re.DOTALL)
    assert len(yaml_blocks) >= 3, (
        f"§2 Public API 必须含 ≥3 个 yaml block, 实际 {len(yaml_blocks)}"
    )
    # Output schema 必须含 verdict + findings
    output_combined = "\n".join(yaml_blocks)
    assert "verdict" in output_combined, "§2 Public API 必须含 verdict 字段"
    assert "findings" in output_combined, "§2 Public API 必须含 findings 字段"


def test_AC_204_invariants_at_least_5_and_includes_isolation() -> None:
    content = _spec_text()
    behavior_section = _section_text(content, "## 3. Behavior Contract")
    # 计数 I1..IN 形式的 invariants (粗匹配 `**I\d+**` markdown bold)
    invariants = re.findall(r"\*\*I\d+\*\*", behavior_section)
    assert len(invariants) >= 5, (
        f"§3.1 Invariants 至少 5 条, 实际 {len(invariants)} 条 ({invariants})"
    )
    # 必含隔离 invariant: "独立 session, 不继承 implementer context"
    # 宽松匹配多种写法
    isolation_keywords = ["独立", "不继承", "implementer"]
    for kw in isolation_keywords:
        assert kw in behavior_section, (
            f"§3 必含隔离 invariant 关键字: {kw}（C5 独立 session 不继承 implementer context）"
        )


def test_AC_205_prompt_template_not_na() -> None:
    content = _spec_text()
    prompt_section = _section_text(content, "## 4. AI Prompt Template")
    # 不能是 N/A
    body = prompt_section.strip()
    assert body, "§4 AI Prompt Template 不能为空"
    # 排除 "N/A" 开头声明
    first_500 = body[:500]
    assert "N/A" not in first_500 or "N/A —" not in first_500, (
        "§4 不能标 N/A — C5 是 imperative 组件必有完整 prompt"
    )
    # 必含 Your Role / Input / Steps / Output / Constraints 5 个子节
    for required in ["Your Role", "Input", "Steps", "Output", "Constraints"]:
        assert required in prompt_section, (
            f"§4 AI Prompt Template 必须含 '{required}' 子节"
        )


def test_AC_206_at_least_6_ac_in_spec() -> None:
    content = _spec_text()
    ac_section = _section_text(content, "## 5. Acceptance Criteria")
    # 匹配 `**AC-N**` markdown bold 形式
    acs = re.findall(r"\*\*AC-\d+\*\*", ac_section)
    assert len(acs) >= 6, (
        f"§5 Acceptance Criteria 至少 6 条 AC (C5 自己的), 实际 {len(acs)} 条 ({acs})"
    )


def test_AC_207_finding_categories_include_complexity_and_reusable_knowledge() -> None:
    content = _spec_text()
    # 全文搜 (AC-207: §5/§3/§7 任一处含; 全文搜即可覆盖)
    assert "complexity" in content, (
        "finding category 必须含 'complexity' (Fork L: 跨文件查重 / 调 C11 query)"
    )
    assert "reusable_knowledge_not_captured" in content, (
        "finding category 必须含 'reusable_knowledge_not_captured' "
        "(C12 Knowledge Capture, 见 discussion-notes.md §十 + diagrams.md 图 11)"
    )


def test_AC_208_q5_listed_in_open_questions() -> None:
    content = _spec_text()
    q_section = _section_text(content, "## 6. Open Questions")
    # 必含 Q5 (来自 toolchain.md §六附录 B)
    assert re.search(r"\bQ5\b", q_section), "§6 必须列 Q5 (toolchain.md §六附录 B)"
    # Q5 内容描述: 单次 vs N=2 仲裁 + criticality 路由
    q5_keywords = ["N=2", "criticality"]
    for kw in q5_keywords:
        assert kw in q_section, (
            f"§6 Q5 描述必须含关键字: {kw} (单次 review vs N=2 分歧仲裁, 按 criticality 路由)"
        )
