"""C5 AI Reviewer — Pydantic schema.

按 docs/sdd/components/c5-ai-reviewer.md v0.1.1 §2 schema 实现.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

# 跟 docs/sdd/components/c5-ai-reviewer.md 顶部 Version 同步.
# v0.1.1 (2026-05-24): verdict 二元化 + 按 category 决定 + Block Recovery.
CONTRACT_VERSION: str = "v0.1.1"

# -------------------------------------------------------------------
# Enums
# -------------------------------------------------------------------

Severity = Literal["low", "medium", "high", "critical"]
Criticality = Literal["low", "medium", "high"]
Verdict = Literal["approve", "block"]  # v0.1.1: 去 request_changes

# Finding categories (C5 spec §2.2 + §7 Finding Category 设计要点)
Category = Literal[
    "complexity",                       # Fork L: C11 query + jscpd
    "spec_drift",                       # PR diff 跟 spec 不对齐
    "ac_uncovered",                     # spec AC 缺对应 test
    "nc_violation",                     # 违反 constitution NC-1..NC-5
    "pc_violation",                     # 违反 PC-1..PC-3
    "cross_platform",                   # NC-5 跨平台违规
    "security",                         # hardcoded secret / injection / 等
    "reusable_knowledge_not_captured",  # C12 触发, I6 必输出
]

# Block 集合 (v0.1.1 I5): finding 含其中任一 category → verdict=block.
# 其他 category → approve + finding audit trail.
BLOCK_SET: frozenset[Category] = frozenset(
    {"nc_violation", "security", "spec_drift", "ac_uncovered"}
)


# -------------------------------------------------------------------
# §2.1 Input Schema
# -------------------------------------------------------------------


class ReviewInput(BaseModel):
    """C5 §2.1 Input Schema (v0.1.1: task_id 进 required)."""

    pr_ref: str = Field(description="PR URL (gh 可达) 或本地分支名 (无 remote 时降级)")
    spec_ref: str = Field(description="spec.md 路径 (相对 repo_root 或绝对)")
    plan_ref: str = Field(description="plan.md 路径")
    constitution_ref: str = Field(
        default="docs/sdd/constitution.md",
        description="constitution.md 路径",
    )
    verify_report_path: str | None = Field(
        default=None,
        description=(
            "optional; C4 verify_report.json 绝对路径; "
            "缺失时 C5 仍 work 但 AC 覆盖判断变弱"
        ),
    )
    task_id: str = Field(
        pattern=r"^T-\d{3,}$",
        description=(
            "v0.1.1 required: 所有 PR 必须来自 task (含 hotfix / Initiative). "
            "C5 不审'非 task PR' (应先把任务 task 化)."
        ),
    )
    criticality: Criticality = Field(
        description="low/medium → 单次 review; high → N=2 仲裁 (P1.2 spike 后启用)"
    )
    repo_root: str = Field(description="业务项目根目录绝对路径")
    session_timeout_seconds: int = Field(
        default=1800,
        description="单 review session 上限 (默认 30 min, kill -9 整树)",
    )
    max_retries: int = Field(
        default=2,
        ge=0,
        le=2,
        description="SESSION_CRASHED / PR_DIFF_FETCH_FAILED 重试上限",
    )


# -------------------------------------------------------------------
# §2.2 Output Schema — review_report.json
# -------------------------------------------------------------------


class Finding(BaseModel):
    """单条 finding (C5 spec §I2: 必 4 字段齐)."""

    # pytest opt-out: Pydantic model 不是 test class
    __test__ = False

    severity: Severity
    category: Category
    location: str = Field(
        description="file:line 或 spec section reference, 例 'src/foo.py:42' / 'spec.md §3.1'"
    )
    suggested_fix: str = Field(
        description="具体可操作的修复建议 (不是泛泛 '改进代码')"
    )


ArbitrationMode = Literal["single", "n2_consensus", "n2_arbitrated"]


class Arbitration(BaseModel):
    """N=2 仲裁模式信息 (v0.1.x 阶段未启用, P1.2 spike 后实际生效)."""

    mode: ArbitrationMode = "single"
    reviewer_count: int = 1
    arbiter_session_id: str | None = None


class ReviewReport(BaseModel):
    """C5 §2.2 Output Schema — review_report.json (v0.1.1)."""

    verdict: Verdict = Field(
        description="always; 按 finding category 决定 (block 集合任一 → block; 其他 → approve)"
    )
    findings: list[Finding] = Field(
        default_factory=list,
        description="always; 每条 Finding 4 字段齐 (I2); 空数组合法 (无 issue → approve)",
    )
    reviewed_at: datetime = Field(description="always; ISO 8601")
    session_id: str = Field(description="always; 本次 review session UUID")
    task_id: str | None = Field(
        default=None,
        pattern=r"^T-\d{3,}$",
        description="conditional (when input.task_id 非空, v0.1.1 实际 always)",
    )
    pr_ref: str = Field(description="always; 回传 input.pr_ref")
    contract_version: str = Field(
        pattern=r"^v\d+\.\d+\.\d+$",
        description="always; 本 spec 版本号",
    )
    arbitration: Arbitration | None = Field(
        default=None,
        description="conditional (when criticality=high 走 N=2 模式)",
    )


# -------------------------------------------------------------------
# §2.3 Error Schema
# -------------------------------------------------------------------

ErrorCode = Literal[
    "SESSION_CRASHED",
    "TIMEOUT",
    "SPEC_NOT_FOUND",
    "PR_DIFF_FETCH_FAILED",
    "INVALID_PR_REF",
    "VERIFY_REPORT_PARSE_FAILED",
    "ARBITRATION_DEADLOCK",
    "REPO_ROOT_NOT_FOUND",
    "INVALID_TASK_ID",  # task_id required after v0.1.1, schema 校验失败
]


class ReviewError(BaseModel):
    """C5 §2.3 Error Schema."""

    code: ErrorCode
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ReviewerError(Exception):
    """Python exception wrapping ReviewError, raised inside C5 components."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        **details: Any,
    ) -> None:
        self.error = ReviewError(code=code, message=message, details=details)
        super().__init__(f"{code}: {message}")
