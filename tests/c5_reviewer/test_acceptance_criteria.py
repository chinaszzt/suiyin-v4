"""C5 §5 Acceptance Criteria tests.

按 c5-ai-reviewer.md v0.1.1 §5 AC-1..AC-10. Fork G 命名约定 `test_AC_N_...`.
Mock 策略见 conftest.py.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from suiyin_flow.c5_reviewer.cli import execute_review
from suiyin_flow.c5_reviewer.contract import (
    BLOCK_SET,
    CONTRACT_VERSION,
    Arbitration,
    Finding,
    ReviewerError,
    ReviewInput,
    ReviewReport,
)
from suiyin_flow.c5_reviewer.findings import (
    audit_findings,
    derive_verdict,
)
from suiyin_flow.c5_reviewer.inputs import (
    load_inputs_manifest,
    resolve_inputs,
    synthesize_core_inputs,
)
from suiyin_flow.c5_reviewer.prompt import render_prompt, validate_refs
from suiyin_flow.c5_reviewer.report import build_report


def _make_input(
    repo: Path,
    *,
    task_id: str = "T-100",
    criticality: str = "medium",
    spec_ref: str = "spec.md",
    pr_ref: str = "pr-test",
    session_timeout_seconds: int = 1800,
) -> ReviewInput:
    # Pydantic validates Literal at runtime; mypy needs cast
    return ReviewInput.model_validate({
        "pr_ref": pr_ref,
        "spec_ref": spec_ref,
        "plan_ref": "plan.md",
        "constitution_ref": "constitution.md",
        "task_id": task_id,
        "criticality": criticality,
        "repo_root": str(repo),
        "session_timeout_seconds": session_timeout_seconds,
    })


# =============================================================================
# AC-1: valid input → verdict ∈ {approve, block}, findings 4-field 齐
# =============================================================================


def test_AC_1_valid_input_returns_verdict_and_findings_schema(
    fixture_pr_repo: Path, mock_claude_review_approve: list[str]
) -> None:
    """AC-1: completed review → verdict + findings 都符合 schema."""
    review_input = _make_input(fixture_pr_repo)
    verdict, report_path = execute_review(
        review_input, claude_cmd=mock_claude_review_approve
    )
    assert verdict in ("approve", "block")
    assert report_path.exists()
    # report 反序列化通过 schema
    import json
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    report = ReviewReport(**payload)
    assert report.verdict == verdict
    assert report.task_id == "T-100"
    assert report.contract_version == CONTRACT_VERSION
    # findings 每条 4 字段齐
    for f in report.findings:
        assert f.severity and f.category and f.location and f.suggested_fix


# =============================================================================
# AC-2: nc_violation category → block (any severity)
# =============================================================================


def test_AC_2_nc_violation_category_triggers_block() -> None:
    """AC-2: category=nc_violation 任一 severity → verdict=block (I5 按 category)."""
    for sev in ("low", "medium", "high", "critical"):
        findings = [
            Finding(
                severity=sev,
                category="nc_violation",
                location="src/foo.py:1",
                suggested_fix="fix",
            )
        ]
        assert derive_verdict(findings) == "block"


def test_AC_2_other_block_set_categories_also_block() -> None:
    """AC-2 推广: 整个 BLOCK_SET 都触发 block (security / spec_drift / ac_uncovered)."""
    for cat in BLOCK_SET:
        findings = [
            Finding(
                severity="low",  # 故意 low, 验证 v0.1.1 按 category 不按 severity
                category=cat,
                location="src/x.py:1",
                suggested_fix="fix",
            )
        ]
        assert derive_verdict(findings) == "block"


# =============================================================================
# AC-3: 全非 block-set category → approve + finding audit
# =============================================================================


def test_AC_3_non_block_categories_approve_with_audit() -> None:
    """AC-3 (v0.1.1 重写): complexity / pc_violation / cross_platform /
    reusable_knowledge_not_captured → approve, findings 仍保留 audit."""
    non_block_cats = [
        "complexity",
        "pc_violation",
        "cross_platform",
        "reusable_knowledge_not_captured",
    ]
    findings = [
        Finding(
            severity="high",  # 高 severity 也无所谓, 不按 severity
            category=cat,  # type: ignore[arg-type]
            location=f"src/x.py:{i}",
            suggested_fix="fix",
        )
        for i, cat in enumerate(non_block_cats, start=1)
    ]
    assert derive_verdict(findings) == "approve"
    # Audit 保留全部 (I6: reusable_knowledge_not_captured 即使 low 也输出)
    audit = audit_findings(findings)
    assert len(audit) == len(non_block_cats)


# =============================================================================
# AC-4: spec.md 不存在 → SPEC_NOT_FOUND, 不启动 session
# =============================================================================


def test_AC_4_spec_not_found_raises_before_session(fixture_pr_repo: Path) -> None:
    """AC-4: validate_refs 在 session 启动之前 raise SPEC_NOT_FOUND."""
    review_input = _make_input(fixture_pr_repo, spec_ref="missing.md")
    with pytest.raises(ReviewerError) as exc_info:
        validate_refs(review_input)
    assert exc_info.value.error.code == "SPEC_NOT_FOUND"


# =============================================================================
# AC-5: session > timeout → TIMEOUT + kill -9
# =============================================================================


def test_AC_5_timeout_kills_session(
    fixture_pr_repo: Path, mock_claude_sleep: list[str]
) -> None:
    """AC-5 (I7): timeout 极小 → watchdog kill + raise TIMEOUT."""
    review_input = _make_input(fixture_pr_repo, session_timeout_seconds=2)
    with pytest.raises(ReviewerError) as exc_info:
        execute_review(review_input, claude_cmd=mock_claude_sleep)
    assert exc_info.value.error.code == "TIMEOUT"


# =============================================================================
# AC-6: prompt 不含 .suiyin/sessions/* (I1 隔离)
# =============================================================================


def test_AC_6_prompt_excludes_implementer_session_log(fixture_pr_repo: Path) -> None:
    """AC-6 (I1): render_prompt 输出**不含** .suiyin/sessions/ 路径
    (避免 AI 误以为可以读 implementer log)."""
    review_input = _make_input(fixture_pr_repo)
    resolved = resolve_inputs(synthesize_core_inputs(review_input), fixture_pr_repo)
    prompt = render_prompt(
        review_input, str(fixture_pr_repo / "pr_diff.patch"), resolved
    )
    # 隔离 invariant: prompt 中可以提到 'sessions' (在 Constraints 节里告诫 AI 不读),
    # 但不应该 inject 任何 .suiyin/sessions/<某文件> 作为 context_seed
    # 简单 audit: 不含 attempt-N.log 路径
    assert "attempt-1.log" not in prompt
    assert "attempt-2.log" not in prompt
    # 应含警示文本
    assert "implementer" in prompt or "session log" in prompt or "sessions" in prompt


# =============================================================================
# AC-7: C12 触发 - low severity reusable_knowledge_not_captured 仍要输出 (I6)
# =============================================================================


def test_AC_7_c12_low_severity_still_in_audit() -> None:
    """AC-7 (I6, C12): reusable_knowledge_not_captured finding 即使 low 也必须
    出现在 audit list (不被 filter 掉)."""
    findings = [
        Finding(
            severity="low",
            category="reusable_knowledge_not_captured",
            location="docs/sdd/constitution.md §6b",
            suggested_fix="升 NC-6 (建议)",
        ),
    ]
    audit = audit_findings(findings)
    assert len(audit) == 1
    assert audit[0].category == "reusable_knowledge_not_captured"
    # verdict 仍 approve (non-blocking)
    assert derive_verdict(findings) == "approve"


# =============================================================================
# AC-8: criticality=high → output 含 arbitration
# =============================================================================


def test_AC_8_high_criticality_sets_arbitration(
    fixture_pr_repo: Path, mock_claude_review_approve: list[str]
) -> None:
    """AC-8: criticality=high → ReviewReport.arbitration 非空."""
    review_input = _make_input(fixture_pr_repo, criticality="high")
    _, report_path = execute_review(
        review_input, claude_cmd=mock_claude_review_approve
    )
    import json
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload.get("arbitration") is not None
    assert payload["arbitration"]["mode"] in ("single", "n2_consensus", "n2_arbitrated")


def test_AC_8_low_criticality_arbitration_is_none(
    fixture_pr_repo: Path, mock_claude_review_approve: list[str]
) -> None:
    """AC-8 反例: criticality=low → arbitration 为 None."""
    review_input = _make_input(fixture_pr_repo, criticality="low")
    _, report_path = execute_review(
        review_input, claude_cmd=mock_claude_review_approve
    )
    import json
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload.get("arbitration") is None


# =============================================================================
# AC-9: complexity category 存在但**不在** BLOCK_SET (按 v0.1.1 不阻断)
# =============================================================================


def test_AC_9_complexity_not_in_block_set() -> None:
    """AC-9 (v0.1.1 调整): complexity 是 category 但 NOT block 集合
    (v0.1.0 按 severity 时 high complexity 会 block; v0.1.1 按 category 不阻断)."""
    assert "complexity" not in BLOCK_SET
    findings = [
        Finding(
            severity="high",
            category="complexity",
            location="src/foo.py:42",
            suggested_fix="抽函数",
        )
    ]
    assert derive_verdict(findings) == "approve"


# =============================================================================
# AC-10: review_report.json schema 跨 100 次 stable
# =============================================================================


def test_AC_10_report_schema_stable_across_100_builds() -> None:
    """AC-10: 100 次 build_report → 100% schema validate."""
    review_input = ReviewInput(
        pr_ref="test-pr",
        spec_ref="spec.md",
        plan_ref="plan.md",
        constitution_ref="constitution.md",
        task_id="T-001",
        criticality="medium",
        repo_root="/tmp",
    )
    for _ in range(100):
        report = build_report(
            review_input=review_input,
            verdict="approve",
            findings=[],
            session_id="test-uuid",
            arbitration=None,
        )
        json_str = report.model_dump_json()
        # Pydantic strict round-trip
        ReviewReport.model_validate_json(json_str)


# Touch unused imports to silence ruff F401 (test fixture deps)
_ = (datetime, UTC, Arbitration)


# =============================================================================
# AC-9 (P0-1): review 落盘按 canonical key 定位
# =============================================================================


def test_AC_9_review_dir_keyed_by_identity(
    fixture_pr_repo: Path, mock_claude_review_approve: list[str]
) -> None:
    """P0-1: reviews/<review_key>/<uuid>/latest.json — 不再是裸 uuid 目录."""
    review_input = _make_input(fixture_pr_repo).model_copy(
        update={"feature_id": "001-demo"}
    )
    _, report_path = execute_review(
        review_input, claude_cmd=mock_claude_review_approve
    )
    # <repo>/.suiyin/reviews/001-demo-T-100/<uuid>/latest.json
    assert report_path.name == "latest.json"
    key_dir = report_path.parent.parent
    assert key_dir.name == "001-demo-T-100"
    assert key_dir.parent.name == "reviews"


def test_AC_9b_review_dir_key_falls_back_to_task_id(
    fixture_pr_repo: Path, mock_claude_review_approve: list[str]
) -> None:
    """feature_id 缺省 → 键退化为 task_id (兼容旧调用方)."""
    _, report_path = execute_review(
        _make_input(fixture_pr_repo), claude_cmd=mock_claude_review_approve
    )
    assert report_path.parent.parent.name == "T-100"


# =============================================================================
# v0.4.0 typed inputs (M3 件 1, 拍板 7): AC-11..AC-16
# =============================================================================


def test_AC_11_required_input_missing_fail_closed(fixture_pr_repo: Path) -> None:
    """AC-11: required entry 文件缺失 → REVIEW_INPUT_MISSING, session 不启动."""
    from suiyin_flow.c5_reviewer.contract import ReviewInputEntry

    entries = [ReviewInputEntry(kind="contract", path="contracts/nope.md")]
    with pytest.raises(ReviewerError) as ei:
        resolve_inputs(entries, fixture_pr_repo)
    assert ei.value.error.code == "REVIEW_INPUT_MISSING"


def test_AC_11b_optional_input_missing_skipped(fixture_pr_repo: Path) -> None:
    """AC-11b: required=False 缺失 → skipped_missing, 不 fail."""
    from suiyin_flow.c5_reviewer.contract import ReviewInputEntry

    entries = [
        ReviewInputEntry(kind="advisory", path="notes/nope.md", required=False)
    ]
    resolved = resolve_inputs(entries, fixture_pr_repo)
    assert resolved[0].status == "skipped_missing"
    assert resolved[0].content_sha256 is None


def test_AC_12_content_hash_drift_fail_closed(fixture_pr_repo: Path) -> None:
    """AC-12: content_sha256 声明值 != 盘上实测 → REVIEW_INPUT_HASH_DRIFT."""
    from suiyin_flow.c5_reviewer.contract import ReviewInputEntry

    entries = [
        ReviewInputEntry(kind="spec", path="spec.md", content_sha256="0" * 64)
    ]
    with pytest.raises(ReviewerError) as ei:
        resolve_inputs(entries, fixture_pr_repo)
    assert ei.value.error.code == "REVIEW_INPUT_HASH_DRIFT"
    assert ei.value.error.details["actual_sha256"] != "0" * 64


def test_AC_12b_content_hash_crlf_normalized(tmp_path: Path) -> None:
    """AC-12b: hash 按 CRLF→LF 归一化 (PR #64 Windows autocrlf 教训) —
    声明 LF 内容的 hash, 盘上是 CRLF → 不算漂移."""
    from suiyin_flow.acgate.gate import content_hash
    from suiyin_flow.c5_reviewer.contract import ReviewInputEntry

    lf_content = b"line1\nline2\n"
    (tmp_path / "spec.md").write_bytes(b"line1\r\nline2\r\n")
    entries = [
        ReviewInputEntry(
            kind="spec", path="spec.md", content_sha256=content_hash(lf_content)
        )
    ]
    resolved = resolve_inputs(entries, tmp_path)
    assert resolved[0].status == "loaded"


def test_AC_13_authority_derived_and_ordered(fixture_pr_repo: Path) -> None:
    """AC-13: authority 由 kind 派生 (调用方不可自定), resolved 按权威序排列."""
    from suiyin_flow.c5_reviewer.contract import ReviewInputEntry

    (fixture_pr_repo / "failure-modes.md").write_text("坑1", encoding="utf-8")
    entries = [
        ReviewInputEntry(kind="failure_modes", path="failure-modes.md"),
        ReviewInputEntry(kind="spec", path="spec.md"),
        ReviewInputEntry(kind="constitution", path="constitution.md"),
    ]
    resolved = resolve_inputs(entries, fixture_pr_repo)
    assert [r.authority for r in resolved] == ["nc", "acceptance", "failure_modes"]


def test_AC_14_prompt_contains_typed_inputs_and_nc_rule(
    fixture_pr_repo: Path,
) -> None:
    """AC-14: prompt 含权威序声明 + nc 命中一律 nc_violation 钉死规则 +
    契约文件路径 (契约进输入面 — 尺子对照实验落地)."""
    from suiyin_flow.c5_reviewer.contract import ReviewInputEntry

    contracts = fixture_pr_repo / "contracts"
    contracts.mkdir()
    (contracts / "api.md").write_text("## 接口契约", encoding="utf-8")
    review_input = _make_input(fixture_pr_repo)
    entries = [
        *synthesize_core_inputs(review_input),
        ReviewInputEntry(kind="contract", path="contracts/api.md"),
    ]
    resolved = resolve_inputs(entries, fixture_pr_repo)
    prompt = render_prompt(
        review_input, str(fixture_pr_repo / "pr_diff.patch"), resolved
    )
    assert "nc_violation" in prompt
    assert "权威序" in prompt
    assert "api.md" in prompt
    # 权威序: constitution 行先于 contract 行
    assert prompt.index("constitution") < prompt.index("api.md")


def test_AC_15_inputs_manifest_invalid_fail_closed(tmp_path: Path) -> None:
    """AC-15: manifest 不可解析 / schema_version 不符 / inputs 空 / kind 不在闭集
    → REVIEW_INPUT_MANIFEST_INVALID."""
    bad_version = tmp_path / "m1.yaml"
    bad_version.write_text("schema_version: v9.9.9\ninputs: []\n", encoding="utf-8")
    with pytest.raises(ReviewerError) as ei:
        load_inputs_manifest(bad_version)
    assert ei.value.error.code == "REVIEW_INPUT_MANIFEST_INVALID"

    empty = tmp_path / "m2.yaml"
    empty.write_text("schema_version: v0.1.0\ninputs: []\n", encoding="utf-8")
    with pytest.raises(ReviewerError) as ei:
        load_inputs_manifest(empty)
    assert ei.value.error.code == "REVIEW_INPUT_MANIFEST_INVALID"

    bad_kind = tmp_path / "m3.yaml"
    bad_kind.write_text(
        "schema_version: v0.1.0\ninputs:\n  - kind: warez\n    path: x.md\n",
        encoding="utf-8",
    )
    with pytest.raises(ReviewerError) as ei:
        load_inputs_manifest(bad_kind)
    assert ei.value.error.code == "REVIEW_INPUT_MANIFEST_INVALID"


def test_AC_16_report_records_resolved_inputs(
    fixture_pr_repo: Path, mock_claude_review_approve: list[str]
) -> None:
    """AC-16: review_report.json 记录本次输入面 (kind/authority/实测 hash) —
    可审计 verdict 用什么尺子量出来."""
    import json

    review_input = _make_input(fixture_pr_repo)
    _, report_path = execute_review(
        review_input, claude_cmd=mock_claude_review_approve
    )
    data = json.loads(Path(report_path).read_text(encoding="utf-8"))
    inputs = data["review_inputs"]
    assert inputs is not None
    kinds = [i["kind"] for i in inputs]
    assert kinds[:3] == ["constitution", "spec", "plan"]  # 权威序
    for i in inputs:
        if i["status"] == "loaded":
            assert len(i["content_sha256"]) == 64
