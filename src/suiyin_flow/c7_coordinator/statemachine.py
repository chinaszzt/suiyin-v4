"""C7 状态机 — 确定性 transition table (spec I1).

输入只有: (a) C2 输出的语义字段 (status), (b) git 可观察事实 (ff 可达性 /
rebase 退出码 / verify 退出码), (c) spec 枚举的配置. routing path 零 AI.

每次状态转移后先落盘再执行下一动作 (I3, crash-safe resume).
"""

from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

from suiyin_flow.c2_executor.batch import (
    BatchAdapterError,
    BatchManifest,
    BatchTaskEntry,
    precheck_refs_on_base,
)
from suiyin_flow.c2_executor.cli import execute_task
from suiyin_flow.c2_executor.schema import TaskExecutorError, TaskOutput
from suiyin_flow.c2_executor.worktree import ensure_worktree
from suiyin_flow.c7_coordinator import integrate as g
from suiyin_flow.c7_coordinator.lock import acquire_lock, release_lock
from suiyin_flow.c7_coordinator.plan import load_manifest_and_plan, manifest_sha256
from suiyin_flow.c7_coordinator.schema import (
    CoordinatorAbort,
    CoordinatorState,
    ParkReason,
    PhaseRecord,
    PhaseRunOutput,
    TaskRecord,
)
from suiyin_flow.c7_coordinator.state import (
    StateStore,
    load_latest,
    make_run_id,
    safe_ref,
)


@dataclass
class CoordinatorConfig:
    tasks_yaml: Path
    repo_root: Path
    dry_run: bool = False
    resume: bool = True
    retry_parked: list[str] = field(default_factory=list)  # task_id 列表或 ["all"]
    max_parallel: int = 1  # 1 = 确定性串行 (默认); >1 = 并发 dispatch (Q7-1, 整合仍串行)
    max_requeue: int = 3
    claude_cmd: list[str] | None = None


def _log(msg: str) -> None:
    print(msg, file=sys.stderr)


# -------------------------------------------------------------------
# 入口
# -------------------------------------------------------------------


def run_coordinator(cfg: CoordinatorConfig) -> PhaseRunOutput:
    """跑完整 coordinator run. Raises CoordinatorAbort (run 级 Error)."""
    repo_root = cfg.repo_root.resolve()
    if not repo_root.exists() or not repo_root.is_dir():
        raise CoordinatorAbort(
            "REPO_ROOT_NOT_FOUND",
            f"repo_root not a directory: {repo_root}",
            repo_root=str(repo_root),
        )

    try:
        manifest, phases, base_branch = load_manifest_and_plan(cfg.tasks_yaml)
    except BatchAdapterError as e:
        raise CoordinatorAbort(
            e.error.code,  # MANIFEST_NOT_FOUND / INVALID_MANIFEST (枚举子集, 透传)
            e.error.message,
            **e.error.details,
        ) from e

    safe_key = safe_ref(base_branch)
    run_id = make_run_id()
    store = StateStore(repo_root, safe_key, run_id)

    state = CoordinatorState(
        run_id=run_id,
        manifest_path=str(cfg.tasks_yaml.resolve()),
        manifest_sha256=manifest_sha256(cfg.tasks_yaml),
        base_branch=base_branch,
        phases=phases,
    )

    # ---- dry_run: 校验 + 计划输出; 不取锁 / 不碰 git / latest 不更新 (spec §3.2) ----
    if cfg.dry_run:
        state.dry_run = True
        state.status = "dry_run"
        for ph in state.phases:
            ph.status = "dry_run"
            for t in ph.tasks:
                t.state = "dry_run"
        store.write(state)
        return _build_output(state, store)

    # 真跑前 fail-fast: spec_ref/plan_ref 必须在 base HEAD 可见 (复用 batch precheck)
    try:
        precheck_refs_on_base(manifest, str(repo_root))
    except BatchAdapterError as e:
        raise CoordinatorAbort(e.error.code, e.error.message, **e.error.details) from e

    lock_path = acquire_lock(repo_root, safe_key, run_id)  # I9
    try:
        state = _maybe_resume(cfg, repo_root, safe_key, state)
        state.run_id = run_id
        store.write(state)
        _run_phases(cfg, repo_root, manifest, state, store)
    finally:
        release_lock(lock_path)

    return _build_output(state, store)


# -------------------------------------------------------------------
# Resume (I3)
# -------------------------------------------------------------------


