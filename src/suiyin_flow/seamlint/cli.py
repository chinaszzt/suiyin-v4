"""CLI for `suiyin-flow seamlint run`."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from suiyin_flow.seamlint.lint import run_lint
from suiyin_flow.seamlint.schema import SeamLintError


def _make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="suiyin-flow", description="Seam manifest static lint"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    seam_p = sub.add_parser("seamlint", help="检查跨 task 接缝清单")
    seam_sub = seam_p.add_subparsers(dest="seamlint_command", required=True)

    run_p = seam_sub.add_parser("run", help="校验 manifest、task 身份与依赖闭包")
    run_p.add_argument("--manifest", required=True, help="seam-manifest.yaml 路径")
    run_p.add_argument("--tasks-yaml", required=True, help="tasks.yaml 路径")
    run_p.add_argument("--report", help="可选 JSON report 输出路径")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _make_parser()
    args = parser.parse_args(argv)
    if args.command != "seamlint" or args.seamlint_command != "run":
        parser.print_help()
        return 2

    try:
        report = run_lint(Path(args.manifest), Path(args.tasks_yaml))
    except SeamLintError as exc:
        print(f"ERROR {exc.code}: {exc.message}", file=sys.stderr)
        return 2

    if args.report:
        Path(args.report).write_text(
            report.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )

    for finding in report.findings:
        location = finding.seam_id if finding.seam_id is not None else "manifest"
        print(f"{finding.code} {location}: {finding.message}")

    pending = report.counts["SEAM_TEST_PENDING"]
    verdict = "PASS" if report.passed else "FAIL"
    print(f"seamlint: {verdict}; {pending} pending test hook(s)")
    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
