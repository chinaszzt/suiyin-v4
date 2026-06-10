"""C7 Phase Coordinator AC test fixtures.

Mock 策略:
- fixture_repo: 最小 git repo (main + spec/plan/constitution 已 commit)
- fake execute_task: monkeypatch statemachine.execute_task —
  真建 worktree (复用 C2 ensure_worktree, 让整合子流程跑在真 git 状态上),
  按 behaviors 表写文件 + commit / 返回 failed / 抛 Error.
  不真起 Claude session (NC-1 / 零 token).
"""

from __future__ import annotations

import shlex
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml

from suiyin_flow.c2_executor.schema import (
    SessionLog,
    TaskExecutorError,
    TaskInput,
    TaskOutput,
)
from suiyin_flow.c2_executor.worktree import ensure_worktree

VERIFY_OK = f"{shlex.quote(sys.executable)} -c pass"
VERIFY_FAIL = f"{shlex.quote(sys.executable)} -c \"raise SystemExit(1)\""


def git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(cwd), *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        shell=False,
    )
    return result.stdout.strip()


@pytest.fixture
def fixture_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.email", "test@suiyin.local")
    git(repo, "config", "user.name", "test")
    git(repo, "config", "commit.gpgsign", "false")
    (repo / "spec.md").write_text(
        "# Spec\n\n## 5. Acceptance Criteria\n\n- **AC-1**: x\n", encoding="utf-8"
    )
    (repo / "plan.md").write_text("# Plan\n", encoding="utf-8")
    (repo / "constitution.md").write_text("# Constitution\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "initial")
    return repo


def write_manifest(
    repo: Path,
    tasks: list[dict[str, Any]],
    execution_plan: list[dict[str, Any]] | None = None,
    *,
    commit: bool = False,
) -> Path:
    """写 tasks.yaml 到 repo 外侧 tmp (manifest 不必在 repo 内)."""
    data: dict[str, Any] = {
        "schema_version": "v0.1.0",
        "feature_name": "c7-test",
        "tasks": tasks,
    }
    if execution_plan is not None:
        data["execution_plan"] = execution_plan
    path = repo.parent / "tasks.yaml"
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    if commit:
        pass
    return path


def task_entry(
    task_id: str,
    *,
    depends_on: list[str] | None = None,
    verify_cmd: str = VERIFY_OK,
    base_branch: str = "main",
) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "spec_ref": "spec.md",
        "plan_ref": "plan.md",
        "constitution_ref": "constitution.md",
        "context_seeds": [],
        "verify_cmd": verify_cmd,
        "criticality": "medium",
        "depends_on": depends_on or [],
        "base_branch": base_branch,
    }


# Behavior spec per task_id:
#   ("success", {filename: content})  → 写文件 + commit, 返回 success
#   ("success_nocommit", {})          → 不写不 commit (零新增 commit edge)
#   ("fail", {})                      → 返回 status=failed
#   ("error", {})                     → 抛 TaskExecutorError(SESSION_CRASHED)
Behavior = tuple[str, dict[str, str]]


def make_fake_execute(
    repo: Path,
    behaviors: dict[str, Behavior],
    record: dict[str, Any],
) -> Callable[..., TaskOutput]:
    """fake C2 execute_task. record 收集: calls 计数 / fork 时 worktree 可见文件."""

    def fake_execute(
        task_input: TaskInput, *, claude_cmd: list[str] | None = None
    ) -> TaskOutput:
        tid = task_input.task_id
        record.setdefault("calls", []).append(tid)
        record.setdefault("open_pr_seen", {})[tid] = task_input.open_pr
        wt = ensure_worktree(
            Path(task_input.repo_root), tid, task_input.base_branch
        )
        record.setdefault("visible_at_dispatch", {})[tid] = sorted(
            p.name for p in wt.iterdir() if p.suffix == ".txt"
        )
        kind, files = behaviors.get(tid, ("success", {f"{tid}.txt": tid}))
        if kind == "error":
            raise TaskExecutorError(
                "SESSION_CRASHED", "mock crash", task_id=tid
            )
        if kind == "fail":
            return _output(tid, wt, status="failed")
        if kind == "success" and not files:
            files = {f"{tid}.txt": tid}
        for name, content in files.items():
            (wt / name).write_text(content, encoding="utf-8")
        if kind != "success_nocommit" and files:
            git(wt, "add", ".")
            git(wt, "commit", "-m", f"{tid}: mock impl")
        return _output(tid, wt, status="success")

    return fake_execute


def _output(tid: str, wt: Path, *, status: str) -> TaskOutput:
    return TaskOutput(
        task_id=tid,
        status=status,  # type: ignore[arg-type]
        attempts=1,
        worktree_path=str(wt),
        pr_url_or_branch=f"task/{tid}" if status == "success" else None,
        pr_created=False,
        verify_report_path=None,
        session_logs=[
            SessionLog(
                attempt=1,
                log_path=str(wt / ".suiyin" / "sessions" / "attempt-1.log"),
                duration_seconds=0.1,
                verify_pass=status == "success",
            )
        ],
        diff_stats=None,
    )
