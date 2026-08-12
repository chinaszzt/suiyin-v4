"""P0-1 canonical identity AC tests (gen4-plan §三 P0-1).

覆盖:
- AC-ID1: T-001B 回归靶 — 002·T001 沙盒实验被旧 pattern 拒收的 id 转正
- AC-ID2 (失败型): 非法 id 仍拒 (空格 / 斜杠 / 空串 / 超长)
- AC-ID3: v0.1.0 manifest 兼容读 + feature_id 派生链
- AC-ID4: v0.2.0 manifest 显式 feature_id 优先
- AC-ID5 (失败型): tasks.yaml 未提交 / 与 base HEAD 漂移 → INVALID_MANIFEST
- AC-ID6: manifest 在 repo 外 → 警告 + 放行 (不误伤手写实验工件)
- AC-ID7: 五落点键一致性 (worktree / branch / state 键 / review 键同源)
- AC-ID8: TaskInput.feature_id 缺省从 base_branch 派生
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from suiyin_flow.c2_executor.batch import (
    BatchAdapterError,
    BatchManifest,
    BatchTaskEntry,
    load_tasks_yaml,
    precheck_refs_on_base,
    resolve_feature_id,
)
from suiyin_flow.c2_executor.schema import TaskInput
from suiyin_flow.c2_executor.worktree import worktree_branch_name, worktree_path_for
from suiyin_flow.c5_reviewer.contract import ReviewInput
from suiyin_flow.identity import (
    derive_feature_id,
    is_valid_local_id,
    review_key,
    safe_ref,
    task_branch,
)


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(cwd), *args],
        check=True, capture_output=True, text=True, encoding="utf-8", shell=False,
    )


@pytest.fixture
def id_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "t@suiyin.local")
    _git(repo, "config", "user.name", "t")
    _git(repo, "config", "commit.gpgsign", "false")
    (repo / "spec.md").write_text("# Spec\n", encoding="utf-8")
    (repo / "plan.md").write_text("# Plan\n", encoding="utf-8")
    (repo / "constitution.md").write_text("# C\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "initial")
    return repo


def _entry(task_id: str = "T-001") -> dict[str, object]:
    return {
        "task_id": task_id,
        "spec_ref": "spec.md",
        "plan_ref": "plan.md",
        "constitution_ref": "constitution.md",
        "verify_cmd": "true",
    }


def _task_input(task_id: str = "T-001", **kw: object) -> TaskInput:
    return TaskInput.model_validate({
        "task_id": task_id,
        "spec_ref": "spec.md",
        "plan_ref": "plan.md",
        "context_seeds": [],
        "verify_cmd": "true",
        "criticality": "medium",
        "repo_root": "/tmp/x",
        **kw,
    })


# =============================================================================
# AC-ID1: T-001B 回归靶 (002·T001 实验拒收案例转正)
# =============================================================================


def test_AC_ID1_t001b_accepted_everywhere() -> None:
    """沙盒实验里 'T-001B' 被 ^T-\\d{3,}$ 拒收 → 新 LOCAL_ID_PATTERN 下三处 schema 全放行."""
    assert _task_input("T-001B").task_id == "T-001B"
    entry = BatchTaskEntry.model_validate(_entry("T-001B"))
    assert entry.task_id == "T-001B"
    review = ReviewInput.model_validate({
        "pr_ref": "task/f/T-001B",
        "spec_ref": "spec.md",
        "plan_ref": "plan.md",
        "task_id": "T-001B",
        "criticality": "medium",
        "repo_root": "/tmp/x",
    })
    assert review.task_id == "T-001B"


# =============================================================================
# AC-ID2 (失败型): 非法 id 仍被拒
# =============================================================================


@pytest.mark.parametrize("bad_id", ["", "T 001", "a/b", "-lead", "x" * 65])
def test_AC_ID2_invalid_ids_rejected(bad_id: str) -> None:
    with pytest.raises(ValidationError):
        _task_input(bad_id)
    with pytest.raises(ValidationError):
        BatchTaskEntry.model_validate(_entry(bad_id))
    assert not is_valid_local_id(bad_id)


# =============================================================================
# AC-ID3 / AC-ID4: manifest 兼容读 + feature_id 解析链
# =============================================================================


def test_AC_ID3_v010_manifest_loads_and_derives(tmp_path: Path) -> None:
    """v0.1.0 manifest (r3/r4 工件形态) 仍可加载; feature_id 从 feature_name 派生."""
    path = tmp_path / "tasks.yaml"
    path.write_text(
        yaml.safe_dump({
            "schema_version": "v0.1.0",
            "feature_name": "003-login-core",
            "tasks": [_entry()],
        }),
        encoding="utf-8",
    )
    manifest = load_tasks_yaml(path)
    assert manifest.feature_id is None
    assert resolve_feature_id(manifest) == "003-login-core"


def test_AC_ID3b_derivation_falls_back_to_base_branch() -> None:
    """feature_name 缺失 → 从 base_branch 派生 (safe_ref 转义)."""
    manifest = BatchManifest.model_validate({
        "schema_version": "v0.1.0",
        "tasks": [{**_entry(), "base_branch": "claude/login-core-r4"}],
    })
    assert resolve_feature_id(manifest) == "claude-login-core-r4"


def test_AC_ID4_explicit_feature_id_wins() -> None:
    manifest = BatchManifest.model_validate({
        "schema_version": "v0.2.0",
        "feature_id": "002-desk-engine",
        "feature_name": "ignored-when-explicit",
        "tasks": [_entry()],
    })
    assert resolve_feature_id(manifest) == "002-desk-engine"


def test_AC_ID4b_unknown_schema_version_rejected(tmp_path: Path) -> None:
    """失败型: v0.3.0 (未来版本) 拒收, 不静默降级."""
    path = tmp_path / "tasks.yaml"
    path.write_text(
        yaml.safe_dump({"schema_version": "v0.3.0", "tasks": [_entry()]}),
        encoding="utf-8",
    )
    with pytest.raises(BatchAdapterError) as exc:
        load_tasks_yaml(path)
    assert exc.value.error.code == "INVALID_MANIFEST"


# =============================================================================
# AC-ID5 (失败型): manifest 基线一致性 (precheck v2)
# =============================================================================


def _manifest_for(repo: Path, rel: str = "tasks.yaml") -> tuple[BatchManifest, Path]:
    path = repo / rel
    path.write_text(
        yaml.safe_dump({
            "schema_version": "v0.2.0",
            "feature_id": "001-x",
            "tasks": [_entry()],
        }),
        encoding="utf-8",
    )
    return load_tasks_yaml(path), path


def test_AC_ID5_uncommitted_manifest_fails(id_repo: Path) -> None:
    manifest, path = _manifest_for(id_repo)
    with pytest.raises(BatchAdapterError) as exc:
        precheck_refs_on_base(manifest, str(id_repo), path)
    assert exc.value.error.code == "INVALID_MANIFEST"
    assert "not committed" in exc.value.error.message


def test_AC_ID5b_drifted_manifest_fails(id_repo: Path) -> None:
    """commit 后盘上再改 (模拟 C1 写回 execution_plan 忘 commit) → 漂移拒."""
    manifest, path = _manifest_for(id_repo)
    _git(id_repo, "add", "tasks.yaml")
    _git(id_repo, "commit", "-m", "tasks.yaml")
    precheck_refs_on_base(manifest, str(id_repo), path)  # 一致 → 放行

    path.write_text(path.read_text(encoding="utf-8") + "\n# drift\n", encoding="utf-8")
    with pytest.raises(BatchAdapterError) as exc:
        precheck_refs_on_base(manifest, str(id_repo), path)
    assert exc.value.error.code == "INVALID_MANIFEST"
    assert "differs" in exc.value.error.message


def test_AC_ID6_manifest_outside_repo_warns_and_passes(
    id_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    outside = id_repo.parent / "tasks.yaml"
    outside.write_text(
        yaml.safe_dump({
            "schema_version": "v0.2.0",
            "feature_id": "001-x",
            "tasks": [_entry()],
        }),
        encoding="utf-8",
    )
    manifest = load_tasks_yaml(outside)
    precheck_refs_on_base(manifest, str(id_repo), outside)  # 不抛
    assert "outside repo_root" in capsys.readouterr().err


# =============================================================================
# AC-ID7 / AC-ID8: 键一致性 + 派生
# =============================================================================


def test_AC_ID7_key_consistency(tmp_path: Path) -> None:
    """worktree / branch / review 键从同一 canonical key 出, 互相可推."""
    fid, tid = "002-desk", "T-001B"
    wt = worktree_path_for(tmp_path, fid, tid)
    assert wt == (tmp_path / "worktrees" / fid / tid).resolve()
    assert worktree_branch_name(fid, tid) == task_branch(fid, tid) == "task/002-desk/T-001B"
    assert review_key(fid, tid) == "002-desk-T-001B"
    assert review_key(None, tid) == "T-001B"
    # state 键 = safe_ref(feature_id) (C7 落盘文件名用)
    assert safe_ref(fid) == "002-desk"
    assert safe_ref("claude/x y") == "claude-x-y"


def test_AC_ID8_taskinput_feature_id_derived() -> None:
    ti = _task_input(base_branch="claude/login-core-r4")
    assert ti.feature_id == "claude-login-core-r4"
    ti2 = _task_input(feature_id="004-explicit")
    assert ti2.feature_id == "004-explicit"
    assert derive_feature_id(None, "main") == "main"
