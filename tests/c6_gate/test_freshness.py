"""M3 report freshness binding acceptance tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from suiyin_flow.c6_gate.cli import execute_gate
from suiyin_flow.c6_gate.contract import GateContractError, GateInput
from suiyin_flow.treesha import resolve_tree_sha


def _gate_input(
    repo: Path, verify_report: Path, review_report: Path
) -> GateInput:
    return GateInput(
        pr_ref="feature",
        verify_report_path=str(verify_report),
        review_report_path=str(review_report),
        repo_root=str(repo),
        dry_run=True,
    )


def _rewrite(path: Path, **updates: object) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    for key, value in updates.items():
        if value is _MISSING:
            payload.pop(key, None)
        else:
            payload[key] = value
    path.write_text(json.dumps(payload), encoding="utf-8")


_MISSING = object()


def test_AC_freshness_matching_tickets_enter_rules(
    fixture_repo: Path,
    verify_report_pass: Path,
    review_report_approve: Path,
    mock_gh_on_path: Path,
) -> None:
    out = execute_gate(_gate_input(fixture_repo, verify_report_pass, review_report_approve))
    assert out.gate_result == "merged"
    assert out.rules.verify_all_pass is True


def test_AC_freshness_verify_mismatch_fails_before_rules_with_all_shas(
    fixture_repo: Path,
    verify_report_pass: Path,
    review_report_approve: Path,
    mock_gh_on_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = resolve_tree_sha(fixture_repo, "feature")
    stale = "a" * 40
    _rewrite(verify_report_pass, target_tree_sha=stale)

    def rules_must_not_run(**_kwargs: object) -> None:
        pytest.fail("rules evaluated before report freshness validation")

    monkeypatch.setattr("suiyin_flow.c6_gate.cli.evaluate_rules", rules_must_not_run)
    with pytest.raises(GateContractError) as caught:
        execute_gate(_gate_input(fixture_repo, verify_report_pass, review_report_approve))
    assert caught.value.code == "STALE_REPORT"
    assert stale in caught.value.message
    assert current in caught.value.message
    assert f"review={current}" in caught.value.message


def test_AC_freshness_old_review_without_sha_fails_closed(
    fixture_repo: Path,
    verify_report_pass: Path,
    review_report_approve: Path,
    mock_gh_on_path: Path,
) -> None:
    current = resolve_tree_sha(fixture_repo, "feature")
    _rewrite(review_report_approve, target_tree_sha=_MISSING)
    with pytest.raises(GateContractError) as caught:
        execute_gate(_gate_input(fixture_repo, verify_report_pass, review_report_approve))
    assert caught.value.code == "STALE_REPORT"
    assert f"verify={current}" in caught.value.message
    assert "review=missing" in caught.value.message
    assert f"current={current}" in caught.value.message


def test_AC_freshness_unresolvable_current_tree_fails_closed(
    fixture_repo: Path,
    verify_report_pass: Path,
    review_report_approve: Path,
    mock_gh_on_path: Path,
) -> None:
    gate_input = _gate_input(fixture_repo, verify_report_pass, review_report_approve)
    gate_input.pr_ref = "branch-does-not-exist"
    with pytest.raises(GateContractError) as caught:
        execute_gate(gate_input)
    assert caught.value.code == "STALE_REPORT"
    assert "current=missing" in caught.value.message
