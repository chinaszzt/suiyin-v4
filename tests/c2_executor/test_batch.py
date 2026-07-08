"""C2 batch adapter AC tests (P1.2.5).

Mock 策略: monkeypatch `suiyin_flow.c2_executor.batch.execute_task`. batch.py 本身
只负责"解析 yaml + 顺序调度 + fail-stop", 不依赖真 git/Claude session. C2 单 task
pipeline 已由 tests/c2_executor/test_acceptance_criteria.py 覆盖.

Fork G 命名: test_AC_B<n>_<desc>.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from suiyin_flow.c2_executor import batch as batch_mod
from suiyin_flow.c2_executor import cli as c2_cli
from suiyin_flow.c2_executor.batch import (
    BATCH_SCHEMA_VERSION,
    BatchAdapterError,
    BatchManifest,
    BatchTaskEntry,
    load_tasks_yaml,
    run_batch,
)
from suiyin_flow.c2_executor.schema import (
    DiffStats,
    SessionLog,
    TaskExecutorError,
    TaskInput,
    TaskOutput,
)


def _make_success_output(task_id: str, wt: str = "/tmp/wt") -> TaskOutput:
    return TaskOutput(
        task_id=task_id,
        status="success",
        attempts=1,
        worktree_path=wt,
        pr_url_or_branch=f"task/{task_id}",
        pr_created=False,
        verify_report_path=None,
        session_logs=[
            SessionLog(
                attempt=1,
                log_path=f"/tmp/sessions/{task_id}.log",
                duration_seconds=1.0,
                verify_pass=True,
            )
        ],
        diff_stats=DiffStats(files_changed=1, insertions=2, deletions=0),
    )


def _task_entry(
    task_id: str = "T-001",
    deps: list[str] | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    """Build a tasks.yaml task entry as a Python dict (avoid textwrap pitfalls)."""
    entry: dict[str, Any] = {
        "task_id": task_id,
        "spec_ref": f"specs/{task_id}/spec.md",
        "plan_ref": f"specs/{task_id}/plan.md",
        "verify_cmd": "true",
        "context_seeds": [],
        "ac_list": ["AC-1"],
        "criticality": "medium",
    }
    if deps is not None:
        entry["depends_on"] = deps
    entry.update(overrides)
    return entry


def _write_manifest(
    path: Path,
    tasks: list[dict[str, Any]],
    *,
    schema_version: str = BATCH_SCHEMA_VERSION,
    feature_name: str | None = None,
) -> None:
    """Dump a tasks.yaml file from typed Python data."""
    manifest: dict[str, Any] = {"schema_version": schema_version, "tasks": tasks}
    if feature_name is not None:
        manifest["feature_name"] = feature_name
    path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")


def _make_manifest(task_ids: list[str]) -> BatchManifest:
    """Build a BatchManifest with N minimal BatchTaskEntry directly (skipping yaml round-trip).

    用于"测 run_batch 调度行为"那一族 AC test — yaml 解析路径由 B1/B5 系列覆盖。
    """
    return BatchManifest(
        schema_version=BATCH_SCHEMA_VERSION,
        tasks=[
            BatchTaskEntry(
                task_id=tid,
                spec_ref="s.md",
                plan_ref="p.md",
                verify_cmd="true",
                context_seeds=[],
                ac_list=[],
            )
            for tid in task_ids
        ],
    )


# =============================================================================
# AC-B1: tasks.yaml 解析 — 合法 + 缺字段
# =============================================================================


def test_AC_B1a_load_valid_yaml(tmp_path: Path) -> None:
    """AC-B1a: 合法 tasks.yaml 解析成 BatchManifest."""
    yaml_path = tmp_path / "tasks.yaml"
    _write_manifest(
        yaml_path,
        [_task_entry("T-001"), _task_entry("T-002")],
        feature_name="001-test-feature",
    )
    manifest = load_tasks_yaml(yaml_path)
    assert manifest.schema_version == BATCH_SCHEMA_VERSION
    assert manifest.feature_name == "001-test-feature"
    assert len(manifest.tasks) == 2
    assert [t.task_id for t in manifest.tasks] == ["T-001", "T-002"]
    # 默认值兜底
    assert manifest.tasks[0].max_retries == 3
    assert manifest.tasks[0].base_branch == "main"
    assert manifest.tasks[0].criticality == "medium"


def test_AC_B1b_missing_required_field_raises(tmp_path: Path) -> None:
    """AC-B1b: 缺 verify_cmd → INVALID_MANIFEST."""
    yaml_path = tmp_path / "tasks.yaml"
    bad_entry = {
        "task_id": "T-001",
        "spec_ref": "spec.md",
        "plan_ref": "plan.md",
        "context_seeds": [],
        "ac_list": [],
    }
    _write_manifest(yaml_path, [bad_entry])
    with pytest.raises(BatchAdapterError) as exc:
        load_tasks_yaml(yaml_path)
    assert exc.value.error.code == "INVALID_MANIFEST"
    assert "verify_cmd" in exc.value.error.message


def test_AC_B1c_malformed_yaml_raises(tmp_path: Path) -> None:
    """AC-B1c: 非法 yaml syntax → INVALID_MANIFEST."""
    yaml_path = tmp_path / "tasks.yaml"
    yaml_path.write_text("schema_version: v0.1.0\ntasks: [unclosed", encoding="utf-8")
    with pytest.raises(BatchAdapterError) as exc:
        load_tasks_yaml(yaml_path)
    assert exc.value.error.code == "INVALID_MANIFEST"


def test_AC_B1d_path_not_found(tmp_path: Path) -> None:
    """AC-B1d: tasks.yaml 不存在 → MANIFEST_NOT_FOUND."""
    with pytest.raises(BatchAdapterError) as exc:
        load_tasks_yaml(tmp_path / "nope.yaml")
    assert exc.value.error.code == "MANIFEST_NOT_FOUND"


def test_AC_B1e_unsupported_schema_version(tmp_path: Path) -> None:
    """AC-B1e: schema_version 不识别 → INVALID_MANIFEST + 明确 msg."""
    yaml_path = tmp_path / "tasks.yaml"
    _write_manifest(yaml_path, [_task_entry("T-001")], schema_version="v9.99.0")
    with pytest.raises(BatchAdapterError) as exc:
        load_tasks_yaml(yaml_path)
    assert exc.value.error.code == "INVALID_MANIFEST"
    assert "v9.99.0" in exc.value.error.message


def test_AC_B1f_duplicate_task_id(tmp_path: Path) -> None:
    """AC-B1f: tasks[] 内 task_id 重复 → INVALID_MANIFEST."""
    yaml_path = tmp_path / "tasks.yaml"
    _write_manifest(yaml_path, [_task_entry("T-001"), _task_entry("T-001")])
    with pytest.raises(BatchAdapterError) as exc:
        load_tasks_yaml(yaml_path)
    assert exc.value.error.code == "INVALID_MANIFEST"
    assert "duplicate" in exc.value.error.message.lower()


# =============================================================================
# AC-B2: 顺序调度 — 3 task 按 yaml 顺序跑
# =============================================================================


def test_AC_B2_sequential_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    """AC-B2: 3 个 task 顺序调 execute_task, 顺序 = yaml 顺序."""
    call_order: list[str] = []

    def fake_execute(
        task_input: TaskInput, *, claude_cmd: list[str] | None = None
    ) -> TaskOutput:
        call_order.append(task_input.task_id)
        return _make_success_output(task_input.task_id)

    monkeypatch.setattr(batch_mod, "execute_task", fake_execute)

    manifest = _make_manifest(["T-001", "T-002", "T-003"])

    output = run_batch(manifest, repo_root="/tmp/repo")

    assert call_order == ["T-001", "T-002", "T-003"]
    assert output.status == "all_success"
    assert [r.task_id for r in output.tasks] == ["T-001", "T-002", "T-003"]
    assert all(r.status == "success" for r in output.tasks)
    assert output.stopped_at_task_id is None


# =============================================================================
# AC-B3: 中间 fail → 后续 task 不跑 (fail-stop)
# =============================================================================


def test_AC_B3a_middle_task_returns_failed_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-B3a: T-002 返回 status=failed → T-003 不调用, 标 skipped."""
    call_count = {"n": 0}

    def fake_execute(
        task_input: TaskInput, *, claude_cmd: list[str] | None = None
    ) -> TaskOutput:
        call_count["n"] += 1
        if task_input.task_id == "T-002":
            # status=failed 通过修改 _make_success_output 的 status 字段模拟
            out = _make_success_output(task_input.task_id)
            return out.model_copy(update={"status": "failed"})
        return _make_success_output(task_input.task_id)

    monkeypatch.setattr(batch_mod, "execute_task", fake_execute)

    manifest = _make_manifest(["T-001", "T-002", "T-003"])

    output = run_batch(manifest, repo_root="/tmp/repo")

    assert call_count["n"] == 2  # T-003 skipped, 没调
    assert output.status == "partial_failed"
    assert output.stopped_at_task_id == "T-002"
    statuses = [r.status for r in output.tasks]
    assert statuses == ["success", "failed", "skipped"]


