"""C7 CLI — `suiyin-flow phase run`.

exit code (spec I4, harness 边界):
  0 = all_merged (或 dry_run)
  1 = stopped (出现 parked, fail-stop 于 phase 边界)
  2 = Error (run 级)
caller (sy-* harness / dogfood orchestrator) 对非 0 必须 stop + surface to human.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from suiyin_flow.c7_coordinator.schema import CoordinatorAbort
from suiyin_flow.c7_coordinator.statemachine import (
    CoordinatorConfig,
    run_coordinator,
)


def _make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="suiyin-flow", description="碎银 v4 SDD 工具链 CLI"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    phase_p = sub.add_parser("phase", help="C7 Phase Coordinator")
    phase_sub = phase_p.add_subparsers(dest="phase_command", required=True)

    run_p = phase_sub.add_parser(
        "run", help="按 execution_plan 逐 phase 调度 + 逐 task ff-merge 回 base_branch"
    )
    run_p.add_argument(
        "--tasks",
        dest="tasks_yaml",
        required=True,
        help="tasks.yaml 路径 (batch manifest v0.1.0 + 可选 execution_plan)",
    )
    run_p.add_argument("--repo-root", required=True, help="业务项目根 (绝对路径)")
    run_p.add_argument(
        "--dry-run",
        action="store_true",
        help="解析 + 校验 + 输出 phase 计划; 不取锁 / 不建 worktree / 不 merge",
    )
    run_p.add_argument(
        "--no-resume",
        action="store_true",
        help="忽略 latest phase-state, 全新开跑 (旧 versioned state 保留为 audit)",
    )
    run_p.add_argument(
        "--retry-parked",
        default=None,
        help="逗号分隔 task_id 列表或 'all'; resume 时显式重试 parked task",
    )
    run_p.add_argument(
        "--max-parallel",
        type=int,
        default=1,
        help=(
            "phase 内并发 dispatch 上限 (Q7-1). 默认 1 = 确定性串行; >1 = 并发起 "
            "C2 session (整合仍串行 ff), 提速但 dispatch 完成序非确定 (谁先 merge/rebase "
            "随之变, 结局正确不变). 按机器核数 + claude API rate limit 调"
        ),
    )
    run_p.add_argument("--max-requeue", type=int, default=3)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _make_parser()
    args = parser.parse_args(argv)

    if args.command != "phase" or args.phase_command != "run":
        parser.print_help()
        return 2

    retry_parked: list[str] = []
    if args.retry_parked:
        retry_parked = [s.strip() for s in args.retry_parked.split(",") if s.strip()]

    if args.max_parallel > 1:
        print(
            f"phase: note: --max-parallel={args.max_parallel} → 并发 dispatch "
            "(整合仍串行 ff); dispatch 完成序非确定 (C7 spec Q7-1)",
            file=sys.stderr,
        )

    cfg = CoordinatorConfig(
        tasks_yaml=Path(args.tasks_yaml),
        repo_root=Path(args.repo_root),
        dry_run=args.dry_run,
        resume=not args.no_resume,
        retry_parked=retry_parked,
        max_parallel=args.max_parallel,
        max_requeue=args.max_requeue,
    )

    try:
        output = run_coordinator(cfg)
    except CoordinatorAbort as e:
        print(
            f"ERROR {e.error.code}: {e.error.message}",
            file=sys.stderr,
        )
        print(e.error.model_dump_json(indent=2))
        return 2

    print(output.model_dump_json(indent=2))
    if output.status in ("all_merged", "dry_run"):
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
