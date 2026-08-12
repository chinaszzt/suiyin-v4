"""Mutation 探针 CLI — `suiyin-flow mutation run`.

exit code:
  0 = pass (全部 mutant killed)
  1 = fail (survived / apply_failed / error / 零适用, fail-closed)
  2 = run 级错误
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from suiyin_flow.mutation.runner import run_probe
from suiyin_flow.mutation.schema import MutationError


def _make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="suiyin-flow", description="Mutation 探针 (gen4-plan P0-3)"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    mut_p = sub.add_parser("mutation", help="冻结测试证伪力验证")
    mut_sub = mut_p.add_subparsers(dest="mutation_command", required=True)

    run_p = mut_sub.add_parser("run", help="按 catalog 逐 mutant 注入 + 杀手测试")
    run_p.add_argument("--catalog", required=True, help="mutants.yaml 路径")
    run_p.add_argument("--repo-root", required=True)
    run_p.add_argument("--ref", required=True, help="被测基准 (commit/branch)")
    run_p.add_argument(
        "--env",
        action="append",
        default=[],
        metavar="KEY=VAL",
        help="可重复; 注入杀手测试的环境变量 (lane 隔离用, 例 MONGO_URI=...)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _make_parser()
    args = parser.parse_args(argv)
    if args.command != "mutation" or args.mutation_command != "run":
        parser.print_help()
        return 2

    env_extra: dict[str, str] = {}
    for item in args.env:
        if "=" not in item:
            print(f"ERROR: --env expects KEY=VAL, got {item!r}", file=sys.stderr)
            return 2
        k, v = item.split("=", 1)
        env_extra[k] = v

    try:
        report = run_probe(
            repo_root=Path(args.repo_root).resolve(),
            catalog_path=Path(args.catalog),
            ref=args.ref,
            env_extra=env_extra,
        )
    except MutationError as e:
        print(f"ERROR {e.code}: {e.message}", file=sys.stderr)
        return 2

    print(report.model_dump_json(indent=2))
    return 0 if report.verdict == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
