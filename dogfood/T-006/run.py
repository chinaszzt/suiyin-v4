#!/usr/bin/env python3
"""T-006 mini-dogfood — 跑 C2 `task batch` 真 CLI 验证 3 个场景 + 落 evidence.

按 dogfood/T-006/spec.md AC-501..AC-505.

Run:
    python dogfood/T-006/run.py

Output:
    - dogfood/T-006/results/<scenario>-{stdout,stderr,exit_code}.txt × 3
    - dogfood/T-006/results/README.md (汇总)
    - 退出码 0 = 全 pass，非 0 = 至少一个场景 actual ≠ expected
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

WORKTREE_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = WORKTREE_ROOT / "dogfood" / "T-006" / "fixtures"
RESULTS_DIR = WORKTREE_ROOT / "dogfood" / "T-006" / "results"

SUIYIN_FLOW_CMD = [sys.executable, "-m", "suiyin_flow.cli"]


def _run(cmd: list[str]) -> tuple[int, str, str]:
    """Run cmd, return (exit_code, stdout, stderr)."""
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        shell=False,
        check=False,
    )
    return proc.returncode, proc.stdout, proc.stderr


def _dump(scenario: str, exit_code: int, stdout: str, stderr: str) -> None:
    """Dump evidence to results/."""
    (RESULTS_DIR / f"{scenario}-stdout.txt").write_text(stdout, encoding="utf-8")
    (RESULTS_DIR / f"{scenario}-stderr.txt").write_text(stderr, encoding="utf-8")
    (RESULTS_DIR / f"{scenario}-exit_code.txt").write_text(str(exit_code), encoding="utf-8")


def _check(condition: bool, label: str, scenario: str) -> str:
    """Return ✓/✗ line; tracker accumulates pass/fail counts via caller."""
    return f"  {'✓' if condition else '✗'} {label}"


def main() -> int:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    all_pass = True
    summary_lines: list[str] = [
        "# T-006 mini-dogfood results",
        "",
        f"Worktree: `{WORKTREE_ROOT}`",
        f"suiyin-flow cmd: `{' '.join(SUIYIN_FLOW_CMD)}`",
        "",
    ]

    # ============================================================
    # AC-502: happy dry-run
    # ============================================================
    scenario = "1-happy-dry-run"
    yaml_path = FIXTURE_DIR / "tasks-happy.yaml"
    rc, out, err = _run(
        SUIYIN_FLOW_CMD
        + [
            "task",
            "batch",
            "--tasks-yaml",
            str(yaml_path),
            "--repo-root",
            str(WORKTREE_ROOT),
            "--dry-run",
        ]
    )
    _dump(scenario, rc, out, err)

    summary_lines.append(f"## Scenario {scenario}")
    summary_lines.append(f"- exit_code: `{rc}` (expected 0)")
    try:
        payload: dict[str, Any] = json.loads(out)
    except json.JSONDecodeError as e:
        payload = {}
        summary_lines.append(f"- ✗ stdout JSON parse failed: {e}")
        all_pass = False

    checks: list[tuple[bool, str]] = [
        (rc == 0, "exit code = 0"),
        (payload.get("status") == "dry_run", 'status == "dry_run"'),
        (
            [t.get("task_id") for t in payload.get("tasks", [])] == ["T-201", "T-202", "T-203"],
            "task order = T-201, T-202, T-203",
        ),
        (
            all(t.get("status") == "dry_run" for t in payload.get("tasks", [])),
            "all tasks status = dry_run",
        ),
        (payload.get("stopped_at_task_id") is None, "stopped_at_task_id == null"),
        (payload.get("feature_name") == "dogfood-T-006-happy", "feature_name passed through"),
    ]
    for ok, label in checks:
        if not ok:
            all_pass = False
        summary_lines.append(_check(ok, label, scenario))
    summary_lines.append("")

    # ============================================================
    # AC-503: missing required field (verify_cmd)
    # ============================================================
    scenario = "2-missing-verify-cmd"
    yaml_path = FIXTURE_DIR / "tasks-missing-verify.yaml"
    rc, out, err = _run(
        SUIYIN_FLOW_CMD
        + [
            "task",
            "batch",
            "--tasks-yaml",
            str(yaml_path),
            "--repo-root",
            str(WORKTREE_ROOT),
        ]
    )
    _dump(scenario, rc, out, err)

    summary_lines.append(f"## Scenario {scenario}")
    summary_lines.append(f"- exit_code: `{rc}` (expected 2)")
    try:
        err_payload: dict[str, Any] = json.loads(err)
    except json.JSONDecodeError as e:
        err_payload = {}
        summary_lines.append(f"- ✗ stderr JSON parse failed: {e}")
        all_pass = False

    checks = [
        (rc == 2, "exit code = 2"),
        (err_payload.get("code") == "INVALID_MANIFEST", 'stderr.code == "INVALID_MANIFEST"'),
        ("verify_cmd" in err_payload.get("message", ""), "message mentions verify_cmd"),
    ]
    for ok, label in checks:
        if not ok:
            all_pass = False
        summary_lines.append(_check(ok, label, scenario))
    summary_lines.append("")

    # ============================================================
    # AC-504: depends_on order violation
    # ============================================================
    scenario = "3-order-violation"
    yaml_path = FIXTURE_DIR / "tasks-order-violation.yaml"
    rc, out, err = _run(
        SUIYIN_FLOW_CMD
        + [
            "task",
            "batch",
            "--tasks-yaml",
            str(yaml_path),
            "--repo-root",
            str(WORKTREE_ROOT),
        ]
    )
    _dump(scenario, rc, out, err)

    summary_lines.append(f"## Scenario {scenario}")
    summary_lines.append(f"- exit_code: `{rc}` (expected 2)")
    try:
        err_payload = json.loads(err)
    except json.JSONDecodeError as e:
        err_payload = {}
        summary_lines.append(f"- ✗ stderr JSON parse failed: {e}")
        all_pass = False

    checks = [
        (rc == 2, "exit code = 2"),
        (err_payload.get("code") == "INVALID_MANIFEST", 'stderr.code == "INVALID_MANIFEST"'),
        (
            "BATCH_ORDER_VIOLATION" in err_payload.get("message", ""),
            "message mentions BATCH_ORDER_VIOLATION",
        ),
        ("T-402" in err_payload.get("message", ""), "message names offending dep (T-402)"),
    ]
    for ok, label in checks:
        if not ok:
            all_pass = False
        summary_lines.append(_check(ok, label, scenario))
    summary_lines.append("")

    # ============================================================
    # Summary
    # ============================================================
    summary_lines.append("---")
    summary_lines.append(
        f"## Overall: {'✓ ALL PASS' if all_pass else '✗ AT LEAST ONE FAILURE'}"
    )

    (RESULTS_DIR / "README.md").write_text("\n".join(summary_lines), encoding="utf-8")

    print("\n".join(summary_lines))
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