def _maybe_resume(
    cfg: CoordinatorConfig,
    repo_root: Path,
    safe_key: str,
    fresh: CoordinatorState,
) -> CoordinatorState:
    if not cfg.resume:
        return fresh
    prev = load_latest(repo_root, safe_key)
    if prev is None:
        return fresh

    if prev.manifest_sha256 != fresh.manifest_sha256:
        raise CoordinatorAbort(
            "STATE_CORRUPTED",
            "latest phase-state was produced from a different tasks.yaml "
            f"(sha {prev.manifest_sha256[:12]} != {fresh.manifest_sha256[:12]}). "
            "Rerun with --no-resume to start fresh, or restore the manifest.",
            prev_sha=prev.manifest_sha256,
            current_sha=fresh.manifest_sha256,
        )
    if prev.base_branch != fresh.base_branch:
        raise CoordinatorAbort(
            "STATE_CORRUPTED",
            f"latest phase-state targets base_branch {prev.base_branch!r}, "
            f"manifest says {fresh.base_branch!r}",
        )

    base_sha = g.rev_parse(repo_root, prev.base_branch)
    if base_sha is None:
        raise CoordinatorAbort(
            "GIT_ERROR",
            f"cannot resolve base_branch {prev.base_branch!r} in {repo_root}",
            retryable=True,
        )

    retry_all = "all" in cfg.retry_parked
    for ph in prev.phases:
        for t in ph.tasks:
            if t.state == "merged":
                # merged 必须与 git 事实一致 (spec I3 resume 表)
                if not t.merged_sha or not g.is_ancestor(
                    repo_root, t.merged_sha, base_sha
                ):
                    raise CoordinatorAbort(
                        "STATE_CORRUPTED",
                        f"state claims {t.task_id} merged at "
                        f"{t.merged_sha or '?'} but that sha is not an "
                        f"ancestor of {prev.base_branch} HEAD",
                        task_id=t.task_id,
                    )
            elif t.state == "parked" and (retry_all or t.task_id in cfg.retry_parked):
                if t.park_reason in ("REBASE_CONFLICT", "REVERIFY_FAILED", "MERGE_NOT_FF"):
                    t.state = "awaiting_merge"  # 整合类 park → 重入整合
                else:
                    t.state = "pending"  # task 类 park → 重 dispatch C2
                t.park_reason = None
                t.requeue_count = 0
            elif t.state == "skipped":
                t.state = "pending"  # 因前序 park 被略过的 → 这轮重新有机会
        if ph.status != "merged":
            ph.status = "pending"

    prev.status = "in_progress"
    prev.stopped_at_phase = None
    return prev


# -------------------------------------------------------------------
# Phase 主循环
# -------------------------------------------------------------------


def _run_phases(
    cfg: CoordinatorConfig,
    repo_root: Path,
    manifest: BatchManifest,
    state: CoordinatorState,
    store: StateStore,
) -> None:
    entries: dict[str, BatchTaskEntry] = {t.task_id: t for t in manifest.tasks}
    stopped = False

    for ph in state.phases:
        if all(t.state == "merged" for t in ph.tasks):
            ph.status = "merged"
            continue
        if stopped:
            ph.status = "skipped"
            for t in ph.tasks:
                if t.state not in ("merged", "parked"):
                    t.state = "skipped"
            store.write(state)
            continue

        ph.status = "executing"
        store.write(state)
        _log(f"[phase {ph.phase}] start ({len(ph.tasks)} task(s))")

        # 预 fork: phase 内全部待跑 task 先从当前 base HEAD 起 worktree,
        # 钉死 fork point = phase 开始时刻 (并行语义; 串行执行只是 wall-clock 实现)
        for t in ph.tasks:
            if t.state != "pending":
                continue
            try:
                wt = ensure_worktree(
                    repo_root, t.task_id, entries[t.task_id].base_branch
                )
                t.worktree_path = str(wt)
            except TaskExecutorError as e:
                t.state = "parked"
                t.park_reason = "TASK_ERROR"
                t.c2_error = e.error
                _log(f"[phase {ph.phase}] {t.task_id}: parked (TASK_ERROR @prefork)")
        store.write(state)

        if cfg.max_parallel > 1:
            _execute_phase_parallel(cfg, repo_root, ph, entries, state, store)
        else:
            _execute_phase_serial(cfg, repo_root, ph, entries, state, store)

        if any(t.state == "parked" for t in ph.tasks):
            ph.status = "parked"
            state.status = "stopped"
            state.stopped_at_phase = ph.phase
            stopped = True
        else:
            ph.status = "merged"
            _log(f"[phase {ph.phase}] merged")
        store.write(state)

    if not stopped:
        state.status = "all_merged"
        store.write(state)


