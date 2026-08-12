"""C5 CLI — `suiyin-flow review run`.

Orchestrator: ReviewInput → validate refs / repo / pr_ref → pull diff →
render prompt → claude session → parse final JSON → build ReviewReport →
落盘 review_report.json (+ Block Recovery R1 if verdict=block) → 返回 process exit code.
"""

from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

from pydantic import ValidationError

from suiyin_flow.c5_reviewer.contract import (
    Arbitration,
    Finding,
    ReviewerError,
    ReviewInput,
    Verdict,
)
from suiyin_flow.c5_reviewer.diff import fetch_pr_diff
from suiyin_flow.c5_reviewer.findings import derive_verdict
from suiyin_flow.c5_reviewer.prompt import render_prompt, validate_refs
from suiyin_flow.c5_reviewer.report import (
    apply_block_recovery_r1,
    build_report,
    validate_repo_root,
    write_report,
)
from suiyin_flow.c5_reviewer.session import run_session
from suiyin_flow.identity import review_key


def execute_review(
    review_input: ReviewInput,
    *,
    claude_cmd: list[str] | None = None,
) -> tuple[Verdict, Path]:
    """跑完一次 C5 review pipeline.

    Returns:
        (verdict, review_report_path)

    Raises:
        ReviewerError — 各种 input/runtime 错误
    """
    repo_root = Path(review_input.repo_root).resolve()
    validate_repo_root(repo_root)
    validate_refs(review_input)

    # Review dir (per spec §3.2 + NC-4 隔离)
    # P0-1: reviews/<review_key>/<session_id> — 按 canonical key 可定位
    # (旧 reviews/<uuid> 与 task 身份完全脱钩); session_id 保留为 run 维度
    session_id = str(uuid.uuid4())
    review_dir = (
        repo_root
        / ".suiyin"
        / "reviews"
        / review_key(review_input.feature_id, review_input.task_id)
        / session_id
    )

    # 1. Pull PR diff
    pr_diff_path = review_dir / "pr_diff.patch"
    fetch_pr_diff(
        pr_ref=review_input.pr_ref,
        repo_root=repo_root,
        output_path=pr_diff_path,
    )

    # 2. Render prompt
    prompt_text = render_prompt(review_input, str(pr_diff_path))

    # 3. Run session
    session_result = run_session(
        task_id=review_input.task_id,
        prompt=prompt_text,
        review_dir=review_dir,
        session_id=session_id,
        timeout_seconds=float(review_input.session_timeout_seconds),
        claude_cmd=claude_cmd,
    )

    if session_result.timed_out:
        raise ReviewerError(
            "TIMEOUT",
            f"review session timed out after {review_input.session_timeout_seconds}s",
            task_id=review_input.task_id,
            session_id=session_id,
            log_path=str(session_result.log_path),
        )

    if session_result.exit_code != 0:
        raise ReviewerError(
            "SESSION_CRASHED",
            f"claude session exit_code={session_result.exit_code}",
            task_id=review_input.task_id,
            session_id=session_id,
            log_path=str(session_result.log_path),
        )

    # 4. Parse final JSON → build findings + verdict
    if session_result.final_review_json is None:
        # Session 跑完但没出 final JSON — 视为 SESSION_CRASHED
        raise ReviewerError(
            "SESSION_CRASHED",
            "claude session finished but no final review JSON found in output",
            task_id=review_input.task_id,
            session_id=session_id,
            log_path=str(session_result.log_path),
        )

    findings_raw = session_result.final_review_json.get("findings", [])
    findings = [Finding(**f) for f in findings_raw]
    # Verdict 优先 AI 给的, 但用 derive_verdict 兜底 (确保符合 I3-I5)
    ai_verdict = session_result.final_review_json.get("verdict", "")
    derived = derive_verdict(findings)
    verdict: Verdict = derived  # I3-I5 enforced, AI 不可降级
    # (AI 给的 verdict 跟 derived 不一致时取 derived; future Q: log mismatch warning)
    _ = ai_verdict  # 暂留作 audit trail (未来 log)

    # Arbitration (high criticality, P1.2 spike 阶段 stub)
    arbitration: Arbitration | None = None
    if review_input.criticality == "high":
        arbitration = Arbitration(mode="single", reviewer_count=1)
        # TODO: P1.2 spike 后实施 N=2 (Q5)

    # 5. Build + write report
    report = build_report(
        review_input=review_input,
        verdict=verdict,
        findings=findings,
        session_id=session_id,
        arbitration=arbitration,
    )
    report_path = write_report(report, review_dir)

    # 6. Block Recovery R1
    if verdict == "block":
        apply_block_recovery_r1(
            pr_ref=review_input.pr_ref,
            findings=findings,
            repo_root=repo_root,
        )

    return verdict, report_path


def _make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="suiyin-flow", description="C5 AI Reviewer (subcommand)"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    review_p = sub.add_parser("review", help="C5 AI Reviewer")
    review_sub = review_p.add_subparsers(dest="review_command", required=True)

    run_p = review_sub.add_parser("run", help="跑一次 review")
    run_p.add_argument("--pr-ref", required=True, help="PR URL / number / 本地分支名")
    run_p.add_argument("--spec", dest="spec_ref", required=True)
    run_p.add_argument("--plan", dest="plan_ref", required=True)
    run_p.add_argument(
        "--constitution", dest="constitution_ref", default=".specify/memory/constitution.md"
    )
    run_p.add_argument("--verify-report", dest="verify_report_path", default=None)
    run_p.add_argument("--task-id", required=True, help="所有 PR 必走 task (v0.1.1)")
    run_p.add_argument(
        "--feature-id",
        default=None,
        help="canonical key 上半 (P0-1, 可选); 落盘键 <feature>-<task_id>",
    )
    run_p.add_argument(
        "--criticality", choices=["low", "medium", "high"], default="medium"
    )
    run_p.add_argument("--repo-root", required=True)
    run_p.add_argument(
        "--timeout", dest="session_timeout_seconds", type=int, default=1800
    )
    run_p.add_argument("--max-retries", type=int, default=2)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _make_parser()
    args = parser.parse_args(argv)

    if args.command != "review" or args.review_command != "run":
        parser.print_help()
        return 2

    try:
        review_input = ReviewInput(
            pr_ref=args.pr_ref,
            spec_ref=args.spec_ref,
            plan_ref=args.plan_ref,
            constitution_ref=args.constitution_ref,
            verify_report_path=args.verify_report_path,
            task_id=args.task_id,
            feature_id=args.feature_id,
            criticality=args.criticality,
            repo_root=str(Path(args.repo_root).resolve()),
            session_timeout_seconds=args.session_timeout_seconds,
            max_retries=args.max_retries,
        )
    except ValidationError as e:
        # task_id pattern 不合法 → INVALID_TASK_ID
        print(f"ERROR INVALID_TASK_ID: {e}", file=sys.stderr)
        return 2

    try:
        verdict, report_path = execute_review(review_input)
        print(f"review_report → {report_path}")
        print(f"verdict: {verdict}")
        return 0 if verdict == "approve" else 1
    except ReviewerError as e:
        print(
            f"ERROR {e.error.code}: {e.error.message}",
            file=sys.stderr,
        )
        print(e.error.model_dump_json(indent=2))
        return 2


if __name__ == "__main__":
    sys.exit(main())
