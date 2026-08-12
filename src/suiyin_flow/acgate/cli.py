"""AC 冻结闸 CLI — `suiyin-flow acgate {run,freeze}`.

exit code:
  0 = pass (run) / freeze 成功
  1 = block (含 UNKNOWN, fail-closed)
  2 = run 级错误 (MANIFEST_NOT_FOUND / INVALID_MANIFEST / GIT_ERROR / ...)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from suiyin_flow.acgate.gate import freeze_manifest, run_gate
from suiyin_flow.acgate.schema import AcGateError


def _make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="suiyin-flow", description="AC 冻结闸 (gen4-plan P0-2)"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    ac_p = sub.add_parser("acgate", help="AC/守卫测试冻结闸")
    ac_sub = ac_p.add_subparsers(dest="acgate_command", required=True)

    run_p = ac_sub.add_parser("run", help="对 base...head diff 跑冻结判定")
    run_p.add_argument("--manifest", required=True, help="ac-manifest.yaml 路径")
    run_p.add_argument("--repo-root", required=True)
    run_p.add_argument("--base", required=True, help="基准 ref (feature 分支)")
    run_p.add_argument("--head", required=True, help="待评 ref (task 分支/HEAD)")

    freeze_p = ac_sub.add_parser(
        "freeze", help="按 ref 刷新 manifest 的 hash 基准 (冻结动作走 PR 受审)"
    )
    freeze_p.add_argument("--manifest", required=True)
    freeze_p.add_argument("--repo-root", required=True)
    freeze_p.add_argument("--ref", required=True, help="冻结基准 (commit/branch)")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _make_parser()
    args = parser.parse_args(argv)
    if args.command != "acgate":
        parser.print_help()
        return 2

    try:
        if args.acgate_command == "run":
            report = run_gate(
                repo_root=Path(args.repo_root).resolve(),
                manifest_path=Path(args.manifest),
                base_ref=args.base,
                head_ref=args.head,
            )
            print(report.model_dump_json(indent=2))
            return 0 if report.verdict == "pass" else 1
        if args.acgate_command == "freeze":
            manifest = freeze_manifest(
                repo_root=Path(args.repo_root).resolve(),
                manifest_path=Path(args.manifest),
                ref=args.ref,
            )
            print(
                f"acgate: froze {len(manifest.entries)} entries at {args.ref}",
                file=sys.stderr,
            )
            return 0
    except AcGateError as e:
        print(f"ERROR {e.code}: {e.message}", file=sys.stderr)
        return 2
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
