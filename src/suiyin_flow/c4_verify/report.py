"""verify_report.json 落盘 + ac_summary 计算.

I1: overall_verdict=pass ⇔ 所有 requested 且 implemented 的 level 都 pass.
I3: ac_summary 即使 P0 不跑 L3 也要填.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from suiyin_flow.c4_verify.contract import (
    CONTRACT_VERSION,
    AcSummary,
    LevelsReport,
    MultiAcViolation,
    OverallVerdict,
    Target,
    TestOutcome,
    VerifyReport,
)
from suiyin_flow.c4_verify.parser import extract_ac_prefixes


def compute_ac_summary(
    requested: list[str],
    test_results: list[TestOutcome],
) -> AcSummary:
    """基于 L2 test results 算 ac_summary.

    - covered: AC-N 至少有 1 个 passing test name 含该 prefix
    - missing: requested - covered
    - multi_ac_violations: 任一 test name 含 ≥2 个 distinct AC-N
    """
    covered_set: set[str] = set()
    violations: list[MultiAcViolation] = []

    for r in test_results:
        prefixes = extract_ac_prefixes(r.test_name)
        unique = list(dict.fromkeys(prefixes))
        if r.status == "passed" and unique:
            covered_set.add(unique[0])
        if len(unique) >= 2:
            violations.append(
                MultiAcViolation(test_name=r.test_name, ac_prefixes_found=unique)
            )

    requested_set = set(requested)
    return AcSummary(
        requested=sorted(requested_set),
        covered=sorted(covered_set & requested_set),
        missing=sorted(requested_set - covered_set),
        multi_ac_violations=violations,
    )


def compute_overall_verdict(levels: LevelsReport) -> OverallVerdict:
    """I1: all (requested & implemented) levels must pass.

    P0 阶段：L1/L2 都 pass → pass；任一 fail → fail.
    L3/L4/L5 P0 不参与判定 (skipped).
    """
    statuses: list[str] = []
    if levels.L1:
        statuses.append(levels.L1.status)
    if levels.L2:
        statuses.append(levels.L2.status)
    if any(s == "fail" for s in statuses):
        return "fail"
    return "pass"


def build_report(
    *,
    target: Target,
    task_id: str | None,
    levels: LevelsReport,
    requested_acs: list[str],
) -> VerifyReport:
    """组装完整 VerifyReport."""
    test_results = levels.L2.test_results if levels.L2 else []
    return VerifyReport(
        target=target,
        task_id=task_id,
        overall_verdict=compute_overall_verdict(levels),
        generated_at=datetime.now(UTC),
        contract_version=CONTRACT_VERSION,
        levels=levels,
        ac_summary=compute_ac_summary(requested_acs, test_results),
    )


def write_report(report: VerifyReport, output_dir: Path) -> Path:
    """落盘 verify_report.json 到 output_dir，返回 latest.json 路径.

    输出 2 个文件:
    - <output_dir>/<timestamp>.json (历史保留)
    - <output_dir>/latest.json (副本，跨平台不用 symlink — Windows 默认不支持)
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = report.generated_at.strftime("%Y%m%dT%H%M%SZ")
    versioned = output_dir / f"{ts}.json"
    latest = output_dir / "latest.json"

    payload = report.model_dump_json(indent=2)
    versioned.write_text(payload, encoding="utf-8")
    latest.write_text(payload, encoding="utf-8")

    return latest
