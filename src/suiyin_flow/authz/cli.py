"""Authorization manifest CLI — ``suiyin-flow authz check``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from suiyin_flow.authz.gate import run_check
from suiyin_flow.authz.schema import AuthzError


def _make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="suiyin-flow", description="Authorization manifest static gate"
    )
    sub = parser.add_subparsers(dest="top_command", required=True)
    authz_p = sub.add_parser("authz", help="authorization manifest gate")
    authz_sub = authz_p.add_subparsers(dest="authz_command", required=True)

    check_p = authz_sub.add_parser("check", help="check a task diff and command")
    check_p.add_argument("--manifest", required=True)
    check_p.add_argument("--tasks-yaml", required=True)
    check_p.add_argument("--diff", required=True)
    check_p.add_argument("--task-id", required=True)
    check_p.add_argument("--command")
    check_p.add_argument("--report", help="optional AuthzReport JSON output path")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _make_parser()
    args = parser.parse_args(argv)
    if args.top_command != "authz" or args.authz_command != "check":
        parser.print_help()
        return 2

    try:
        report = run_check(
            manifest_path=Path(args.manifest),
            tasks_yaml_path=Path(args.tasks_yaml),
            diff_path=Path(args.diff),
            task_id=args.task_id,
            command=args.command,
        )
    except AuthzError as exc:
        single_line_message = " ".join(exc.message.splitlines())
        print(f"ERROR {exc.code}: {single_line_message}", file=sys.stderr)
        return 2

    if args.report is not None:
        Path(args.report).write_text(
            f"{report.model_dump_json(indent=2)}\n",
            encoding="utf-8",
        )
    for finding in report.findings:
        print(f"{finding.code} {finding.dimension}: {finding.detail}")
    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