def test_AC_B3b_middle_task_raises_executor_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-B3b: T-002 raise TaskExecutorError → T-003 skipped, error 序列化到 result."""

    def fake_execute(
        task_input: TaskInput, *, claude_cmd: list[str] | None = None
    ) -> TaskOutput:
        if task_input.task_id == "T-002":
            raise TaskExecutorError(
                "RETRY_EXHAUSTED",
                "boom",
                task_id="T-002",
                last_error="VERIFY_FAILED",
                attempts=3,
            )
        return _make_success_output(task_input.task_id)

    monkeypatch.setattr(batch_mod, "execute_task", fake_execute)

    manifest = _make_manifest(["T-001", "T-002", "T-003"])

    output = run_batch(manifest, repo_root="/tmp/repo")

    assert output.status == "partial_failed"
    assert output.stopped_at_task_id == "T-002"
    t2 = output.tasks[1]
    assert t2.status == "failed"
    assert t2.error is not None
    assert t2.error.code == "RETRY_EXHAUSTED"
    # T-003 没 error, 只是 skipped
    assert output.tasks[2].status == "skipped"
    assert output.tasks[2].error is None


# =============================================================================
# AC-B4: dry-run 不调 execute_task
# =============================================================================


def test_AC_B4_dry_run_does_not_invoke_executor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-B4: dry_run=True 不调 execute_task, 每 task 标 dry_run."""

    def fake_execute(
        task_input: TaskInput, *, claude_cmd: list[str] | None = None
    ) -> TaskOutput:
        raise AssertionError("execute_task 不应该在 dry_run 模式下被调用")

    monkeypatch.setattr(batch_mod, "execute_task", fake_execute)

    manifest = _make_manifest(["T-001", "T-002"])

    output = run_batch(manifest, repo_root="/tmp/repo", dry_run=True)

    assert output.status == "dry_run"
    assert all(r.status == "dry_run" for r in output.tasks)
    assert all(r.output is None and r.error is None for r in output.tasks)
    assert output.stopped_at_task_id is None


