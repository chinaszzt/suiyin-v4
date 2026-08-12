"""Feature 收口 harness AC tests (gen4-plan P0-4, spec: close-harness.md §5).

真 git fixture: main + feature 分支 (含 task 产物); C5 用 mock claude;
C6 在 fixture repo 上真 ff-merge。
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any

import pytest
import yaml

from suiyin_flow.acgate.gate import content_hash
from suiyin_flow.close_harness.blocks import load_block, set_block
from suiyin_flow.close_harness.cli import main as close_main
from suiyin_flow.close_harness.harness import CloseConfig, run_close
from tests.fixtures.shell_quote import quote_for_shell

_PY = quote_for_shell(sys.executable)
FEATURE = "claude/002-demo"


def _git(repo: Path, *args: str) -> str:
    r = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True, capture_output=True, text=True, encoding="utf-8", shell=False,
    )
    return r.stdout.strip()


@pytest.fixture
def feature_repo(tmp_path: Path) -> Path:
    """main (spec/plan/constitution/冻结测试) + feature 分支 (task 实现产物)."""
    bare = tmp_path / "origin.git"
    subprocess.run(
        ["git", "init", "--bare", "-b", "main", str(bare)],
        check=True, capture_output=True, text=True, shell=False,
    )
    repo = tmp_path / "repo"
    (repo / "tests").mkdir(parents=True)
    repo.mkdir(exist_ok=True)
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "t@suiyin.local")
    _git(repo, "config", "user.name", "t")
    _git(repo, "config", "commit.gpgsign", "false")
    _git(repo, "remote", "add", "origin", str(bare))
    (repo / "spec.md").write_text("# Spec\n- AC-1\n", encoding="utf-8")
    (repo / "plan.md").write_text("# Plan\n", encoding="utf-8")
    (repo / "constitution.md").write_text("# C\n", encoding="utf-8")
    (repo / "tests" / "test_ac.py").write_text(
        "def test_AC_1_ok():\n    assert True\n", encoding="utf-8"
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "baseline")
    _git(repo, "checkout", "-q", "-b", FEATURE)
    (repo / "impl.py").write_text("VALUE = 1\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "T-001: impl")
    _git(repo, "checkout", "-q", "main")  # 主树留 main (worktree-centric 常态)
    _git(repo, "push", "-q", "-u", "origin", "main")
    _git(repo, "push", "-q", "origin", FEATURE)
    return repo


def _write_tasks(tmp_path: Path, repo: Path) -> Path:
    d = tmp_path / "specs"
    d.mkdir(exist_ok=True)
    path = d / "tasks.yaml"
    path.write_text(yaml.safe_dump({
        "schema_version": "v0.2.0",
        "feature_id": "002-demo",
        "tasks": [
            {
                "task_id": "T-001",
                "spec_ref": "spec.md",
                "plan_ref": "plan.md",
                "constitution_ref": "constitution.md",
                "verify_cmd": "true",
                "criticality": "medium",
                "base_branch": FEATURE,
            },
            {
                "task_id": "T-002",
                "spec_ref": "spec.md",
                "plan_ref": "plan.md",
                "constitution_ref": "constitution.md",
                "verify_cmd": "true",
                "criticality": "low",
                "base_branch": FEATURE,
            },
        ],
    }, allow_unicode=True), encoding="utf-8")
    return path


def _mock_claude(tmp_path: Path, verdict: str, findings: list[dict[str, Any]]) -> list[str]:
    final = {
        "verdict": verdict,
        "findings": findings,
        "reviewed_at": "2026-08-12T10:00:00Z",
        "session_id": "mock-close",
        "task_id": "002-demo",
        "pr_ref": FEATURE,
        "contract_version": "v0.3.0",
    }
    body = textwrap.dedent(
        f"""\
        import json, sys
        sys.stdin.read()
        print(json.dumps({{"type": "system", "subtype": "init"}}))
        final = {final!r}
        print(json.dumps({{"type": "result", "subtype": "success", "is_error": False,
                           "result": "done. ```json\\n" + json.dumps(final) + "\\n```"}}))
        """
    )
    script = tmp_path / f"claude_mock_{verdict}.py"
    script.write_text(body, encoding="utf-8")
    return [sys.executable, str(script)]


def _cfg(repo: Path, tasks: Path, tmp_path: Path, *, verdict: str = "approve",
         verify_cmd: str = f"{_PY} -c pass", **kw: Any) -> CloseConfig:
    findings = [] if verdict == "approve" else [{
        "severity": "high", "category": "nc_violation",
        "location": "impl.py:1", "suggested_fix": "fix it",
    }]
    return CloseConfig(
        tasks_yaml=tasks,
        repo_root=repo,
        verify_cmd=verify_cmd,
        claude_cmd=_mock_claude(tmp_path, verdict, findings),
        **kw,
    )


# =============================================================================
# AC-1: happy path — 全链过 → C6 真 ff-merge feature→main
# =============================================================================


def test_AC_1_happy_path_merges(feature_repo: Path, tmp_path: Path) -> None:
    tasks = _write_tasks(tmp_path, feature_repo)
    head_before = _git(feature_repo, "rev-parse", FEATURE)
    report = run_close(_cfg(feature_repo, tasks, tmp_path))
    assert report.verdict == "merged"
    assert report.feature_id == "002-demo"
    # main 已 ff 到 feature HEAD
    assert _git(feature_repo, "rev-parse", "main") == head_before
    # acgate/mutation 缺工件 → skipped_warning (迁移期语义)
    by_name = {s.name: s for s in report.steps}
    assert by_name["acgate"].status == "skipped_warning"
    assert by_name["mutation"].status == "skipped_warning"
    assert by_name["verify"].status == "passed"
    assert by_name["review"].status == "passed"
    assert by_name["gate"].status == "passed"
    # 落盘: versioned + latest
    d = feature_repo / ".suiyin" / "close"
    assert (d / "latest-002-demo.json").exists()


# =============================================================================
# AC-2: 本地 human:block → blocked, 零后续步骤
# =============================================================================


def test_AC_2_local_block_stops_everything(feature_repo: Path, tmp_path: Path) -> None:
    tasks = _write_tasks(tmp_path, feature_repo)
    set_block(feature_repo, "002-demo", reason="等人工确认数据迁移")
    report = run_close(_cfg(feature_repo, tasks, tmp_path))
    assert report.verdict == "blocked"
    assert report.held_at == "human_block"
    by_name = {s.name: s for s in report.steps}
    assert by_name["verify"].status == "not_reached"
    assert by_name["gate"].status == "not_reached"
    # main 未动
    assert _git(feature_repo, "rev-parse", "main") != _git(feature_repo, "rev-parse", FEATURE)


# =============================================================================
# AC-3: verify 红 → held at verify, review 不起 session (fail-closed 顺序)
# =============================================================================


def test_AC_3_verify_fail_holds_before_review(feature_repo: Path, tmp_path: Path) -> None:
    tasks = _write_tasks(tmp_path, feature_repo)
    report = run_close(_cfg(
        feature_repo, tasks, tmp_path,
        verify_cmd=f'{_PY} -c "raise SystemExit(1)"',
    ))
    assert report.verdict == "held"
    assert report.held_at == "verify"
    by_name = {s.name: s for s in report.steps}
    assert by_name["review"].status == "not_reached"
    assert by_name["verify"].report_path is not None  # 失败 report 也落盘 (audit)


# =============================================================================
# AC-4: review block → held at review, gate 不跑
# =============================================================================


def test_AC_4_review_block_holds(feature_repo: Path, tmp_path: Path) -> None:
    tasks = _write_tasks(tmp_path, feature_repo)
    report = run_close(_cfg(feature_repo, tasks, tmp_path, verdict="block"))
    assert report.verdict == "held"
    assert report.held_at == "review"
    assert {s.name: s for s in report.steps}["gate"].status == "not_reached"
    assert _git(feature_repo, "rev-parse", "main") != _git(feature_repo, "rev-parse", FEATURE)


# =============================================================================
# AC-5: acgate 拦 (feature 弱化冻结测试且 spec 未变) → held, verify 不跑
# =============================================================================


def test_AC_5_acgate_blocks_weakened_frozen_test(
    feature_repo: Path, tmp_path: Path
) -> None:
    tasks = _write_tasks(tmp_path, feature_repo)
    # feature 分支上删断言 (spec 未变)
    _git(feature_repo, "checkout", "-q", FEATURE)
    (feature_repo / "tests" / "test_ac.py").write_text(
        "def test_AC_1_ok():\n    pass\n", encoding="utf-8"
    )
    _git(feature_repo, "add", "-A")
    _git(feature_repo, "commit", "-m", "weaken frozen test")
    _git(feature_repo, "checkout", "-q", "main")
    # ac-manifest 与 tasks.yaml 同目录 (基准 = main 侧内容)
    spec_b = _git(feature_repo, "show", "main:spec.md")
    test_b = _git(feature_repo, "show", "main:tests/test_ac.py")
    (tasks.parent / "ac-manifest.yaml").write_text(yaml.safe_dump({
        "schema_version": "v0.1.0",
        "feature_id": "002-demo",
        "entries": [{
            "ac_id": "AC-1", "kind": "behavior",
            "spec_ref": "spec.md",
            "spec_hash": content_hash((spec_b + "\n").encode()),
            "test_ref": "tests/test_ac.py",
            "test_hash": content_hash((test_b + "\n").encode()),
            "test_names": [], "baseline_ref": "main",
        }],
    }, allow_unicode=True), encoding="utf-8")
    report = run_close(_cfg(feature_repo, tasks, tmp_path))
    assert report.verdict == "held"
    assert report.held_at == "acgate"
    assert {s.name: s for s in report.steps}["verify"].status == "not_reached"


# =============================================================================
# AC-6: mutation 触发键 — 未命中 skipped; 命中且 survivor → held
# =============================================================================


def test_AC_6_mutation_trigger_key(feature_repo: Path, tmp_path: Path) -> None:
    tasks = _write_tasks(tmp_path, feature_repo)
    (tasks.parent / "mutants.yaml").write_text(yaml.safe_dump({
        "schema_version": "v0.1.0",
        "feature_id": "002-demo",
        "default_test_cmd": f"{_PY} -c pass",  # 空心杀手: 永绿
        "mutants": [{
            "mutant_id": "M-x", "mutant_class": "tag_rename",
            "target_file": "impl.py",
            "match": "VALUE = 1", "replacement": "VALUE = 2",
        }],
    }, allow_unicode=True), encoding="utf-8")

    # 命中: impl.py (被测面) 在 feature diff 里 → 探针跑 → survivor → held
    report = run_close(_cfg(feature_repo, tasks, tmp_path))
    assert report.verdict == "held"
    assert report.held_at == "mutation"
    assert "survived=1" in {s.name: s for s in report.steps}["mutation"].detail


def test_AC_6b_mutation_not_triggered_skips(feature_repo: Path, tmp_path: Path) -> None:
    tasks = _write_tasks(tmp_path, feature_repo)
    (tasks.parent / "mutants.yaml").write_text(yaml.safe_dump({
        "schema_version": "v0.1.0",
        "feature_id": "002-demo",
        "default_test_cmd": f"{_PY} -c pass",
        "mutants": [{
            "mutant_id": "M-x", "mutant_class": "tag_rename",
            "target_file": "other.py",  # 与 feature diff (impl.py) 无交集
            "match": "x", "replacement": "y",
        }],
    }, allow_unicode=True), encoding="utf-8")
    report = run_close(_cfg(feature_repo, tasks, tmp_path))
    assert report.verdict == "merged"
    assert {s.name: s for s in report.steps}["mutation"].status == "skipped"


# =============================================================================
# AC-7: block/unblock/status CLI + history
# =============================================================================


def test_AC_7_block_cli_lifecycle(feature_repo: Path) -> None:
    rc = close_main([
        "close", "block", "--feature", "002-demo",
        "--repo-root", str(feature_repo), "--reason", "hold it",
    ])
    assert rc == 0
    assert load_block(feature_repo, "002-demo").blocked is True

    rc = close_main([
        "close", "unblock", "--feature", "002-demo",
        "--repo-root", str(feature_repo),
    ])
    assert rc == 0
    state = load_block(feature_repo, "002-demo")
    assert state.blocked is False
    assert [e.action for e in state.history] == ["block", "unblock"]

    rc = close_main([
        "close", "status", "--feature", "002-demo",
        "--repo-root", str(feature_repo),
    ])
    assert rc == 0


# =============================================================================
# AC-8: gate dry-run — 全链过但不真 merge
# =============================================================================


def test_AC_8_gate_dry_run_does_not_merge(feature_repo: Path, tmp_path: Path) -> None:
    tasks = _write_tasks(tmp_path, feature_repo)
    main_before = _git(feature_repo, "rev-parse", "main")
    report = run_close(_cfg(feature_repo, tasks, tmp_path, gate_dry_run=True))
    assert report.verdict == "merged"  # 评估通过 (dry-run 标记在 detail)
    assert "[dry-run]" in {s.name: s for s in report.steps}["gate"].detail
    assert _git(feature_repo, "rev-parse", "main") == main_before
