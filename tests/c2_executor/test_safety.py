"""P0-5 C2 安全闸测试。"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

from suiyin_flow.c2_executor.cli import execute_task
from suiyin_flow.c2_executor.safety import SafetyViolation, check_command, check_diff
from suiyin_flow.c2_executor.schema import TaskExecutorError, TaskInput
from suiyin_flow.c2_executor.worktree import worktree_path_for


def _make_input(repo: Path, *, verify_cmd: str = "true") -> TaskInput:
    """构造安全闸集成测试所需的最小输入。"""
    return TaskInput(
        task_id="T-001",
        spec_ref="spec.md",
        plan_ref="plan.md",
        constitution_ref="constitution.md",
        context_seeds=["context.md"],
        verify_cmd=verify_cmd,
        criticality="medium",
        repo_root=str(repo),
        ac_list=["AC-1"],
        open_pr=False,
    )


def _rule_ids(diff_or_command_result: list[SafetyViolation]) -> set[str]:
    """从 violation 列表提取 rule_id，减少测试重复。"""
    return {item.rule_id for item in diff_or_command_result}


def test_AC_S1_mongo_prod_port_blocks() -> None:
    """规则 1：标准生产 MongoDB 端口立即阻断。"""
    violations = check_command("pytest --mongo-uri mongodb://prod:27017/db")
    assert _rule_ids(violations) == {"SAFETY_MONGO_PROD_PORT"}


def test_AC_S2_mongo_port_numeric_boundaries_are_allowed() -> None:
    """规则 1：更长数字中的 27017 片段不误伤。"""
    assert check_command("probe 127017 && probe 270170") == []


def test_AC_S3_bzds_write_blocks() -> None:
    """规则 2：bzds 与写操作同一行共现即阻断。"""
    violations = check_command('mongosh --user bzds --eval "db.users.updateOne({}, {})"')
    assert _rule_ids(violations) == {"SAFETY_BZDS_WRITE"}


def test_AC_S4_bzds_read_only_is_allowed() -> None:
    """规则 2：bzds 只读 find/query/read 放行。"""
    assert check_command('mongosh --user bzds --eval "db.users.find({})"') == []


@pytest.mark.parametrize(
    "line",
    [
        "+-----BEGIN RSA PRIVATE KEY-----",
        '+AWS_ACCESS_KEY_ID = "AKIA1234567890ABCDEF"',
        '+service_key = "sk-1234567890abcdefghij"',
    ],
)
def test_AC_S5_credential_in_added_diff_blocks(line: str) -> None:
    """规则 3：新增 private key / AWS key / sk- key 均阻断。"""
    violations = check_diff(f"{line}\n")
    assert _rule_ids(violations) == {"SAFETY_CREDENTIAL_IN_DIFF"}


@pytest.mark.parametrize(
    "line",
    [
        '+password = "xxxxxxxx"',
        '+password = "your_password_here"',
    ],
)
def test_AC_S6_obvious_credential_placeholders_are_allowed(line: str) -> None:
    """规则 3：明显占位符不误伤。"""
    assert check_diff(f"{line}\n") == []


def test_AC_S7_real_quoted_credential_blocks() -> None:
    """规则 3：非占位符的明文凭证赋值阻断。"""
    violations = check_diff('+api_key = "productionKey123456"\n')
    assert _rule_ids(violations) == {"SAFETY_CREDENTIAL_IN_DIFF"}


def test_AC_S8_diff_scans_only_added_lines() -> None:
    """删除行里的凭证及 +++ 文件头不参与扫描。"""
    diff_text = (
        "diff --git a/file b/file\n"
        "--- a/file\n"
        "+++ b/file\n"
        '-token = "realDeletedToken123"\n'
    )
    assert check_diff(diff_text) == []


def test_AC_S9_unsafe_verify_command_blocks_before_worktree(
    fixture_repo: Path,
    mock_claude_success: list[str],
) -> None:
    """输入闸命中后不创建 worktree，也不起 session。"""
    task_input = _make_input(fixture_repo, verify_cmd="pytest --db mongodb://prod:27017/db")

    with pytest.raises(TaskExecutorError) as exc_info:
        execute_task(task_input, claude_cmd=mock_claude_success)

    error = exc_info.value.error
    assert error.code == "SAFETY_BLOCKED"
    assert error.retryable is False
    assert error.details["violations"][0]["rule_id"] == "SAFETY_MONGO_PROD_PORT"
    assert not worktree_path_for(fixture_repo, "main", "T-001").exists()


def test_AC_S10_credential_commit_blocks_adoption_and_keeps_worktree(
    fixture_repo: Path,
    tmp_path: Path,
) -> None:
    """session 提交 AWS key 后，采纳闸阻断并保留现场。"""
    mock_script = tmp_path / "claude_mock_commit_credential.py"
    mock_script.write_text(
        textwrap.dedent(
            """\
            import json
            import subprocess
            import sys
            from pathlib import Path

            sys.stdin.read()
            Path("credential.py").write_text(
                'AWS_ACCESS_KEY_ID = "AKIA1234567890ABCDEF"\\n',
                encoding="utf-8",
            )
            subprocess.run(
                ["git", "add", "credential.py"],
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                shell=False,
            )
            subprocess.run(
                ["git", "commit", "-m", "add credential"],
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                shell=False,
            )
            print(json.dumps({
                "task_id": "T-001",
                "files_changed": ["credential.py"],
                "verify_cmd_exit_code": 0,
                "commit_sha": "mock",
            }))
            """
        ),
        encoding="utf-8",
    )

    with pytest.raises(TaskExecutorError) as exc_info:
        execute_task(_make_input(fixture_repo), claude_cmd=[sys.executable, str(mock_script)])

    error = exc_info.value.error
    worktree = worktree_path_for(fixture_repo, "main", "T-001")
    assert error.code == "SAFETY_BLOCKED"
    assert error.retryable is False
    assert error.details["worktree_path"] == str(worktree)
    assert error.details["violations"][0]["rule_id"] == "SAFETY_CREDENTIAL_IN_DIFF"
    assert worktree.exists()
    assert (worktree / "credential.py").exists()


# =============================================================================
# AC-S11 (v0.5.1): .suiyin/ 运行时工件入 diff → 拦 (E4 floor blocker 承接)
# =============================================================================


def test_AC_S11_runtime_artifact_in_diff_blocks() -> None:
    diff = (
        "diff --git a/.suiyin/sessions/attempt-3.log b/.suiyin/sessions/attempt-3.log\n"
        "--- /dev/null\n"
        "+++ b/.suiyin/sessions/attempt-3.log\n"
        "+session content with /Users/someone paths\n"
    )
    violations = check_diff(diff)
    assert any(v.rule_id == "SAFETY_RUNTIME_ARTIFACT_IN_DIFF" for v in violations)


def test_AC_S11b_normal_files_not_flagged() -> None:
    diff = (
        "diff --git a/src/app.py b/src/app.py\n"
        "--- a/src/app.py\n"
        "+++ b/src/app.py\n"
        "+x = 1\n"
    )
    assert not any(
        v.rule_id == "SAFETY_RUNTIME_ARTIFACT_IN_DIFF" for v in check_diff(diff)
    )


# =============================================================================
# v0.6.0 误报校准 (M3 件 8, desk 真 diff 73 FP 回归靶)
# =============================================================================


def test_AC_S12_runtime_artifact_content_skips_content_rules() -> None:
    """file-aware: .suiyin/ 文件的内容行不再重复过规则 1-3
    (desk 50/73 FP: session log 内容逐行误报); 后续正常文件恢复扫描."""
    diff = (
        "+++ b/.suiyin/sessions/attempt-1.log\n"
        '+{"content": "bzds insert mongodb://h:27017 sk-abcdefghij0123456789xy"}\n'
        "+++ b/src/app.py\n"
        "+uri = 'mongodb://prod:27017/db'\n"
    )
    ids = [v.rule_id for v in check_diff(diff)]
    assert ids.count("SAFETY_RUNTIME_ARTIFACT_IN_DIFF") == 1
    assert "SAFETY_BZDS_WRITE" not in ids           # log 内容不重复报
    assert "SAFETY_CREDENTIAL_IN_DIFF" not in ids
    assert ids.count("SAFETY_MONGO_PROD_PORT") == 1  # 正常文件的真违规仍中


def test_AC_S13_mongo_port_mention_vs_pointing() -> None:
    """规则 1 收紧为连接/指向形态: 守卫代码/文档'提到禁令'不再误中
    (desk testmongo_uri_ok / orchestrator-policy 案), 真指向仍全中."""
    # desk 真实 FP 行
    assert check_command("# 铁律投影：loopback + 38xxx；其余（尤其 27017/远程主机）一律拒") == []
    assert check_diff("+++ b/docs/policy.md\n+- bzds 只读：可自行开 27017 隧道做只读核对\n") == []
    # 指向形态全中
    for cmd in (
        "mongosh mongodb://localhost:27017/x",
        "pytest --port 27017",
        "MONGO_PORT=27017 go test ./...",
        "port: 27017",
    ):
        assert "SAFETY_MONGO_PROD_PORT" in _rule_ids(check_command(cmd)), cmd


def test_AC_S14_credential_patterns_tightened() -> None:
    """凭证 regex 收紧: 路径片段/混合大小写随机串不误中, 真密钥形态仍中
    (desk 16 处 sk-v4lab-worktrees-T-002 + 2 处 aKIa 混合案)."""
    fp_lines = (
        "+cd /Users/x/suiyin-desk-v4lab/worktrees/T-002 && ls",  # sk- 路径片段
        "+id=aKIah9ewys7kVQMqE4CN",                              # 混合大小写非 AWS key
        "+ref=AKiaPl8zHInNcrrDV3Xy",
    )
    for line in fp_lines:
        assert check_diff(f"+++ b/scripts/x.sh\n{line}\n") == [], line
    tp_lines = (
        "+key = 'sk-abcdefghijklmnopqrstuv123456'",
        "+key = 'sk-proj-abcdefghijklmnopqrstuv'",
        "+aws = 'AKIAIOSFODNN7EXAMPLE'",
    )
    for line in tp_lines:
        assert "SAFETY_CREDENTIAL_IN_DIFF" in _rule_ids(
            check_diff(f"+++ b/src/cfg.py\n{line}\n")
        ), line


def test_AC_S15_waiver_marker_skips_line() -> None:
    """safety-ok 行内豁免: 守卫代码自身含违禁字面量时可标注跳过 (可审计,
    标注留在 diff 里 C5 看得到); 无标注同内容仍中."""
    guarded = '+reject_if_matches "mongodb://prod:27017"  # safety-ok: 守卫拒绝清单字面量'
    assert check_diff(f"+++ b/scripts/guard.sh\n{guarded}\n") == []
    bare = '+reject_if_matches "mongodb://prod:27017"'
    assert "SAFETY_MONGO_PROD_PORT" in _rule_ids(
        check_diff(f"+++ b/scripts/guard.sh\n{bare}\n")
    )
