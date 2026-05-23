"""Test _compute_diff_stats fallback (v0.1.3 Bug 4 fix).

P0 spike (dogfood T-001) 发现: base_branch=claude/dogfood-adr-0002 未 push 到
remote 时, `origin/claude/dogfood-adr-0002` 不存在, git diff 失败 → silent None.
修后 fallback 到本地 base.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from suiyin_flow.c2_executor.cli import _compute_diff_stats


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        shell=False,
    )


@pytest.fixture
def fixture_repo_with_branches(tmp_path: Path) -> Path:
    """造一个 repo: main 分支有 1 commit, dev 分支有 1 commit + 文件改动."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "t@t.local")
    _git(repo, "config", "user.name", "t")
    _git(repo, "config", "commit.gpgsign", "false")

    (repo / "a.txt").write_text("initial content\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "initial on main")

    # 切到 dev 分支加改动
    _git(repo, "checkout", "-b", "dev")
    (repo / "b.txt").write_text("new file b\n", encoding="utf-8")
    (repo / "a.txt").write_text("modified content\nline 2\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "diff commit on dev")

    return repo


def test_diff_stats_fallback_to_local_when_origin_missing(
    fixture_repo_with_branches: Path,
) -> None:
    """Bug 4: 无 origin/main 时 fallback 到本地 main (返回真实 stats)."""
    # fixture repo 没 origin, 所以 origin/main 不存在
    stats = _compute_diff_stats(fixture_repo_with_branches, "main")
    assert stats is not None, "fallback 应该成功 (本地 main 存在)"
    # b.txt 新增 + a.txt 改 → 2 files changed
    assert stats.files_changed == 2
    assert stats.insertions >= 2  # 至少 b.txt + a.txt 第 2 行
    assert stats.deletions >= 1  # a.txt 原内容删除


def test_diff_stats_returns_none_when_base_branch_does_not_exist(
    fixture_repo_with_branches: Path,
) -> None:
    """origin/<base> 失败 + 本地 <base> 也失败 → None."""
    stats = _compute_diff_stats(fixture_repo_with_branches, "nonexistent-branch")
    assert stats is None


def test_diff_stats_returns_none_when_not_a_git_repo(tmp_path: Path) -> None:
    """非 git repo → None (subprocess error)."""
    stats = _compute_diff_stats(tmp_path, "main")
    assert stats is None
