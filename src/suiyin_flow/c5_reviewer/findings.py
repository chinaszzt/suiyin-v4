"""C5 finding 处理 — verdict 推导 + 4-field validation.

v0.1.1: verdict 按 finding **category** 决定 (替代旧"按 severity").
BLOCK_SET 集合内任一 category 出现 → verdict=block; 其他 → approve + audit.
"""

from __future__ import annotations

from suiyin_flow.c5_reviewer.contract import (
    BLOCK_SET,
    Finding,
    Verdict,
)


def derive_verdict(findings: list[Finding]) -> Verdict:
    """按 v0.1.1 I3-I5: 按 category 决定 verdict.

    - 空 findings → approve (I4)
    - 任一 finding.category ∈ BLOCK_SET → block (I5)
    - 否则 (全是 complexity / pc_violation / cross_platform /
      reusable_knowledge_not_captured) → approve (I3 audit)
    """
    if not findings:
        return "approve"
    if any(f.category in BLOCK_SET for f in findings):
        return "block"
    return "approve"


def has_blocking_findings(findings: list[Finding]) -> bool:
    """语义糖: 是否含 block 集合 category."""
    return any(f.category in BLOCK_SET for f in findings)


def audit_findings(findings: list[Finding]) -> list[Finding]:
    """非阻断 findings (verdict=approve 时也要保留作 audit trail).

    用于 review_report.json 输出: 即使 approve 也保留全部 findings (audit) —
    特别是 C12 触发的 `reusable_knowledge_not_captured` (I6 要求即使 low 也输出).
    """
    return list(findings)  # 不过滤; 全保留
