"""C6 Gate Contract AC tests (AC-1 .. AC-10).

按 docs/sdd/components/c6-gate-contract.md v0.1.1 §5 AC.

测试名 prefix `test_AC_<N>_` 由 C4 parser (Fork G) 识别为覆盖 AC-N.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from suiyin_flow.c6_gate.cli import execute_gate, main
from suiyin_flow.c6_gate.contract import (
    GateContractError,
    GateInput,
)
from suiyin_flow.c6_gate.report import safe_pr_ref

# -------------------------------------------------------------------
# AC-1 / AC-1b — 4 全 pass → merged (real vs dry_run)
# -------------------------------------------------------------------


def test_AC_1_all_pass_real_merge_advances_main(
    fixture_repo: Path,
    verify_report_pass: Path,
    review_report_approve: Path,
    mock_gh_on_path: Path,
) -> None:
    """AC-1: 4 条全 pass + dry_run=false → merged, main HEAD 前进, merged_sha 必填.

    跟 AC-9 部分重叠，但 AC-9 焦点是 'ff-only enforce + 无 gh pr merge'，本 test
    焦点是 AC-1 contract (4 全 pass → merged + merged_sha)。两个独立 test 让 C4
    parser 按 `test_AC_<N>_` prefix 正确识别 AC 覆盖。
    """
    import subprocess

    gi = GateInput(
        pr_ref="feature",
        verify_report_path=str(verify_report_pass),
        review_report_path=str(review_report_approve),
        repo_root=str(fixture_repo),
        dry_run=False,
    )
    out = execute_gate(gi)
    assert out.gate_result == "merged"
    assert out.reason is None
    assert out.recovery_action is None
    assert out.merged_sha is not None  # AC-1: 非 dry_run merged_sha 必填
    # main HEAD 真前进了
    head = subprocess.run(
        ["git", "-C", str(fixture_repo), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert head == out.merged_sha


def test_AC_1b_all_pass_dry_run_no_side_effect(
    fixture_repo: Path,
    verify_report_pass: Path,
    review_report_approve: Path,
    mock_gh_on_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-1b: 4 条全 pass + dry_run=true → merged 预测, merged_sha absent, main 不动."""
    monkeypatch.setenv("C6_MOCK_GH_SHA", "fakesha-feature")

    gi = GateInput(
        pr_ref="feature",  # local branch, gh fallback to git rev-parse
        verify_report_path=str(verify_report_pass),
        review_report_path=str(review_report_approve),
        repo_root=str(fixture_repo),
        dry_run=True,
    )
    out = execute_gate(gi)
    assert out.gate_result == "merged"
    assert out.rules.verify_all_pass is True
    assert out.rules.review_approved is True
    assert out.rules.ff_mergeable is True
    assert out.rules.not_human_blocked is True
    assert out.reason is None
    assert out.recovery_action is None
    assert out.merged_sha is None  # AC-1b: dry_run merged_sha absent

    payload = out.to_dict()
    assert "reason" not in payload  # omit-when-absent
    assert "recovery_action" not in payload
    assert "merged_sha" not in payload


# -------------------------------------------------------------------
# AC-2 — verify 失败 → held
# -------------------------------------------------------------------


def test_AC_2_verify_fail_held(
    fixture_repo: Path,
    verify_report_fail: Path,
    review_report_approve: Path,
    mock_gh_on_path: Path,
) -> None:
    """AC-2: overall_verdict=fail 其他全 pass → held + reason=VERIFY_NOT_PASS + no_op."""
    gi = GateInput(
        pr_ref="feature",
        verify_report_path=str(verify_report_fail),
        review_report_path=str(review_report_approve),
        repo_root=str(fixture_repo),
        dry_run=True,
    )
    out = execute_gate(gi)
    assert out.gate_result == "held"
    assert out.reason == "VERIFY_NOT_PASS"
    assert out.rules.verify_all_pass is False
    assert out.rules.review_approved is True
    assert out.recovery_action is not None
    assert out.recovery_action.kind == "no_op"
    # AC-2 不加 label / 不 comment — gh log 应该为空 (除 ff_check 的 view)
    log = mock_gh_on_path.read_text(encoding="utf-8")
    assert "pr edit" not in log
    assert "pr comment" not in log


# -------------------------------------------------------------------
# AC-3 / AC-3b / AC-3c — review block → held + R1 atomicity (I9)
# -------------------------------------------------------------------


