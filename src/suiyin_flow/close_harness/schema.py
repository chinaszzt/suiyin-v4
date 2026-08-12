"""Feature 收口 harness — schema (gen4-plan P0-4).

定位: Q7-3 (feature→main 收口编排) 完整实现前的确定性脚本串接。
**不宣称端到端全自动** — 任一步失败即停 + surface to human (fail-closed)。
路由零 AI (C7 I2 同源纪律); AI 只存在于 C5 review session 内部。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

CLOSE_SCHEMA_VERSION: str = "v0.1.0"


StepName = Literal[
    "human_block",   # 本地 block 状态检查 (最先; HUMAN_BLOCKED 优先级同 C6 I8)
    "acgate",        # AC 冻结闸 (feature 相对 target 的 diff)
    "mutation",      # mutation 探针 (触发键命中才跑)
    "verify",        # C4 全量 (feature HEAD, throwaway worktree)
    "review",        # C5 subject=feature (含 task_ids[])
    "gate",          # C6 (verify+review 票 → ff-merge feature→target)
]

StepStatus = Literal[
    "passed",
    "failed",
    "skipped",            # 触发键未命中等, 语义正常
    "skipped_warning",    # 前置工件缺失 (ac-manifest / mutants.yaml), 迁移期放行 + 警告
    "not_reached",        # 前面某步已停
]


class CloseStep(BaseModel):
    name: StepName
    status: StepStatus
    detail: str = ""
    report_path: str | None = Field(
        default=None, description="该步产物 (gate/probe/verify/review report) 绝对路径"
    )


CloseVerdict = Literal["merged", "held", "blocked", "error"]


class CloseReport(BaseModel):
    """收口 run 的落盘产物: .suiyin/close/<safe_feature>-<run_id>.json + latest."""

    schema_version: str = CLOSE_SCHEMA_VERSION
    feature_id: str
    base_branch: str = Field(description="feature 分支 (被收口方)")
    target_branch: str = Field(description="收口目标 (通常 main)")
    verdict: CloseVerdict = Field(
        description=(
            "merged = 全链过 + C6 已 ff-merge; held = 某闸/门拦下 (worktree 与"
            "工件保留); blocked = 本地 human:block; error = run 级错误"
        )
    )
    held_at: StepName | None = Field(
        default=None, description="verdict=held 时: 停在哪一步"
    )
    steps: list[CloseStep]
    run_id: str
    updated_at: str = ""


# -------------------------------------------------------------------
# 本地 human:block 状态 (GitHub label 降级为可选 adapter, 拍板 P0-4)
# -------------------------------------------------------------------


class BlockEvent(BaseModel):
    action: Literal["block", "unblock"]
    reason: str
    by: str
    ts: str


class BlockState(BaseModel):
    """`.suiyin/blocks/<safe_feature>.json` — versioned 本地 block 状态."""

    schema_version: str = CLOSE_SCHEMA_VERSION
    feature_id: str
    blocked: bool = False
    reason: str = ""
    history: list[BlockEvent] = Field(default_factory=list)


CloseErrorCode = Literal[
    "MANIFEST_NOT_FOUND",
    "INVALID_MANIFEST",
    "REPO_ROOT_NOT_FOUND",
    "GIT_ERROR",
    "STEP_ERROR",
]


class CloseError(Exception):
    def __init__(self, code: CloseErrorCode, message: str, **details: Any) -> None:
        self.code: CloseErrorCode = code
        self.message = message
        self.details = details
        super().__init__(f"{code}: {message}")
