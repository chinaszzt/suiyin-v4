"""Feature 收口 harness CLI — `suiyin-flow close {run,block,unblock,status}`.

exit code (run):
  0 = merged
  1 = held / blocked (surface to human, 工件保留)
  2 = run 级错误
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from suiyin_flow.close_harness.blocks import clear_block, load_block, set_block
from suiyin_flow.close_harness.harness import CloseConfig, run_close
from suiyin_flow.close_harness.schema import CloseError


def _make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="suiyin-flow", description="Feature 收口 harness (gen4-plan P0-4)"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    close_p = sub.add_parser("close", help="feature→target 收口 (C4→C5→C6 确定性串接)")
    close_sub = close_p.add_subparsers(dest="close_command", required=True)

    run_p = close_sub.add_parser("run", help="跑一次收口")
    run_p.add_argument("--tasks", dest="tasks_yaml", required=True, help="tasks.yaml 路径")
    run_p.add_argument("--repo-root", required=True)
    run_p.add_argument("--verify-cmd", required=True, help="feature 级全量验证命令 (shell)")
    run_p.add_argument("--target-branch", default="main")
    run_p.add_argument(
        "--env", action="append", default=[], metavar="KEY=VAL",
        help="可重复; 注入 verify/mutation 的环境 (lane 隔离)",
    )
    run_p.add_argument(
        "--gate-dry-run", action="store_true",
        help="C6 只评估不 merge (预览)",
    )
    run_p.add_argument("--timeout", dest="session_timeout_seconds", type=int, default=1800)

    for name, help_text in (
        ("block", "本地 block 该 feature 的收口 (GitHub label 只是可选 adapter)"),
        ("unblock", "解除本地 block"),
        ("status", "查看 block 状态"),
    ):
        p = close_sub.add_parser(name, help=help_text)
        p.add_argument("--feature", dest="feature_id", required=True)
        p.add_argument("--repo-root", required=True)
        if name == "block":
            p.add_argument("--reason", required=True)
        if name == "unblock":
            p.add_argument("--reason", default="")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _make_parser()
    args = parser.parse_args(argv)
    if args.command != "close":
        parser.print_help()
        return 2
    repo_root = Path(args.repo_root).resolve()

    try:
        if args.close_command == "run":
            env: dict[str, str] = {}
            for item in args.env:
                if "=" not in item:
                    print(f"ERROR: --env expects KEY=VAL, got {item!r}", file=sys.stderr)
                    return 2
                k, v = item.split("=", 1)
                env[k] = v
            report = run_close(CloseConfig(
                tasks_yaml=Path(args.tasks_yaml),
                repo_root=repo_root,
                verify_cmd=args.verify_cmd,
                target_branch=args.target_branch,
                probe_env=env,
                gate_dry_run=args.gate_dry_run,
                session_timeout_seconds=args.session_timeout_seconds,
            ))
            print(report.model_dump_json(indent=2))
            return 0 if report.verdict == "merged" else 1
        if args.close_command == "block":
            state = set_block(repo_root, args.feature_id, reason=args.reason)
            print(state.model_dump_json(indent=2))
            return 0
        if args.close_command == "unblock":
            state = clear_block(repo_root, args.feature_id, reason=args.reason)
            print(state.model_dump_json(indent=2))
            return 0
        if args.close_command == "status":
            state = load_block(repo_root, args.feature_id)
            print(state.model_dump_json(indent=2))
            return 0
    except CloseError as e:
        print(f"ERROR {e.code}: {e.message}", file=sys.stderr)
        return 2
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
