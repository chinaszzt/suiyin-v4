"""C2 Batch Adapter — tasks.yaml → 顺序调度多 task.

P1.2.5: 把 C2 从「人手敲单 task CLI」升级成「读 tasks.yaml 顺序跑一批」。

设计原则 (跟 todo.md §P1.2.5 一致)：
- **不 bump C2 spec**: 这是 CLI adapter, 不改 §2 contract (TaskInput/TaskOutput/TaskError).
- **顺序串行, fail-stop**: 中间 task fail 立即停, 后续 task 标 skipped.
- **不做拓扑/并行**: `depends_on` 只做"被依赖 task 必须在前"的顺序断言.
  真正的依赖图调度 / 并行 phase 划分留给 P1.3 C1 Planning Engine.
- **dry-run**: 解析 + 列 task, 不真起 session.

Schema 版本 v0.1.0 (随 batch 模块 introduce). 跟 C2 SCHEMA_VERSION 解耦.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from suiyin_flow.c2_executor.cli import execute_task
from suiyin_flow.c2_executor.schema import (
    Criticality,
    TaskError,
    TaskExecutorError,
    TaskInput,
    TaskOutput,
)

BATCH_SCHEMA_VERSION: str = "v0.1.0"


# -------------------------------------------------------------------
# Manifest schema (tasks.yaml on disk)
# -------------------------------------------------------------------


class BatchTaskEntry(BaseModel):
    """tasks.yaml 单 task 条目.

    映射到 C2 TaskInput 的字段; `repo_root` 不在 yaml 里 (CLI --repo-root 注入).
    """

    task_id: str = Field(pattern=r"^T-\d{3,}$")
    spec_ref: str
    plan_ref: str
    constitution_ref: str = ".specify/memory/constitution.md"
    context_seeds: list[str] = Field(default_factory=list)
    verify_cmd: str
    criticality: Criticality = "medium"
    ac_list: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(
        default_factory=list,
        description="P1.2.5 只用做顺序断言; 真正调度留 P1.3 C1",
    )
    modifies: list[str] = Field(
        default_factory=list,
        description=(
            "可选; 本 task 的写足迹 (文件路径 / glob, 例 'src/auth/**'). "
            "C1 Planning Engine 联动需求 1 (c1 spec §7): 静态冲突检测据此把"
            "会写同一文件的 task 拆到不同 phase; 缺省时 C1 fallback 用 "
            "context_seeds 重叠当保守近似。batch / C7 不读此字段 (向后兼容, "
            "schema_version 不 bump)。来源: /sy-tasks 声明 (Q1-3) 或人补"
        ),
    )
    max_retries: int = Field(default=3, ge=0, le=3)
    session_timeout_seconds: int = Field(default=7200, gt=0)
    base_branch: str = "main"

    def to_task_input(self, *, repo_root: str) -> TaskInput:
        """转 C2 TaskInput; repo_root 由 batch caller 注入 (CLI 顶层参数)."""
        return TaskInput(
            task_id=self.task_id,
            spec_ref=self.spec_ref,
            plan_ref=self.plan_ref,
            constitution_ref=self.constitution_ref,
            context_seeds=self.context_seeds,
            verify_cmd=self.verify_cmd,
            criticality=self.criticality,
            repo_root=repo_root,
            ac_list=self.ac_list,
            max_retries=self.max_retries,
            session_timeout_seconds=self.session_timeout_seconds,
            base_branch=self.base_branch,
        )


class BatchManifest(BaseModel):
    """tasks.yaml 顶层 schema."""

    schema_version: str = Field(description="tasks.yaml schema 版本; 当前 'v0.1.0'")
    feature_name: str | None = Field(
        default=None,
        description="spec-kit feature 名 (例 '001-c4-no-color'); optional metadata",
    )
    tasks: list[BatchTaskEntry] = Field(min_length=1)

    @field_validator("schema_version")
    @classmethod
    def _check_schema_version(cls, v: str) -> str:
        if v != BATCH_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported schema_version: {v!r}; "
                f"this build only understands {BATCH_SCHEMA_VERSION!r}"
            )
        return v

    @model_validator(mode="after")
    def _check_unique_task_ids(self) -> BatchManifest:
        seen: set[str] = set()
        for entry in self.tasks:
            if entry.task_id in seen:
                raise ValueError(f"duplicate task_id in tasks: {entry.task_id!r}")
            seen.add(entry.task_id)
        return self

    @model_validator(mode="after")
    def _check_dependency_order(self) -> BatchManifest:
        seen: set[str] = set()
        for entry in self.tasks:
            for dep in entry.depends_on:
                if dep == entry.task_id:
                    raise ValueError(
                        f"task {entry.task_id!r} depends_on itself"
                    )
                if dep not in seen:
                    raise ValueError(
                        f"BATCH_ORDER_VIOLATION: task {entry.task_id!r} "
                        f"depends_on {dep!r} which has not appeared earlier in "
                        f"tasks[]. P1.2.5 不做拓扑排序; 请把被依赖 task 放在前面。"
                    )
            seen.add(entry.task_id)
        return self


# -------------------------------------------------------------------
# Batch output schema (CLI artifact)
# -------------------------------------------------------------------


BatchTaskStatus = Literal["success", "failed", "skipped", "dry_run"]
BatchOverallStatus = Literal["all_success", "partial_failed", "dry_run"]


class BatchTaskResult(BaseModel):
    """单 task 在 batch 内的结果记录."""

    task_id: str
    status: BatchTaskStatus
    output: TaskOutput | None = Field(
        default=None,
        description="status in {success, failed} 时填; success 必有, failed best-effort",
    )
    error: TaskError | None = Field(
        default=None,
        description="status=failed 时填; TaskExecutorError 序列化",
    )


class BatchOutput(BaseModel):
    """`task batch` 整体输出."""

    schema_version: str = BATCH_SCHEMA_VERSION
    feature_name: str | None = None
    status: BatchOverallStatus
    tasks: list[BatchTaskResult]
    stopped_at_task_id: str | None = Field(
        default=None,
        description="中间 fail 时填; 之后 task 都 skipped",
    )


# -------------------------------------------------------------------
# Batch errors
# -------------------------------------------------------------------


BatchErrorCode = Literal[
    "INVALID_MANIFEST",      # yaml 解析失败 / pydantic 校验失败
    "MANIFEST_NOT_FOUND",    # path 不存在
    "REPO_ROOT_NOT_FOUND",   # --repo-root 不是目录
]


class BatchError(BaseModel):
    code: BatchErrorCode
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class BatchAdapterError(Exception):
    """Python exception wrapping BatchError."""

    def __init__(self, code: BatchErrorCode, message: str, **details: Any) -> None:
        self.error = BatchError(code=code, message=message, details=details)
        super().__init__(f"{code}: {message}")


# -------------------------------------------------------------------
# Manifest loading
# -------------------------------------------------------------------


def load_tasks_yaml(path: Path) -> BatchManifest:
    """读 tasks.yaml + 解析 + 校验.

    Raises BatchAdapterError:
      - MANIFEST_NOT_FOUND: path 不存在 / 非文件
      - INVALID_MANIFEST: yaml 解析失败 / schema 校验失败 / 字段越界
    """
    if not path.exists() or not path.is_file():
        raise BatchAdapterError(
            "MANIFEST_NOT_FOUND",
            f"tasks.yaml not found: {path}",
            path=str(path),
        )

    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise BatchAdapterError(
            "MANIFEST_NOT_FOUND",
            f"could not read tasks.yaml: {e}",
            path=str(path),
        ) from e

    try:
        data = yaml.safe_load(raw_text)
    except yaml.YAMLError as e:
        raise BatchAdapterError(
            "INVALID_MANIFEST",
            f"YAML parse error: {e}",
            path=str(path),
        ) from e

    if not isinstance(data, dict):
        raise BatchAdapterError(
            "INVALID_MANIFEST",
            f"tasks.yaml top level must be a mapping, got {type(data).__name__}",
            path=str(path),
        )

    try:
        return BatchManifest.model_validate(data)
    except ValidationError as e:
        raise BatchAdapterError(
            "INVALID_MANIFEST",
            f"schema validation failed: {e}",
            path=str(path),
        ) from e


# -------------------------------------------------------------------
# Base-branch ref visibility precheck
# -------------------------------------------------------------------


def _git_ok(repo_root: str, *args: str) -> bool:
    """跑 git 命令, 只看 returncode==0. 任何异常 (git 不存在等) 视为 False."""
    try:
        result = subprocess.run(
            ["git", "-C", repo_root, *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            shell=False,
            check=False,
        )
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return False
    return result.returncode == 0


def _refs_missing_on_base(repo_root: str, entry: BatchTaskEntry) -> list[str]:
    """返回 entry 的 spec_ref/plan_ref 中, 在 base_branch HEAD 上看不到的 ref.

    P1.2.5 真闭环 dogfood 发现 #2: /sy-* 产物若没 commit 到 base_branch,
    C2 task worktree 从 base HEAD 分叉后看不到 spec_ref/plan_ref —— session
    拿不到输入, 整段 ~2h 的真跑直接废掉。这里把这种情况 fail-fast 成清晰错误。

    base_branch 本身解析不了时 (repo_root 非 git repo / 分支不存在 —— 例如
    单测 monkeypatch 场景) **跳过检查返回 []**, 留给 execute_task 自己报错;
    本检查只在 "base 可解析但 ref 缺失" 这个明确坏状态下出手。
    """
    if not _git_ok(repo_root, "rev-parse", "--verify", "--quiet", entry.base_branch):
        return []
    missing: list[str] = []
    for ref in (entry.spec_ref, entry.plan_ref):
        if not _git_ok(repo_root, "cat-file", "-e", f"{entry.base_branch}:{ref}"):
            missing.append(ref)
    return missing


def precheck_refs_on_base(manifest: BatchManifest, repo_root: str) -> None:
    """对 manifest 所有 task 跑 base-branch ref 可见性检查; 有缺失即抛.

    Raises BatchAdapterError(INVALID_MANIFEST): 任一 task 的 spec_ref/plan_ref
    在其 base_branch HEAD 上不可见 (即引用了未提交的文件)。
    """
    for entry in manifest.tasks:
        missing = _refs_missing_on_base(repo_root, entry)
        if missing:
            raise BatchAdapterError(
                "INVALID_MANIFEST",
                f"task {entry.task_id}: refs not committed on base_branch "
                f"{entry.base_branch!r}: {', '.join(missing)}. "
                "C2 task worktrees fork from the base branch HEAD and cannot "
                "see uncommitted files — commit your /sy-specify, /sy-plan and "
                "/sy-tasks artifacts to the base branch first.",
                task_id=entry.task_id,
                base_branch=entry.base_branch,
                missing_refs=missing,
            )


# -------------------------------------------------------------------
# Batch orchestrator
# -------------------------------------------------------------------


def run_batch(
    manifest: BatchManifest,
    *,
    repo_root: str,
    dry_run: bool = False,
    claude_cmd: list[str] | None = None,
) -> BatchOutput:
    """顺序跑 manifest.tasks; 中间 fail 立即停, 后续 skipped.

    Args:
        manifest: load_tasks_yaml 解析过的 BatchManifest.
        repo_root: 业务项目根 (绝对路径); 给每个 task 注入.
        dry_run: True 时只列 task, 不调 execute_task.
        claude_cmd: 测试时 inject mock claude script; None = 走默认 claude CLI.

    Returns:
        BatchOutput: 含 per-task 结果 + 整体 status.
    """
    results: list[BatchTaskResult] = []

    if dry_run:
        for entry in manifest.tasks:
            results.append(BatchTaskResult(task_id=entry.task_id, status="dry_run"))
        return BatchOutput(
            feature_name=manifest.feature_name,
            status="dry_run",
            tasks=results,
        )

    # 真跑前 fail-fast: spec_ref/plan_ref 必须在各自 base_branch HEAD 可见
    precheck_refs_on_base(manifest, repo_root)

    stopped_at: str | None = None
    overall_success = True

    for entry in manifest.tasks:
        if stopped_at is not None:
            results.append(BatchTaskResult(task_id=entry.task_id, status="skipped"))
            continue

        task_input = entry.to_task_input(repo_root=repo_root)
        try:
            output = execute_task(task_input, claude_cmd=claude_cmd)
        except TaskExecutorError as e:
            overall_success = False
            stopped_at = entry.task_id
            results.append(
                BatchTaskResult(
                    task_id=entry.task_id,
                    status="failed",
                    error=e.error,
                )
            )
            continue

        if output.status != "success":
            overall_success = False
            stopped_at = entry.task_id
            results.append(
                BatchTaskResult(
                    task_id=entry.task_id,
                    status="failed",
                    output=output,
                )
            )
            continue

        results.append(
            BatchTaskResult(
                task_id=entry.task_id,
                status="success",
                output=output,
            )
        )

    return BatchOutput(
        feature_name=manifest.feature_name,
        status="all_success" if overall_success else "partial_failed",
        tasks=results,
        stopped_at_task_id=stopped_at,
    )
