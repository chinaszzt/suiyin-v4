"""C1 写回 — marker 块原位替换 (I5 manifest 最小侵入).

只新增/替换文件尾部 marker 块, marker 之前的内容 (含 sy-tasks 顶部注释、
tasks[] 全文) 一字节不碰。先写 .tmp 再 os.replace (WRITE_FAILED 不半写)。
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from suiyin_flow.c1_planning.planner import MARKER
from suiyin_flow.c1_planning.schema import PlanningError
from suiyin_flow.c7_coordinator.plan import ExecutionPlanEntry


def render_block(entries: list[ExecutionPlanEntry]) -> str:
    """渲染 marker + execution_plan yaml (确定性: sort_keys=False 保 phase/parallel 序)."""
    body = yaml.safe_dump(
        {"execution_plan": [e.model_dump() for e in entries]},
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
    )
    return f"{MARKER}\n{body}"


def write_plan(tasks_yaml: Path, entries: list[ExecutionPlanEntry]) -> None:
    """marker 块写回 tasks.yaml (幂等: 已有 marker → 原位替换, AC-8).

    Raises:
        PlanningError(WRITE_FAILED): 读/写失败.
    """
    try:
        original = tasks_yaml.read_text(encoding="utf-8")
    except OSError as e:
        raise PlanningError(
            "WRITE_FAILED", f"could not read tasks.yaml for rewrite: {e}",
            path=str(tasks_yaml),
        ) from e

    idx = original.find(MARKER)
    prefix = original[:idx] if idx != -1 else original
    if prefix and not prefix.endswith("\n"):
        prefix += "\n"

    new_content = prefix + render_block(entries)

    # 原子写: 同目录 .tmp → os.replace (跨平台 atomic rename)
    tmp = tasks_yaml.with_name(tasks_yaml.name + ".c1tmp")
    try:
        tmp.write_text(new_content, encoding="utf-8")
        os.replace(tmp, tasks_yaml)
    except OSError as e:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise PlanningError(
            "WRITE_FAILED", f"could not write tasks.yaml: {e}",
            path=str(tasks_yaml),
        ) from e