def test_AC_3_review_block_r1_full_success(
    fixture_repo: Path,
    feature_sha: str,
    verify_report_pass: Path,
    review_report_block: Path,
    mock_gh_on_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-3: review=block + 全 gh 成功 → held + r1_label_and_comment + label_added/comment_posted true + comment_url."""  # noqa: E501
    monkeypatch.setenv("C6_MOCK_GH_SHA", feature_sha)
    gi = GateInput(
        pr_ref="33",  # PR 编号 — 走 gh 路径
        verify_report_path=str(verify_report_pass),
        review_report_path=str(review_report_block),
        repo_root=str(fixture_repo),
        dry_run=False,
    )
    out = execute_gate(gi)
    assert out.gate_result == "held"
    assert out.reason == "REVIEW_NOT_APPROVE"
    assert out.recovery_action is not None
    assert out.recovery_action.kind == "r1_label_and_comment"
    assert out.recovery_action.label_added is True
    assert out.recovery_action.comment_posted is True
    assert out.recovery_action.comment_url is not None
    assert "issuecomment" in out.recovery_action.comment_url

    log = mock_gh_on_path.read_text(encoding="utf-8")
    assert "pr edit 33 --add-label human:block" in log
    assert "pr comment 33" in log


def test_AC_3b_r1_label_success_comment_fail(
    fixture_repo: Path,
    feature_sha: str,
    verify_report_pass: Path,
    review_report_block: Path,
    mock_gh_on_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-3b I9 atomicity: label 成 + comment 失 → 仍 held + partial_failure=GH_ERROR."""
    monkeypatch.setenv("C6_MOCK_GH_SHA", feature_sha)
    monkeypatch.setenv("C6_MOCK_GH_COMMENT_FAIL", "1")
    gi = GateInput(
        pr_ref="33",
        verify_report_path=str(verify_report_pass),
        review_report_path=str(review_report_block),
        repo_root=str(fixture_repo),
        dry_run=False,
    )
    out = execute_gate(gi)
    assert out.gate_result == "held"  # I7 兜底 — label 成功视作 R1 已触发
    assert out.reason == "REVIEW_NOT_APPROVE"
    assert out.recovery_action is not None
    assert out.recovery_action.label_added is True
    assert out.recovery_action.comment_posted is False
    assert out.recovery_action.partial_failure == "GH_ERROR"


def test_AC_3c_r1_label_fail_downgrade_error(
    fixture_repo: Path,
    feature_sha: str,
    verify_report_pass: Path,
    review_report_block: Path,
    mock_gh_on_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-3c I9: label 失败 → 降级 Error (不 emit Output 形态)."""
    monkeypatch.setenv("C6_MOCK_GH_SHA", feature_sha)
    monkeypatch.setenv("C6_MOCK_GH_LABEL_FAIL", "1")
    gi = GateInput(
        pr_ref="33",
        verify_report_path=str(verify_report_pass),
        review_report_path=str(review_report_block),
        repo_root=str(fixture_repo),
        dry_run=False,
    )
    with pytest.raises(GateContractError) as ei:
        execute_gate(gi)
    assert ei.value.code in ("GH_ERROR", "PERMISSION_DENIED")


# -------------------------------------------------------------------
# AC-4 — 非 ff → held + 不重跑 (不需要真调 C4/C5)
# -------------------------------------------------------------------


def test_AC_4_not_ff_mergeable_held(
    fixture_repo_diverged: Path,
    verify_report_pass: Path,
    review_report_approve: Path,
    mock_gh_on_path: Path,
) -> None:
    """AC-4: feature 跟 main 已 diverge → ff_mergeable=false → held + NOT_FF_MERGEABLE."""
    gi = GateInput(
        pr_ref="feature",
        verify_report_path=str(verify_report_pass),
        review_report_path=str(review_report_approve),
        repo_root=str(fixture_repo_diverged),
        dry_run=True,
    )
    out = execute_gate(gi)
    assert out.gate_result == "held"
    assert out.reason == "NOT_FF_MERGEABLE"
    assert out.rules.ff_mergeable is False
    assert out.recovery_action is not None
    assert out.recovery_action.kind == "no_op"


# -------------------------------------------------------------------
# AC-5 — I8 precedence: HUMAN_BLOCKED + verify=fail → HUMAN_BLOCKED wins
# -------------------------------------------------------------------


def test_AC_5_i8_precedence_human_block_wins_over_verify_fail(
    fixture_repo: Path,
    feature_sha: str,
    verify_report_fail: Path,
    review_report_approve: Path,
    mock_gh_on_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-5 I8: human:block 已存在 + verify=fail → reason=HUMAN_BLOCKED, no_op (不是 VERIFY)."""
    monkeypatch.setenv("C6_MOCK_GH_SHA", feature_sha)
    monkeypatch.setenv("C6_MOCK_GH_LABELS", "human:block\nbug")
    gi = GateInput(
        pr_ref="33",  # PR 编号 — gh 能查 labels
        verify_report_path=str(verify_report_fail),
        review_report_path=str(review_report_approve),
        repo_root=str(fixture_repo),
        dry_run=False,
    )
    out = execute_gate(gi)
    assert out.gate_result == "held"
    assert out.reason == "HUMAN_BLOCKED"  # I8 优先
    # rules 记录 4 boolean 实情, 包含 verify=false
    assert out.rules.verify_all_pass is False
    assert out.rules.not_human_blocked is False
    assert out.recovery_action is not None
    assert out.recovery_action.kind == "no_op"
    # 不重复加 label / 不 comment
    log = mock_gh_on_path.read_text(encoding="utf-8")
    assert "pr edit" not in log
    assert "pr comment" not in log


# -------------------------------------------------------------------
# AC-6 / AC-6b — MISSING_INPUT / INVALID_REPORT
# -------------------------------------------------------------------


def test_AC_6_missing_input_error(
    fixture_repo: Path,
    review_report_approve: Path,
    mock_gh_on_path: Path,
    tmp_path: Path,
) -> None:
    """AC-6: verify_report_path 不存在 → Error code=MISSING_INPUT, 无 Output 字段."""
    gi = GateInput(
        pr_ref="feature",
        verify_report_path=str(tmp_path / "nonexistent.json"),
        review_report_path=str(review_report_approve),
        repo_root=str(fixture_repo),
        dry_run=True,
    )
    with pytest.raises(GateContractError) as ei:
        execute_gate(gi)
    assert ei.value.code == "MISSING_INPUT"
    err_dict = ei.value.to_error().to_dict()
    # AC-6: Error 与 Output 互斥 — Error 不含 gate_result / rules / reason
    assert "gate_result" not in err_dict
    assert "rules" not in err_dict
    assert "reason" not in err_dict
    assert err_dict["code"] == "MISSING_INPUT"


def test_AC_6b_invalid_report_missing_field(
    fixture_repo: Path,
    verify_report_missing_field: Path,
    review_report_approve: Path,
    mock_gh_on_path: Path,
) -> None:
    """AC-6b: verify_report 缺 overall_verdict → INVALID_REPORT, 不静默当 fail 走 held."""
    gi = GateInput(
        pr_ref="feature",
        verify_report_path=str(verify_report_missing_field),
        review_report_path=str(review_report_approve),
        repo_root=str(fixture_repo),
        dry_run=True,
    )
    with pytest.raises(GateContractError) as ei:
        execute_gate(gi)
    assert ei.value.code == "INVALID_REPORT"
    assert "overall_verdict" in ei.value.message


# -------------------------------------------------------------------
# AC-7 Determinism — same input N runs → same core fields
# -------------------------------------------------------------------


def test_AC_7_determinism(
    fixture_repo: Path,
    verify_report_fail: Path,
    review_report_approve: Path,
    mock_gh_on_path: Path,
) -> None:
    """AC-7: 同 input N≥3 次 dry_run → gate_result + reason + rules 完全一致 (timestamp 忽略)."""
    gi = GateInput(
        pr_ref="feature",
        verify_report_path=str(verify_report_fail),
        review_report_path=str(review_report_approve),
        repo_root=str(fixture_repo),
        dry_run=True,
    )
    outs = [execute_gate(gi) for _ in range(3)]
    core = [(o.gate_result, o.reason, o.rules.model_dump()) for o in outs]
    assert core[0] == core[1] == core[2]
    # timestamps 每次都 set (不参与 determinism 等价比较)
    assert all(o.timestamp for o in outs)


# -------------------------------------------------------------------
# AC-8 — dry_run absent fields (not null, not false)
# -------------------------------------------------------------------


def test_AC_8_dry_run_absent_fields(
    fixture_repo: Path,
    feature_sha: str,
    verify_report_pass: Path,
    review_report_block: Path,
    mock_gh_on_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-8: dry_run + review=block → kind=r1，label_added/comment_posted/url 全 absent."""
    monkeypatch.setenv("C6_MOCK_GH_SHA", feature_sha)
    gi = GateInput(
        pr_ref="33",
        verify_report_path=str(verify_report_pass),
        review_report_path=str(review_report_block),
        repo_root=str(fixture_repo),
        dry_run=True,
    )
    out = execute_gate(gi)
    assert out.reason == "REVIEW_NOT_APPROVE"
    assert out.recovery_action is not None
    assert out.recovery_action.kind == "r1_label_and_comment"
    assert out.recovery_action.label_added is None
    assert out.recovery_action.comment_posted is None
    assert out.recovery_action.comment_url is None

    payload = out.to_dict()
    ra = payload["recovery_action"]
    assert ra == {"kind": "r1_label_and_comment"}  # omit-when-absent

    # 副作用未触发 (gh log 只含 ff_check 的 view 调用，无 edit/comment)
    log = mock_gh_on_path.read_text(encoding="utf-8")
    assert "pr edit" not in log
    assert "pr comment" not in log


# -------------------------------------------------------------------
# AC-9 — ff-only enforce (no `gh pr merge`, no fallback to merge-commit)
# -------------------------------------------------------------------


def test_AC_9_ff_only_no_gh_pr_merge(
    fixture_repo: Path,
    verify_report_pass: Path,
    review_report_approve: Path,
    mock_gh_on_path: Path,
) -> None:
    """AC-9: 真 merge 路径必须用本地 git merge --ff-only, 不能调 `gh pr merge`."""
    gi = GateInput(
        pr_ref="feature",
        verify_report_path=str(verify_report_pass),
        review_report_path=str(review_report_approve),
        repo_root=str(fixture_repo),
        dry_run=False,
    )
    out = execute_gate(gi)
    assert out.gate_result == "merged"
    assert out.merged_sha is not None
    # main HEAD 真前进了
    import subprocess

    head = subprocess.run(
        ["git", "-C", str(fixture_repo), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert head == out.merged_sha

    # gh log 应该不含任何 `pr merge` 调用
    log = mock_gh_on_path.read_text(encoding="utf-8")
    assert "pr merge" not in log


# -------------------------------------------------------------------
# AC-10 — gate report 落盘 + pr_ref 转义
# -------------------------------------------------------------------


def test_AC_10_gate_report_persisted_with_safe_pr_ref(
    fixture_repo: Path,
    feature_sha: str,
    verify_report_pass: Path,
    review_report_approve: Path,
    mock_gh_on_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("C6_MOCK_GH_SHA", feature_sha)
    """AC-10: 落盘 .suiyin/gates/<safe_pr_ref>-<ts>.json + 文件名扁平不含 / : 等."""
    # 用 PR URL 形式触发 safe_pr_ref 规则
    pr_url = "https://github.com/owner/repo/pull/33"
    expected_safe = safe_pr_ref(pr_url)
    assert expected_safe == "pull-33"

    # 经 main CLI 路径以触发 write_gate_report
    rc = main(
        [
            "gate", "run",
            "--pr-ref", pr_url,
            "--verify-report", str(verify_report_pass),
            "--review-report", str(review_report_approve),
            "--repo-root", str(fixture_repo),
            "--dry-run",
        ]
    )
    assert rc == 0  # merged dry_run → exit 0
    gates_dir = fixture_repo / ".suiyin" / "gates"
    assert gates_dir.exists()
    files = list(gates_dir.iterdir())
    # 至少有 versioned + latest
    versioned = [f for f in files if f.name.startswith("pull-33-")]
    latest = [f for f in files if f.name == "latest-pull-33.json"]
    assert versioned, f"missing versioned gate report: {[f.name for f in files]}"
    assert latest, "missing latest copy"

    # 文件名扁平 — 不含 / : <空白> 等
    for f in files:
        for bad in ["/", ":", "?", "<", ">", "|", '"', "\\"]:
            assert bad not in f.name, f"unsafe char {bad!r} in {f.name}"

    # latest 是合法 JSON + 含核心字段
    data = json.loads(latest[0].read_text(encoding="utf-8"))
    assert data["gate_result"] == "merged"
    assert "rules" in data
    assert "timestamp" in data


def test_AC_10_safe_pr_ref_branch_name() -> None:
    """补 AC-10: branch name 形式也要扁平."""
    assert safe_pr_ref("claude/c6-gate-impl") == "claude-c6-gate-impl"
    assert safe_pr_ref("#33") == "33"
    assert safe_pr_ref("33") == "33"
    assert safe_pr_ref("https://github.com/o/r/pull/9999") == "pull-9999"
