"""C2 CLI — `suiyin-flow task run`.

Orchestrator: TaskInput → validate → worktree → render prompt → session(s) →
verify → retry → commit / push / open PR → TaskOutput.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from suiyin_flow.c2_executor.prompt import (
    render_prompt,
    validate_context_seeds,
    validate_refs,
)
from suiyin_flow.c2_executor.retry import should_retry
from suiyin_flow.c2_executor.schema import (
    DiffStats,
    SessionLog,
    TaskErrorCode,
    TaskExecutorError,
    TaskInput,
    TaskOutput,
)
from suiyin_flow.c2_executor.session import run_session
from suiyin_flow.c2_executor.worktree import (
    ensure_worktree,
    worktree_branch_name,
)

# -------------------------------------------------------------------
# Orchestrator
# -------------------------------------------------------------------


def execute_task(
    task_input: TaskInput,
    *,
    claude_cmd: list[str] | None = None,
) -> TaskOutput:
    """跑完一个 task 的完整 pipeline.

    Args:
        task_input: 校验过的 TaskInput.
        claude_cmd: injectable claude 命令; 测试时可 mock script.

    Returns:
        TaskOutput (status=success or failed).

    Raises:
        TaskExecutorError — HIGH_CRITICALITY_REJECT / SPEC_NOT_FOUND /
        CONTEXT_SEEDS_MISSING / WORKTREE_CONFLICT / RETRY_EXHAUSTED.
    """
    # I5: high criticality 拒接 (调度责任在 C3)
    if task_input.criticality == "high":
        raise TaskExecutorError(
            "HIGH_CRITICALITY_REJECT",
            "criticality=high should be routed to C3 Arbiter, not C2",
            task_id=task_input.task_id,
            criticality=task_input.criticality,
        )

    # 输入校验 (path 存在性)
    validate_refs(task_input)
    validate_context_seeds(task_input)

    repo_root = Path(task_input.repo_root).resolve()

    # 创建/复用 worktree (raises WORKTREE_CONFLICT if mismatch)
    wt_path = ensure_worktree(
        repo_root=repo_root,
        task_id=task_input.task_id,
        base_branch=task_input.base_branch,
    )

    prompt_text = render_prompt(task_input, wt_path)

    # 重试循环
    session_logs: list[SessionLog] = []
    last_error: TaskErrorCode | None = None
    timeout_retries = 0
    attempt = 0

    while True:
        attempt += 1
        session_result = run_session(
            task_id=task_input.task_id,
            prompt=prompt_text,
            worktree_path=wt_path,
            attempt=attempt,
            timeout_seconds=float(task_input.session_timeout_seconds),
            claude_cmd=claude_cmd,
        )

        # 解析 verify_pass: 看 session final_output_json 里 verify_cmd_exit_code
        verify_pass = (
            session_result.final_output_json is not None
            and session_result.final_output_json.get("verify_cmd_exit_code") == 0
        )

        session_logs.append(
            SessionLog(
                attempt=attempt,
                log_path=str(session_result.log_path),
                duration_seconds=session_result.duration_seconds,
                verify_pass=verify_pass,
            )
        )

        # 决定下一步
        if session_result.timed_out:
            last_error = "TIMEOUT"
            timeout_retries += 1
        elif session_result.exit_code != 0:
            last_error = "SESSION_CRASHED"
        elif not verify_pass:
            last_error = "VERIFY_FAILED"
        else:
            last_error = None  # success

        if last_error is None:
            break  # success

        if not should_retry(
            last_error,
            attempts_so_far=attempt,
            max_retries=task_input.max_retries,
            timeout_retries_so_far=timeout_retries,
        ):
            break  # exhausted, fall through to RETRY_EXHAUSTED

        # else: 再 loop 一次

    # 找 verify_report_path (P0: 用 worktree/.suiyin/verify/latest.json 软规约)
    verify_report_path: str | None = None
    report_candidate = wt_path / ".suiyin" / "verify" / "latest.json"
    if report_candidate.exists():
        verify_report_path = str(report_candidate)

    if last_error is not None:
        # 跑完循环还有 error → RETRY_EXHAUSTED 终态
        raise TaskExecutorError(
            "RETRY_EXHAUSTED",
            f"Retries exhausted after {attempt} attempts (last error: {last_error})",
            task_id=task_input.task_id,
            last_error=last_error,
            attempts=attempt,
            worktree_path=str(wt_path),
            verify_report_path=verify_report_path,
        )

    # success — commit + push + open PR (best effort)
    return _finalize_success(
        task_input=task_input,
        wt_path=wt_path,
        attempts=attempt,
        session_logs=session_logs,
        verify_report_path=verify_report_path,
    )


def _finalize_success(
    *,
    task_input: TaskInput,
    wt_path: Path,
    attempts: int,
    session_logs: list[SessionLog],
    verify_report_path: str | None,
) -> TaskOutput:
    """成功后 commit + push + (best effort) 开 PR. 返回 TaskOutput."""
    branch = worktree_branch_name(task_input.task_id)
    diff_stats = _compute_diff_stats(wt_path, task_input.base_branch)
    pr_url_or_branch = _open_pr_or_branch(
        wt_path=wt_path,
        task_id=task_input.task_id,
        ac_list=task_input.ac_list,
        spec_ref=task_input.spec_ref,
        attempts=attempts,
        branch=branch,
    )
    pr_created = pr_url_or_branch is not None and pr_url_or_branch.startswith("http")

    return TaskOutput(
        task_id=task_input.task_id,
        status="success",
        attempts=attempts,
        worktree_path=str(wt_path),
        pr_url_or_branch=pr_url_or_branch or branch,
        pr_created=pr_created,
        verify_report_path=verify_report_path,
        session_logs=session_logs,
        diff_stats=diff_stats,
    )


def _git_shortstat(wt_path: Path, base_ref: str) -> str | None:
    """跑 `git diff --shortstat <base_ref>...HEAD`, 返回 stdout 或 None (失败)."""
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(wt_path),
                "diff",
                "--shortstat",
                f"{base_ref}...HEAD",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            shell=False,
            check=False,
        )
    except (subprocess.SubprocessError, FileNotFoundError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def _compute_diff_stats(wt_path: Path, base_branch: str) -> DiffStats | None:
    """git diff --shortstat <base> 解析 files/insertions/deletions.

    v0.1.3 Bug 4 fix (P0 spike 2026-05-24 dogfood): 旧版只试 `origin/<base>...HEAD`,
    若 base_branch 未 push 到 remote (例 dogfood 用 claude/dogfood-adr-0002 本地分支)
    则 silent None → TaskOutput.diff_stats=null 即使 success.
    修后 fallback: 先试 `origin/<base>`, 失败再试本地 `<base>`.
    """
    # 优先 1: origin/<base> (业务项目 push remote 常见情形)
    text = _git_shortstat(wt_path, f"origin/{base_branch}")
    # 优先 2: 本地 base (无 remote 时兜底)
    if text is None:
        text = _git_shortstat(wt_path, base_branch)
    if text is None:
        return None

    # output e.g. " 3 files changed, 42 insertions(+), 7 deletions(-)"
    import re

    files = ins = dels = 0
    m = re.search(r"(\d+) files? changed", text)
    if m:
        files = int(m.group(1))
    m = re.search(r"(\d+) insertions?\(\+\)", text)
    if m:
        ins = int(m.group(1))
    m = re.search(r"(\d+) deletions?\(-\)", text)
    if m:
        dels = int(m.group(1))
    return DiffStats(files_changed=files, insertions=ins, deletions=dels)


def _open_pr_or_branch(
    *,
    wt_path: Path,
    task_id: str,
    ac_list: list[str],
    spec_ref: str,
    attempts: int,
    branch: str,
) -> str | None:
    """Best-effort: push branch + open PR with gh; 失败降级返回本地 branch.

    NC-1 友好: 无 gh / 无 remote → 返回 branch 名 (caller 看 pr_created=false).
    """
    # push (允许失败 — 无 remote 时本地分支也算 OK)
    push_result = subprocess.run(
        ["git", "-C", str(wt_path), "push", "-u", "origin", branch],
        capture_output=True,
        text=True,
        encoding="utf-8",
        shell=False,
        check=False,
    )
    if push_result.returncode != 0:
        return None  # caller 看到 pr_created=false → pr_url_or_branch=branch 兜底

    # try gh pr create
    gh = shutil.which("gh")
    if not gh:
        return None

    body = (
        f"## Task {task_id}\n\n"
        f"- **spec_ref**: `{spec_ref}`\n"
        f"- **ac_list**: {', '.join(ac_list) if ac_list else '(无)'}\n"
        f"- **attempts**: {attempts}\n\n"
        f"_Auto-opened by suiyin-flow C2 Task Executor._\n"
    )
    title = f"task({task_id}): auto PR"
    pr_result = subprocess.run(
        [
            gh,
            "pr",
            "create",
            "--head",
            branch,
            "--title",
            title,
            "--body",
            body,
        ],
        cwd=wt_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        shell=False,
        check=False,
    )
    if pr_result.returncode != 0:
        return None  # PR creation 失败 → 降级 branch
    return pr_result.stdout.strip() or None


# -------------------------------------------------------------------
# argparse entry
# -------------------------------------------------------------------


def _make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="suiyin-flow", description="碎银 v4 SDD 工具链 CLI"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # task subcommand
    task_p = sub.add_parser("task", help="C2 Task Executor")
    task_sub = task_p.add_subparsers(dest="task_command", required=True)

    run_p = task_sub.add_parser("run", help="跑一个 task")
    run_p.add_argument("--task-id", required=True)
    run_p.add_argument("--spec", dest="spec_ref", required=True)
    run_p.add_argument("--plan", dest="plan_ref", required=True)
    run_p.add_argument(
        "--constitution",
        dest="constitution_ref",
        default="docs/sdd/constitution.md",
    )
    run_p.add_argument(
        "--context-seed",
        dest="context_seeds",
        action="append",
        default=[],
        help="可重复; 注入给 AI 的必读文件 (相对 repo_root)",
    )
    run_p.add_argument("--verify-cmd", required=True)
    run_p.add_argument(
        "--criticality",
        choices=["low", "medium", "high"],
        default="medium",
    )
    run_p.add_argument("--repo-root", required=True)
    run_p.add_argument(
        "--ac",
        dest="ac_list",
        action="append",
        default=[],
        help="可重复; AC-N 编号",
    )
    run_p.add_argument("--max-retries", type=int, default=3)
    run_p.add_argument("--timeout", dest="session_timeout_seconds", type=int, default=7200)
    run_p.add_argument("--base-branch", default="main")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _make_parser()
    args = parser.parse_args(argv)

    if args.command != "task" or args.task_command != "run":
        parser.print_help()
        return 2

    try:
        task_input = TaskInput(
            task_id=args.task_id,
            spec_ref=args.spec_ref,
            plan_ref=args.plan_ref,
            constitution_ref=args.constitution_ref,
            context_seeds=args.context_seeds,
            verify_cmd=args.verify_cmd,
            criticality=args.criticality,
            repo_root=str(Path(args.repo_root).resolve()),
            ac_list=args.ac_list,
            max_retries=args.max_retries,
            session_timeout_seconds=args.session_timeout_seconds,
            base_branch=args.base_branch,
        )
        output = execute_task(task_input)
        print(output.model_dump_json(indent=2))
        return 0 if output.status == "success" else 1
    except TaskExecutorError as e:
        print(
            f"ERROR {e.error.code} ({e.error.task_id}): {e.error.message}",
            file=sys.stderr,
        )
        # 详细 error 也 dump 到 stdout 让 caller 解析
        print(e.error.model_dump_json(indent=2))
        return 2


if __name__ == "__main__":
    sys.exit(main())
