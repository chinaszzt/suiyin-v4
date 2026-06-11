"""C1 静态规划核心 — 环检测 / 依赖分层 / 冲突拆分 / I1 自检.

确定性算法 (I2): 同输入同输出, 无随机/时间戳/dict 序依赖.
冲突检测偏保守 (I3): 宁可 false positive (过度串行), 不承诺 false negative=0
—— 漏检由 C7 整合子流程兜底.
"""

from __future__ import annotations

from fnmatch import fnmatch
from pathlib import Path

import yaml

from suiyin_flow.c1_planning.schema import ConflictReason, ConflictSplit, PlanningError
from suiyin_flow.c2_executor.batch import BatchManifest
from suiyin_flow.c7_coordinator.plan import ExecutionPlanEntry, _validate_plan
from suiyin_flow.c7_coordinator.schema import CoordinatorAbort

# I5 写回 marker (writer.py 也引用)
MARKER = "# --- execution_plan (C1 generated, do not hand-edit) ---"


# -------------------------------------------------------------------
# 环检测 (在 raw 图上跑, 早于 load_tasks_yaml —— batch 的顺序断言会把环
# 误判成 BATCH_ORDER_VIOLATION/INVALID_MANIFEST, 抢在 CYCLE_DETECTED 前)
# -------------------------------------------------------------------


def raw_dep_graph(tasks_yaml: Path) -> dict[str, list[str]] | None:
    """从 yaml 抽 {task_id: depends_on}; 解析失败返回 None (让 load_tasks_yaml 报正经错)."""
    try:
        raw = yaml.safe_load(tasks_yaml.read_text(encoding="utf-8"))
    except (yaml.YAMLError, OSError):
        return None
    if not isinstance(raw, dict):
        return None
    tasks = raw.get("tasks")
    if not isinstance(tasks, list):
        return None
    graph: dict[str, list[str]] = {}
    for t in tasks:
        if isinstance(t, dict) and isinstance(t.get("task_id"), str):
            deps = t.get("depends_on") or []
            graph[t["task_id"]] = [d for d in deps if isinstance(d, str)]
    return graph


def detect_cycle(graph: dict[str, list[str]]) -> list[str] | None:
    """DFS 三色环检测; 返回一条环路径 (含闭合首尾) 或 None.

    路径形如 ['T-001', 'T-003', 'T-001'] (确定性: 按 graph 插入序遍历).
    """
    WHITE, GREY, BLACK = 0, 1, 2
    color = dict.fromkeys(graph, WHITE)
    stack: list[str] = []

    def visit(node: str) -> list[str] | None:
        color[node] = GREY
        stack.append(node)
        for dep in graph.get(node, []):
            if dep not in color:
                continue  # 指向不存在的 task_id —— 留给 load_tasks_yaml/_validate_plan 报
            if color[dep] == GREY:
                # 找到环: 从 stack 里 dep 首次出现处截到当前
                idx = stack.index(dep)
                return [*stack[idx:], dep]
            if color[dep] == WHITE:
                found = visit(dep)
                if found is not None:
                    return found
        color[node] = BLACK
        stack.pop()
        return None

    for node in graph:  # dict 插入序 = 确定性
        if color[node] == WHITE:
            found = visit(node)
            if found is not None:
                return found
    return None


# -------------------------------------------------------------------
# 路径足迹重叠 (modifies / context_seeds)
# -------------------------------------------------------------------


def _norm(p: str) -> str:
    p = p.strip().replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p.rstrip("/") if p not in ("/", "") else p


def _static_prefix(p: str) -> str:
    """glob 的静态前缀 (到第一个通配符前的目录边界); 无通配符则原样返回."""
    cut = len(p)
    for i, ch in enumerate(p):
        if ch in "*?[":
            cut = i
            break
    if cut == len(p):
        return p  # 无通配符
    head = p[:cut]
    return head[: head.rfind("/")] if "/" in head else ""


def _dir_prefix(prefix: str, path: str) -> bool:
    """prefix 是否为 path 的目录前缀 (含相等)."""
    if not prefix:
        return False
    return path == prefix or path.startswith(prefix + "/")


def _paths_overlap(a: str, b: str) -> bool:
    """两个路径/glob 是否可能命中同一文件 (保守: 偏 True = FP, 安全)."""
    a, b = _norm(a), _norm(b)
    if a == b:
        return True
    if fnmatch(b, a) or fnmatch(a, b):
        return True
    cands_a = [a, _static_prefix(a)]
    cands_b = [b, _static_prefix(b)]
    for x in cands_a:
        for y in cands_b:
            if _dir_prefix(x, y) or _dir_prefix(y, x):
                return True
    return False