# =============================================================================
# AC-B5: depends_on 顺序断言 — 反序 raise BATCH_ORDER_VIOLATION
# =============================================================================


def test_AC_B5a_depends_on_in_order_ok(tmp_path: Path) -> None:
    """AC-B5a: T-002 depends_on T-001, T-001 在前 → 合法."""
    yaml_path = tmp_path / "tasks.yaml"
    _write_manifest(
        yaml_path,
        [_task_entry("T-001"), _task_entry("T-002", deps=["T-001"])],
    )
    manifest = load_tasks_yaml(yaml_path)
    assert manifest.tasks[1].depends_on == ["T-001"]


def test_AC_B5b_depends_on_reverse_order_raises(tmp_path: Path) -> None:
    """AC-B5b: T-001 depends_on T-002, 但 T-002 在后 → BATCH_ORDER_VIOLATION."""
    yaml_path = tmp_path / "tasks.yaml"
    _write_manifest(
        yaml_path,
        [_task_entry("T-001", deps=["T-002"]), _task_entry("T-002")],
    )
    with pytest.raises(BatchAdapterError) as exc:
        load_tasks_yaml(yaml_path)
    assert exc.value.error.code == "INVALID_MANIFEST"
    assert "BATCH_ORDER_VIOLATION" in exc.value.error.message
    assert "T-002" in exc.value.error.message


