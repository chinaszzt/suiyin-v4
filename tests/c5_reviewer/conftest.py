"""Shared fixtures for C5 Reviewer AC tests.

Mock 策略 (跟 C2 风格一致):
- fixture_pr_repo: 最小 git repo, 含 spec/plan/constitution + 1 个 PR branch
- mock_claude_review_*: 不同行为的假 claude script (Python)
- 不真起 Claude session, 不真 PR API
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest


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
def fixture_pr_repo(tmp_path: Path) -> Path:
    """最小 git repo: main 分支 + pr-test 分支含 diff."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "t@t.local")
    _git(repo, "config", "user.name", "t")
    _git(repo, "config", "commit.gpgsign", "false")

    (repo / "spec.md").write_text(
        "# Spec\n\n## 5. Acceptance Criteria\n\n- **AC-1**: example\n",
        encoding="utf-8",
    )
    (repo / "plan.md").write_text("# Plan\n", encoding="utf-8")
    (repo / "constitution.md").write_text("# Constitution\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "initial main")

    _git(repo, "checkout", "-b", "pr-test")
    (repo / "hello.py").write_text("def hello():\n    return 'hi'\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "add hello.py on pr-test")
    _git(repo, "checkout", "main")
    return repo


def _make_claude_mock_with_final(
    tmp_path: Path, final_review_dict: Mapping[str, Any], name: str
) -> list[str]:
    """Build a mock claude script that outputs stream-json + final review JSON.

    final_review_dict 用 Python repr() 注入到 mock script, 避免 JSON 双层转义.
    """
    body = textwrap.dedent(
        f"""\
        import json
        import sys

        sys.stdin.read()
        # mock stream-json events
        print(json.dumps({{"type": "system", "subtype": "init"}}))
        final = {final_review_dict!r}
        result_text = "review done. ```json\\n" + json.dumps(final) + "\\n```"
        print(json.dumps({{
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "result": result_text,
        }}))
        """
    )
    script = tmp_path / name
    script.write_text(body, encoding="utf-8")
    return [sys.executable, str(script)]


@pytest.fixture
def mock_claude_review_approve(tmp_path: Path) -> list[str]:
    """Mock: AI 输出 verdict=approve + 0 findings."""
    final = {
        "verdict": "approve",
        "findings": [],
        "reviewed_at": "2026-05-24T10:00:00Z",
        "session_id": "mock-001",
        "task_id": "T-100",
        "pr_ref": "test-pr",
        "contract_version": "v0.1.1",
    }
    return _make_claude_mock_with_final(tmp_path, final, "claude_mock_approve.py")


@pytest.fixture
def mock_claude_review_block_nc(tmp_path: Path) -> list[str]:
    """Mock: AI 输出 verdict=block + 1 nc_violation finding."""
    final = {
        "verdict": "block",
        "findings": [
            {
                "severity": "high",
                "category": "nc_violation",
                "location": "src/foo.py:1",
                "suggested_fix": "remove SaaS dependency",
            }
        ],
        "reviewed_at": "2026-05-24T10:00:00Z",
        "session_id": "mock-002",
        "task_id": "T-100",
        "pr_ref": "test-pr",
        "contract_version": "v0.1.1",
    }
    return _make_claude_mock_with_final(tmp_path, final, "claude_mock_block.py")


@pytest.fixture
def mock_claude_sleep(tmp_path: Path) -> list[str]:
    """Mock: 长 sleep, 用于 TIMEOUT test."""
    body = textwrap.dedent(
        """\
        import sys
        import time

        sys.stdin.read()
        time.sleep(120)
        """
    )
    script = tmp_path / "claude_mock_sleep.py"
    script.write_text(body, encoding="utf-8")
    return [sys.executable, str(script)]
