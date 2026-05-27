"""C6 Gate Contract — Pydantic schema.

按 docs/sdd/components/c6-gate-contract.md v0.1.1 §2 schema 实现.

**Schema 形态约定** (§2.2 顶部 + Q6-6):
- 可选字段一律 **omit-when-absent** — `model_dump(exclude_none=True)` 序列化时
  不 emit `null` 占位。consumer 用 `"reason" in payload` 判存在。
- Error 与 Output 互斥 top-level shape (§2.3 顶部) — `code in payload` 区分。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

# 跟 docs/sdd/components/c6-gate-contract.md 顶部 Version 同步.
# v0.1.3 (2026-05-27, PR #35 dogfood Bug 1): §3.2 Merge to main 收敛为单一路径
# (push <sha>:main + update-ref refs/heads/main), 删 checkout-based 选项 (NC-4
# worktree 不兼容). impl actions.py 跟随 refs-direct 重写. PATCH bump (路径
# 收敛, invariant 仍 ff-only main history).
# v0.1.2 (2026-05-25, PR #34 cascade): §3.2 dry_run 落盘边界 clarify.
# v0.1.1 (2026-05-25): round-3 max-effort review — omit-when-absent / I8 / I9 / etc.
CONTRACT_VERSION: str = "v0.1.3"

# -------------------------------------------------------------------
# Enums (§2.2 / §2.3)
# -------------------------------------------------------------------

GateResult = Literal["merged", "held"]

# 4 个 held 原因 — 按 I8 precedence 单选其一
Reason = Literal[
    "HUMAN_BLOCKED",       # I8 优先级最高 (人已介入)
    "VERIFY_NOT_PASS",
    "REVIEW_NOT_APPROVE",  # 触发 R1 (label + comment)
    "NOT_FF_MERGEABLE",
]

# 按 I8 precedence 排序的元组 — rules.py / actions.py 共用
REASON_PRECEDENCE: tuple[Reason, ...] = (
    "HUMAN_BLOCKED",
    "VERIFY_NOT_PASS",
    "REVIEW_NOT_APPROVE",
    "NOT_FF_MERGEABLE",
)

RecoveryKind = Literal["r1_label_and_comment", "no_op"]

# §2.3 Error code (跟 reason 命名空间互斥)
Code = Literal[
    "MISSING_INPUT",
    "INVALID_REPORT",
    "GIT_ERROR",
    "GH_ERROR",
    "PERMISSION_DENIED",
]


# -------------------------------------------------------------------
# Models (§2.1 / §2.2 / §2.3)
# -------------------------------------------------------------------


class GateInput(BaseModel):
    """§2.1 Input Schema."""

    pr_ref: str = Field(..., description="PR URL / PR 编号 / 本地分支名")
    verify_report_path: str = Field(..., description="C4 verify_report.json 路径")
    review_report_path: str = Field(..., description="C5 review_report.json 路径")
    repo_root: str = Field(..., description="业务项目根目录（绝对路径）")
    dry_run: bool = Field(default=False, description="true 时跳过所有副作用")


class RulesBreakdown(BaseModel):
    """§2.2 rules 字段 — 4 条规则的 pass/fail boolean breakdown."""

    verify_all_pass: bool
    review_approved: bool
    ff_mergeable: bool
    not_human_blocked: bool


class RecoveryAction(BaseModel):
    """§2.2 recovery_action 字段 — held 时填，merged 时整体 absent."""

    kind: RecoveryKind
    # I9 atomicity — kind=r1_label_and_comment 时必填，kind=no_op 时 absent
    label_added: bool | None = None
    comment_posted: bool | None = None
    comment_url: str | None = None
    partial_failure: Code | None = None  # I9 R1 partial failure 时填错误码

    model_config = {"json_schema_extra": {"description": "omit-when-absent (exclude_none)"}}


class GateOutput(BaseModel):
    """§2.2 Output Schema — gate_result + rules + (held 时) reason/recovery_action."""

    gate_result: GateResult
    rules: RulesBreakdown
    reason: Reason | None = None             # held 时必填，merged 时 absent
    recovery_action: RecoveryAction | None = None  # held 时必填，merged 时 absent
    merged_sha: str | None = None            # merged+dry_run=false 时必填
    timestamp: str                            # ISO8601 UTC，不参与 I6 determinism

    def to_dict(self) -> dict[str, Any]:
        """omit-when-absent 序列化 (Q6-6 决议).

        exclude_none=True 把 None 字段全 drop，不输出 `null` 占位。
        recovery_action 内部嵌套字段同理（Pydantic 递归 exclude_none）。
        """
        return self.model_dump(exclude_none=True)


class GateError(BaseModel):
    """§2.3 Error Schema — 与 Output 互斥 top-level shape."""

    code: Code
    message: str
    details: dict[str, Any] | None = None
    retryable: bool = False

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


# -------------------------------------------------------------------
# Internal exception (raised in pipeline, caught at top-level → GateError)
# -------------------------------------------------------------------


class GateContractError(Exception):
    """Pipeline-internal raise; cli.main 转 GateError 序列化."""

    def __init__(
        self,
        code: Code,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code: Code = code
        self.message = message
        self.details = details
        self.retryable = retryable

    def to_error(self) -> GateError:
        return GateError(
            code=self.code,
            message=self.message,
            details=self.details,
            retryable=self.retryable,
        )
