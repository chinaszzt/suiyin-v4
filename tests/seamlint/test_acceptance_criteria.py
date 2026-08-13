"""Acceptance criteria for seam manifest lint v0.1.0."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from suiyin_flow import cli as unified_cli
from suiyin_flow.seamlint import cli as seamlint_cli
from suiyin_flow.seamlint.lint import run_lint
from suiyin_flow.seamlint.schema import PENDING_TEST_AUTHOR


def _task(task_id: str, depends_on: list[str] | None = None) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "spec_ref": "specs/001-test/spec.md",
        "plan_ref": "specs/001-test/plan.md",
        "verify_cmd": "true",
        "depends_on": depends_on or [],
    }


def _write_tasks(path: Path, tasks: list[dict[str, Any]]) -> None:
    path.write_text(
        yaml.safe_dump(
            {
                "schema_version": "v0.2.0",
                "feature_id": "001-test",
                "tasks": tasks,
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def _entry(
    seam_id: str,
    *,
    provider: str = "T-C",
    consumers: list[str] | None = None,
    test_ref: str | None = "tests/integration/test_seam.py::test_contract",
    **overrides: Any,
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "seam_id": seam_id,
        "kind": "schema",
        "declaration": "type Contract string",
        "provider_task": provider,
        "consumer_tasks": consumers or ["T-A"],
        "source": "contracts/README.md:1-10",
        "test_ref": test_ref,
    }
    entry.update(overrides)
    return entry


def _write_manifest(
    path: Path,
    entries: list[dict[str, Any]],
    *,
    schema_version: str = "v0.1.0",
) -> None:
    path.write_text(
        yaml.safe_dump(
            {
                "schema_version": schema_version,
                "feature_id": "001-test",
                "source_basis": "contracts/README.md v1",
                "entries": entries,
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def _write_chain(tmp_path: Path) -> tuple[Path, Path]:
    """Write T-A -> T-B -> T-C, where arrows point along depends_on."""
    tasks_path = tmp_path / "tasks.yaml"
    manifest_path = tmp_path / "seam-manifest.yaml"
    _write_tasks(
        tasks_path,
        [
            _task("T-C"),
            _task("T-B", ["T-C"]),
            _task("T-A", ["T-B"]),
        ],
    )
    return manifest_path, tasks_path


def test_AC_1_valid_closed_manifest_passes_with_zero_counts(tmp_path: Path) -> None:
    manifest_path, tasks_path = _write_chain(tmp_path)
    _write_manifest(manifest_path, [_entry("SEAM-VALID")])
    report_path = tmp_path / "report.json"

    rc = unified_cli.main(
        [
            "seamlint",
            "run",
            "--manifest",
            str(manifest_path),
            "--tasks-yaml",
            str(tasks_path),
            "--report",
            str(report_path),
        ]
    )

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert rc == 0
    assert report["passed"] is True
    assert all(count == 0 for count in report["counts"].values())


def test_AC_2_draft_manifest_is_rejected_with_promotion_hint(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest_path, tasks_path = _write_chain(tmp_path)
    _write_manifest(
        manifest_path, [_entry("SEAM-DRAFT")], schema_version="draft-v0.1"
    )

    rc = seamlint_cli.main(
        ["seamlint", "run", "--manifest", str(manifest_path), "--tasks-yaml", str(tasks_path)]
    )

    captured = capsys.readouterr()
    assert rc == 2
    assert captured.out == ""
    assert captured.err.startswith("ERROR SEAMLINT_MANIFEST_UNREADABLE:")
    assert "draft 需转正" in captured.err


def test_AC_3_duplicate_kind_and_declaration_errors_are_all_named(tmp_path: Path) -> None:
    manifest_path, tasks_path = _write_chain(tmp_path)
    _write_manifest(
        manifest_path,
        [
            _entry("SEAM-DUPLICATE"),
            _entry("SEAM-DUPLICATE"),
            _entry("SEAM-BAD-KIND", kind="unknown"),
            _entry("SEAM-EMPTY-DECLARATION", declaration=""),
        ],
    )

    report = run_lint(manifest_path, tasks_path)

    invalid = [finding for finding in report.findings if finding.code == "SEAM_ENTRY_INVALID"]
    assert report.passed is False
    assert report.counts["SEAM_ENTRY_INVALID"] == 3
    assert {finding.seam_id for finding in invalid} == {
        "SEAM-DUPLICATE",
        "SEAM-BAD-KIND",
        "SEAM-EMPTY-DECLARATION",
    }


def test_AC_4_unknown_provider_is_blocking(tmp_path: Path) -> None:
    manifest_path, tasks_path = _write_chain(tmp_path)
    _write_manifest(manifest_path, [_entry("SEAM-UNKNOWN", provider="T-MISSING")])

    report = run_lint(manifest_path, tasks_path)

    assert report.passed is False
    assert report.counts["SEAM_TASK_UNKNOWN"] == 1
    assert "T-MISSING" in report.findings[0].message


def test_AC_5_parallel_tasks_without_edge_report_missing_dependency(tmp_path: Path) -> None:
    tasks_path = tmp_path / "tasks.yaml"
    manifest_path = tmp_path / "seam-manifest.yaml"
    _write_tasks(tasks_path, [_task("T-PROVIDER"), _task("T-CONSUMER")])
    _write_manifest(
        manifest_path,
        [
            _entry(
                "SEAM-PARALLEL",
                provider="T-PROVIDER",
                consumers=["T-CONSUMER"],
            )
        ],
    )

    report = run_lint(manifest_path, tasks_path)

    assert report.passed is False
    assert report.counts["SEAM_DEPENDENCY_MISSING"] == 1
    message = next(
        finding.message
        for finding in report.findings
        if finding.code == "SEAM_DEPENDENCY_MISSING"
    )
    assert "T-CONSUMER" in message
    assert "T-PROVIDER" in message
    assert "SEAM-PARALLEL" in message


def test_AC_6_transitive_dependency_reachability_does_not_misreport(tmp_path: Path) -> None:
    manifest_path, tasks_path = _write_chain(tmp_path)
    _write_manifest(manifest_path, [_entry("SEAM-TRANSITIVE")])

    report = run_lint(manifest_path, tasks_path)

    assert report.passed is True
    assert report.counts["SEAM_DEPENDENCY_MISSING"] == 0


def test_AC_7_provider_cannot_also_be_a_consumer(tmp_path: Path) -> None:
    manifest_path, tasks_path = _write_chain(tmp_path)
    _write_manifest(
        manifest_path,
        [_entry("SEAM-SELF", provider="T-C", consumers=["T-C"])],
    )

    report = run_lint(manifest_path, tasks_path)

    assert report.passed is False
    assert report.counts["SEAM_ENTRY_INVALID"] == 1
    assert report.findings[0].seam_id == "SEAM-SELF"
    assert "provider_task" in report.findings[0].message


def test_AC_8_pending_test_hooks_warn_without_failing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest_path, tasks_path = _write_chain(tmp_path)
    _write_manifest(
        manifest_path,
        [
            _entry("SEAM-PENDING-ONE", test_ref=PENDING_TEST_AUTHOR),
            _entry("SEAM-PENDING-TWO", test_ref=PENDING_TEST_AUTHOR),
        ],
    )
    report_path = tmp_path / "report.json"

    rc = seamlint_cli.main(
        [
            "seamlint",
            "run",
            "--manifest",
            str(manifest_path),
            "--tasks-yaml",
            str(tasks_path),
            "--report",
            str(report_path),
        ]
    )

    output = capsys.readouterr().out
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert rc == 0
    assert output.count("SEAM_TEST_PENDING") == 2
    assert "2 pending test hook(s)" in output
    assert report["counts"]["SEAM_TEST_PENDING"] == 2
    assert report["passed"] is True


def test_AC_9_empty_entries_fail_closed(tmp_path: Path) -> None:
    manifest_path, tasks_path = _write_chain(tmp_path)
    _write_manifest(manifest_path, [])

    rc = seamlint_cli.main(
        ["seamlint", "run", "--manifest", str(manifest_path), "--tasks-yaml", str(tasks_path)]
    )

    assert rc == 2


def test_AC_10_entry_identity_and_dependency_findings_are_aggregated(tmp_path: Path) -> None:
    tasks_path = tmp_path / "tasks.yaml"
    manifest_path = tmp_path / "seam-manifest.yaml"
    _write_tasks(tasks_path, [_task("T-ONE"), _task("T-TWO")])
    _write_manifest(
        manifest_path,
        [
            _entry(
                "SEAM-INVALID-ENTRY",
                provider="T-ONE",
                consumers=["T-TWO"],
                kind="not-a-kind",
            ),
            _entry(
                "SEAM-UNKNOWN-TASK",
                provider="T-MISSING",
                consumers=["T-TWO"],
            ),
            _entry(
                "SEAM-MISSING-EDGE",
                provider="T-ONE",
                consumers=["T-TWO"],
            ),
        ],
    )

    report = run_lint(manifest_path, tasks_path)

    assert report.passed is False
    assert report.counts["SEAM_ENTRY_INVALID"] == 1
    assert report.counts["SEAM_TASK_UNKNOWN"] == 1
    assert report.counts["SEAM_DEPENDENCY_MISSING"] == 1
    assert {
        finding.code for finding in report.findings
    } >= {"SEAM_ENTRY_INVALID", "SEAM_TASK_UNKNOWN", "SEAM_DEPENDENCY_MISSING"}


# =============================================================================
# v0.2.0: external_consumers (M4 回放 finding — 跨 feature 消费方表达)
# =============================================================================


def test_AC_11_external_only_consumer_passes(tmp_path: Path) -> None:
    """v0.2.0: consumer_tasks 空 + external_consumers 非空 → 合法, 不产 L2/L3
    (M4 病例: SEAM-CORRECTIONS-ERRORS 真实消费方是 feature 003, 强塞 T003 曾制造假 L3)."""
    manifest_path, tasks_path = _write_chain(tmp_path)
    _write_manifest(
        manifest_path,
        [
            _entry(
                "SEAM-CROSS-FEATURE",
                provider="T-C",
                consumer_tasks=[],
                external_consumers=["003-workbench"],
            )
        ],
        schema_version="v0.2.0",
    )
    report = run_lint(manifest_path, tasks_path)
    assert report.passed is True
    assert report.counts["SEAM_DEPENDENCY_MISSING"] == 0
    assert report.counts["SEAM_TASK_UNKNOWN"] == 0


def test_AC_12_no_consumer_at_all_rejected(tmp_path: Path) -> None:
    """v0.2.0: consumer_tasks 与 external_consumers 都空 → SEAM_ENTRY_INVALID."""
    manifest_path, tasks_path = _write_chain(tmp_path)
    _write_manifest(
        manifest_path,
        [
            _entry(
                "SEAM-NO-CONSUMER",
                provider="T-C",
                consumer_tasks=[],
                external_consumers=[],
            )
        ],
        schema_version="v0.2.0",
    )
    report = run_lint(manifest_path, tasks_path)
    assert report.passed is False
    assert report.counts["SEAM_ENTRY_INVALID"] == 1


def test_AC_13_external_consumers_not_checked_against_tasks(tmp_path: Path) -> None:
    """v0.2.0: external_consumers 自由标识不对 tasks.yaml 校验; 混用时
    consumer_tasks 照常走 L2/L3."""
    manifest_path, tasks_path = _write_chain(tmp_path)
    _write_manifest(
        manifest_path,
        [
            _entry(
                "SEAM-MIXED",
                provider="T-C",
                consumers=["T-A"],
                external_consumers=["cmd/server", "ops"],
            )
        ],
        schema_version="v0.2.0",
    )
    report = run_lint(manifest_path, tasks_path)
    assert report.passed is True
    assert report.counts["SEAM_TASK_UNKNOWN"] == 0