def _execute_phase_serial(
    cfg: CoordinatorConfig,
    repo_root: Path,
    ph: PhaseRecord,
    entries: dict[str, BatchTaskEntry],
    state: CoordinatorState,
    store: StateStore,
) -> None:
    """max_parallel=1: dispatch+integrate 交替, 早 park 则 phase 内剩余 pending skip.

    确定性串行 (默认; AC-9 determinism / AC-4 rebased 归属都依赖此序)。
    """
    for t in ph.tasks:
        park_in_phase = any(x.state == "parked" for x in ph.tasks)
        if t.state in ("merged", "skipped", "parked"):
            continue
        if park_in_phase and t.state == "pending":
            t.state = "skipped"  # phase 已出 park, 不再起新 session
            store.write(state)
            continue
        if t.state in ("pending", "executing"):
            _dispatch(cfg, ph, t, entries[t.task_id], state, store)
        if t.state in ("awaiting_merge", "integrating"):
            _integrate(cfg, repo_root, ph, t, entries[t.task_id], state, store)


def _execute_phase_parallel(
    cfg: CoordinatorConfig,
    repo_root: Path,
    ph: PhaseRecord,
    entries: dict[str, BatchTaskEntry],
    state: CoordinatorState,
    store: StateStore,
) -> None:
    """max_parallel>1 (Q7-1): dispatch 并发 (≤max_parallel), integrate 严格串行.

    - **dispatch 并发**: C2 session 是阻塞 subprocess, 线程并发省 wall-clock。
      execute_task 在 worker 线程跑 (无 C7 state 副作用); 所有 state mutation +
      store.write 留主线程 (as_completed 循环), 单线程改 state → 无 race。
    - **integrate 串行**: ff / rebase-requeue 推进 base 必须串行 (spec §3.3 整合
      队列 + I7); 按完成序 (merge_queue) dequeue。
    - **非确定边界**: dispatch 完成序非确定 → "谁先 merge / 谁 rebase" 随之变
      (wall-clock 层), 但 routing 逻辑确定 (I2) + 结局正确 (all_merged / park 集合
      一致)。phase 内全部 pending 都跑 (不像串行早 park 即 skip), 符合并行语义。
    """
    pending = [t for t in ph.tasks if t.state in ("pending", "executing")]
    for t in pending:
        t.state = "executing"
    store.write(state)
    _log(f"[phase {ph.phase}] dispatch {len(pending)} task(s), max_parallel={cfg.max_parallel}")

    if pending:
        with ThreadPoolExecutor(max_workers=cfg.max_parallel) as ex:
            fut_to_task = {ex.submit(_run_c2, cfg, entries[t.task_id]): t for t in pending}
            for fut in as_completed(fut_to_task):
                t = fut_to_task[fut]
                try:
                    out = fut.result()
                except TaskExecutorError as e:
                    _apply_dispatch_result(ph, t, None, e, state, store)
                    continue
                _apply_dispatch_result(ph, t, out, None, state, store)

    # 串行整合: 完成序 (merge_queue) dequeue (spec §3.3 整合子流程)
    for tid in list(state.merge_queue):
        mt = next((x for x in ph.tasks if x.task_id == tid), None)
        if mt is not None and mt.state in ("awaiting_merge", "integrating"):
            _integrate(cfg, repo_root, ph, mt, entries[mt.task_id], state, store)


def _run_c2(cfg: CoordinatorConfig, entry: BatchTaskEntry) -> TaskOutput:
    """纯 C2 调用 (无 C7 state 副作用 → 可在 worker 线程并发跑, Q7-1).

    I6: C7 调度下 task→feature 是本地 merge 语义 — 不 push / 不开 task PR.
    worktree 已由 phase 预 fork 建好, execute_task 内 ensure_worktree 复用。
    Raises TaskExecutorError (caller 主线程接住转 park).
    """
    task_input = entry.to_task_input(repo_root=str(cfg.repo_root.resolve()))
    task_input = task_input.model_copy(update={"open_pr": False})
    return execute_task(task_input, claude_cmd=cfg.claude_cmd)


def _apply_dispatch_result(
    ph: PhaseRecord,
    t: TaskRecord,
    out: TaskOutput | None,
    err: TaskExecutorError | None,
    state: CoordinatorState,
    store: StateStore,
) -> None:
    """主线程串行处理 dispatch 结果 → awaiting_merge | parked (state mutation 单线程)."""
    if err is not None:
        t.state = "parked"
        t.park_reason = "TASK_ERROR"
        t.c2_error = err.error
        store.write(state)
        _log(f"[phase {ph.phase}] {t.task_id}: parked (TASK_ERROR {err.error.code})")
        return
    assert out is not None
    t.c2_output = out
    t.worktree_path = out.worktree_path
    if out.status != "success":
        t.state = "parked"
        t.park_reason = "TASK_FAILED"
        store.write(state)
        _log(f"[phase {ph.phase}] {t.task_id}: parked (TASK_FAILED)")
        return
    t.state = "awaiting_merge"
    if t.task_id not in state.merge_queue:
        state.merge_queue.append(t.task_id)  # 完成序入队 (spec §3.3)
    store.write(state)


