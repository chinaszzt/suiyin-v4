"""Mutation 探针 AC tests (gen4-plan P0-3, spec: mutation-probe.md §5).

真 git fixture: 一个含"实心测试 + 空心测试"的微型 python 项目。
杀手测试命令用本 venv python 直跑 (跨平台, 不依赖 pytest 装进 fixture)。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from suiyin_flow.mutation.cli import main as mutation_main
from suiyin_flow.mutation.runner import run_probe
from suiyin_flow.mutation.schema import MutationError, ProbeReport
from tests.fixtures.shell_quote import quote_for_shell

_PY = quote_for_shell(sys.executable)

# app.py: audit() 返回带 tag 字段的 dict — mutant 模拟 desk 五类缺陷的两种
APP = '''TAG = "audit.v1"


def audit(user):
    return {"tag": TAG, "user": user, "checked": True}
'''

# 实心测试: 断言 tag 具体值 + checked 字段 → mutant 注入必红
SOLID_TEST = '''import app


def run():
    r = app.audit("u1")
    assert r["tag"] == "audit.v1", r
    assert r["checked"] is True, r


if __name__ == "__main__":
    run()
    print("OK")
'''

# 空心测试: 只断言"有返回" → tag 改名/字段缺失都仍绿 (E4 五处空心的形态)
HOLLOW_TEST = '''import app


def run():
    r = app.audit("u1")
    assert r is not None


if __name__ == "__main__":
    run()
    print("OK")
'''


def _git(repo: Path, *args: str) -> str:
    r = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True, capture_output=True, text=True, encoding="utf-8", shell=False,
    )
    return r.stdout.strip()


def _make_repo(tmp_path: Path, *, hollow: bool) -> Path:
    repo = tmp_path / ("repo-hollow" if hollow else "repo-solid")
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "t@suiyin.local")
    _git(repo, "config", "user.name", "t")
    _git(repo, "config", "commit.gpgsign", "false")
    (repo / "app.py").write_text(APP, encoding="utf-8")
    (repo / "test_app.py").write_text(
        HOLLOW_TEST if hollow else SOLID_TEST, encoding="utf-8"
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "baseline")
    return repo


def _write_catalog(tmp_path: Path, name: str = "mutants.yaml", **overrides: object) -> Path:
    data: dict[str, object] = {
        "schema_version": "v0.1.0",
        "feature_id": "001-audit",
        "default_test_cmd": f"{_PY} test_app.py",
        "mutants": [
            {
                "mutant_id": "M-tag-rename",
                "mutant_class": "tag_rename",
                "target_file": "app.py",
                "match": 'TAG = "audit.v1"',
                "replacement": 'TAG = "audit.v2"',
                "description": "tag 改名仍绿 = 空心",
            },
            {
                "mutant_id": "M-field-drop",
                "mutant_class": "assert_field_drop",
                "target_file": "app.py",
                "match": '"checked": True',
                "replacement": '"checked": False',
                "description": "审计断言字段翻转",
            },
        ],
    }
    data.update(overrides)
    path = tmp_path / name
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return path


def _probe(repo: Path, catalog: Path) -> ProbeReport:
    return run_probe(repo_root=repo, catalog_path=catalog, ref="main")


# =============================================================================
# AC-1: 实心测试杀光全部 mutant → pass
# =============================================================================


def test_AC_1_solid_tests_kill_all_mutants(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path, hollow=False)
    catalog = _write_catalog(tmp_path)
    report = _probe(repo, catalog)
    assert report.verdict == "pass"
    assert report.killed_count == 2 and report.survived_count == 0
    assert all(r.outcome == "killed" for r in report.results)


# =============================================================================
# AC-2: 空心测试放跑 mutant → fail + 逐个点名 (探针核心捕获目标)
# =============================================================================


def test_AC_2_hollow_tests_let_mutants_survive(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path, hollow=True)
    catalog = _write_catalog(tmp_path)
    report = _probe(repo, catalog)
    assert report.verdict == "fail"
    assert report.survived_count == 2
    survivors = {r.mutant_id for r in report.results if r.outcome == "survived"}
    assert survivors == {"M-tag-rename", "M-field-drop"}


# =============================================================================
# AC-3: 原 worktree 全程零接触 (byte-identical)
# =============================================================================


def test_AC_3_original_tree_untouched(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path, hollow=False)
    catalog = _write_catalog(tmp_path)
    before_app = (repo / "app.py").read_bytes()
    before_status = _git(repo, "status", "--porcelain")
    _probe(repo, catalog)
    assert (repo / "app.py").read_bytes() == before_app
    assert _git(repo, "status", "--porcelain") == before_status
    # throwaway 全部清理
    wt_dir = repo / ".suiyin" / "mutation-wt"
    assert not wt_dir.exists() or not any(wt_dir.iterdir())


# =============================================================================
# AC-4 (失败型): match 失配 = catalog stale → apply_failed → fail
# =============================================================================


def test_AC_4_stale_catalog_apply_failed(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path, hollow=False)
    catalog = _write_catalog(
        tmp_path,
        mutants=[{
            "mutant_id": "M-stale",
            "mutant_class": "tag_rename",
            "target_file": "app.py",
            "match": "NO_SUCH_TEXT_ANYWHERE",
            "replacement": "x",
        }],
    )
    report = _probe(repo, catalog)
    assert report.verdict == "fail"
    assert report.results[0].outcome == "apply_failed"
    assert "catalog stale" in report.results[0].output_tail


def test_AC_4b_missing_target_apply_failed(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path, hollow=False)
    catalog = _write_catalog(
        tmp_path,
        mutants=[{
            "mutant_id": "M-missing",
            "mutant_class": "tag_rename",
            "target_file": "nonexistent.py",
            "match": "x",
            "replacement": "y",
        }],
    )
    report = _probe(repo, catalog)
    assert report.verdict == "fail"
    assert report.results[0].outcome == "apply_failed"


# =============================================================================
# AC-5 (失败型): 无效 catalog — 空 mutants / match==replacement / 未知版本
# =============================================================================


def test_AC_5_invalid_catalogs_rejected(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path, hollow=False)
    cases: list[dict[str, object]] = [
        {"mutants": []},
        {"mutants": [{
            "mutant_id": "M-noop", "mutant_class": "x", "target_file": "app.py",
            "match": "same", "replacement": "same",
        }]},
        {"schema_version": "v9.9.9"},
    ]
    for overrides in cases:
        catalog = _write_catalog(tmp_path, name=f"c-{len(str(overrides))}.yaml", **overrides)
        with pytest.raises(MutationError) as exc:
            _probe(repo, catalog)
        assert exc.value.code == "INVALID_CATALOG"


# =============================================================================
# AC-6: occurrence 定位第 N 处 (确定性)
# =============================================================================


def test_AC_6_occurrence_targets_nth_match(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path, hollow=False)
    (repo / "app.py").write_text(APP + '\nEXTRA = "audit.v1"\n', encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "add EXTRA")
    catalog = _write_catalog(
        tmp_path,
        mutants=[{
            "mutant_id": "M-second",
            "mutant_class": "tag_rename",
            "target_file": "app.py",
            "match": '"audit.v1"',
            "replacement": '"audit.v2"',
            "occurrence": 2,   # 只动 EXTRA 那处 → 测试仍绿 → survived
        }],
    )
    report = _probe(repo, catalog)
    assert report.results[0].outcome == "survived"  # 第 2 处与断言无关


# =============================================================================
# AC-7: per-mutant test_cmd 覆盖默认 + env 注入
# =============================================================================


def test_AC_7_per_mutant_cmd_and_env(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path, hollow=False)
    (repo / "test_env.py").write_text(
        'import os\nassert os.environ.get("LANE") == "mut-1", os.environ.get("LANE")\n'
        'print("ENV OK")\n',
        encoding="utf-8",
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "env test")
    catalog = _write_catalog(
        tmp_path,
        mutants=[{
            "mutant_id": "M-env",
            "mutant_class": "tag_rename",
            "target_file": "app.py",
            "match": 'TAG = "audit.v1"',
            "replacement": 'TAG = "audit.v2"',
            "test_cmd": f"{_PY} test_env.py && {_PY} test_app.py",
        }],
    )
    report = run_probe(
        repo_root=repo, catalog_path=catalog, ref="main",
        env_extra={"LANE": "mut-1"},
    )
    # env 注入生效 (test_env 过) + 复合命令 && 生效 + 实心测试杀掉 mutant
    assert report.results[0].outcome == "killed"


# =============================================================================
# AC-8: CLI smoke (exit code 契约 + --env 解析)
# =============================================================================


def test_AC_8_cli_exit_codes(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path, hollow=False)
    catalog = _write_catalog(tmp_path)
    rc = mutation_main([
        "mutation", "run", "--catalog", str(catalog),
        "--repo-root", str(repo), "--ref", "main",
    ])
    assert rc == 0

    hollow = _make_repo(tmp_path, hollow=True)
    rc_fail = mutation_main([
        "mutation", "run", "--catalog", str(catalog),
        "--repo-root", str(hollow), "--ref", "main",
    ])
    assert rc_fail == 1

    rc_err = mutation_main([
        "mutation", "run", "--catalog", str(tmp_path / "none.yaml"),
        "--repo-root", str(repo), "--ref", "main",
    ])
    assert rc_err == 2

    rc_badenv = mutation_main([
        "mutation", "run", "--catalog", str(catalog),
        "--repo-root", str(repo), "--ref", "main", "--env", "NOEQUALS",
    ])
    assert rc_badenv == 2
