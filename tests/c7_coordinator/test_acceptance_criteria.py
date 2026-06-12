"""C7 Phase Coordinator AC tests — spec §5 AC-1..AC-13.

命名: test_AC_<n>_<desc> (Fork G 约定).
不真起 Claude session; git 状态是真的 (整合子流程跑真 git).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from suiyin_flow.c2_executor.schema import TaskOutput
from suiyin_flow.c7_coordinator import cli as c7_cli
from suiyin_flow.c7_coordinator import statemachine as sm
from suiyin_flow.c7_coordinator.schema import CoordinatorAbort, PhaseRunOutput
from suiyin_flow.c7_coordinator.statemachine import (
    CoordinatorConfig,
    run_coordinator,
)
from tests.c7_coordinator.conftest import (
    VERIFY_FAIL,
    Behavior,
    git,
    make_fake_execute,
    task_entry,
    write_manifest,
)

# -------------------------------------------------------------------
# helpers
# -------------------------------------------------------------------


def _run(
    repo: Path,
    manifest_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    behaviors: dict[str, Behavior] | None = None,
    record: dict[str, Any] | None = None,
    **cfg_kw: Any,
) -> PhaseRunOutput:
    rec = record if record is not None else {}
    fake = make_fake_execute(repo, behaviors or {}, rec)
    monkeypatch.setattr(sm, "execute_task", fake)
    cfg = CoordinatorConfig(tasks_yaml=manifest_path, repo_root=repo, **cfg_kw)
    return run_coordinator(cfg)


def _task(out: PhaseRunOutput, task_id: str) -> Any:
    for ph in out.phases:
        for t in ph.tasks:
            if t.task_id == task_id:
                return t
    raise AssertionError(f"{task_id} not in output")


def _merge_commit_count(repo: Path, base: str = "main") -> int:
    return int(git(repo, "rev-list", "--merges", "--count", base))


def _normalize(data: Any) -> Any:
    """AC-9/AC-10 等价比较: 剔除时变量 / 路径 / sha."""
    drop = {
        "merged_sha", "worktree_path", "state_file_path", "updated_at",
        "log_path", "run_id", "manifest_path", "manifest_sha256",
        "verify_report_path", "pr_url_or_branch", "duration_seconds",
    }
    if isinstance(data, dict):
        return {k: _normalize(v) for k, v in data.items() if k not in drop}
    if isinstance(data, list):
        return [_normalize(x) for x in data]
    return data


# -------------------------------------------------------------------
# AC-1 / AC-2: 依赖链闭环 + execution_plan 调度
# -------------------------------------------------------------------


def test_AC_1_dependency_chain_degenerate_plan(
    fixture_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """无 execution_plan: T-002 depends_on T-001 → 串行两 phase;
    T-002 worktree 创建时 base HEAD 已含 T-001 产物 (头号发现 closure)."""
    mp = write_manifest(
        fixture_repo,
        [task_entry("T-001"), task_entry("T-002", depends_on=["T-001"])],
    )
    record: dict[str, Any] = {}
    out = _run(fixture_repo, mp, monkeypatch, record=record)

    assert out.status == "all_merged"
    assert [ph.phase for ph in out.phases] == [1, 2]  # degenerate: 每 task 一 phase
    # T-002 fork 时看得见 T-001 的产物
    assert "T-001.txt" in record["visible_at_dispatch"]["T-002"]
    # base 全程 ff (零 merge commit), 两个 task commit 都在
    assert _merge_commit_count(fixture_repo) == 0
    log = git(fixture_repo, "log", "--oneline", "main")
    assert "T-001: mock impl" in log and "T-002: mock impl" in log
    # I6: C7 调度下 C2 拿到 open_pr=False
    assert record["open_pr_seen"] == {"T-001": False, "T-002": False}


def test_AC_2_execution_plan_phase_barrier(
    fixture_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """phase 2 的 worktree 创建晚于 phase 1 全部 merge;
    phase 内 task fork 点 = phase 开始时刻 (并行语义)."""
    mp = write_manifest(
        fixture_repo,
        [task_entry("T-001"), task_entry("T-002"), task_entry("T-003")],
        execution_plan=[
            {"phase": 1, "parallel": ["T-001", "T-002"]},
            {"phase": 2, "parallel": ["T-003"]},
        ],
    )
    record: dict[str, Any] = {}
    out = _run(fixture_repo, mp, monkeypatch, record=record)

    assert out.status == "all_merged"
    # 同 phase: T-002 的 fork 点在 T-001 merge 之前 → 看不见 T-001 产物
    assert "T-001.txt" not in record["visible_at_dispatch"]["T-002"]
    # 跨 phase: T-003 看得见 phase 1 全部产物 (I5)
    assert {"T-001.txt", "T-002.txt"} <= set(record["visible_at_dispatch"]["T-003"])


# -------------------------------------------------------------------
# AC-3: fail-stop + 不回滚 (I8, Q7)
# -------------------------------------------------------------------


def test_AC_3_failstop_no_rollback(
    fixture_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mp = write_manifest(
        fixture_repo,
        [task_entry("T-001"), task_entry("T-002"), task_entry("T-003")],
        execution_plan=[
            {"phase": 1, "parallel": ["T-001"]},
            {"phase": 2, "parallel": ["T-002"]},
            {"phase": 3, "parallel": ["T-003"]},
        ],
    )
    out = _run(
        fixture_repo, mp, monkeypatch, behaviors={"T-002": ("fail", {})}
    )

    assert out.status == "stopped"
    assert out.stopped_at_phase == 2
    assert _task(out, "T-001").state == "merged"
    t2 = _task(out, "T-002")
    assert t2.state == "parked" and t2.park_reason == "TASK_FAILED"
    assert _task(out, "T-003").state == "skipped"
    assert out.phases[2].status == "skipped"
    # 不回滚: T-001 的 merge 仍在 main HEAD 祖先链上
    assert _task(out, "T-001").merged_sha == git(fixture_repo, "rev-parse", "main")
    assert "T-001: mock impl" in git(fixture_repo, "log", "--oneline", "main")


# -------------------------------------------------------------------
# AC-4 / AC-5 / AC-6: 整合子流程 (rebase-requeue, Q6-2 (b))
# -------------------------------------------------------------------


def test_AC_4_rebase_requeue_clean(
    fixture_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """同 phase A/B 并行 fork; A 先 merge → B 非 ff → rebase + 重 verify → merge."""
    mp = write_manifest(
        fixture_repo,
        [task_entry("T-001"), task_entry("T-002")],
        execution_plan=[{"phase": 1, "parallel": ["T-001", "T-002"]}],
    )
    out = _run(fixture_repo, mp, monkeypatch)

    assert out.status == "all_merged"
    t2 = _task(out, "T-002")
    assert t2.state == "merged"
    assert t2.rebased is True
    assert t2.reverify_pass is True
    assert _task(out, "T-001").rebased is False
    assert _merge_commit_count(fixture_repo) == 0  # I7 ff-only


def test_AC_5_rebase_conflict_parks_and_restores(
    fixture_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mp = write_manifest(
        fixture_repo,
        [task_entry("T-001"), task_entry("T-002")],
        execution_plan=[{"phase": 1, "parallel": ["T-001", "T-002"]}],
    )
    behaviors: dict[str, Behavior] = {
        "T-001": ("success", {"conflict.txt": "from T-001\n"}),
        "T-002": ("success", {"conflict.txt": "from T-002\n"}),
    }
    out = _run(fixture_repo, mp, monkeypatch, behaviors=behaviors)

    assert out.status == "stopped"
    t2 = _task(out, "T-002")
    assert t2.state == "parked" and t2.park_reason == "REBASE_CONFLICT"
    # worktree 还原到 rebase 前 (无 conflict marker), 保留现场
    wt = fixture_repo / "worktrees" / "T-002"
    assert wt.exists()
    assert (wt / "conflict.txt").read_text(encoding="utf-8") == "from T-002\n"
    assert git(wt, "status", "--porcelain") == ""
    # main 只含 T-001 版本 (不回滚 / 不混入)
    assert (
        git(fixture_repo, "show", "main:conflict.txt") == "from T-001"
    )


def test_AC_6_reverify_failed_parks(
    fixture_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """rebase 干净但重 verify 非绿 (I10) → park, 不 merge."""
    mp = write_manifest(
        fixture_repo,
        [task_entry("T-001"), task_entry("T-002", verify_cmd=VERIFY_FAIL)],
        execution_plan=[{"phase": 1, "parallel": ["T-001", "T-002"]}],
    )
    out = _run(fixture_repo, mp, monkeypatch)

    assert out.status == "stopped"
    t2 = _task(out, "T-002")
    assert t2.state == "parked" and t2.park_reason == "REVERIFY_FAILED"
    assert t2.rebased is True and t2.reverify_pass is False
    # 发现 #3: park 时 reverify_output 被赋值 (从默认 None) 供诊断;
    # VERIFY_FAIL 是静默 SystemExit(1) 故内容为空, 但字段已填 (非 None)
    assert t2.reverify_output is not None
    assert "T-002: mock impl" not in git(fixture_repo, "log", "--oneline", "main")


# -------------------------------------------------------------------
# AC-7: coordinator 锁 (I9, 发现 #8)
# -------------------------------------------------------------------


def _write_lock(repo: Path, pid: int) -> Path:
    lock = repo / ".suiyin" / "locks" / "coordinator-main.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(
        json.dumps({"pid": pid, "run_id": "prior", "start_ts": "t"}),
        encoding="utf-8",
    )
    return lock


def test_AC_7_coordinator_locked(
    fixture_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_lock(fixture_repo, os.getpid())  # 活进程 (本测试进程)
    mp = write_manifest(fixture_repo, [task_entry("T-001")])

    with pytest.raises(CoordinatorAbort) as exc:
        _run(fixture_repo, mp, monkeypatch)
    assert exc.value.error.code == "COORDINATOR_LOCKED"
    # 绝不静默复用: 没建任何 worktree, 没写 state
    assert not (fixture_repo / "worktrees").exists()
    state_dir = fixture_repo / ".suiyin" / "phase-state"
    assert not state_dir.exists() or not any(state_dir.iterdir())


def test_AC_7b_stale_lock_takeover(
    fixture_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock = _write_lock(fixture_repo, 2_000_000_000)  # 不存在的 pid → stale
    mp = write_manifest(fixture_repo, [task_entry("T-001")])
    out = _run(fixture_repo, mp, monkeypatch)
    assert out.status == "all_merged"
    assert not lock.exists()  # 正常退出释放锁


# -------------------------------------------------------------------
# AC-8: crash resume + retry_parked (I3)
# -------------------------------------------------------------------


def _stopped_run(
    repo: Path, mp: Path, monkeypatch: pytest.MonkeyPatch
) -> dict[str, Any]:
    record: dict[str, Any] = {}
    out = _run(
        repo, mp, monkeypatch, behaviors={"T-002": ("fail", {})}, record=record
    )
    assert out.status == "stopped"
    return record


def _two_phase_manifest(repo: Path) -> Path:
    return write_manifest(
        repo,
        [task_entry("T-001"), task_entry("T-002", depends_on=["T-001"])],
        execution_plan=[
            {"phase": 1, "parallel": ["T-001"]},
            {"phase": 2, "parallel": ["T-002"]},
        ],
    )


def test_AC_8_crash_resume_skips_merged(
    fixture_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """模拟 crash: state 停在 T-002 executing → resume 重 dispatch T-002,
    T-001 (merged) 不重跑."""
    mp = _two_phase_manifest(fixture_repo)
    _stopped_run(fixture_repo, mp, monkeypatch)

    latest = fixture_repo / ".suiyin" / "phase-state" / "latest-main.json"
    state = json.loads(latest.read_text(encoding="utf-8"))
    t2 = state["phases"][1]["tasks"][0]
    assert t2["task_id"] == "T-002"
    t2["state"] = "executing"  # 仿佛 kill -9 在 session 中途
    t2["park_reason"] = None
    state["status"] = "in_progress"
    latest.write_text(json.dumps(state), encoding="utf-8")

    record2: dict[str, Any] = {}
    out2 = _run(fixture_repo, mp, monkeypatch, record=record2)
    assert out2.status == "all_merged"
    assert record2["calls"] == ["T-002"]  # merged 的 T-001 没被重 dispatch


def test_AC_8b_retry_parked_redispatch(
    fixture_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """task 类 park (TASK_FAILED) + --retry-parked → 重 dispatch C2."""
    mp = _two_phase_manifest(fixture_repo)
    _stopped_run(fixture_repo, mp, monkeypatch)

    record2: dict[str, Any] = {}
    out2 = _run(
        fixture_repo, mp, monkeypatch, record=record2, retry_parked=["T-002"]
    )
    assert out2.status == "all_merged"
    assert record2["calls"] == ["T-002"]


def test_AC_8c_retry_parked_reintegrates_without_redispatch(
    fixture_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """整合类 park (REBASE_CONFLICT) + 人解完 conflict + --retry-parked →
    直接重入整合, 不重 dispatch C2."""
    mp = write_manifest(
        fixture_repo,
        [task_entry("T-001"), task_entry("T-002")],
        execution_plan=[{"phase": 1, "parallel": ["T-001", "T-002"]}],
    )
    behaviors: dict[str, Behavior] = {
        "T-001": ("success", {"conflict.txt": "from T-001\n"}),
        "T-002": ("success", {"conflict.txt": "from T-002\n"}),
    }
    out = _run(fixture_repo, mp, monkeypatch, behaviors=behaviors)
    assert _task(out, "T-002").park_reason == "REBASE_CONFLICT"

    # 人工解 conflict: worktree 内 rebase + 取双方合并版 + continue
    wt = fixture_repo / "worktrees" / "T-002"
    import subprocess

    subprocess.run(
        ["git", "-C", str(wt), "rebase", "main"],
        capture_output=True, text=True, shell=False, check=False,
    )
    (wt / "conflict.txt").write_text("from T-001\nfrom T-002\n", encoding="utf-8")
    git(wt, "add", "conflict.txt")
    env = dict(os.environ, GIT_EDITOR="true")
    subprocess.run(
        ["git", "-C", str(wt), "rebase", "--continue"],
        capture_output=True, text=True, shell=False, check=True, env=env,
    )

    record2: dict[str, Any] = {}
    out2 = _run(
        fixture_repo, mp, monkeypatch, behaviors=behaviors,
        record=record2, retry_parked=["T-002"],
    )
    assert out2.status == "all_merged"
    assert record2.get("calls", []) == []  # 零重 dispatch
    assert git(fixture_repo, "show", "main:conflict.txt") == "from T-001\nfrom T-002"


# -------------------------------------------------------------------
# AC-9 / AC-10: determinism + 路由集中
# -------------------------------------------------------------------


def test_AC_9_determinism(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """同 input + 同组件结果 → 归一化后 Output 完全一致 (跑 3 个独立 repo)."""
    from tests.c7_coordinator.conftest import fixture_repo as _unused  # noqa: F401

    outputs = []
    for i in range(3):
        repo = tmp_path / f"r{i}" / "repo"
        repo.mkdir(parents=True)
        git(repo, "init", "-b", "main")
        git(repo, "config", "user.email", "t@t")
        git(repo, "config", "user.name", "t")
        git(repo, "config", "commit.gpgsign", "false")
        (repo / "spec.md").write_text("# s\n", encoding="utf-8")
        (repo / "plan.md").write_text("# p\n", encoding="utf-8")
        (repo / "constitution.md").write_text("# c\n", encoding="utf-8")
        git(repo, "add", ".")
        git(repo, "commit", "-m", "initial")
        mp = write_manifest(
            repo,
            [task_entry("T-001"), task_entry("T-002")],
            execution_plan=[{"phase": 1, "parallel": ["T-001", "T-002"]}],
        )
        out = _run(repo, mp, monkeypatch)
        outputs.append(_normalize(json.loads(out.model_dump_json())))

    assert outputs[0] == outputs[1] == outputs[2]


def test_AC_10_topology_fields_ignored(
    fixture_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """C2 output 混入 next_action_owner 等拓扑字段 → C7 决策不变 (I2)."""
    mp = write_manifest(
        fixture_repo, [task_entry("T-001"), task_entry("T-002", depends_on=["T-001"])]
    )
    record: dict[str, Any] = {}
    inner = make_fake_execute(fixture_repo, {}, record)

    def fake_with_topology(task_input: Any, *, claude_cmd: Any = None) -> TaskOutput:
        out = inner(task_input, claude_cmd=claude_cmd)
        # 注入拓扑字段 — pydantic schema 必须丢弃而非消费
        return TaskOutput.model_validate(
            {**out.model_dump(), "next_action_owner": "human"}
        )

    monkeypatch.setattr(sm, "execute_task", fake_with_topology)
    cfg = CoordinatorConfig(tasks_yaml=mp, repo_root=fixture_repo)
    out = run_coordinator(cfg)
    assert out.status == "all_merged"
    dumped = out.model_dump()
    assert "next_action_owner" not in json.dumps(dumped)


# -------------------------------------------------------------------
# AC-11: exit code + dry_run 边界 (I4)
# -------------------------------------------------------------------


def test_AC_11_exit_codes(
    fixture_repo: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    mp = write_manifest(
        fixture_repo, [task_entry("T-001"), task_entry("T-002")]
    )
    record: dict[str, Any] = {}
    # all_merged → 0
    fake = make_fake_execute(fixture_repo, {}, record)
    monkeypatch.setattr(sm, "execute_task", fake)
    rc = c7_cli.main(
        ["phase", "run", "--tasks", str(mp), "--repo-root", str(fixture_repo)]
    )
    assert rc == 0
    capsys.readouterr()

    # Error (INVALID_PLAN) → 2
    bad = write_manifest(
        fixture_repo,
        [task_entry("T-001")],
        execution_plan=[{"phase": 1, "parallel": ["T-999"]}],
    )
    rc = c7_cli.main(
        ["phase", "run", "--tasks", str(bad), "--repo-root", str(fixture_repo)]
    )
    assert rc == 2
    captured = capsys.readouterr()
    assert "INVALID_PLAN" in captured.err


def test_AC_11b_exit_code_stopped_is_1(
    fixture_repo: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    mp = write_manifest(fixture_repo, [task_entry("T-001")])
    record: dict[str, Any] = {}
    fake = make_fake_execute(fixture_repo, {"T-001": ("fail", {})}, record)
    monkeypatch.setattr(sm, "execute_task", fake)
    rc = c7_cli.main(
        ["phase", "run", "--tasks", str(mp), "--repo-root", str(fixture_repo)]
    )
    assert rc == 1


def test_AC_11c_dry_run_boundaries(
    fixture_repo: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """dry_run: 不取锁 / 不建 worktree / base 不动 / versioned 落盘 / latest 不更新."""
    mp = write_manifest(
        fixture_repo, [task_entry("T-001"), task_entry("T-002")]
    )
    head_before = git(fixture_repo, "rev-parse", "main")

    def boom(*a: Any, **k: Any) -> None:
        raise AssertionError("dry_run must not dispatch C2")

    monkeypatch.setattr(sm, "execute_task", boom)
    rc = c7_cli.main(
        ["phase", "run", "--tasks", str(mp), "--repo-root", str(fixture_repo), "--dry-run"]
    )
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "dry_run"
    assert all(
        t["state"] == "dry_run" for ph in out["phases"] for t in ph["tasks"]
    )

    assert git(fixture_repo, "rev-parse", "main") == head_before
    assert not (fixture_repo / "worktrees").exists()
    assert not (fixture_repo / ".suiyin" / "locks").exists()
    state_dir = fixture_repo / ".suiyin" / "phase-state"
    versioned = [p for p in state_dir.iterdir() if p.name.startswith("main-")]
    assert len(versioned) == 1
    assert json.loads(versioned[0].read_text(encoding="utf-8"))["dry_run"] is True
    assert not (state_dir / "latest-main.json").exists()


# -------------------------------------------------------------------
# AC-12: INVALID_PLAN 三规则
# -------------------------------------------------------------------


def test_AC_12_invalid_plan(
    fixture_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cases = [
        # (a) 覆盖集不符 (漏 T-002)
        dict(
            tasks=[task_entry("T-001"), task_entry("T-002")],
            execution_plan=[{"phase": 1, "parallel": ["T-001"]}],
        ),
        # (b) 同 phase 内 depends_on
        dict(
            tasks=[task_entry("T-001"), task_entry("T-002", depends_on=["T-001"])],
            execution_plan=[{"phase": 1, "parallel": ["T-001", "T-002"]}],
        ),
        # (c) base_branch 混用
        dict(
            tasks=[
                task_entry("T-001"),
                task_entry("T-002", base_branch="other"),
            ],
            execution_plan=None,
        ),
    ]
    for case in cases:
        mp = write_manifest(
            fixture_repo, case["tasks"], case["execution_plan"]
        )
        with pytest.raises(CoordinatorAbort) as exc:
            _run(fixture_repo, mp, monkeypatch)
        assert exc.value.error.code == "INVALID_PLAN"
        assert not (fixture_repo / "worktrees").exists()  # 零副作用


# -------------------------------------------------------------------
# AC-13: worktree 生命周期 (I11)
# -------------------------------------------------------------------


def test_AC_13_lifecycle_cleanup(
    fixture_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mp = _two_phase_manifest(fixture_repo)
    _stopped_run(fixture_repo, mp, monkeypatch)

    # merged → worktree 删 + 分支删
    assert not (fixture_repo / "worktrees" / "T-001").exists()
    branches = git(fixture_repo, "branch", "--list", "task/T-001")
    assert branches == ""
    # parked → 双双保留
    assert (fixture_repo / "worktrees" / "T-002").exists()
    assert "task/T-002" in git(fixture_repo, "branch", "--list", "task/T-002")
