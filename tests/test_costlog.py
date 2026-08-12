"""P0-6 成本记账最小版验收测试."""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any, cast

import pytest

from suiyin_flow import costlog
from suiyin_flow.c2_executor.cli import execute_task
from suiyin_flow.c2_executor.schema import TaskInput
from suiyin_flow.c5_reviewer.cli import execute_review
from suiyin_flow.c5_reviewer.contract import ReviewInput
from suiyin_flow.costlog import CostRecord, close_invocation, open_invocation


def _read_ledger(repo_root: Path) -> list[dict[str, Any]]:
    """逐行读取 JSONL 台账，确保每行都能独立解析."""
    path = repo_root / ".suiyin" / "cost" / "log.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _git(repo: Path, *args: str) -> None:
    """执行测试仓库内的 git 命令."""
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        shell=False,
    )


def _make_repo(tmp_path: Path) -> Path:
    """创建同时满足 C2 与 C5 输入约束的最小 git 仓库."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "costlog@test.local")
    _git(repo, "config", "user.name", "costlog-test")
    _git(repo, "config", "commit.gpgsign", "false")
    (repo / "spec.md").write_text("# Spec\n\n- AC-1\n", encoding="utf-8")
    (repo / "plan.md").write_text("# Plan\n", encoding="utf-8")
    (repo / "constitution.md").write_text("# Constitution\n", encoding="utf-8")
    (repo / "context.md").write_text("# Context\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "initial")
    _git(repo, "checkout", "-b", "pr-test")
    (repo / "review_me.py").write_text("value = 1\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "review change")
    _git(repo, "checkout", "main")
    return repo


def _make_mock(tmp_path: Path, body: str, name: str) -> list[str]:
    """创建可由 session 以 list args 启动的 Claude mock."""
    script = tmp_path / name
    script.write_text(textwrap.dedent(body), encoding="utf-8")
    return [sys.executable, str(script)]


def test_AC_C1_open_close_writes_two_complete_jsonl_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """open + close 写双行，字段齐全且 invocation_id 相同."""
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-cost-test")
    record = open_invocation(
        tmp_path,
        feature_id="功能-001",
        task_id="T-001",
        role="implementer",
        attempt=2,
    )
    close_invocation(
        tmp_path,
        record,
        status="success",
        usage={
            "input_tokens": 101,
            "cache_read_input_tokens": 23,
            "output_tokens": 47,
        },
        error=None,
    )

    rows = _read_ledger(tmp_path)
    assert len(rows) == 2
    assert set(rows[0]) == set(CostRecord.model_fields)
    assert set(rows[1]) == set(CostRecord.model_fields)
    assert rows[0]["invocation_id"] == rows[1]["invocation_id"] == record.invocation_id
    assert rows[0]["status"] == "running"
    assert rows[0]["end_ts"] is None
    assert rows[1]["status"] == "success"
    assert rows[1]["end_ts"] is not None
    assert rows[1]["model"] == "claude-cost-test"
    assert rows[1]["input_tokens"] == 101
    assert rows[1]["cache_read_tokens"] == 23
    assert rows[1]["output_tokens"] == 47


def test_AC_C2_open_without_close_preserves_running_row(tmp_path: Path) -> None:
    """模拟进程 kill -9：只执行 open 也留下 running 行."""
    open_invocation(
        tmp_path,
        feature_id="feature-kill",
        task_id="T-002",
        role="reviewer",
        attempt=1,
    )

    rows = _read_ledger(tmp_path)
    assert len(rows) == 1
    assert rows[0]["status"] == "running"
    assert rows[0]["end_ts"] is None


def test_AC_C3_missing_usage_is_not_a_parse_error(tmp_path: Path) -> None:
    """result 没有 usage 时 token 为空，但不产生 cost_log_error."""
    record = open_invocation(
        tmp_path,
        feature_id="feature-no-usage",
        task_id="T-003",
        role="implementer",
        attempt=1,
    )
    close_invocation(tmp_path, record, status="success", usage=None, error=None)

    terminal = _read_ledger(tmp_path)[1]
    assert terminal["input_tokens"] is None
    assert terminal["cache_read_tokens"] is None
    assert terminal["output_tokens"] is None
    assert terminal["cost_log_error"] is None


def test_AC_C4_malformed_usage_records_explicit_error(tmp_path: Path) -> None:
    """usage 结构异常时 token 清空，并显式写 cost_log_error."""
    record = open_invocation(
        tmp_path,
        feature_id="feature-bad-usage",
        task_id="T-004",
        role="reviewer",
        attempt=1,
    )
    close_invocation(
        tmp_path,
        record,
        status="success",
        usage=cast(Any, "garbage"),
        error=None,
    )

    terminal = _read_ledger(tmp_path)[1]
    assert terminal["input_tokens"] is None
    assert terminal["cache_read_tokens"] is None
    assert terminal["output_tokens"] is None
    assert terminal["cost_log_error"]
    assert "usage" in terminal["cost_log_error"]


def test_AC_C5_write_failure_never_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """open / close 写盘抛 OSError 时只警告，不向主流程传播."""

    def _raise_oserror(repo_root: Path, record: CostRecord) -> None:
        _ = (repo_root, record)
        raise OSError("disk unavailable")

    monkeypatch.setattr(costlog, "_append_record", _raise_oserror)
    record = open_invocation(
        tmp_path,
        feature_id="feature-io",
        task_id="T-005",
        role="implementer",
        attempt=1,
    )
    close_invocation(tmp_path, record, status="crashed", usage=None, error="boom")

    assert capsys.readouterr().err.count("cost ledger write failed") == 2


def test_AC_C6_c2_execute_task_writes_implementer_ledger(tmp_path: Path) -> None:
    """C2 mock session 跑完后，repo 台账含正确 canonical identity."""
    repo = _make_repo(tmp_path)
    mock = _make_mock(
        tmp_path,
        """\
        import json
        import sys

        sys.stdin.read()
        final = {
            "task_id": "T-006",
            "files_changed": [],
            "verify_cmd_exit_code": 0,
            "commit_sha": "abc1234",
        }
        print(json.dumps({
            "type": "result",
            "subtype": "success",
            "result": json.dumps(final),
            "usage": {
                "input_tokens": 10,
                "cache_read_input_tokens": 2,
                "output_tokens": 3,
            },
        }))
        """,
        "c2_mock.py",
    )
    task_input = TaskInput(
        task_id="T-006",
        feature_id="feature-cost",
        spec_ref="spec.md",
        plan_ref="plan.md",
        constitution_ref="constitution.md",
        context_seeds=["context.md"],
        verify_cmd="true",
        criticality="medium",
        repo_root=str(repo),
        ac_list=["AC-1"],
        max_retries=0,
        open_pr=False,
    )

    output = execute_task(task_input, claude_cmd=mock)

    assert output.status == "success"
    terminal = [row for row in _read_ledger(repo) if row["status"] != "running"]
    assert len(terminal) == 1
    assert terminal[0]["role"] == "implementer"
    assert terminal[0]["feature_id"] == "feature-cost"
    assert terminal[0]["task_id"] == "T-006"
    assert terminal[0]["input_tokens"] == 10


def test_AC_C7_c5_execute_review_writes_reviewer_ledger(tmp_path: Path) -> None:
    """C5 mock session 跑完后，repo 台账含 reviewer 终态行."""
    repo = _make_repo(tmp_path)
    mock = _make_mock(
        tmp_path,
        """\
        import json
        import sys

        sys.stdin.read()
        final = {"verdict": "approve", "findings": []}
        print(json.dumps({
            "type": "result",
            "subtype": "success",
            "result": json.dumps(final),
            "usage": {
                "input_tokens": 20,
                "cache_read_input_tokens": 4,
                "output_tokens": 5,
            },
        }))
        """,
        "c5_mock.py",
    )
    review_input = ReviewInput(
        pr_ref="pr-test",
        spec_ref="spec.md",
        plan_ref="plan.md",
        constitution_ref="constitution.md",
        task_id="T-007",
        feature_id="feature-review",
        criticality="medium",
        repo_root=str(repo),
    )

    verdict, _ = execute_review(review_input, claude_cmd=mock)

    assert verdict == "approve"
    terminal = [row for row in _read_ledger(repo) if row["status"] != "running"]
    assert len(terminal) == 1
    assert terminal[0]["role"] == "reviewer"
    assert terminal[0]["feature_id"] == "feature-review"
    assert terminal[0]["task_id"] == "T-007"
    assert terminal[0]["output_tokens"] == 5
