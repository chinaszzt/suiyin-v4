"""C2 `_open_pr_or_branch` PR base 测试 (P1.2.5 真闭环发现 #6).

旧版 gh pr create 不传 --base → gh 默认 repo default branch (main), worktree-centric
流里 task 从 claude/<feature> 分叉, PR 对 main 开会对错基线。修后必须显式 --base <base_branch>。

Mock 策略: monkeypatch cli.subprocess.run 捕获命令 (不真跑 git push / gh)。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from suiyin_flow.c2_executor import cli as c2_cli


class _FakeCompleted:
    returncode = 0
    stdout = "https://github.com/example/repo/pull/99\n"
    stderr = ""


def test_pr_create_uses_task_base_branch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """gh pr create 必须带 --base <task.base_branch> (不是默认 main)."""
    captured_cmds: list[list[str]] = []

    def fake_run(cmd: list[str], **kwargs: Any) -> _FakeCompleted:
        captured_cmds.append(list(cmd))
        return _FakeCompleted()

    monkeypatch.setattr(
        "suiyin_flow.c2_executor.cli.subprocess.run", fake_run
    )
    monkeypatch.setattr(
        "suiyin_flow.c2_executor.cli.shutil.which", lambda _: "/usr/bin/gh"
    )

    result = c2_cli._open_pr_or_branch(
        wt_path=tmp_path,
        task_id="T-001",
        ac_list=["AC-1"],
        spec_ref="specs/001-x/spec.md",
        attempts=1,
        branch="task/T-001",
        base_branch="claude/login-core",
    )

    assert result == "https://github.com/example/repo/pull/99"
    gh_cmds = [c for c in captured_cmds if "pr" in c and "create" in c]
    assert len(gh_cmds) == 1, f"expected exactly one gh pr create, got: {captured_cmds}"
    gh_cmd = gh_cmds[0]
    assert "--base" in gh_cmd
    assert gh_cmd[gh_cmd.index("--base") + 1] == "claude/login-core"
    # head 仍是 task 分支
    assert gh_cmd[gh_cmd.index("--head") + 1] == "task/T-001"
