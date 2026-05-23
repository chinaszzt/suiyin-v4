"""Python L1+L2 runner: ruff + mypy (L1) + pytest with json-report (L2)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from suiyin_flow.c4_verify.contract import (
    L1Check,
    L1Report,
    L2Report,
    L2Summary,
    LevelStatus,
    TestOutcome,
    TestStatus,
)
from suiyin_flow.c4_verify.parser import primary_ac_prefix
from suiyin_flow.c4_verify.runners._subprocess import (
    require_tool,
    run_subprocess,
    truncate_tail,
)


def run_l1(repo_root: Path) -> L1Report:
    """L1 Static: ruff (lint) + mypy (typecheck).

    `ruff format --check` 可选但增加 dev 摩擦; P0 先只跑 lint + typecheck.
    """
    checks: list[L1Check] = []

    # ruff lint
    ruff_path = require_tool("ruff")
    code, stdout, stderr, dur = run_subprocess(
        [ruff_path, "check", "src", "tests"],
        repo_root,
    )
    checks.append(
        L1Check(
            name="lint",
            tool="ruff",
            exit_code=code,
            stdout_tail=truncate_tail(stdout, stderr),
            duration_seconds=dur,
        )
    )

    # mypy typecheck
    mypy_path = require_tool("mypy")
    code, stdout, stderr, dur = run_subprocess([mypy_path], repo_root)
    checks.append(
        L1Check(
            name="typecheck",
            tool="mypy",
            exit_code=code,
            stdout_tail=truncate_tail(stdout, stderr),
            duration_seconds=dur,
        )
    )

    status: LevelStatus = "pass" if all(c.exit_code == 0 for c in checks) else "fail"
    return L1Report(status=status, checks=checks)


def run_l2(repo_root: Path) -> L2Report:
    """L2 Tests: pytest with --json-report.

    解析 JSON 提取每个 test name + status + AC prefix.
    pytest exit_code: 0=all pass, 1=failures, 2=usage error, 5=no tests collected.
    """
    pytest_path = require_tool("pytest")
    report_dir = repo_root / ".suiyin"
    report_dir.mkdir(parents=True, exist_ok=True)
    json_report = report_dir / "pytest-report.json"

    code, _stdout, _stderr, _dur = run_subprocess(
        [
            pytest_path,
            "--json-report",
            f"--json-report-file={json_report}",
            "-q",
            "tests",
        ],
        repo_root,
    )

    test_results: list[TestOutcome] = []
    summary = L2Summary()

    if json_report.exists():
        data: dict[str, Any] = json.loads(json_report.read_text(encoding="utf-8"))
        for t in data.get("tests", []):
            # pytest nodeid: "tests/c4_verify/test_x.py::test_AC_1_foo" → "test_AC_1_foo"
            test_name = t["nodeid"].rsplit("::", maxsplit=1)[-1]
            outcome = t.get("outcome", "failed")
            test_status: TestStatus = (
                outcome if outcome in ("passed", "failed", "skipped") else "failed"
            )
            failure_msg: str | None = None
            if outcome == "failed":
                call_info = t.get("call", {})
                failure_msg = call_info.get("longrepr") or str(
                    call_info.get("crash", {}).get("message", "")
                )
            test_results.append(
                TestOutcome(
                    test_name=test_name,
                    ac_prefix=primary_ac_prefix(test_name),
                    status=test_status,
                    duration_seconds=float(t.get("duration", 0.0)),
                    failure_message=failure_msg,
                )
            )
        s: dict[str, Any] = data.get("summary", {})
        summary = L2Summary(
            total=int(s.get("total", 0)),
            passed=int(s.get("passed", 0)),
            failed=int(s.get("failed", 0)),
            skipped=int(s.get("skipped", 0)),
        )

    # exit_code 0 = pass; 5 = no tests collected (报 fail，业务一定要有 tests)
    status: LevelStatus = "pass" if code == 0 else "fail"
    return L2Report(status=status, test_results=test_results, summary=summary)