def _footprint_overlap(
    paths_a: list[str], paths_b: list[str]
) -> str | None:
    """返回首个重叠对的 evidence 'pa ∩ pb' 或 None (列表序遍历 = 确定性)."""
    for pa in paths_a:
        for pb in paths_b:
            if _paths_overlap(pa, pb):
                return f"{pa} ∩ {pb}"
    return None


def _compare(a: object, b: object) -> tuple[str, ConflictReason] | None:
    """两 task 足迹冲突? both 有 modifies → 比 modifies; 否则 fallback 比 context_seeds (AC-4)."""
    a_mod, b_mod = a.modifies, b.modifies  # type: ignore[attr-defined]
    if a_mod and b_mod:
        ev = _footprint_overlap(a_mod, b_mod)
        if ev:
            return ev, "modifies_overlap"
        return None
    ev = _footprint_overlap(
        a.context_seeds, b.context_seeds  # type: ignore[attr-defined]
    )
    if ev:
        return ev, "context_seeds_overlap"
    return None


# -------------------------------------------------------------------
# 分层 + 冲突拆分 (fixpoint)
# -------------------------------------------------------------------


def compute_phases(
    manifest: BatchManifest,
    forced_conflicts: frozenset[frozenset[str]] = frozenset(),
) -> tuple[dict[str, int], list[ConflictSplit]]:
    """依赖分层 + 同 phase 足迹冲突拆分, 迭代到 fixpoint.

    Args:
        manifest: 已校验的 BatchManifest.
        forced_conflicts: 语义 pass 追加的强制冲突对 (frozenset({a,b}) 集合, I4 只收紧).

    Returns:
        (phase_map, conflict_splits) —— phase 从 1 起、最终连续 (caller renumber);
        splits 按处理序 (phase 升序 + manifest 序) append, 确定性.
    """
    ids = [t.task_id for t in manifest.tasks]
    entry_of = {t.task_id: t for t in manifest.tasks}
    deps = {t.task_id: list(t.depends_on) for t in manifest.tasks}
    phase = dict.fromkeys(ids, 1)
    splits: list[ConflictSplit] = []
    seen_pairs: set[frozenset[str]] = set()

    changed = True
    while changed:
        changed = False

        # 1) 依赖地板: phase(t) >= 1 + max(phase(dep))
        for tid in ids:
            floor = 1 + max((phase[d] for d in deps[tid] if d in phase), default=0)
            if phase[tid] < floor:
                phase[tid] = floor
                changed = True

        # 2) 同 phase 冲突 → manifest 序更后者推到 phase+1 (I6)
        by_phase: dict[int, list[str]] = {}
        for tid in ids:  # manifest 序
            by_phase.setdefault(phase[tid], []).append(tid)

        for p in sorted(by_phase):
            committed: list[str] = []
            for tid in by_phase[p]:
                hit: tuple[str, str, ConflictReason] | None = None
                for c in committed:
                    cmp = _compare(entry_of[tid], entry_of[c])
                    if cmp is not None:
                        hit = (c, cmp[0], cmp[1])
                        break
                    if frozenset({tid, c}) in forced_conflicts:
                        hit = (c, "semantic pass: 判定会动同一资源", "semantic_conflict")
                        break
                if hit is not None:
                    phase[tid] = p + 1
                    changed = True
                    pair = frozenset({tid, hit[0]})
                    if pair not in seen_pairs:
                        seen_pairs.add(pair)
                        splits.append(
                            ConflictSplit(
                                task_a=hit[0],
                                task_b=tid,
                                reason=hit[2],
                                evidence=hit[1],
                            )
                        )
                else:
                    committed.append(tid)

    return phase, splits


def to_entries(phase_map: dict[str, int]) -> list[ExecutionPlanEntry]:
    """phase_map → 连续编号的 ExecutionPlanEntry 列表 (I6; parallel 按 task_id 排序确定性)."""
    used = sorted(set(phase_map.values()))
    renumber = {old: new for new, old in enumerate(used, start=1)}
    buckets: dict[int, list[str]] = {}
    for tid, p in phase_map.items():
        buckets.setdefault(renumber[p], []).append(tid)
    return [
        ExecutionPlanEntry(phase=p, parallel=sorted(buckets[p]))
        for p in sorted(buckets)
    ]


def self_check(manifest: BatchManifest, entries: list[ExecutionPlanEntry]) -> None:
    """I1: 写回前用 C7 的 _validate_plan 当 oracle 自检 (AC-5); 失败 → PLAN_SELF_CHECK_FAILED."""
    try:
        _validate_plan(manifest, entries)
    except CoordinatorAbort as e:
        raise PlanningError(
            "PLAN_SELF_CHECK_FAILED",
            f"generated execution_plan failed C7 validation (C1 algorithm bug): "
            f"{e.error.message}",
            c7_code=e.error.code,
        ) from e
