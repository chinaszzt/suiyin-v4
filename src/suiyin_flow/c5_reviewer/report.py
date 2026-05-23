"""C5 review_report.json 落盘 + Block Recovery R1 (human:block 标签).

按 C5 spec §3.2 Side Effects + §7 "Block Recovery".

v0.1.1 Block Recovery R1: C5 verdict=block 时
  1. gh pr edit <pr> --add-label "human:block"
  2. gh pr comment <pr> --body "<findings 摘要>"
  3. 不重试 (R2 P1.3 加)
"""

from __future__ import annotations

import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from suiyin_flow.c5_reviewer.contract import (
    CONTRACT_VERSION,
    Arbitration,
    Finding,
    ReviewerError,
    ReviewInput,
    ReviewReport,
    Verdict,
)


def build_report(
    *,
    review_input: ReviewInput,
    verdict: Verdict,
    findings: list[Finding],
    session_id: str,
    arbitration: Arbitration | None = None,
) -> ReviewReport:
    """组装 ReviewReport (跟 spec §2.2 字段对齐)."""
    return ReviewReport(
        verdict=verdict,
        findings=findings,
        reviewed_at=datetime.now(UTC),
        session_id=session_id,
        task_id=review_input.task_id,
        pr_ref=review_input.pr_ref,
        contract_version=CONTRACT_VERSION,
        arbitration=arbitration,
    )


def write_report(report: ReviewReport, output_dir: Path) -> Path:
    """落盘 review_report.json + latest.json 副本.

    Returns latest.json absolute path.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = report.reviewed_at.strftime("%Y%m%dT%H%M%SZ")
    versioned = output_dir / f"{ts}.json"
    latest = output_dir / "latest.json"

    payload = report.model_dump_json(indent=2)
    versioned.write_text(payload, encoding="utf-8")
    # 跨平台兼容: Windows 不支持 symlink → 用 copy (NC-5)
    latest.write_text(payload, encoding="utf-8")

    return latest


def apply_block_recovery_r1(
    *,
    pr_ref: str,
    findings: list[Finding],
    repo_root: Path,
) -> bool:
    """v0.1.1 Block Recovery R1: 给 PR 加 `human:block` 标签 + comment findings.

    Best effort: gh 不可用 / 不是 PR ref → 静默跳过.
    P1.3 R2 (C2 retry with feedback) 之前的兜底.

    Returns:
        True = 成功加标签 + comment; False = 跳过 (gh 不可用 / 非 PR ref / 失败)
    """
    gh_path = shutil.which("gh")
    if not gh_path:
        return False
    # pr_ref 必须是 URL 或 PR number (gh pr edit 不接受 branch name)
    is_pr_ref = pr_ref.startswith("http") or pr_ref.isdigit()
    if not is_pr_ref:
        return False

    # 1. 加 human:block 标签
    label_result = subprocess.run(
        [gh_path, "pr", "edit", pr_ref, "--add-label", "human:block"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        shell=False,
        check=False,
    )
    if label_result.returncode != 0:
        return False

    # 2. comment findings 摘要
    body = _render_findings_comment(findings)
    comment_result = subprocess.run(
        [gh_path, "pr", "comment", pr_ref, "--body", body],
        cwd=repo_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        shell=False,
        check=False,
    )
    return comment_result.returncode == 0


def _render_findings_comment(findings: list[Finding]) -> str:
    """格式化 findings 为 markdown body for gh pr comment."""
    lines = [
        "## C5 AI Reviewer — Block Recovery R1",
        "",
        f"v0.1.1: verdict=`block`, 共 {len(findings)} 条 findings (含 block 集合任一即触发).",
        "",
        "| Severity | Category | Location | Suggested Fix |",
        "|---|---|---|---|",
    ]
    for f in findings:
        # 转义 markdown table 内 `|` 字符
        loc = f.location.replace("|", r"\|")
        fix = f.suggested_fix.replace("|", r"\|").replace("\n", " ")
        lines.append(f"| {f.severity} | {f.category} | {loc} | {fix} |")
    lines.extend(
        [
            "",
            "**Block Recovery R1**: PR 已加 `human:block` 标签。请人工 fix + 重新打开 review。",
            "(P1.3 起 R2 自动 retry-with-feedback, 见 C5 spec §7 Block Recovery)",
        ]
    )
    return "\n".join(lines)


def validate_repo_root(repo_root: Path) -> None:
    """REPO_ROOT_NOT_FOUND 校验."""
    if not repo_root.exists() or not repo_root.is_dir():
        raise ReviewerError(
            "REPO_ROOT_NOT_FOUND",
            f"repo_root not a directory: {repo_root}",
            repo_root=str(repo_root),
        )
