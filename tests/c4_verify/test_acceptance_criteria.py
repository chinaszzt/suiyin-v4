"""C4 §5 Acceptance Criteria tests.

每个 test 函数名 prefix `test_AC_N_` 对应 spec §5 AC-N (Fork G 命名约定).
P0 阶段以 unit test 为主, 避免 subprocess 起 fixture project 的 overhead;
端到端 dogfood 在阶段 2.C 由 C2 实施.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from suiyin_flow.c4_verify.cli import run_verify, validate_spec_has_ac_section
from suiyin_flow.c4_verify.contract import (
    CONTRACT_VERSION,
    L1Report,
    L2Report,
    L2Summary,
    LevelsReport,
    TargetWorktree,
    TestOutcome,
    VerifyContractError,
    VerifyInput,
    VerifyReport,
)
from suiyin_flow.c4_verify.parser import is_multi_ac_violation
from suiyin_flow.c4_verify.report import (
    build_report,
    compute_ac_summary,
    compute_overall_verdict,
)

# =============================================================================
# AC-1: 给定 worktree 含 1 个 passing test 名为 test_AC_1_xxx,
#       请求 levels=[L1, L2], 返回 overall_verdict=pass + ac_summary.covered=['AC-1']
# =============================================================================


def test_AC_1_pass_when_single_passing_test_covers_requested_ac() -> None:
    """AC-1: 单个 passing test_AC_1_xxx 覆盖 requested AC-1 → covered=['AC-1']."""
    test_results = [
        TestOutcome(
            test_name="test_AC_1_some_behavior",
            ac_prefix="AC-1",
            status="passed",
        ),
    ]
    summary = compute_ac_summary(["AC-1"], test_results)
    assert summary.requested == ["AC-1"]
    assert summary.covered == ["AC-1"]
    assert summary.missing == []
    assert summary.multi_ac_violations == []


# =============================================================================
# AC-2: 给定 worktree 含 1 个 failing test, 返回 overall_verdict=fail + L2.summary.failed=1
# =============================================================================


def test_AC_2_fail_verdict_when_l2_has_failing_test() -> None:
    """AC-2: L2 内 1 个 failing test → overall_verdict=fail."""
    levels = LevelsReport(
        L1=L1Report(status="pass", checks=[]),
        L2=L2Report(
            status="fail",
            test_results=[
                TestOutcome(test_name="test_AC_2_failing", status="failed"),
            ],
            summary=L2Summary(total=1, passed=0, failed=1, skipped=0),
        ),
    )
    verdict = compute_overall_verdict(levels)
    assert verdict == "fail"
    assert levels.L2 is not None
    assert levels.L2.summary.failed == 1


# =============================================================================
# AC-3: test 名 test_AC_1_AC_2_combined (2 个 AC prefix) → multi_ac_violations 非空
# =============================================================================


def test_AC_3_multi_ac_violation_when_test_name_has_two_ac_prefixes() -> None:
    """AC-3 (I2 invariant): 1 test 名带 2 个不同 AC-N → violation."""
    violated, prefixes = is_multi_ac_violation("test_AC_1_AC_2_combined")
    assert violated is True
    assert prefixes == ["AC-1", "AC-2"]

    # compute_ac_summary 也应标记 violation
    test_results = [
        TestOutcome(test_name="test_AC_1_AC_2_combined", status="passed"),
    ]
    summary = compute_ac_summary(["AC-1", "AC-2"], test_results)
    assert len(summary.multi_ac_violations) == 1
    assert summary.multi_ac_violations[0].test_name == "test_AC_1_AC_2_combined"
    assert summary.multi_ac_violations[0].ac_prefixes_found == ["AC-1", "AC-2"]


# =============================================================================
# AC-4: 请求 levels=[L3] 但 contract v0.1.1 → LEVEL_NOT_IMPLEMENTED
# =============================================================================


def test_AC_4_level_not_implemented_when_l3_requested() -> None:
    """AC-4 (I6 invariant): 请求 P0 未实现的 L3/L4/L5 立即 raise."""
    verify_input = VerifyInput(
        target=TargetWorktree(worktree_path="/tmp/dummy_worktree"),
        spec_ref="docs/sdd/components/c4-verify-contract.md",
        ac_list=["AC-1"],
        levels=["L3"],
        repo_root="/tmp/dummy_repo",
    )
    with pytest.raises(VerifyContractError) as exc_info:
        run_verify(verify_input)
    assert exc_info.value.error.code == "LEVEL_NOT_IMPLEMENTED"


# =============================================================================
# AC-5: spec.md 缺 §5 AC 段 → SPEC_PARSE_FAILED
# =============================================================================


def test_AC_5_spec_parse_failed_when_spec_missing_section(tmp_path: Path) -> None:
    """AC-5: spec.md 不含 '## 5. Acceptance Criteria' → SPEC_PARSE_FAILED."""
    bad_spec = tmp_path / "bad_spec.md"
    bad_spec.write_text("# Some doc\n\nNo AC section here.\n", encoding="utf-8")

    with pytest.raises(VerifyContractError) as exc_info:
        validate_spec_has_ac_section(bad_spec)
    assert exc_info.value.error.code == "SPEC_PARSE_FAILED"


def test_AC_5_spec_parse_failed_when_section_present_but_no_ac_entries(
    tmp_path: Path,
) -> None:
    """AC-5 边角: §5 段存在但无 AC-N 编号 → 也 SPEC_PARSE_FAILED."""
    bad_spec = tmp_path / "empty_section.md"
    bad_spec.write_text(
        "## 5. Acceptance Criteria\n\nTBD — no AC entries yet.\n",
        encoding="utf-8",
    )
    with pytest.raises(VerifyContractError) as exc_info:
        validate_spec_has_ac_section(bad_spec)
    assert exc_info.value.error.code == "SPEC_PARSE_FAILED"


def test_AC_5_spec_parse_succeeds_when_section_with_ac_present(tmp_path: Path) -> None:
    """AC-5 正向: §5 段含 AC-N 编号 → 不 raise."""
    good_spec = tmp_path / "good_spec.md"
    good_spec.write_text(
        "## 5. Acceptance Criteria\n\n- **AC-1**: Some behavior.\n",
        encoding="utf-8",
    )
    validate_spec_has_ac_section(good_spec)  # 不 raise


# =============================================================================
# AC-6: requested AC-1/2/3 但 test 只覆盖 AC-1 → missing=[AC-2, AC-3]
# =============================================================================


def test_AC_6_ac_summary_lists_missing_ACs() -> None:
    """AC-6: requested AC 缺 covering test → missing 列表."""
    requested = ["AC-1", "AC-2", "AC-3"]
    test_results = [
        TestOutcome(test_name="test_AC_1_only", status="passed", ac_prefix="AC-1"),
    ]
    summary = compute_ac_summary(requested, test_results)
    assert sorted(summary.covered) == ["AC-1"]
    assert sorted(summary.missing) == ["AC-2", "AC-3"]


# =============================================================================
# AC-7: verify_report.json 严格符合 §2.2 schema (Pydantic round-trip)
# =============================================================================


def test_AC_7_report_schema_round_trip_preserves_fields() -> None:
    """AC-7: VerifyReport serialize → JSON → deserialize 保留所有关键字段."""
    target = TargetWorktree(worktree_path="/path/to/wt")
    report = build_report(
        target=target,
        task_id="T-042",
        levels=LevelsReport(
            L1=L1Report(status="pass", checks=[]),
            L2=L2Report(status="pass"),
        ),
        requested_acs=["AC-1"],
    )
    json_str = report.model_dump_json()

    # Pydantic strict round-trip
    reparsed = VerifyReport.model_validate_json(json_str)
    assert reparsed.task_id == "T-042"
    assert reparsed.contract_version == CONTRACT_VERSION
    assert reparsed.overall_verdict == "pass"
    assert reparsed.target.kind == "worktree"


# =============================================================================
# AC-8: 跨实现谱系 schema 一致
# P0 简化版: 100 次构建相同 input → 100% schema-valid report (Pydantic strict)
# 完整版 (P1+): 跨 (a) lefthook vs (b) CI 实测对齐 (P0 阶段 CI 没实现)
# =============================================================================


def test_AC_8_report_schema_stable_across_100_invocations() -> None:
    """AC-8 (P0 简化): 100 次同 input → 100% pass schema validation."""
    target = TargetWorktree(worktree_path="/path/to/wt")
    for _ in range(100):
        report = build_report(
            target=target,
            task_id="T-042",
            levels=LevelsReport(
                L1=L1Report(status="pass", checks=[]),
                L2=L2Report(status="pass"),
            ),
            requested_acs=["AC-1"],
        )
        json_str = report.model_dump_json()
        VerifyReport.model_validate_json(json_str)  # 任一次 raise 即 test fail
