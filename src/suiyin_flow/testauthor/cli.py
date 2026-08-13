"""CLI for ``suiyin-flow testauthor run``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from suiyin_flow.c5_reviewer.contract import ReviewerError
from suiyin_flow.testauthor.runner import run_author
from suiyin_flow.testauthor.schema import TestAuthorError


def _make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="suiyin-flow", description="Independent test author"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    author_p = sub.add_parser("testauthor", help="write independent red tests")
    author_sub = author_p.add_subparsers(dest="testauthor_command", required=True)
    run_p = author_sub.add_parser("run", help="run one independent author session")
    run_p.add_argument("--tasks-yaml", required=True)
    run_p.add_argument("--task-id", required=True)
    run_p.add_argument("--repo-root", required=True)
    run_p.add_argument("--targets", required=True)
    run_p.add_argument("--test-paths", nargs="+", required=True)
    run_p.add_argument("--inputs-manifest", default=None)
    run_p.add_argument("--base-ref", default=None)
    run_p.add_argument("--red-cmd", default=None)
    run_p.add_argument("--timeout", type=float, default=1800.0)
    run_p.add_argument("--report", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _make_parser()
    args = parser.parse_args(argv)
    if args.command != "testauthor" or args.testauthor_command != "run":
        parser.print_help()
        return 2
    try:
        report = run_author(
            repo_root=Path(args.repo_root).resolve(),
            tasks_yaml_path=Path(args.tasks_yaml).resolve(),
            task_id=args.task_id,
            targets_path=Path(args.targets).resolve(),
            test_paths=args.test_paths,
            inputs_manifest_path=(
                Path(args.inputs_manifest).resolve() if args.inputs_manifest else None
            ),
            base_ref=args.base_ref,
            red_cmd=args.red_cmd,
            timeout_seconds=args.timeout,
        )
    except TestAuthorError as exc:
        print(f"ERROR {exc.error.code}: {exc.error.message}", file=sys.stderr)
        print(exc.error.model_dump_json(indent=2), file=sys.stderr)
        return 2
    except ReviewerError as exc:
        print(f"ERROR {exc.error.code}: {exc.error.message}", file=sys.stderr)
        print(exc.error.model_dump_json(indent=2), file=sys.stderr)
        return 2
    if args.report:
        report_path = Path(args.report).resolve()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    print(report.model_dump_json(indent=2))
    return 0 if report.verdict == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
