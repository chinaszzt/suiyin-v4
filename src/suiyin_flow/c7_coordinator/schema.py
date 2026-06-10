"""C7 Phase Coordinator — Pydantic schema.

按 docs/sdd/components/c7-phase-coordinator.md v0.1.0 §2 schema 实现.

分层原则 (spec §2.3): task/phase 级失败是 park (Output park_reason),
run 级失败才是 Error (CoordinatorError).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from suiyin_flow.c2_executor.schema import TaskError, TaskOutput

# 跟 docs/sdd/components/c7-phase-coordinator.md 顶部 Version 同步
C7_SCHEMA_VERSION: str = "v0.1.0"

# -------------------------------------------------------------------
# 状态枚举 (state file 用全集; Output 终态只出现 terminal 子集)
# -------------------------------------------------------------------

TaskState = Literal[
    "pending",         # 未调度
    "executing",       # C2 session 在跑 (crash 后 resume 重 dispatch)
    "awaiting_merge",  # C2 success, 排队待整合
    "integrating",     # 整合子流程中 (ff / rebase-requeue)
    "merged",          # terminal: 已 ff-merge 进 base_branch
    "parked",          # terminal: 隔离 (I8), worktree 保留
    "skipped",         # terminal: 因前序 park 未调度
    "dry_run",         # terminal: dry_run 占位
]

PhaseState = Literal[
    "pending", "executing", "merged", "parked", "skipped", "dry_run"
]

RunStatus = Literal["in_progress", "all_merged", "stopped", "dry_run"]

ParkReason = Literal[
    "TASK_FAILED",      # C2 status=failed (C2 内部重试已耗尽)
    "TASK_ERROR",       # C2 抛 Error (TIMEOUT / SESSION_CRASHED / ...)
    "REBASE_CONFLICT",  # requeue rebase 冲突 (已 abort 还原)
    "REVERIFY_FAILED",  # rebase 干净但重跑 verify_cmd 非绿 (I10)
    "MERGE_NOT_FF",     # requeue 超 max_requeue 仍非 ff (防御性)
]


# -------------------------------------------------------------------
# 记录结构 (state file 与 Output 共用; Output 时全部 terminal)
# -------------------------------------------------------------------


class TaskRecord(BaseModel):
    """单 task 在 coordinator 视角的记录."""

    task_id: str
    state: TaskState = "pending"
    park_reason: ParkReason | None = None
    merged_sha: str | None = Field(
        default=None, description="state=merged 时必填; merge 后 base_branch HEAD"
    )
    requeue_count: int = Field(
        default=0, description="整合阶段 rebase-requeue 已重试次数 (spec I3 retry_count)"
    )
    rebased: bool = False
    reverify_pass: bool | None = Field(
        default=None, description="rebased=true 时必填 (I10)"
    )
    worktree_path: str | None = None
    c2_output: TaskOutput | None = None
    c2_error: TaskError | None = None


class PhaseRecord(BaseModel):
    phase: int
    status: PhaseState = "pending"
    tasks: list[TaskRecord]


class CoordinatorState(BaseModel):
    """Phase-state file schema (spec §2.2) — resume 与 dogfood 都读它."""

    schema_version: str = C7_SCHEMA_VERSION
    run_id: str
    manifest_path: str
    manifest_sha256: str = Field(
        description="resume 时校验 manifest 未被改; 不符 → STATE_CORRUPTED"
    )
    base_branch: str
    status: RunStatus = "in_progress"
    dry_run: bool = False
    phases: list[PhaseRecord]
    merge_queue: list[str] = Field(
        default_factory=list,
        description="待整合 task_id 队列快照 (完成序 = 整合优先级)",
    )
    stopped_at_phase: int | None = None
    updated_at: str = ""


class PhaseRunOutput(BaseModel):
    """`phase run` 整体输出 (spec §2.2)."""

    schema_version: str = C7_SCHEMA_VERSION
    status: Literal["all_merged", "stopped", "dry_run"]
    base_branch: str
    phases: list[PhaseRecord]
    stopped_at_phase: int | None = None
    state_file_path: str


# -------------------------------------------------------------------
# Error (run 级; spec §2.3)
# -------------------------------------------------------------------


CoordinatorErrorCode = Literal[
    "MANIFEST_NOT_FOUND",   # 透传 batch loader
    "INVALID_MANIFEST",     # 透传 batch loader (含 precheck_refs_on_base)
    "INVALID_PLAN",         # execution_plan 校验失败 (§2.1 规则 1/2/3)
    "COORDINATOR_LOCKED",   # I9: 同 repo+base 已有活跃 coordinator
    "STATE_CORRUPTED",      # resume 时 state 解析失败 / manifest 变更 / 与 git 事实矛盾
    "REPO_ROOT_NOT_FOUND",
    "GIT_ERROR",
]


class CoordinatorError(BaseModel):
    code: CoordinatorErrorCode
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    retryable: bool = False


class CoordinatorAbort(Exception):
    """Python exception wrapping CoordinatorError."""

    def __init__(
        self,
        code: CoordinatorErrorCode,
        message: str,
        *,
        retryable: bool = False,
        **details: Any,
    ) -> None:
        self.error = CoordinatorError(
            code=code, message=message, details=details, retryable=retryable
        )
        super().__init__(f"{code}: {message}")