def _dispatch(
    cfg: CoordinatorConfig,
    ph: PhaseRecord,
    t: TaskRecord,
    entry: BatchTaskEntry,
    state: CoordinatorState,
    store: StateStore,
) -> None:
    """pending/executing → C2 session → awaiting_merge | parked (串行路径)."""
    t.state = "executing"
    store.write(state)
    _log(f"[phase {ph.phase}] {t.task_id}: dispatch C2")
    try:
        out = _run_c2(cfg, entry)
    except TaskExecutorError as e:
        _apply_dispatch_result(ph, t, None, e, state, store)
        return
    _apply_dispatch_result(ph, t, out, None, state, store)


def _integrate(
    cfg: CoordinatorConfig,
    repo_root: Path,
    ph: PhaseRecord,
    t: TaskRecord,
    entry: BatchTaskEntry,
    state: CoordinatorState,
    store: StateStore,
) -> None:
    """awaiting_merge → 整合子流程 (spec §3.3) → merged | parked."""
    t.state = "integrating"
    store.write(state)
    task_branch = f"task/{t.task_id}"
    base_branch = state.base_branch
    wt = Path(t.worktree_path) if t.worktree_path else None

    attempts = t.requeue_count
    while True:
        task_sha = g.rev_parse(repo_root, task_branch)
        base_sha = g.rev_parse(repo_root, base_branch)
        if task_sha is None or base_sha is None:
            raise CoordinatorAbort(
                "GIT_ERROR",
                f"cannot resolve {task_branch!r} or {base_branch!r} in {repo_root}",
                retryable=True,
                task_id=t.task_id,
            )

        if task_sha == base_sha or g.is_ancestor(repo_root, task_sha, base_sha):
            # task 无新增 commit / 已被整合 (resume 幂等) → merged no-op
            _mark_merged(repo_root, ph, t, base_sha, state, store)
            return

        if g.is_ancestor(repo_root, base_sha, task_sha):
            if g.ff_advance(repo_root, base_branch, task_sha, base_sha):
                _mark_merged(repo_root, ph, t, task_sha, state, store)
                return
            # CAS race (理论上单实例锁下不可达) → 计一次 requeue 重derive
        else:
            # 非 ff (同 phase 先完成者推进了 base) → rebase-requeue
            if attempts >= cfg.max_requeue:
                _park(ph, t, "MERGE_NOT_FF", state, store)
                return
            if wt is None or not wt.exists():
                raise CoordinatorAbort(
                    "GIT_ERROR",
                    f"worktree missing for {t.task_id}, cannot rebase",
                    task_id=t.task_id,
                )
            t.rebased = True
            _log(f"[phase {ph.phase}] {t.task_id}: non-ff, rebase onto {base_branch}")
            if not g.rebase_onto(wt, base_branch):
                _park(ph, t, "REBASE_CONFLICT", state, store)
                return
            ok, reverify_out = g.run_verify(wt, entry.verify_cmd)  # I10: rebase 后必重 verify
            t.reverify_pass = ok
            if not ok:
                t.reverify_output = reverify_out  # 发现 #3: 存诊断输出
                _park(ph, t, "REVERIFY_FAILED", state, store)
                return

        attempts += 1
        t.requeue_count = attempts
        store.write(state)
        if attempts > cfg.max_requeue:
            _park(ph, t, "MERGE_NOT_FF", state, store)
            return


def _mark_merged(
    repo_root: Path,
    ph: PhaseRecord,
    t: TaskRecord,
    merged_sha: str,
    state: CoordinatorState,
    store: StateStore,
) -> None:
    t.state = "merged"
    t.merged_sha = merged_sha
    if t.task_id in state.merge_queue:
        state.merge_queue.remove(t.task_id)
    store.write(state)  # 先落盘 merge 事实, 再 best-effort 清理 (I3)
    g.cleanup_merged(repo_root, t.task_id)  # I11
    t.worktree_path = None
    store.write(state)
    _log(f"[phase {ph.phase}] {t.task_id}: merged @ {merged_sha[:10]}")


def _park(
    ph: PhaseRecord,
    t: TaskRecord,
    reason: ParkReason,
    state: CoordinatorState,
    store: StateStore,
) -> None:
    t.state = "parked"
    t.park_reason = reason
    if t.task_id in state.merge_queue:
        state.merge_queue.remove(t.task_id)
    store.write(state)
    _log(f"[phase {ph.phase}] {t.task_id}: parked ({reason}); worktree retained")


def _build_output(state: CoordinatorState, store: StateStore) -> PhaseRunOutput:
    assert state.status in ("all_merged", "stopped", "dry_run")
    return PhaseRunOutput(
        status=state.status,
        base_branch=state.base_branch,
        phases=state.phases,
        stopped_at_phase=state.stopped_at_phase,
        state_file_path=str(store.versioned),
    )
