"""C1 Planning Engine — Pydantic schema.

按 docs/sdd/components/c1-planning-engine.md v0.1.0 §2.
execution_plan 形态复用 C7 的 ExecutionPlanEntry (单一真相, I1 自检也用 C7 校验).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

# 跟 docs/sdd/components/c1-planning-engine.md 顶部 Version 同步.
# v0.1.0 (2026-06-10): 初版 — 静态依赖分层 + 冲突拆分 + 语义 pass 骨架.
SCHEMA_VERSION: str = "v0.1.0"


# -------------------------------------------------------------------
# §2.2 Output Schema
# -------------------------------------------------------------------

ConflictReason = Literal[
    "modifies_overlap",
    "context_seeds_overlap",
    "semantic_conflict",
]


class ConflictSplit(BaseModel):
    """被冲突检测拆开的 task 对 + 依据 (audit trail)."""

    task_a: str
    task_b: str = Field(description="manifest 序更靠后、被推到更晚 phase 的一方")
    reason: ConflictReason
    evidence: str = Field(description="重叠路径/glob, 或语义 pass 的一句话理由")


class SemanticPassResult(BaseModel):
    """--semantic-pass 透明记录 (conditional)."""

    completed: bool = Field(description="session 成功跑完且输出可解析")
    adjustments: int = Field(default=0, description="语义 pass 收紧的 task 对数")
    fallback_reason: str | None = Field(
        default=None,
        description="session 失败时 fallback 纯静态结果的原因 (Q1-2)",
    )


class PlanOutput(BaseModel):
    """C1 §2.2 Output Schema."""

    schema_version: str = SCHEMA_VERSION
    status: Literal["written", "dry_run"] = Field(description="always")
    phases_count: int = Field(description="always")
    tasks_count: int = Field(description="always")
    execution_plan: list[dict[str, Any]] = Field(
        default_factory=list,
        description="always; [{phase, parallel: [task_id]}], 与写回 yaml 一致",
    )
    conflict_splits: list[ConflictSplit] = Field(
        default_factory=list,
        description="always (可空); 冲突拆分 audit",
    )
    semantic_pass: SemanticPassResult | None = Field(
        default=None,
        description="conditional (when input.semantic_pass=true)",
    )
    written_to: str | None = Field(
        default=None,
        description="always; 绝对路径; dry_run 时 null",
    )


# -------------------------------------------------------------------
# §2.3 Error Schema
# -------------------------------------------------------------------

PlanErrorCode = Literal[
    "MANIFEST_NOT_FOUND",      # 透传 batch loader
    "INVALID_MANIFEST",        # 透传 batch loader (+ C1 扩展: base_branch 不一致)
    "CYCLE_DETECTED",          # depends_on 全图成环
    "PLAN_SELF_CHECK_FAILED",  # 产出未过 C7 三规则自检 (I1; 防御性)
    "WRITE_FAILED",            # 写回 tasks.yaml 失败
]


class PlanError(BaseModel):
    """C1 §2.3 Error Schema."""

    code: PlanErrorCode
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    retryable: bool = False


class PlanningError(Exception):
    """Python exception wrapping PlanError."""

    def __init__(
        self,
        code: PlanErrorCode,
        message: str,
        *,
        retryable: bool = False,
        **details: Any,
    ) -> None:
        self.error = PlanError(
            code=code, message=message, details=details, retryable=retryable
        )
        super().__init__(f"{code}: {message}")
