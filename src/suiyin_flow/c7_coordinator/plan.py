"""C7 plan — execution_plan 校验 + degenerate plan 推导.

spec §2.1:
- execution_plan 校验三规则 (覆盖恰好 / 依赖只指向更早 phase / base_branch 一致)
- 缺省 → degenerate plan: 每 task 自成一 phase, 按 manifest 顺序
  (依赖链照跑 — 每 task 后 merge, 下一 task 看得见; C1 提供并行加速, 不是正确性)
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, ValidationError

from suiyin_flow.c2_executor.batch import BatchManifest, load_tasks_yaml
from suiyin_flow.c7_coordinator.schema import (
    CoordinatorAbort,
    PhaseRecord,
    TaskRecord,
)


class ExecutionPlanEntry(BaseModel):
    phase: int = Field(ge=1)
    parallel: list[str] = Field(min_length=1)


def manifest_sha256(tasks_yaml: Path) -> str:
    return hashlib.sha256(tasks_yaml.read_bytes()).hexdigest()


def _load_execution_plan_raw(tasks_yaml: Path) -> list[dict[str, object]] | None:
    """二次读 yaml 取 execution_plan (BatchManifest pydantic 会静默丢 extra key)."""
    raw = yaml.safe_load(tasks_yaml.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return None
    plan = raw.get("execution_plan")
    if plan is None:
        return None
    if not isinstance(plan, list):
        raise CoordinatorAbort(
            "INVALID_PLAN",
            f"execution_plan must be a list, got {type(plan).__name__}",
        )
    return plan


def _validate_plan(
    manifest: BatchManifest, entries: list[ExecutionPlanEntry]
) -> list[PhaseRecord]:
    """spec §2.1 校验规则 1/2/3; 全过则返回 PhaseRecord 列表."""
    # phase 编号: 从 1 起连续递增
    numbers = [e.phase for e in sorted(entries, key=lambda e: e.phase)]
    if numbers != list(range(1, len(numbers) + 1)):
        raise CoordinatorAbort(
            "INVALID_PLAN",
            f"execution_plan phase numbers must be 1..N contiguous, got {numbers}",
        )
    entries = sorted(entries, key=lambda e: e.phase)

    # 规则 1: 恰好覆盖 tasks[] 集合 (无缺 / 无多 / 无重复)
    manifest_ids = [t.task_id for t in manifest.tasks]
    plan_ids: list[str] = [tid for e in entries for tid in e.parallel]
    if len(plan_ids) != len(set(plan_ids)):
        dupes = sorted({t for t in plan_ids if plan_ids.count(t) > 1})
        raise CoordinatorAbort(
            "INVALID_PLAN", f"execution_plan has duplicate task_ids: {dupes}"
        )
    missing = sorted(set(manifest_ids) - set(plan_ids))
    extra = sorted(set(plan_ids) - set(manifest_ids))
    if missing or extra:
        raise CoordinatorAbort(
            "INVALID_PLAN",
            "execution_plan must cover exactly the manifest task set; "
            f"missing={missing} extra={extra}",
        )

    # 规则 2: depends_on 只允许指向更早 phase
    phase_of = {tid: e.phase for e in entries for tid in e.parallel}
    for task in manifest.tasks:
        for dep in task.depends_on:
            if phase_of[dep] >= phase_of[task.task_id]:
                raise CoordinatorAbort(
                    "INVALID_PLAN",
                    f"task {task.task_id!r} (phase {phase_of[task.task_id]}) "
                    f"depends_on {dep!r} (phase {phase_of[dep]}); dependencies "
                    "must point to an earlier phase",
                )

    return [
        PhaseRecord(
            phase=e.phase,
            tasks=[TaskRecord(task_id=tid) for tid in e.parallel],
        )
        for e in entries
    ]


def _degenerate_plan(manifest: BatchManifest) -> list[PhaseRecord]:
    """每 task 自成一 phase, manifest 顺序 (依赖序由 batch _check_dependency_order 保证)."""
    return [
        PhaseRecord(phase=i, tasks=[TaskRecord(task_id=t.task_id)])
        for i, t in enumerate(manifest.tasks, start=1)
    ]


def load_manifest_and_plan(
    tasks_yaml: Path,
) -> tuple[BatchManifest, list[PhaseRecord], str]:
    """读 manifest + 推导/校验 phase 计划.

    Returns:
        (manifest, phases, base_branch)

    Raises:
        BatchAdapterError: MANIFEST_NOT_FOUND / INVALID_MANIFEST (caller 透传转 CoordinatorAbort)
        CoordinatorAbort: INVALID_PLAN
    """
    manifest = load_tasks_yaml(tasks_yaml)

    # 规则 3: base_branch 必须一致 (逐 phase merge 目标只能有一个)
    bases = {t.base_branch for t in manifest.tasks}
    if len(bases) > 1:
        raise CoordinatorAbort(
            "INVALID_PLAN",
            f"all tasks must share one base_branch, got {sorted(bases)}",
        )
    base_branch = bases.pop()

    raw_plan = _load_execution_plan_raw(tasks_yaml)
    if raw_plan is None:
        return manifest, _degenerate_plan(manifest), base_branch

    try:
        entries = [ExecutionPlanEntry.model_validate(item) for item in raw_plan]
    except ValidationError as e:
        raise CoordinatorAbort(
            "INVALID_PLAN", f"execution_plan schema validation failed: {e}"
        ) from e
    return manifest, _validate_plan(manifest, entries), base_branch
