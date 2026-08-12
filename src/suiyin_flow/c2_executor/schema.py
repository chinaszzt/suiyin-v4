"""C2 Task Executor — Pydantic schema.

按 docs/sdd/components/c2-task-executor.md v0.1.1 §2 schema 实现.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from suiyin_flow.identity import LOCAL_ID_PATTERN, derive_feature_id

# 跟 docs/sdd/components/c2-task-executor.md 顶部 Version 同步
# v0.1.2 (2026-05-24): session.py _maybe_parse_final_output 支持 Claude 真实 stream-json
# v0.1.3 (2026-05-24): P0 spike triage 4 bug bundle:
#   1. session.py 默认 cmd 加 --permission-mode bypassPermissions (AI 工具被拒)
#   2. session.py 默认 cmd 加 --verbose (stream-json + --print 强制要求)
#   3. pyproject.toml entry point 改 suiyin_flow.cli:main + 新增 unified dispatcher
#   4. cli.py:_compute_diff_stats origin/<base> 失败时 fallback 本地 <base>
# PATCH bump (非 schema 变更, 仅 impl 健壮).
# v0.2.0 (2026-06-10): TaskInput 加 open_pr (default true 向后兼容).
# MINOR bump — C7 spec v0.1.0 §7 联动需求 1 (I6: C7 调度下不 push 不开 task PR).
# v0.3.0 (2026-06-10): MINOR — P1.3 R2 + C7 联动需求 2:
#   1. review_feedback input + review_feedback_applied output + REVIEW_FEEDBACK_INVALID
#      (R2 retry-with-feedback, C5 §7 Block Recovery R2 / Q5-5 的 C2 半边)
#   2. WORKTREE_LOCKED + I8 worktree pid 锁 (dogfood 发现 #8 C2 半边)
# v0.3.1 (2026-06-12): PATCH — constitution_ref 默认 docs/sdd/constitution.md →
#   .specify/memory/constitution.md (业务项目 spec-kit 标准位置). r4 真闭环发现 #1:
#   旧默认是 v4 自身路径, 业务项目跑 C2 校验 base HEAD 可见性时 SPEC_NOT_FOUND 阻断
#   (v4 自身 dogfood 显式传 docs/sdd/...; 全部测试显式传 → 零影响).
# v0.4.0 (2026-08-12): MINOR — gen4-plan P0-1 canonical identity:
#   1. TaskInput 加 feature_id (缺省从 base_branch 派生, 向后兼容)
#   2. task_id pattern ^T-\d{3,}$ → LOCAL_ID_PATTERN (T-001B 合法; 002·T001
#      沙盒实验 schema 拒收案例转正)
#   3. worktree 命名 worktrees/<task_id> → worktrees/<feature_id>/<task_id>,
#      分支 task/<task_id> → task/<feature_id>/<task_id> (I1 修订)
SCHEMA_VERSION: str = "v0.4.0"

# -------------------------------------------------------------------
# §2.1 Input Schema
# -------------------------------------------------------------------

Criticality = Literal["low", "medium", "high"]


class TaskInput(BaseModel):
    """C2 §2.1 Input Schema."""

    task_id: str = Field(
        pattern=LOCAL_ID_PATTERN,
        description=(
            "feature 内唯一 (local id), 例 'T-042' / 'T-001B'; "
            "全局身份 = feature_id + task_id"
        ),
    )
    feature_id: str = Field(
        default="",
        description=(
            "canonical key 上半 (gen4-plan P0-1); 约定 = spec-kit feature 目录名。"
            "缺省 ('') 时从 base_branch 派生 (identity.derive_feature_id), "
            "向后兼容旧调用方"
        ),
    )
    spec_ref: str = Field(description="spec.md 路径 (相对 repo_root)")
    plan_ref: str = Field(description="plan.md 路径")
    constitution_ref: str = Field(
        default=".specify/memory/constitution.md",
        description="constitution.md 路径",
    )
    context_seeds: list[str] = Field(
        description="AI session 启动时强制注入的文件清单 (相对 repo_root)",
    )
    verify_cmd: str = Field(
        description="C4 L1+L2 跑通的命令 (worktree 内执行), 例 'suiyin-flow verify run ...'",
    )
    criticality: Criticality = Field(
        description="high 由 C3 Arbiter 调度, C2 直接拒",
    )
    repo_root: str = Field(description="业务项目根目录绝对路径")
    ac_list: list[str] = Field(
        default_factory=list,
        description="本 task 对应的 AC 编号集合 (来自 spec)",
    )
    max_retries: int = Field(
        default=3,
        ge=0,
        le=3,
        description="重试上限 ≤ 3 (PC-1)",
    )
    session_timeout_seconds: int = Field(
        default=7200,
        description="单 session 上限, 超时强制 kill (Q2-1 已拍 2h)",
    )
    base_branch: str = Field(default="main")
    open_pr: bool = Field(
        default=True,
        description=(
            "False 时跳过 push + gh pr create, 只留本地 task/<id> 分支 "
            "(pr_created=False). C7 调度时传 False — task→feature 是本地 "
            "merge 语义, PR 只在 feature→main 层 (C7 spec I6, dogfood 发现 #7)"
        ),
    )
    review_feedback: str | None = Field(
        default=None,
        description=(
            "可选; C5 review_report.json 路径 (绝对或相对 repo_root). "
            "提供时 = R2 retry-with-feedback: findings 注入 prompt "
            "「上次 Review 发现的问题」节. 文件系统校验语义 (运行时 artifact "
            "不入库, 不走 base_branch 可见性校验). retry budget 由 caller "
            "编排 (Q2-6 → Q7-2), C2 单次调用无状态"
        ),
    )

    @model_validator(mode="after")
    def _fill_feature_id(self) -> TaskInput:
        if not self.feature_id:
            self.feature_id = derive_feature_id(None, self.base_branch)
        return self


# -------------------------------------------------------------------
# §2.2 Output Schema
# -------------------------------------------------------------------

Status = Literal["success", "failed"]


class SessionLog(BaseModel):
    """单次 attempt 的 session 日志元信息."""

    # pytest opt-out (虽然不以 Test 开头, 防御性处理)
    __test__ = False

    attempt: int
    log_path: str = Field(description="绝对路径, 指向 .suiyin/sessions/attempt-{N}.log")
    duration_seconds: float
    verify_pass: bool = Field(
        description="本 attempt 末次 verify 是否绿; 未跑到 verify 阶段则为 False",
    )


class DiffStats(BaseModel):
    """git diff 统计 (conditional, when status=success)."""

    files_changed: int = 0
    insertions: int = 0
    deletions: int = 0


class TaskOutput(BaseModel):
    """C2 §2.2 Output Schema.

    填写约定: always (终态必填) / conditional / optional.
    所有 path 字段约定绝对路径.
    """

    task_id: str = Field(description="always; 回传 input.task_id")
    status: Status = Field(description="always; 终态")
    attempts: int = Field(description="always; 实际跑的 session 轮数, ≤ max_retries+1")
    worktree_path: str = Field(
        description=(
            "always; 绝对路径. retain artifact 字段 (不是主产物), 用于: "
            "(1) 失败时人/上游去看现场; (2) 透传给 C4/C5 作为 verify/review input. "
            "主产物是 pr_url_or_branch."
        )
    )
    pr_url_or_branch: str | None = Field(
        default=None,
        description=(
            "conditional (when status=success); "
            "gh 可用 + remote 配置 → PR URL; "
            "gh 不可用 / 无 remote → 本地分支名; "
            "status=failed 时为 null (应同时看 pr_created)"
        ),
    )
    pr_created: bool = Field(
        description="always; true = PR 真的开了; false = 只有本地分支或未推送",
    )
    verify_report_path: str | None = Field(
        default=None,
        description=(
            "conditional (when 至少跑过 1 次 verify_cmd); 绝对路径; "
            "success 时最后一次 (pass), failed 时最后一次 (fail); "
            "verify 一次没跑 (极早期失败) 时为 null"
        ),
    )
    session_logs: list[SessionLog] = Field(
        default_factory=list,
        description="always; 每次 attempt 一项, 按时间顺序",
    )
    diff_stats: DiffStats | None = Field(
        default=None,
        description="conditional (when status=success); git diff 统计",
    )
    review_feedback_applied: bool = Field(
        default=False,
        description=(
            "always; True = 本次 run 注入了 review feedback "
            "(input.review_feedback 提供且解析通过). R2 audit trail"
        ),
    )


# -------------------------------------------------------------------
# §2.3 Error Schema
# -------------------------------------------------------------------

TaskErrorCode = Literal[
    "TIMEOUT",
    "SESSION_CRASHED",
    "VERIFY_FAILED",
    "RETRY_EXHAUSTED",
    "WORKTREE_CONFLICT",
    "SPEC_NOT_FOUND",
    "INVALID_TASK_ID",
    "HIGH_CRITICALITY_REJECT",
    "CONTEXT_SEEDS_MISSING",
    "WORKTREE_LOCKED",
    "REVIEW_FEEDBACK_INVALID",
]


class TaskError(BaseModel):
    """C2 §2.3 Error Schema."""

    code: TaskErrorCode
    message: str
    task_id: str
    details: dict[str, Any] = Field(default_factory=dict)
    retryable: bool = False


class TaskExecutorError(Exception):
    """Python exception wrapping TaskError, raised inside C2 components."""

    def __init__(
        self,
        code: TaskErrorCode,
        message: str,
        task_id: str,
        *,
        retryable: bool = False,
        **details: Any,
    ) -> None:
        self.error = TaskError(
            code=code,
            message=message,
            task_id=task_id,
            details=details,
            retryable=retryable,
        )
        super().__init__(f"{code} ({task_id}): {message}")
