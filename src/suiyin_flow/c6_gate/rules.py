"""C6 rules evaluation — 4 boolean rules + I8 reason precedence.

按 c6 spec §3.1 I1-I9 + AC-1..AC-10.

**纯函数模块** — 无 IO，不调 git / gh / subprocess。input = 解析好的
verify_report / review_report dict + ff_mergeable bool + has_human_block bool,
output = (RulesBreakdown, reason | None)。
"""

from __future__ import annotations

from typing import Any

from suiyin_flow.c6_gate.contract import (
    REASON_PRECEDENCE,
    GateContractError,
    Reason,
    RulesBreakdown,
)


def evaluate_rules(
    *,
    verify_report: dict[str, Any],
    review_report: dict[str, Any],
    ff_mergeable: bool,
    has_human_block: bool,
) -> RulesBreakdown:
    """评估 4 条规则，返回 boolean breakdown (§2.2 rules 字段).

    严格按 c6 §3.1 I1 字段名:
      verify_all_pass = verify_report["overall_verdict"] == "pass"  (C4 §2.2)
      review_approved = review_report["verdict"] == "approve"        (C5 §2.2)

    Raises:
        GateContractError("INVALID_REPORT") 字段缺失时
            — AC-6b: 缺字段不静默当 fail / not-approve。
    """
    if "overall_verdict" not in verify_report:
        raise GateContractError(
            "INVALID_REPORT",
            "verify_report missing required field 'overall_verdict' (C4 §2.2)",
            details={"field": "overall_verdict", "report": "verify_report"},
        )
    if "verdict" not in review_report:
        raise GateContractError(
            "INVALID_REPORT",
            "review_report missing required field 'verdict' (C5 §2.2)",
            details={"field": "verdict", "report": "review_report"},
        )

    return RulesBreakdown(
        verify_all_pass=verify_report["overall_verdict"] == "pass",
        review_approved=review_report["verdict"] == "approve",
        ff_mergeable=ff_mergeable,
        not_human_blocked=not has_human_block,
    )


def select_reason(rules: RulesBreakdown) -> Reason | None:
    """I8 precedence — 多条规则同时 false 时按固定优先级单选 reason.

    优先级 (高→低): HUMAN_BLOCKED > VERIFY > REVIEW > NOT_FF.
    全 pass → 返回 None (caller 视作 merged)。

    Examples:
        verify=fail + human:block 已存在 → HUMAN_BLOCKED (AC-5).
        verify=fail + review=block       → VERIFY_NOT_PASS.
    """
    rule_to_reason: dict[Reason, bool] = {
        "HUMAN_BLOCKED": not rules.not_human_blocked,
        "VERIFY_NOT_PASS": not rules.verify_all_pass,
        "REVIEW_NOT_APPROVE": not rules.review_approved,
        "NOT_FF_MERGEABLE": not rules.ff_mergeable,
    }
    for reason in REASON_PRECEDENCE:
        if rule_to_reason[reason]:
            return reason
    return None  # 全 pass


def all_rules_pass(rules: RulesBreakdown) -> bool:
    """Convenience — gate_result=merged 当且仅当 4 条全 true。"""
    return (
        rules.verify_all_pass
        and rules.review_approved
        and rules.ff_mergeable
        and rules.not_human_blocked
    )
