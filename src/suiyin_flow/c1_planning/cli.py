"""C1 CLI — `suiyin-flow plan run`.

Orchestrator: tasks.yaml → 环检测 → load+校验 → 分层+冲突拆分 →
(可选语义 pass) → I1 自检 → marker 写回 → PlanOutput.
"""

from __future__ import annotations

import argparse
import sys
from itertools import combinations
from pathlib import Path

from suiyin_flow.c1_planning.planner import (
    compute_phases,
    detect_cycle,
    raw_dep_graph,
    self_check,
    to_entries,
)
from suiyin_flow.c1_planning.schema import (
    PlanningError,
    PlanOutput,
    SemanticPassResult,
)
from suiyin_flow.c1_planning.semantic import run_semantic_pass
from suiyin_flow.c1_planning.writer import write_plan
from suiyin_flow.c2_executor.batch import BatchAdapterError, load_tasks_yaml


def run_plan(
    tasks_yaml: Path,
    repo_root: Path,
    *,
    dry_run: bool = False,
    semantic_pass: bool = False,
    output_path: Path | None = None,
    claude_cmd: list[str] | None = None,
) -> PlanOutput:
    """跑 C1 规划全流程.

    Raises:
        PlanningError — CYCLE_DETECTED / INVALID_MANIFEST / PLAN_SELF_CHECK_FAILED / WRITE_FAILED
        BatchAdapterError — MANIFEST_NOT_FOUND / INVALID_MANIFEST (透传 loader)
    """
    # 1) 环检测 (raw 图, 抢在 load_tasks_yaml 的顺序断言前 —— 否则环被误判 INVALID_MANIFEST)
    graph = raw_dep_graph(tasks_yaml)
    if graph is not None:
        cycle = detect_cycle(graph)
        if cycle is not None:
            raise PlanningError(
                "CYCLE_DETECTED",
                f"depends_on cycle: {' → '.join(cycle)}",
                cycle=cycle,
            )

    # 2) load + schema/顺序校验 (透传 MANIFEST_NOT_FOUND / INVALID_MANIFEST)
    manifest = load_tasks_yaml(tasks_yaml)

    # 3) base_branch 一致性 (C7 规则 3; C1 提前自查, 不一致无法逐 phase merge)
    bases = {t.base_branch for t in manifest.tasks}
    if len(bases) > 1:
        raise PlanningError(
            "INVALID_MANIFEST",
            f"all tasks must share one base_branch (逐 phase merge 目标唯一), "
            f"got {sorted(bases)}",
            base_branches=sorted(bases),
        )

    # 4) 静态分层 + 冲突拆分
    static_phase, _ = compute_phases(manifest)

    # 5) 可选语义 pass (默认关; fallback-safe)
    sem_result: SemanticPassResult | None = None
    forced: frozenset[frozenset[str]] = frozenset()
    if semantic_pass:
        candidates = _same_phase_pairs(static_phase)
        forced, sem_result = run_semantic_pass(
            manifest, repo_root, candidates, claude_cmd=claude_cmd
        )

    # 6) 最终分层 (静态 + 语义强制冲突一起算; splits 含 semantic_conflict reason)
    final_phase, splits = compute_phases(manifest, forced_conflicts=forced)
    entries = to_entries(final_phase)

    # 7) I1 自检 (C7 _validate_plan 当 oracle); 失败不落盘
    self_check(manifest, entries)

    # 8) 写回 (dry_run 不写)
    written_to: str | None = None
    if not dry_run:
        target = output_path or tasks_yaml
        write_plan(target, entries)
        written_to = str(target.resolve())

    return PlanOutput(
        status="dry_run" if dry_run else "written",
        phases_count=len(entries),
        tasks_count=len(manifest.tasks),
        execution_plan=[e.model_dump() for e in entries],
        conflict_splits=splits,
        semantic_pass=sem_result,
        written_to=written_to,
    )


def _same_phase_pairs(phase_map: dict[str, int]) -> list[tuple[str, str]]:
    """同 phase 的 task 对 (语义 pass 候选; 确定性: task_id 排序)."""
    by_phase: dict[int, list[str]] = {}
    for tid, p in phase_map.items():
        by_phase.setdefault(p, []).append(tid)
    pairs: list[tuple[str, str]] = []
    for p in sorted(by_phase):
        for a, b in combinations(sorted(by_phase[p]), 2):
            pairs.append((a, b))
    return pairs


# -------------------------------------------------------------------
# argparse entry
# -------------------------------------------------------------------


def _make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="suiyin-flow", description="碎银 v4 SDD CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    plan_p = sub.add_parser("plan", help="C1 Planning Engine")
    plan_sub = plan_p.add_subparsers(dest="plan_command", required=True)

    run_p = plan_sub.add_parser("run", help="生成 execution_plan 写回 tasks.yaml")
    run_p.add_argument("--tasks-yaml", dest="tasks_yaml", required=True)
    run_p.add_argument("--repo-root", required=True)
    run_p.add_argument(
        "--dry-run",
        action="store_true",
        help="只输出 plan, 不写回 tasks.yaml",
    )
    run_p.add_argument(
        "--semantic-pass",
        action="store_true",
        help="开可选 AI 语义冲突分析 (默认关; 只收紧不放宽; 失败 fallback 静态结果)",
    )
    run_p.add_argument(
        "--output",
        dest="output_path",
        default=None,
        help="写到别处而非原地 (默认原地写回)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _make_parser()
    args = parser.parse_args(argv)

    if args.command != "plan" or args.plan_command != "run":
        parser.print_help()
        return 2

    try:
        output = run_plan(
            tasks_yaml=Path(args.tasks_yaml),
            repo_root=Path(args.repo_root).resolve(),
            dry_run=args.dry_run,
            semantic_pass=args.semantic_pass,
            output_path=Path(args.output_path) if args.output_path else None,
        )
    except (PlanningError, BatchAdapterError) as e:
        print(e.error.model_dump_json(indent=2), file=sys.stderr)
        return 2

    print(output.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
