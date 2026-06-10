"""C2 v0.3.0 AC tests — AC-10..AC-14 (R2 review feedback + I8 worktree 锁).

按 c2-task-executor.md v0.3.0 §5. Fork G 命名约定 `test_AC_N_...`.
Mock 策略同 conftest.py (假 claude script + 最小 git repo).
"""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
import time
from pathlib import Path
from typing import Any

import pytest

from suiyin_flow.c2_executor.cli import execute_task
from suiyin_flow.c2_executor.prompt import load_review_findings, render_prompt
from suiyin_flow.c2_executor.schema import TaskExecutorError, TaskInput
from suiyin_flow.c2_executor.worktree import (
    acquire_worktree_lock,
    ensure_worktree,
    lock_path_for,
)

_FEEDBACK_HEADER = "上次 Review 发现的问题"


def _make_input(repo: Path, **overrides: Any) -> TaskInput:
    defaults: dict[str, Any] = dict(
        task_id="T-001",
        spec_ref="spec.md",
        plan_ref="plan.md",
        constitution_ref="constitution.md",
        context_seeds=["context.md"],
        verify_cmd="true",
        criticality="medium",
        repo_root=str(repo),
        ac_list=["AC-1"],
    )
    defaults.update(overrides)
    return TaskInput(**defaults)


def _write_review_report(path: Path, findings: list[dict[str, Any]]) -> Path:
    """造一个最小合法 C5 review_report.json (只需 findings 字段被 C2 读)."""
    path.write_text(
        json.dumps({"verdict": "block", "findings": findings}),
        encoding="utf-8",
    )
    return path


_FINDINGS_SAMPLE: list[dict[str, Any]] = [
    {
        "severity": "low",
        "category": "reusable_knowledge_not_captured",
        "location": "src/util.py:10",
        "suggested_fix": "extract helper to shared module",
    },
    {
        "severity": "high",
        "category": "spec_drift",
        "location": "src/core.py:42",
        "suggested_fix": "align return type with spec §2.2",
    },
]


def _mock_claude_dump_prompt(tmp_path: Path) -> list[str]:
    """假 claude: 把 stdin prompt 落盘到 cwd/prompt_dump.txt 再输出成功 JSON."""
    script = tmp_path / "claude_dump_prompt.py"
    script.write_text(
        textwrap.dedent(
            """\
            import json
            import pathlib
            import sys

            prompt = sys.stdin.read()
            pathlib.Path("prompt_dump.txt").write_text(prompt, encoding="utf-8")
            print(json.dumps({
                "task_id": "T-001",
                "files_changed": [],
                "verify_cmd_exit_code": 0,
                "commit_sha": "abc1234",
            }))
            """
        ),
        encoding="utf-8",
    )
    return [sys.executable, str(script)]


# =============================================================================
# AC-10: review_feedback 注入 prompt + review_feedback_applied 标记
# =============================================================================


def test_AC_10_feedback_injected_into_prompt_and_flagged(
    fixture_repo: Path, tmp_path: Path
) -> None:
    report = _write_review_report(tmp_path / "report.json", _FINDINGS_SAMPLE)
    task_input = _make_input(fixture_repo, review_feedback=str(report))

    output = execute_task(task_input, claude_cmd=_mock_claude_dump_prompt(tmp_path))

    assert output.status == "success"
    assert output.review_feedback_applied is True
    prompt = (Path(output.worktree_path) / "prompt_dump.txt").read_text(
        encoding="utf-8"
    )
    assert _FEEDBACK_HEADER in prompt
    assert "src/core.py:42" in prompt
    assert "align return type with spec §2.2" in prompt
    assert "src/util.py:10" in prompt
    # severity 降序: high finding 在 low 之前
    assert prompt.index("src/core.py:42") < prompt.index("src/util.py:10")


def test_AC_10_no_feedback_no_section_flag_false(
    fixture_repo: Path, tmp_path: Path
) -> None:
    task_input = _make_input(fixture_repo)

    output = execute_task(task_input, claude_cmd=_mock_claude_dump_prompt(tmp_path))

    assert output.review_feedback_applied is False
    prompt = (Path(output.worktree_path) / "prompt_dump.txt").read_text(
        encoding="utf-8"
    )
    assert _FEEDBACK_HEADER not in prompt


def test_AC_10_relative_feedback_path_resolved_against_repo_root(
    fixture_repo: Path,
) -> None:
    _write_review_report(fixture_repo / "report.json", _FINDINGS_SAMPLE)
    task_input = _make_input(fixture_repo, review_feedback="report.json")

    findings = load_review_findings(task_input)

    assert findings is not None and len(findings) == 2
    # render_prompt 单元层也含 section (execute_task 集成层见上)
    prompt = render_prompt(task_input, Path("/tmp/wt"), findings)
    assert _FEEDBACK_HEADER in prompt


# =============================================================================
# AC-11: review_feedback 非法 → REVIEW_FEEDBACK_INVALID, 不启动 session
# =============================================================================


