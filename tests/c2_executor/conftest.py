"""Shared fixtures for C2 Task Executor AC tests.

Mock strategy:
- fixture_repo: 起一个最小 git repo (init + 1 commit), 含 spec/plan/seeds 文件
- mock_claude_*: 不同行为的假 claude script (Python 写, subprocess inject 为 claude_cmd)
- 不真起 Claude session, 不真 push remote (NC-1 兼容)
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest


def _git(repo: Path, *args: str) -> None:
    """跑 git -C repo <args>; check=True; capture output."""
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        shell=False,
    )


@pytest.fixture
def fixture_repo(tmp_path: Path) -> Path:
    """最小 git repo, 在 'main' 分支上有 1 commit + spec/plan/seeds.

    包含:
    - spec.md (符合 C4 §5 格式, 含 AC-1)
    - plan.md
    - constitution.md
    - context.md (作为 context_seed)
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@suiyin.local")
    _git(repo, "config", "user.name", "test")
    _git(repo, "config", "commit.gpgsign", "false")

    (repo / "spec.md").write_text(
        "# Test Spec\n\n## 5. Acceptance Criteria\n\n- **AC-1**: example behavior\n",
        encoding="utf-8",
    )
    (repo / "plan.md").write_text("# Plan\n", encoding="utf-8")
    (repo / "constitution.md").write_text("# Constitution\n", encoding="utf-8")
    (repo / "context.md").write_text("# Context seed\n", encoding="utf-8")

    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "initial")
    return repo


def _make_claude_mock(tmp_path: Path, script_body: str, name: str = "claude_mock.py") -> list[str]:
    """造一个 Python 假 claude 脚本; 返回 subprocess command list."""
    script = tmp_path / name
    script.write_text(script_body, encoding="utf-8")
    return [sys.executable, str(script)]


@pytest.fixture
def mock_claude_success(tmp_path: Path) -> list[str]:
    """claude mock: 输出 1 行 stream-json event + 最终成功 JSON (verify_pass=True)."""
    return _make_claude_mock(
        tmp_path,
        textwrap.dedent(
            """\
            import json
            import sys

            sys.stdin.read()  # consume prompt
            # 一些 stream-json 事件 (mock)
            print(json.dumps({"type": "message", "content": "starting"}))
            print(json.dumps({"type": "tool_use", "tool": "edit"}))
            # 最终输出 (C2 §4 Prompt Output)
            print(json.dumps({
                "task_id": "T-001",
                "files_changed": ["README.md"],
                "verify_cmd_exit_code": 0,
                "commit_sha": "abc1234",
            }))
            """
        ),
    )


@pytest.fixture
def mock_claude_verify_fail(tmp_path: Path) -> list[str]:
    """claude mock: 输出最终 JSON 但 verify_cmd_exit_code=1 (verify 失败)."""
    return _make_claude_mock(
        tmp_path,
        textwrap.dedent(
            """\
            import json
            import sys

            sys.stdin.read()
            print(json.dumps({
                "task_id": "T-001",
                "files_changed": [],
                "verify_cmd_exit_code": 1,
                "commit_sha": "",
            }))
            """
        ),
        name="claude_mock_verify_fail.py",
    )


@pytest.fixture
def mock_claude_sleep(tmp_path: Path) -> list[str]:
    """claude mock: sleep 长时间 (用于 TIMEOUT test)."""
    return _make_claude_mock(
        tmp_path,
        textwrap.dedent(
            """\
            import sys
            import time

            sys.stdin.read()
            # 长 sleep 触发 timeout
            time.sleep(120)
            """
        ),
        name="claude_mock_sleep.py",
    )


@pytest.fixture
def _disable_push_and_pr(monkeypatch: pytest.MonkeyPatch) -> None:
    """阻止真 push/PR creation: 让 gh 找不到 + git push 跑 fake 命令."""
    monkeypatch.setenv("PATH", os.path.dirname(sys.executable))  # 收窄 PATH 去掉 gh
    # subprocess 调 git 还能找到 (假设系统 git 在标准位置, 或者通过 sys.executable 同目录的 git)
    # 这里允许 push 失败 → caller pr_created=false 兜底
