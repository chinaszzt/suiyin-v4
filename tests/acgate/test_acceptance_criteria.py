"""AC 冻结闸 AC tests (gen4-plan P0-2, spec: ac-freeze-gate.md §5).

真 git fixture: main 分支冻结基线, task 分支做各类变更, gate 判 base...head。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

from suiyin_flow.acgate.cli import main as acgate_main
from suiyin_flow.acgate.gate import content_hash, freeze_manifest, run_gate
from suiyin_flow.acgate.schema import AcGateError

TEST_FILE = "tests/test_ac.py"
GUARD_FILE = "tests/test_guard.py"

TEST_BODY = '''"""frozen AC tests."""


def test_AC_1_login_ok():
    assert 1 + 1 == 2
    assert "token" in {"token": "x"}


def test_AC_2_login_reject():
    assert 2 * 2 == 4


def test_impl_scaffold():
    assert True
'''

GUARD_BODY = '''"""frozen guard tests."""


def test_GUARD_1_no_prod_db():
    assert "27017" not in "mongodb://localhost:27018"
'''


def _git(repo: Path, *args: str) -> str:
    r = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True, capture_output=True, text=True, encoding="utf-8", shell=False,
    )
    return r.stdout.strip()


@pytest.fixture
def frozen_repo(tmp_path: Path) -> Path:
    """main 分支: spec/plan/两份冻结测试已提交; task 分支已创建 (等各测试改)."""
    repo = tmp_path / "repo"
    (repo / "tests").mkdir(parents=True)
    _git_init(repo)
    (repo / "spec.md").write_text("# Spec\n- AC-1 login ok\n- AC-2 reject\n", encoding="utf-8")
    (repo / "plan.md").write_text("# Plan\n- GUARD-1 no prod db\n", encoding="utf-8")
    (repo / TEST_FILE).write_text(TEST_BODY, encoding="utf-8")
    (repo / GUARD_FILE).write_text(GUARD_BODY, encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "frozen baseline")
    _git(repo, "checkout", "-q", "-b", "task1")
    return repo


def _git_init(repo: Path) -> None:
    repo.mkdir(exist_ok=True)
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "t@suiyin.local")
    _git(repo, "config", "user.name", "t")
    _git(repo, "config", "commit.gpgsign", "false")


def _write_manifest(repo: Path, tmp_path: Path) -> Path:
    entries = [
        {
            "ac_id": "AC-1",
            "kind": "behavior",
            "spec_ref": "spec.md",
            "spec_hash": content_hash((repo / "spec.md").read_bytes()),
            "test_ref": TEST_FILE,
            "test_hash": content_hash((repo / TEST_FILE).read_bytes()),
            "test_names": ["test_AC_1_login_ok"],
            "baseline_ref": "main",
        },
        {
            "ac_id": "AC-2",
            "kind": "behavior",
            "spec_ref": "spec.md",
            "spec_hash": content_hash((repo / "spec.md").read_bytes()),
            "test_ref": TEST_FILE,
            "test_hash": content_hash((repo / TEST_FILE).read_bytes()),
            "test_names": ["test_AC_2_login_reject"],
            "baseline_ref": "main",
        },
        {
            "ac_id": "GUARD-1",
            "kind": "guard",
            "spec_ref": "plan.md",
            "spec_hash": content_hash((repo / "plan.md").read_bytes()),
            "test_ref": GUARD_FILE,
            "test_hash": content_hash((repo / GUARD_FILE).read_bytes()),
            "test_names": [],
            "baseline_ref": "main",
        },
    ]
    path = tmp_path / "ac-manifest.yaml"
    path.write_text(
        yaml.safe_dump(
            {"schema_version": "v0.1.0", "feature_id": "001-login", "entries": entries},
            allow_unicode=True, sort_keys=False,
        ),
        encoding="utf-8",
    )
    return path


def _commit_all(repo: Path, msg: str) -> None:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", msg)


def _run(repo: Path, manifest: Path):
    return run_gate(
        repo_root=repo, manifest_path=manifest, base_ref="main", head_ref="task1"
    )


# =============================================================================
# AC-1: 冻结完好 → pass
# =============================================================================


def test_AC_1_untouched_frozen_tests_pass(frozen_repo: Path, tmp_path: Path) -> None:
    manifest = _write_manifest(frozen_repo, tmp_path)
    (frozen_repo / "src.py").write_text("x = 1\n", encoding="utf-8")
    _commit_all(frozen_repo, "impl only")
    report = _run(frozen_repo, manifest)
    assert report.verdict == "pass"
    assert report.findings == []


# =============================================================================
# AC-2/3/4/5: 闭集四类 → block (失败型)
# =============================================================================


def test_AC_2_deleted_test_file_blocks(frozen_repo: Path, tmp_path: Path) -> None:
    manifest = _write_manifest(frozen_repo, tmp_path)
    (frozen_repo / TEST_FILE).unlink()
    _commit_all(frozen_repo, "delete frozen tests")
    report = _run(frozen_repo, manifest)
    assert report.verdict == "block"
    assert any(f.kind == "TEST_FILE_DELETED" and f.blocking for f in report.findings)


def test_AC_3_renamed_test_def_blocks(frozen_repo: Path, tmp_path: Path) -> None:
    """冻结测试函数改名 (旧 def 删 + 新名加) → TEST_DELETED."""
    manifest = _write_manifest(frozen_repo, tmp_path)
    body = (frozen_repo / TEST_FILE).read_text(encoding="utf-8")
    (frozen_repo / TEST_FILE).write_text(
        body.replace("def test_AC_1_login_ok", "def test_AC_1_renamed"),
        encoding="utf-8",
    )
    _commit_all(frozen_repo, "rename frozen test")
    report = _run(frozen_repo, manifest)
    assert report.verdict == "block"
    kinds = {f.kind for f in report.findings}
    assert "TEST_DELETED" in kinds


def test_AC_4_skip_marker_blocks(frozen_repo: Path, tmp_path: Path) -> None:
    manifest = _write_manifest(frozen_repo, tmp_path)
    body = (frozen_repo / TEST_FILE).read_text(encoding="utf-8")
    (frozen_repo / TEST_FILE).write_text(
        "import pytest\n" + body.replace(
            "def test_AC_1_login_ok():",
            "@pytest.mark.skip(reason='flaky')\ndef test_AC_1_login_ok():",
        ),
        encoding="utf-8",
    )
    _commit_all(frozen_repo, "skip frozen test")
    report = _run(frozen_repo, manifest)
    assert report.verdict == "block"
    assert any(f.kind == "TEST_SKIPPED" for f in report.findings)


def test_AC_5_weakened_assert_blocks_as_unknown(
    frozen_repo: Path, tmp_path: Path
) -> None:
    """删断言行 (spec 未变) → 闭集归不了类 → UNKNOWN 同样不放行 (fail-closed 灵魂)."""
    manifest = _write_manifest(frozen_repo, tmp_path)
    body = (frozen_repo / TEST_FILE).read_text(encoding="utf-8")
    (frozen_repo / TEST_FILE).write_text(
        body.replace('    assert "token" in {"token": "x"}\n', ""),
        encoding="utf-8",
    )
    _commit_all(frozen_repo, "weaken assert")
    report = _run(frozen_repo, manifest)
    assert report.verdict == "block"
    assert any(f.kind == "TEST_WEAKENED_UNKNOWN" and f.blocking for f in report.findings)


# =============================================================================
# AC-6: 纯新增 = 加强 → pass
# =============================================================================


def test_AC_6_pure_addition_passes(frozen_repo: Path, tmp_path: Path) -> None:
    manifest = _write_manifest(frozen_repo, tmp_path)
    with (frozen_repo / TEST_FILE).open("a", encoding="utf-8") as f:
        f.write("\n\ndef test_AC_1_extra_case():\n    assert 3 > 2\n")
    _commit_all(frozen_repo, "add test case")
    report = _run(frozen_repo, manifest)
    assert report.verdict == "pass"


# =============================================================================
# AC-7/8: 合法通道 → 放行 (finding 留 audit, blocking=False)
# =============================================================================


def test_AC_7_spec_changed_channel_passes(frozen_repo: Path, tmp_path: Path) -> None:
    """Type B/C: spec 同 diff 变更 → 弱化 finding 非 blocking."""
    manifest = _write_manifest(frozen_repo, tmp_path)
    (frozen_repo / "spec.md").write_text(
        "# Spec v2\n- AC-1 login ok (revised)\n- AC-2 reject\n", encoding="utf-8"
    )
    body = (frozen_repo / TEST_FILE).read_text(encoding="utf-8")
    (frozen_repo / TEST_FILE).write_text(
        body.replace('    assert "token" in {"token": "x"}\n', ""),
        encoding="utf-8",
    )
    _commit_all(frozen_repo, "revise spec + test together")
    report = _run(frozen_repo, manifest)
    assert report.verdict == "pass"
    assert any(
        f.channel == "spec_changed" and not f.blocking for f in report.findings
    )


def test_AC_8_projection_fix_channel_passes(frozen_repo: Path, tmp_path: Path) -> None:
    """spec 未变但附 projection-fixes/<ac_id>* 新旧 oracle 证据 → 放行."""
    manifest = _write_manifest(frozen_repo, tmp_path)
    ev = frozen_repo / ".specify" / "projection-fixes"
    ev.mkdir(parents=True)
    (ev / "AC-1-oracle.md").write_text(
        "# 旧 oracle 断言错译, 新 oracle 对齐 spec 原文\n", encoding="utf-8"
    )
    body = (frozen_repo / TEST_FILE).read_text(encoding="utf-8")
    (frozen_repo / TEST_FILE).write_text(
        body.replace('    assert "token" in {"token": "x"}\n',
                     '    assert {"token": "x"}["token"] == "x"\n'),
        encoding="utf-8",
    )
    _commit_all(frozen_repo, "projection fix with oracle evidence")
    report = _run(frozen_repo, manifest)
    assert report.verdict == "pass"
    assert any(f.channel == "projection_fix" for f in report.findings)


# =============================================================================
# AC-9: manifest 基准漂移 → 恒 block (spec_changed 不豁免)
# =============================================================================


def test_AC_9_stale_manifest_blocks_even_with_spec_change(
    frozen_repo: Path, tmp_path: Path
) -> None:
    manifest_path = _write_manifest(frozen_repo, tmp_path)
    data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    data["entries"][0]["test_hash"] = "0" * 64  # 人为漂移
    manifest_path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    (frozen_repo / "spec.md").write_text("# Spec v2\n", encoding="utf-8")
    _commit_all(frozen_repo, "spec change")
    report = _run(frozen_repo, manifest_path)
    assert report.verdict == "block"
    assert any(f.kind == "MANIFEST_STALE" and f.blocking for f in report.findings)


# =============================================================================
# AC-10: freeze 刷新 hash → gate 恢复可用
# =============================================================================


def test_AC_10_freeze_refreshes_hashes(frozen_repo: Path, tmp_path: Path) -> None:
    manifest_path = _write_manifest(frozen_repo, tmp_path)
    data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    data["entries"][0]["test_hash"] = "0" * 64
    data["entries"][0]["spec_hash"] = "0" * 64
    manifest_path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    freeze_manifest(repo_root=frozen_repo, manifest_path=manifest_path, ref="main")
    report = _run(frozen_repo, manifest_path)  # task1 == main 内容 → pass
    assert report.verdict == "pass"
    refreshed = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    assert refreshed["entries"][0]["test_hash"] != "0" * 64
    assert refreshed["entries"][0]["baseline_ref"] == "main"


def test_AC_10b_freeze_missing_ref_fails(frozen_repo: Path, tmp_path: Path) -> None:
    """失败型: manifest 指向 ref 上不存在的文件 → INVALID_MANIFEST."""
    manifest_path = _write_manifest(frozen_repo, tmp_path)
    data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    data["entries"][0]["test_ref"] = "tests/nonexistent.py"
    manifest_path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    with pytest.raises(AcGateError) as exc:
        freeze_manifest(repo_root=frozen_repo, manifest_path=manifest_path, ref="main")
    assert exc.value.code == "INVALID_MANIFEST"


# =============================================================================
# AC-11: CLI smoke (exit code 契约)
# =============================================================================


def test_AC_11_cli_exit_codes(frozen_repo: Path, tmp_path: Path) -> None:
    manifest = _write_manifest(frozen_repo, tmp_path)
    (frozen_repo / "src.py").write_text("x = 1\n", encoding="utf-8")
    _commit_all(frozen_repo, "impl only")
    rc_pass = acgate_main([
        "acgate", "run", "--manifest", str(manifest),
        "--repo-root", str(frozen_repo), "--base", "main", "--head", "task1",
    ])
    assert rc_pass == 0

    (frozen_repo / TEST_FILE).unlink()
    _commit_all(frozen_repo, "delete frozen tests")
    rc_block = acgate_main([
        "acgate", "run", "--manifest", str(manifest),
        "--repo-root", str(frozen_repo), "--base", "main", "--head", "task1",
    ])
    assert rc_block == 1

    rc_err = acgate_main([
        "acgate", "run", "--manifest", str(tmp_path / "missing.yaml"),
        "--repo-root", str(frozen_repo), "--base", "main", "--head", "task1",
    ])
    assert rc_err == 2


# =============================================================================
# AC-12: 文件改名 (git R 状态) → 旧路径按删除拦
# =============================================================================


def test_AC_12_renamed_file_blocks(frozen_repo: Path, tmp_path: Path) -> None:
    manifest = _write_manifest(frozen_repo, tmp_path)
    _git(frozen_repo, "mv", TEST_FILE, "tests/test_moved.py")
    _commit_all(frozen_repo, "rename frozen test file")
    report = _run(frozen_repo, manifest)
    assert report.verdict == "block"
    assert any(
        f.kind == "TEST_FILE_DELETED" and f.file == TEST_FILE for f in report.findings
    )