def test_AC_11_feedback_file_not_found(fixture_repo: Path) -> None:
    task_input = _make_input(
        fixture_repo, review_feedback=str(fixture_repo / "nope.json")
    )
    with pytest.raises(TaskExecutorError) as exc_info:
        execute_task(task_input)
    assert exc_info.value.error.code == "REVIEW_FEEDBACK_INVALID"
    # 校验在 worktree 创建之前 → 不留现场
    assert not (fixture_repo / "worktrees" / "T-001").exists()


def test_AC_11_feedback_invalid_json(fixture_repo: Path, tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    task_input = _make_input(fixture_repo, review_feedback=str(bad))
    with pytest.raises(TaskExecutorError) as exc_info:
        execute_task(task_input)
    assert exc_info.value.error.code == "REVIEW_FEEDBACK_INVALID"


def test_AC_11_feedback_empty_findings(fixture_repo: Path, tmp_path: Path) -> None:
    report = _write_review_report(tmp_path / "empty.json", [])
    task_input = _make_input(fixture_repo, review_feedback=str(report))
    with pytest.raises(TaskExecutorError) as exc_info:
        execute_task(task_input)
    assert exc_info.value.error.code == "REVIEW_FEEDBACK_INVALID"


# =============================================================================
# AC-12: lock 持有者 pid 存活 → WORKTREE_LOCKED, 不启动 session
# =============================================================================


def test_AC_12_live_holder_pid_rejects_run(
    fixture_repo: Path, mock_claude_success: list[str]
) -> None:
    wt_path = ensure_worktree(fixture_repo, "T-001", base_branch="main")
    # 真起一个存活子进程当锁持有者 (发现 #8 场景: 另一个 C2 run 在跑)
    holder = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        shell=False,
    )
    try:
        lock = lock_path_for(wt_path)
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.write_text(
            json.dumps({"pid": holder.pid, "task_id": "T-001"}), encoding="utf-8"
        )

        task_input = _make_input(fixture_repo)
        with pytest.raises(TaskExecutorError) as exc_info:
            execute_task(task_input, claude_cmd=mock_claude_success)

        assert exc_info.value.error.code == "WORKTREE_LOCKED"
        assert exc_info.value.error.details["holder_pid"] == holder.pid
        # 没起 session → 没有 attempt log
        assert not (wt_path / ".suiyin" / "sessions").exists()
        # 锁未被动 (仍是 holder 的)
        assert json.loads(lock.read_text(encoding="utf-8"))["pid"] == holder.pid
    finally:
        holder.kill()
        holder.wait(timeout=10)


# =============================================================================
# AC-13: stale lock (pid 已死) → 确定性接管, run 正常跑完
# =============================================================================


def test_AC_13_stale_lock_taken_over(
    fixture_repo: Path, mock_claude_success: list[str]
) -> None:
    wt_path = ensure_worktree(fixture_repo, "T-001", base_branch="main")
    # 拿一个真实已死的 pid: 起个立即退出的子进程, wait 完后 pid 必死
    dead = subprocess.Popen([sys.executable, "-c", "pass"], shell=False)
    dead.wait(timeout=10)
    time.sleep(0.05)
    lock = lock_path_for(wt_path)
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(
        json.dumps({"pid": dead.pid, "task_id": "T-001"}), encoding="utf-8"
    )

    output = execute_task(_make_input(fixture_repo), claude_cmd=mock_claude_success)

    assert output.status == "success"


def test_AC_13_corrupt_lock_treated_as_stale(fixture_repo: Path) -> None:
    wt_path = ensure_worktree(fixture_repo, "T-001", base_branch="main")
    lock = lock_path_for(wt_path)
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("garbage not json", encoding="utf-8")

    acquire_worktree_lock(wt_path, "T-001")  # 不该 raise

    assert json.loads(lock.read_text(encoding="utf-8"))["task_id"] == "T-001"


# =============================================================================
# AC-14: 终态后 lock 释放 (success / RETRY_EXHAUSTED 两路径)
# =============================================================================


def test_AC_14_lock_released_after_success(
    fixture_repo: Path, mock_claude_success: list[str]
) -> None:
    output = execute_task(_make_input(fixture_repo), claude_cmd=mock_claude_success)

    assert output.status == "success"
    assert not lock_path_for(Path(output.worktree_path)).exists()


def test_AC_14_lock_released_after_retry_exhausted(
    fixture_repo: Path, mock_claude_verify_fail: list[str]
) -> None:
    task_input = _make_input(fixture_repo, max_retries=0)
    with pytest.raises(TaskExecutorError) as exc_info:
        execute_task(task_input, claude_cmd=mock_claude_verify_fail)

    assert exc_info.value.error.code == "RETRY_EXHAUSTED"
    wt_path = fixture_repo / "worktrees" / "T-001"
    assert wt_path.exists()  # worktree 保留 (AC-5 语义)
    assert not lock_path_for(wt_path).exists()  # 锁释放
