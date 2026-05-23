"""Dart/Flutter L1+L2 runner.

L1: dart analyze + dart format --output=none --set-exit-if-changed
L2: flutter test --reporter json (NDJSON to stdout)

跨平台:
- macOS/Linux: flutter / dart 在 flutter SDK 的 bin 下
- Windows: flutter.bat / dart.bat shim, shutil.which 自动找到

P0 范围 v4 自身用不到这个 runner (v4 是 Python), 写完后等
v5 业务项目 (Flutter) dogfood 时才会真跑.
"""

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
    """L1: dart analyze + dart format --set-exit-if-changed."""
    checks: list[L1Check] = []
    dart_path = require_tool("dart")

    # dart analyze
    code, stdout, stderr, dur = run_subprocess([dart_path, "analyze"], repo_root)
    checks.append(
        L1Check(
            name="lint",
            tool="dart analyze",
            exit_code=code,
            stdout_tail=truncate_tail(stdout, stderr),
            duration_seconds=dur,
        )
    )

    # dart format check (`--output=none --set-exit-if-changed` 不改文件，只 exit 非 0)
    code, stdout, stderr, dur = run_subprocess(
        [dart_path, "format", "--output=none", "--set-exit-if-changed", "."],
        repo_root,
    )
    checks.append(
        L1Check(
            name="format",
            tool="dart format",
            exit_code=code,
            stdout_tail=truncate_tail(stdout, stderr),
            duration_seconds=dur,
        )
    )

    status: LevelStatus = "pass" if all(c.exit_code == 0 for c in checks) else "fail"
    return L1Report(status=status, checks=checks)


def run_l2(repo_root: Path) -> L2Report:
    """L2: flutter test --reporter json.

    NDJSON output on stdout. 关键 event:
    - testStart: 含 test.id / test.name (含 group 嵌套前缀)
    - testDone: 含 testID / result (success/failure/error) / skipped

    Q4-4 设计决策: group 嵌套时 test.name 是 "groupA AC-1: ..."，
    primary_ac_prefix 正则 \\bAC-\\d+\\b 仍能匹配 — group 不影响.
    """
    flutter_path = require_tool("flutter")

    code, stdout, stderr, _dur = run_subprocess(
        [flutter_path, "test", "--reporter", "json"],
        repo_root,
    )

    name_by_test_id: dict[int, str] = {}
    test_results: list[TestOutcome] = []

    for line in stdout.splitlines():
        if not line.strip():
            continue
        try:
            event: dict[str, Any] = json.loads(line)
        except json.JSONDecodeError:
            continue
        event_type = event.get("type")
        if event_type == "testStart":
            test = event.get("test", {})
            test_id = test.get("id")
            if isinstance(test_id, int):
                name_by_test_id[test_id] = test.get("name", "")
        elif event_type == "testDone":
            tid = event.get("testID")
            test_name = name_by_test_id.get(tid, "") if isinstance(tid, int) else ""
            outcome = event.get("result", "error")  # success / failure / error
            status_map: dict[str, TestStatus] = {
                "success": "passed",
                "failure": "failed",
                "error": "failed",
            }
            test_status: TestStatus = status_map.get(outcome, "failed")
            if event.get("skipped"):
                test_status = "skipped"
            test_results.append(
                TestOutcome(
                    test_name=test_name,
                    ac_prefix=primary_ac_prefix(test_name),
                    status=test_status,
                    duration_seconds=float(event.get("time", 0)) / 1000.0,
                )
            )

    summary = L2Summary(
        total=len(test_results),
        passed=sum(1 for r in test_results if r.status == "passed"),
        failed=sum(1 for r in test_results if r.status == "failed"),
        skipped=sum(1 for r in test_results if r.status == "skipped"),
    )

    # 即使 exit_code != 0, 如果所有 test 都 pass 也可能因 deprecated warning 报错;
    # 但保守起见 exit_code 是权威.
    # 如果 stderr 非空且 exit_code 0, 记 stderr 到 stdout_tail 但 status=pass.
    status: LevelStatus = "pass" if code == 0 else "fail"
    if stderr and code != 0:
        # 没有 testDone 但有 stderr 报错 — 加一条 fake test 记录原因.
        # 否则 caller 看到 status=fail + test_results=[] 会困惑.
        test_results.append(
            TestOutcome(
                test_name="<flutter test infrastructure error>",
                ac_prefix="",
                status="failed",
                duration_seconds=0.0,
                failure_message=truncate_tail("", stderr),
            )
        )
        summary = L2Summary(
            total=len(test_results),
            passed=summary.passed,
            failed=summary.failed + 1,
            skipped=summary.skipped,
        )
    return L2Report(status=status, test_results=test_results, summary=summary)
