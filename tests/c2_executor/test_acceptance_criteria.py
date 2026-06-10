"""C2 §5 Acceptance Criteria tests.

按 c2-task-executor.md v0.1.1 §5 9 个 AC. Fork G 命名约定 `test_AC_N_...`.
Mock 策略见 conftest.py.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from suiyin_flow.c2_executor.cli import _open_pr_or_branch, execute_task
from suiyin_flow.c2_executor.prompt import validate_context_seeds, validate_refs
from suiyin_flow.c2_executor.schema import TaskExecutorError, TaskInput
from suiyin_flow.c2_executor.worktree import worktree_branch_name, worktree_path_for


@dataclass
class _FakeRun:
    """Minimal subprocess.CompletedProcess stand-in for monkeypatch."""

    returncode: int = 0
    stdout: str = ""
    stderr: str = ""


def _make_input(
    repo: Path,
    *,
    task_id: str = "T-001",
    criticality: str = "medium",
    verify_cmd: str = "true",
    max_retries: int = 3,
    session_timeout_seconds: int = 7200,
    spec_ref: str = "spec.md",
    context_seeds: list[str] | None = None,
) -> TaskInput:
    return TaskInput(
        task_id=task_id,
        spec_ref=spec_ref,
        plan_ref="plan.md",
        constitution_ref="constitution.md",
        context_seeds=context_seeds if context_seeds is not None else ["context.md"],
        verify_cmd=verify_cmd,
        criticality=criticality,  # type: ignore[arg-type]
        repo_root=str(repo),
        ac_list=["AC-1"],
        max_retries=max_retries,
        session_timeout_seconds=session_timeout_seconds,
    )


# =============================================================================
# AC-1: 给定 valid input → status=success + pr_url_or_branch 非空
# =============================================================================


def test_AC_1_success_with_valid_input(
    fixture_repo: Path, mock_claude_success: list[str]
) -> None:
    """AC-1: 完整 happy path → status=success + branch fallback (无 remote 也 OK)."""
    task_input = _make_input(fixture_repo)
    output = execute_task(task_input, claude_cmd=mock_claude_success)
    assert output.status == "success"
    assert output.task_id == "T-001"
    assert output.attempts == 1  # 一次就过
    # 无 remote → pr_created=False, pr_url_or_branch fallback 到 branch 名
    assert output.pr_url_or_branch is not None
    assert output.pr_url_or_branch.startswith(("task/", "http"))
    assert output.worktree_path.endswith("worktrees/T-001")


# =============================================================================
# AC-2: criticality=high → HIGH_CRITICALITY_REJECT, 不启动 worktree
# =============================================================================


def test_AC_2_high_criticality_rejected(
    fixture_repo: Path, mock_claude_success: list[str]
) -> None:
    """AC-2 (I5 invariant): criticality=high 立即 raise, worktree 没创建."""
    task_input = _make_input(fixture_repo, criticality="high")
    with pytest.raises(TaskExecutorError) as exc_info:
        execute_task(task_input, claude_cmd=mock_claude_success)
    assert exc_info.value.error.code == "HIGH_CRITICALITY_REJECT"
    # worktree 不应被创建
    wt = worktree_path_for(fixture_repo, "T-001")
    assert not wt.exists()


# =============================================================================
# AC-3: 不存在的 spec_ref → SPEC_NOT_FOUND, 不启动 worktree
# =============================================================================


def test_AC_3_spec_not_found(fixture_repo: Path) -> None:
    """AC-3: spec_ref 文件不存在 → SPEC_NOT_FOUND, 不启动 worktree."""
    task_input = _make_input(fixture_repo, spec_ref="missing.md")
    with pytest.raises(TaskExecutorError) as exc_info:
        validate_refs(task_input)
    assert exc_info.value.error.code == "SPEC_NOT_FOUND"
    wt = worktree_path_for(fixture_repo, "T-001")
    assert not wt.exists()


def test_AC_3_context_seeds_missing(fixture_repo: Path) -> None:
    """AC-3 兄弟: context_seed 文件不存在 → CONTEXT_SEEDS_MISSING."""
    task_input = _make_input(fixture_repo, context_seeds=["nonexistent.md"])
    with pytest.raises(TaskExecutorError) as exc_info:
        validate_context_seeds(task_input)
    assert exc_info.value.error.code == "CONTEXT_SEEDS_MISSING"


def test_AC_3b_refs_validated_against_base_branch_not_checkout(
    fixture_repo: Path,
) -> None:
    """v0.2.1 发现 #9 回归: ref 只在 feature 分支上 (repo 当前 checkout 在 main)
    → 校验必须过; worktree 从 base_branch 分叉, checkout 分支无关."""
    import subprocess

    def git(*args: str) -> None:
        subprocess.run(
            ["git", "-C", str(fixture_repo), *args],
            check=True, capture_output=True, text=True, shell=False,
        )

    # feature 分支上提交 main 没有的 seed, 然后切回 main
    git("checkout", "-b", "feature/x")
    (fixture_repo / "feature-only.md").write_text("seed\n", encoding="utf-8")
    git("add", "feature-only.md")
    git("commit", "-m", "feature-only seed")
    git("checkout", "main")
    assert not (fixture_repo / "feature-only.md").exists()

    task_input = _make_input(
        fixture_repo, context_seeds=["feature-only.md"]
    ).model_copy(update={"base_branch": "feature/x"})
    validate_context_seeds(task_input)  # 不应 raise
    validate_refs(task_input)  # spec/plan/constitution 在 main 也在 feature/x


def test_AC_3c_uncommitted_seed_rejected(fixture_repo: Path) -> None:
    """v0.2.1 发现 #9 反向回归: seed 在盘上但未提交到 base_branch
    → session 的 worktree 看不到 → 必须拒 (旧版按 fs 校验会假通过)."""
    (fixture_repo / "uncommitted.md").write_text("seed\n", encoding="utf-8")
    task_input = _make_input(fixture_repo, context_seeds=["uncommitted.md"])
    with pytest.raises(TaskExecutorError) as exc_info:
        validate_context_seeds(task_input)
    assert exc_info.value.error.code == "CONTEXT_SEEDS_MISSING"


# =============================================================================
# AC-4: AI session 超 timeout → TIMEOUT + 进程 kill -9
# =============================================================================


def test_AC_4_timeout_killed(
    fixture_repo: Path, mock_claude_sleep: list[str]
) -> None:
    """AC-4 (I7 invariant): 超 session_timeout_seconds 强制 kill, 终 RETRY_EXHAUSTED.

    TIMEOUT 单独限 1 次重试, max_retries=3 总额度足 → 跑 2 attempts 都 TIMEOUT 才放弃.
    """
    # 极小 timeout = 2 秒, mock claude 会 sleep 120s
    task_input = _make_input(
        fixture_repo, session_timeout_seconds=2, max_retries=3
    )
    with pytest.raises(TaskExecutorError) as exc_info:
        execute_task(task_input, claude_cmd=mock_claude_sleep)
    assert exc_info.value.error.code == "RETRY_EXHAUSTED"
    # last_error 应该是 TIMEOUT
    assert exc_info.value.error.details.get("last_error") == "TIMEOUT"
    # log 文件应该存在 (落盘了)
    wt = worktree_path_for(fixture_repo, "T-001")
    assert (wt / ".suiyin" / "sessions" / "attempt-1.log").exists()


# =============================================================================
# AC-5: verify_cmd 连续 max_retries+1 次非 0 → RETRY_EXHAUSTED + worktree 保留
# =============================================================================


def test_AC_5_retry_exhausted_keeps_worktree(
    fixture_repo: Path, mock_claude_verify_fail: list[str]
) -> None:
    """AC-5: max_retries=2 → 总共跑 3 attempts 都 verify_failed → RETRY_EXHAUSTED, worktree 保留."""
    task_input = _make_input(fixture_repo, max_retries=2)
    with pytest.raises(TaskExecutorError) as exc_info:
        execute_task(task_input, claude_cmd=mock_claude_verify_fail)
    err = exc_info.value.error
    assert err.code == "RETRY_EXHAUSTED"
    assert err.details.get("attempts") == 3  # max_retries+1
    assert err.details.get("last_error") == "VERIFY_FAILED"
    # worktree 保留 (spec §3.3 RETRY_EXHAUSTED: worktree 保留等人介入)
    wt = worktree_path_for(fixture_repo, "T-001")
    assert wt.exists()


# =============================================================================
# AC-6: 同 task_id 复跑, worktree 存在异源分支 → WORKTREE_CONFLICT, 不覆盖
# =============================================================================


def test_AC_6_worktree_conflict_blocks(fixture_repo: Path) -> None:
    """AC-6: 预先用 wrong branch 创建 worktree → execute_task raise WORKTREE_CONFLICT."""
    # 先用 'wrong-branch' 创建同名 worktree
    wt_path = worktree_path_for(fixture_repo, "T-001")
    subprocess.run(
        [
            "git",
            "-C",
            str(fixture_repo),
            "worktree",
            "add",
            "-b",
            "wrong-branch",
            str(wt_path),
            "main",
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        shell=False,
    )

    task_input = _make_input(fixture_repo)
    with pytest.raises(TaskExecutorError) as exc_info:
        execute_task(task_input)
    err = exc_info.value.error
    assert err.code == "WORKTREE_CONFLICT"
    assert err.details.get("existing_branch") == "wrong-branch"
    assert err.details.get("expected_branch") == "task/T-001"


# =============================================================================
# AC-7: worktree_path 严格 worktrees/<task_id>, 100% 满足
# =============================================================================


def test_AC_7_worktree_path_naming(tmp_path: Path) -> None:
    """AC-7 (I1 invariant): worktree_path_for 严格返回 <repo>/worktrees/<task_id>."""
    for task_id in ("T-001", "T-042", "T-12345"):
        wt = worktree_path_for(tmp_path, task_id)
        assert wt.name == task_id
        assert wt.parent.name == "worktrees"
        assert wt.parent.parent == tmp_path.resolve()

    # branch 命名也对齐: task/<task_id>
    assert worktree_branch_name("T-042") == "task/T-042"


# =============================================================================
# AC-8: 成功时 PR 描述含 task_id + ac_list + attempts 三个字段 (I6 invariant)
# =============================================================================


def test_AC_8_pr_description_includes_required_fields(
    fixture_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-8: _open_pr_or_branch 调 gh pr create 时 body 含 task_id / ac_list / attempts."""
    captured_args: list[list[str]] = []

    real_run = subprocess.run

    def fake_run(args: Any, *posargs: Any, **kwargs: Any) -> Any:
        captured_args.append(list(args))
        # git push 假装成功 (让 _open_pr_or_branch 走到 gh 调用)
        if args[0:1] == ["git"] or (len(args) > 0 and "git" in str(args[0])):
            if "push" in args:
                return _FakeRun(returncode=0)
            return real_run(args, *posargs, **kwargs)
        if args[0].endswith("gh") or "gh" in str(args[0]):
            return _FakeRun(
                returncode=0,
                stdout="https://github.com/fake/repo/pull/1",
            )
        return real_run(args, *posargs, **kwargs)

    # monkeypatch shutil.which('gh') 让 _open_pr_or_branch 找到 gh
    monkeypatch.setattr("suiyin_flow.c2_executor.cli.shutil.which", lambda name: "/fake/gh")
    monkeypatch.setattr("suiyin_flow.c2_executor.cli.subprocess.run", fake_run)

    # 创建 worktree (因为 _open_pr_or_branch 用 wt_path 作 cwd)
    wt_path = worktree_path_for(fixture_repo, "T-001")
    subprocess.run(
        [
            "git",
            "-C",
            str(fixture_repo),
            "worktree",
            "add",
            "-b",
            "task/T-001",
            str(wt_path),
            "main",
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        shell=False,
    )

    result = _open_pr_or_branch(
        wt_path=wt_path,
        task_id="T-042",
        ac_list=["AC-1", "AC-2"],
        spec_ref="docs/spec.md",
        attempts=3,
        branch="task/T-042",
        base_branch="main",
    )
    assert result == "https://github.com/fake/repo/pull/1"

    # 找 gh 调用, 看 --body 参数
    gh_calls = [args for args in captured_args if "gh" in str(args[0])]
    assert len(gh_calls) == 1, f"expected 1 gh call, got {gh_calls}"
    gh_args = gh_calls[0]
    body_idx = gh_args.index("--body")
    body_text = gh_args[body_idx + 1]
    assert "T-042" in body_text
    assert "AC-1" in body_text
    assert "AC-2" in body_text
    assert "3" in body_text  # attempts


# =============================================================================
# AC-9: 每个 attempt 在 .suiyin/sessions/attempt-{N}.log 留下完整 stdout
# =============================================================================


def test_AC_9_session_logs_persisted(
    fixture_repo: Path, mock_claude_success: list[str]
) -> None:
    """AC-9: 成功跑完一个 attempt → attempt-1.log 存在且含 session stdout."""
    task_input = _make_input(fixture_repo)
    output = execute_task(task_input, claude_cmd=mock_claude_success)

    wt = worktree_path_for(fixture_repo, "T-001")
    log_path = wt / ".suiyin" / "sessions" / "attempt-1.log"
    assert log_path.exists()
    log_content = log_path.read_text(encoding="utf-8")
    # mock_claude_success 输出 3 行 JSON
    assert "starting" in log_content
    assert "T-001" in log_content
    assert "verify_cmd_exit_code" in log_content

    # session_logs 也应该有一项指向这个 log
    assert len(output.session_logs) == 1
    assert output.session_logs[0].log_path == str(log_path)
    assert output.session_logs[0].attempt == 1
