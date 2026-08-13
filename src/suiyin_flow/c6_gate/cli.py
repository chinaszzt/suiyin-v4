"""C6 CLI — `suiyin-flow gate run`.

Orchestrator: GateInput → load reports → ff_check → has_human_block → evaluate
rules → I8 reason precedence → (merged: ff merge to main) / (held + R1: label
+ comment) → write gate_report.json → exit code.

**Exit codes** (§7 落地形态):
  0 = merged
  1 = held
  2 = Error (MISSING_INPUT / INVALID_REPORT / STALE_REPORT / GIT_ERROR / GH_ERROR /
      PERMISSION_DENIED)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import ValidationError

from suiyin_flow.c6_gate.actions import (
    execute_r1_recovery,
    ff_merge_to_main,
)
from suiyin_flow.c6_gate.contract import (
    GateContractError,
    GateError,
    GateInput,
    GateOutput,
    RecoveryAction,
    RecoveryKind,
)
from suiyin_flow.c6_gate.ff_check import (
    has_human_block_label,
    is_ff_mergeable,
    resolve_pr_sha,
)
from suiyin_flow.c6_gate.report import (
    load_report,
    now_iso8601_utc,
    write_gate_report,
)
from suiyin_flow.c6_gate.rules import (
    all_rules_pass,
    evaluate_rules,
    select_reason,
)
from suiyin_flow.treesha import resolve_tree_sha


def _display_tree_sha(value: object) -> str:
    return value if isinstance(value, str) and value else "missing"


def _validate_report_freshness(
    *,
    verify_report: dict[str, object],
    review_report: dict[str, object],
    current_tree_sha: str | None,
) -> None:
    """Require both report tickets to match the tree currently being gated."""
    verify_tree_sha = verify_report.get("target_tree_sha")
    review_tree_sha = review_report.get("target_tree_sha")
    if not (
        isinstance(verify_tree_sha, str)
        and verify_tree_sha
        and isinstance(review_tree_sha, str)
        and review_tree_sha
        and current_tree_sha
        and verify_tree_sha == current_tree_sha
        and review_tree_sha == current_tree_sha
    ):
        displayed = {
            "verify_tree_sha": _display_tree_sha(verify_tree_sha),
            "review_tree_sha": _display_tree_sha(review_tree_sha),
            "current_tree_sha": _display_tree_sha(current_tree_sha),
        }
        raise GateContractError(
            "STALE_REPORT",
            "report tree SHA mismatch: "
            f"verify={displayed['verify_tree_sha']}, "
            f"review={displayed['review_tree_sha']}, "
            f"current={displayed['current_tree_sha']}",
            details=displayed,
        )


def execute_gate(gate_input: GateInput) -> GateOutput:
    """跑完一次 C6 gate pipeline.

    Returns GateOutput. dry_run=true 时跳过 merge / label / comment.

    Raises GateContractError — Error 路径 (MISSING_INPUT / INVALID_REPORT / etc.)
    Caller (cli.main) 捕获 → GateError 序列化 + exit 2.
    """
    repo_root = Path(gate_input.repo_root).resolve()
    if not repo_root.exists() or not repo_root.is_dir():
        raise GateContractError(
            "MISSING_INPUT",
            f"repo_root not a directory: {repo_root}",
            details={"repo_root": str(repo_root)},
        )

    # 1. Load reports
    verify_report = load_report(gate_input.verify_report_path, kind="verify")
    review_report = load_report(gate_input.review_report_path, kind="review")

    # 2. Mechanically validate both report tickets before evaluating any rules.
    pr_sha = resolve_pr_sha(pr_ref=gate_input.pr_ref, repo_root=repo_root)
    current_tree_sha: str | None = None
    if pr_sha is not None:
        try:
            current_tree_sha = resolve_tree_sha(repo_root, pr_sha)
        except ValueError:
            current_tree_sha = None
    _validate_report_freshness(
        verify_report=verify_report,
        review_report=review_report,
        current_tree_sha=current_tree_sha,
    )
    assert pr_sha is not None  # freshness validation rejects an unresolved current ref

    # 3. Probe remaining git/gh state
    ff_mergeable = is_ff_mergeable(pr_ref=gate_input.pr_ref, repo_root=repo_root)
    has_human_block = has_human_block_label(
        pr_ref=gate_input.pr_ref, repo_root=repo_root
    )

    # 4. Evaluate rules + select reason (I8 precedence)
    rules = evaluate_rules(
        verify_report=verify_report,
        review_report=review_report,
        ff_mergeable=ff_mergeable,
        has_human_block=has_human_block,
    )
    reason = select_reason(rules)

    ts = now_iso8601_utc()

    # 5a. Merged path
    if all_rules_pass(rules):
        if gate_input.dry_run:
            # AC-1b: dry_run 时不真 merge，merged_sha absent
            return GateOutput(
                gate_result="merged",
                rules=rules,
                timestamp=ts,
            )
        # 真 merge — 解 sha + ff merge + push (I5)
        merged_sha = ff_merge_to_main(pr_sha=pr_sha, repo_root=repo_root)
        return GateOutput(
            gate_result="merged",
            rules=rules,
            merged_sha=merged_sha,
            timestamp=ts,
        )

    # 5b. Held path — reason 已由 I8 选定
    assert reason is not None, "rules not all pass but no reason selected"

    if gate_input.dry_run:
        # AC-8: dry_run 跳所有副作用，recovery_action.kind 仍按 reason 填
        kind: RecoveryKind = (
            "r1_label_and_comment" if reason == "REVIEW_NOT_APPROVE" else "no_op"
        )
        return GateOutput(
            gate_result="held",
            rules=rules,
            reason=reason,
            recovery_action=RecoveryAction(kind=kind),  # 所有 bool 字段 absent
            timestamp=ts,
        )

    # 真 held + R1 (REVIEW_NOT_APPROVE only)
    if reason == "REVIEW_NOT_APPROVE":
        findings = review_report.get("findings", [])
        if not isinstance(findings, list):
            findings = []
        recovery = execute_r1_recovery(
            pr_ref=gate_input.pr_ref,
            findings=findings,
            repo_root=repo_root,
        )
    else:
        recovery = RecoveryAction(kind="no_op")

    return GateOutput(
        gate_result="held",
        rules=rules,
        reason=reason,
        recovery_action=recovery,
        timestamp=ts,
    )


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]

    parser = argparse.ArgumentParser(
        prog="suiyin-flow gate",
        description="C6 Gate Contract — automatic merge gate (4 boolean AND rules)",
    )
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    run_parser = subparsers.add_parser("run", help="evaluate gate for a PR")
    run_parser.add_argument("--pr-ref", required=True, help="PR URL / 编号 / 本地分支名")
    run_parser.add_argument("--verify-report", required=True, help="C4 verify_report.json 路径")
    run_parser.add_argument("--review-report", required=True, help="C5 review_report.json 路径")
    run_parser.add_argument("--repo-root", required=True, help="业务项目根目录（绝对路径）")
    run_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只评估，不执行 merge / label / comment 副作用",
    )

    # argv[0] = "gate" when dispatched from unified cli; skip it
    if args and args[0] == "gate":
        args = args[1:]

    parsed = parser.parse_args(args)

    try:
        gate_input = GateInput(
            pr_ref=parsed.pr_ref,
            verify_report_path=parsed.verify_report,
            review_report_path=parsed.review_report,
            repo_root=parsed.repo_root,
            dry_run=parsed.dry_run,
        )
    except ValidationError as e:
        err = GateError(
            code="MISSING_INPUT",
            message=f"input validation failed: {e}",
            retryable=False,
        )
        print(json.dumps(err.to_dict(), indent=2, ensure_ascii=False), file=sys.stderr)
        return 2

    try:
        output = execute_gate(gate_input)
    except GateContractError as e:
        err = e.to_error()
        print(json.dumps(err.to_dict(), indent=2, ensure_ascii=False), file=sys.stderr)
        return 2

    # 落盘 gate_report.json
    repo_root = Path(gate_input.repo_root).resolve()
    report_path = write_gate_report(
        output=output,
        repo_root=repo_root,
        pr_ref=gate_input.pr_ref,
    )

    # stdout: report path + verdict (跟 c5 CLI 风格一致)
    print(f"gate_report → {report_path}")
    print(f"gate_result: {output.gate_result}")
    if output.reason:
        print(f"reason: {output.reason}")

    return 0 if output.gate_result == "merged" else 1


if __name__ == "__main__":
    sys.exit(main())