def test_AC_B5c_self_dependency_raises(tmp_path: Path) -> None:
    """AC-B5c: T-001 depends_on T-001 (自环) → INVALID_MANIFEST."""
    yaml_path = tmp_path / "tasks.yaml"
    _write_manifest(yaml_path, [_task_entry("T-001", deps=["T-001"])])
    with pytest.raises(BatchAdapterError) as exc:
        load_tasks_yaml(yaml_path)
    assert exc.value.error.code == "INVALID_MANIFEST"
    assert "itself" in exc.value.error.message.lower()


# =============================================================================
# AC-B6: CLI smoke — `suiyin-flow task batch --dry-run` 跑通
# =============================================================================


def test_AC_B6_cli_dry_run_smoke(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """AC-B6: CLI 入口 `task batch --dry-run` 输出合法 JSON, exit 0.

    用 in-process call (c2_cli.main) 而不是 subprocess, 因为:
    - 不依赖 `pip install -e .` 装好 entry point;
    - capsys 比 subprocess.run 更准 (无 shell 编码问题).
    """
    yaml_path = tmp_path / "tasks.yaml"
    _write_manifest(
        yaml_path,
        [_task_entry("T-101"), _task_entry("T-102", deps=["T-101"])],
        feature_name="smoke",
    )

    rc = c2_cli.main(
        [
            "task",
            "batch",
            "--tasks-yaml",
            str(yaml_path),
            "--repo-root",
            str(tmp_path),
            "--dry-run",
        ]
    )

    captured = capsys.readouterr()
    assert rc == 0, f"exit={rc}\nstderr={captured.err}\nstdout={captured.out}"
    data: dict[str, Any] = json.loads(captured.out)
    assert data["status"] == "dry_run"
    assert data["feature_name"] == "smoke"
    assert len(data["tasks"]) == 2
    assert [t["status"] for t in data["tasks"]] == ["dry_run", "dry_run"]


def test_AC_B6b_cli_manifest_not_found_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """AC-B6b: tasks.yaml 不存在 → exit 2 + stderr JSON error."""
    rc = c2_cli.main(
        [
            "task",
            "batch",
            "--tasks-yaml",
            str(tmp_path / "nope.yaml"),
            "--repo-root",
            str(tmp_path),
        ]
    )
    captured = capsys.readouterr()
    assert rc == 2
    err = json.loads(captured.err)
    assert err["code"] == "MANIFEST_NOT_FOUND"


def test_AC_B6c_cli_repo_root_not_found_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """AC-B6c: --repo-root 不存在 → exit 2 + stderr JSON REPO_ROOT_NOT_FOUND.

    跟 INVALID_MANIFEST / MANIFEST_NOT_FOUND 共用 BatchAdapterError 序列化路径,
    确保所有 batch error code 走同一形状 (PR #35 round-1 finding #2).
    """
    yaml_path = tmp_path / "tasks.yaml"
    _write_manifest(yaml_path, [_task_entry("T-001")])
    rc = c2_cli.main(
        [
            "task",
            "batch",
            "--tasks-yaml",
            str(yaml_path),
            "--repo-root",
            str(tmp_path / "does-not-exist"),
        ]
    )
    captured = capsys.readouterr()
    assert rc == 2
    err = json.loads(captured.err)
    assert err["code"] == "REPO_ROOT_NOT_FOUND"
    # 验证 details 字段存在 (BatchAdapterError 统一路径自带; inline dict 旧实现没有)
    assert "details" in err
    assert err["details"].get("repo_root", "").endswith("does-not-exist")


# =============================================================================
# AC-B7: integration — run_batch 真跑 (fixture_repo + mock_claude_success)
# =============================================================================
#
# 覆盖原 spec "跑通 2-3 个连续 task" 的真主路径 (round-1 finding #1 medium spec_drift).
# 跟 B2/B3a/B3b 用 monkeypatch fake_execute 不同 — 这里 execute_task 真跑:
# 真 git worktree 创建 / 真 prompt render / 假 claude script 真 subprocess
# / 真 commit / branch 兜底 (无 remote).


def test_AC_B7_real_run_batch_two_tasks_success(
    fixture_repo: Path, mock_claude_success: list[str]
) -> None:
    """AC-B7: 2 个连续 task 真走 run_batch → execute_task → success (no monkeypatch).

    评估 PR #35 mini-dogfood AC 实现: 真 batch 跑通连续 task, 每 task 都创建独立
    worktree、commit、本地分支 (NC-1 无 remote 兼容 → pr_url_or_branch = branch 名).
    """
    manifest = BatchManifest(
        schema_version=BATCH_SCHEMA_VERSION,
        feature_name="ac-b7-integration",
        tasks=[
            BatchTaskEntry(
                task_id="T-901",
                spec_ref="spec.md",
                plan_ref="plan.md",
                constitution_ref="constitution.md",
                context_seeds=["context.md"],
                verify_cmd="true",
                criticality="medium",
                ac_list=["AC-1"],
            ),
            BatchTaskEntry(
                task_id="T-902",
                spec_ref="spec.md",
                plan_ref="plan.md",
                constitution_ref="constitution.md",
                context_seeds=["context.md"],
                verify_cmd="true",
                criticality="medium",
                ac_list=["AC-1"],
                depends_on=["T-901"],
            ),
        ],
    )

    output = run_batch(
        manifest,
        repo_root=str(fixture_repo),
        claude_cmd=mock_claude_success,
    )

    assert output.status == "all_success"
    assert output.stopped_at_task_id is None
    assert [r.task_id for r in output.tasks] == ["T-901", "T-902"]
    for r in output.tasks:
        assert r.status == "success"
        assert r.output is not None
        assert r.output.status == "success"
        assert r.output.attempts == 1  # mock claude 一次过
        # 无 remote → pr_created=false, pr_url_or_branch fallback 到 branch 名
        assert r.output.pr_created is False
        assert r.output.pr_url_or_branch is not None
        assert r.output.pr_url_or_branch.startswith(("task/", "http"))
        # worktree 真创建 —— Path.match 按 path segment 比较 (跨平台: Windows
        # 上 worktree_path 是反斜杠分隔, 字面 endswith("worktrees/...") 恒 False)
        assert Path(r.output.worktree_path).match(f"worktrees/{r.task_id}")


# =============================================================================
# AC-B8: base-branch ref 可见性 precheck (P1.2.5 真闭环发现 #2)
# =============================================================================


def test_AC_B8a_uncommitted_spec_ref_fails_fast(
    fixture_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-B8a: spec_ref 不在 base_branch HEAD → run_batch 抛 INVALID_MANIFEST,
    且 execute_task 一次都不被调用 (fail-fast 在任何 session 起来之前)."""
    called = {"n": 0}

    def fake_execute(
        task_input: TaskInput, *, claude_cmd: list[str] | None = None
    ) -> TaskOutput:
        called["n"] += 1
        return _make_success_output(task_input.task_id)

    monkeypatch.setattr(batch_mod, "execute_task", fake_execute)

    manifest = BatchManifest(
        schema_version=BATCH_SCHEMA_VERSION,
        tasks=[
            BatchTaskEntry(
                task_id="T-001",
                spec_ref="not-committed.md",  # repo 里不存在
                plan_ref="plan.md",  # 已 commit
                verify_cmd="true",
                context_seeds=[],
                ac_list=[],
                base_branch="main",
            )
        ],
    )

    with pytest.raises(BatchAdapterError) as exc_info:
        run_batch(manifest, repo_root=str(fixture_repo))

    assert exc_info.value.error.code == "INVALID_MANIFEST"
    assert "not-committed.md" in exc_info.value.error.message
    assert "T-001" in exc_info.value.error.message
    assert exc_info.value.error.details["missing_refs"] == ["not-committed.md"]
    assert called["n"] == 0


def test_AC_B8b_committed_refs_pass_precheck(
    fixture_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-B8b: spec/plan 都已 commit 在 base HEAD → precheck 放行, 正常调度."""

    def fake_execute(
        task_input: TaskInput, *, claude_cmd: list[str] | None = None
    ) -> TaskOutput:
        return _make_success_output(task_input.task_id)

    monkeypatch.setattr(batch_mod, "execute_task", fake_execute)

    manifest = BatchManifest(
        schema_version=BATCH_SCHEMA_VERSION,
        tasks=[
            BatchTaskEntry(
                task_id="T-001",
                spec_ref="spec.md",
                plan_ref="plan.md",
                verify_cmd="true",
                context_seeds=[],
                ac_list=[],
                base_branch="main",
            )
        ],
    )

    output = run_batch(manifest, repo_root=str(fixture_repo))
    assert output.status == "all_success"


def test_AC_B8c_non_git_repo_root_skips_precheck(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-B8c: repo_root 非 git repo (base_branch 解析不了) → precheck 优雅跳过,
    不挡调度 (兼容单测 mock 场景; 真实坏路径由 execute_task 自己报错)."""

    def fake_execute(
        task_input: TaskInput, *, claude_cmd: list[str] | None = None
    ) -> TaskOutput:
        return _make_success_output(task_input.task_id)

    monkeypatch.setattr(batch_mod, "execute_task", fake_execute)

    manifest = _make_manifest(["T-001"])  # spec_ref="s.md" 哪都不存在
    output = run_batch(manifest, repo_root=str(tmp_path))
    assert output.status == "all_success"


def test_AC_B8d_dry_run_skips_precheck(fixture_repo: Path) -> None:
    """AC-B8d: dry-run 只解析列 task, 不跑 precheck (refs 缺失也 dry_run 成功)."""
    manifest = BatchManifest(
        schema_version=BATCH_SCHEMA_VERSION,
        tasks=[
            BatchTaskEntry(
                task_id="T-001",
                spec_ref="not-committed.md",
                plan_ref="plan.md",
                verify_cmd="true",
                context_seeds=[],
                ac_list=[],
            )
        ],
    )
    output = run_batch(manifest, repo_root=str(fixture_repo), dry_run=True)
    assert output.status == "dry_run"


def test_AC_B8e_cli_precheck_failure_exits_2(
    fixture_repo: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC-B8e: CLI 真跑撞 precheck → exit 2 + stderr 给清晰 JSON error."""
    yaml_path = tmp_path / "tasks.yaml"
    _write_manifest(
        yaml_path,
        [_task_entry("T-001", spec_ref="not-committed.md", plan_ref="plan.md")],
    )

    rc = c2_cli.main(
        [
            "task",
            "batch",
            "--tasks-yaml",
            str(yaml_path),
            "--repo-root",
            str(fixture_repo),
        ]
    )
    assert rc == 2
    captured = capsys.readouterr()
    assert "INVALID_MANIFEST" in captured.err
    assert "not-committed.md" in captured.err
