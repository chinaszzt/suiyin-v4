"""C6 side effect execution — local ff merge / label / comment.

按 c6 spec §3.2 Side Effects + §3.1 I7/I9 atomicity.

**I9 R1 atomicity** (REVIEW_NOT_APPROVE 路径):
  - label add 成 + comment 成 → recovery_action 全字段填好
  - label add 成 + comment 失 → 仍 held + partial_failure=GH_ERROR (R1 部分触发, I7 满足)
  - label add 失 → 整体降级 Error (R1 完全没触发, I7 兜底失效 → caller 介入)

**I5 ff-only merge** — 用本地 `git merge --ff-only` + push, 不用 `gh pr merge`.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from suiyin_flow.c6_gate.contract import (
    Code,
    GateContractError,
    RecoveryAction,
)


def ff_merge_to_main(
    *,
    pr_sha: str,
    repo_root: Path,
    base: str = "main",
    remote: str = "origin",
) -> str:
    """Refs-direct ff push to `<remote>/<base>` — I5 ff-only Main History.

    NC-4 worktree 硬约束下，子 worktree 不能 `git checkout main`（父 worktree
    占着 main）。这里走 `git push <sha>:<base>` + `git update-ref refs/heads/<base>`
    直更 ref，零 checkout，worktree-safe。

    流程：
      1. `git fetch <remote> <base>` — race-condition 防御
         （ff_check 评估时也 fetch 过；幂等）
      2. `git push <remote> <pr_sha>:<base>` — ff-only push（remote 默认拒非 ff）
      3. `git update-ref refs/heads/<base> <pr_sha>` — 本地 base ref 同步前进
         （update-ref 不动 working tree；若 base 在其他 worktree checkout 着，
         该 worktree 的 working tree 变 stale，`git pull` ff 拉齐）

    Returns:
        merged_sha == pr_sha（ff merge 定义下 base 新 HEAD == pr_sha）。

    Raises:
        GateContractError GIT_ERROR — git 命令失败 (retryable)
        GateContractError PERMISSION_DENIED — push 被远程拒 (branch protection)
    """
    git = shutil.which("git")
    if not git:
        raise GateContractError("GIT_ERROR", "git CLI not found on PATH", retryable=False)

    # 1. fetch base — race-condition 防御
    _git(git, ["fetch", remote, base], repo_root, f"fetch {remote} {base}")

    # 2. ff-only push (远程拒非 ff → PERMISSION_DENIED / GIT_ERROR)
    push_res = subprocess.run(
        [git, "push", remote, f"{pr_sha}:{base}"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        shell=False,
        check=False,
    )
    if push_res.returncode != 0:
        stderr_lower = push_res.stderr.lower()
        if "protected branch" in stderr_lower or "rejected" in stderr_lower:
            raise GateContractError(
                "PERMISSION_DENIED",
                f"push to {remote}/{base} rejected (likely branch protection)",
                details={"stderr": push_res.stderr},
                retryable=False,
            )
        raise GateContractError(
            "GIT_ERROR",
            f"git push failed: {push_res.stderr.strip()}",
            details={"stderr": push_res.stderr},
            retryable=True,
        )

    # 3. 本地 refs/heads/<base> 同步前进。worktree-safe — update-ref 不动 working tree。
    _git(
        git,
        ["update-ref", f"refs/heads/{base}", pr_sha],
        repo_root,
        f"update-ref refs/heads/{base}",
    )

    # 4. ff merge 定义下 merged_sha == pr_sha
    return pr_sha


def execute_r1_recovery(
    *,
    pr_ref: str,
    findings: list[dict[str, Any]],
    repo_root: Path,
) -> RecoveryAction:
    """I9 R1 atomicity — label add → comment.

    pr_ref 必须是 URL / 编号 (gh pr edit 不接 branch name)。本地 branch
    模式（无 PR）时 caller 应该跳过 R1 / 走 dry_run；这里 fail-fast.

    Returns:
        RecoveryAction with 完整 / partial / partial_failure 状态。

    Raises:
        GateContractError GH_ERROR — label add 失败时降级 (I7 兜底失效场景)
        GateContractError PERMISSION_DENIED — gh auth 权限不足
        GateContractError MISSING_INPUT — pr_ref 不是 URL/编号
    """
    if not (pr_ref.startswith("http") or pr_ref.lstrip("#").isdigit()):
        raise GateContractError(
            "MISSING_INPUT",
            f"R1 requires PR URL or number, got branch-like ref: {pr_ref}",
            details={"pr_ref": pr_ref},
        )

    gh = shutil.which("gh")
    if not gh:
        raise GateContractError(
            "GH_ERROR",
            "gh CLI not found on PATH (R1 needs it)",
            details={"tool": "gh"},
            retryable=False,
        )

    pr_id = pr_ref.lstrip("#")

    # 1. label add (idempotent — gh pr edit 加已存在 label 不报错)
    label_res = subprocess.run(
        [gh, "pr", "edit", pr_id, "--add-label", "human:block"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        shell=False,
        check=False,
    )
    if label_res.returncode != 0:
        stderr_lower = label_res.stderr.lower()
        is_perm = "forbidden" in stderr_lower or "permission" in stderr_lower
        code: Code = "PERMISSION_DENIED" if is_perm else "GH_ERROR"
        raise GateContractError(
            code,
            f"gh pr edit --add-label failed: {label_res.stderr.strip()}",
            details={"stderr": label_res.stderr, "pr_ref": pr_ref},
            retryable=(code == "GH_ERROR"),
        )

    # 2. comment (I9 — label 成 + comment 失 仍 held + partial_failure)
    body = render_findings_comment(findings)
    comment_res = subprocess.run(
        [gh, "pr", "comment", pr_id, "--body", body],
        cwd=repo_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        shell=False,
        check=False,
    )
    if comment_res.returncode != 0:
        # I9: label 成功 + comment 失败 → partial recovery, 不降级 Error.
        return RecoveryAction(
            kind="r1_label_and_comment",
            label_added=True,
            comment_posted=False,
            partial_failure="GH_ERROR",
        )

    comment_url = comment_res.stdout.strip() or None
    return RecoveryAction(
        kind="r1_label_and_comment",
        label_added=True,
        comment_posted=True,
        comment_url=comment_url,
    )


def render_findings_comment(findings: list[dict[str, Any]]) -> str:
    """渲染 PR comment body — 严格用 C5 finding 四字段 (§3.2 / AC-3).

    `severity / category / location / suggested_fix` — **不引用** phantom
    `summary` 字段 (C5 §2.2 finding required 只有这 4 个)。
    """
    n = len(findings)
    lines = [
        "## C6 Gate Contract — Block Recovery R1",
        "",
        f"C5 verdict=`block` 触发 R1（共 {n} 条 findings）。PR 已加 `human:block` 标签。",
        "",
        "| Severity | Category | Location | Suggested Fix |",
        "|---|---|---|---|",
    ]
    for f in findings:
        sev = _md_cell(f.get("severity", ""))
        cat = _md_cell(f.get("category", ""))
        loc = _md_cell(f.get("location", ""))
        fix = _md_cell(f.get("suggested_fix", ""))
        lines.append(f"| {sev} | {cat} | {loc} | {fix} |")
    lines.extend(
        [
            "",
            "**R1 协议**：请人工 fix → 重新打开 review → 移除 `human:block` 标签",
            "→ 重跑 `suiyin-flow gate run`。",
            "(P1.3 起 R2 自动 retry-with-feedback；详 c6 spec §3.1 I7/I9)",
        ]
    )
    return "\n".join(lines)


def _md_cell(s: str) -> str:
    """转义 markdown table cell — `|` 和换行."""
    return s.replace("|", r"\|").replace("\n", " ").replace("\r", " ")


def _git(git: str, args: list[str], cwd: Path, label: str) -> str:
    """subprocess 包装 — git 命令失败转 GATE_ERROR."""
    res = subprocess.run(
        [git, *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        shell=False,
        check=False,
    )
    if res.returncode != 0:
        raise GateContractError(
            "GIT_ERROR",
            f"git {label} failed: {res.stderr.strip()}",
            details={"cmd": label, "stderr": res.stderr},
            retryable=True,
        )
    return res.stdout
