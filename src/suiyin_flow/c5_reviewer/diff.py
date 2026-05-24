"""C5 PR diff 拉取 — gh 优先, git 降级 (NC-1 零 SaaS 兼容).

按 C5 spec §3.2 Side Effects: "调用 gh pr diff <pr_ref> 或 git diff <base>...<pr_ref>".
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from suiyin_flow.c5_reviewer.contract import ReviewerError


def fetch_pr_diff(
    pr_ref: str,
    repo_root: Path,
    output_path: Path,
    *,
    base_branch: str = "main",
) -> Path:
    """拉 PR diff 落盘.

    优先级:
    1. gh pr diff <pr_ref> (PR URL 或 PR number)
    2. git diff origin/<base>...<pr_ref> (本地 branch fallback)
    3. git diff <base>...<pr_ref> (origin 不存在时 fallback)

    Args:
        pr_ref: PR URL / PR number / 本地分支名
        repo_root: 业务项目根目录 (subprocess cwd)
        output_path: 落盘绝对路径
        base_branch: 比对 base (默认 main)

    Returns:
        output_path (落盘成功后)

    Raises:
        ReviewerError(PR_DIFF_FETCH_FAILED): 三种方式都失败
        ReviewerError(INVALID_PR_REF): pr_ref 为空
    """
    if not pr_ref or not pr_ref.strip():
        raise ReviewerError("INVALID_PR_REF", "pr_ref is empty")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    attempts: list[dict[str, str]] = []

    # 1. gh pr diff (PR URL 或 number)
    gh_path = shutil.which("gh")
    if gh_path:
        result = subprocess.run(
            [gh_path, "pr", "diff", pr_ref],
            cwd=repo_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            shell=False,
            check=False,
        )
        if result.returncode == 0 and result.stdout:
            output_path.write_text(result.stdout, encoding="utf-8")
            return output_path
        attempts.append({"method": "gh pr diff", "stderr": result.stderr[:200]})

    # 2. git diff origin/<base>...<pr_ref>
    git_attempts = [f"origin/{base_branch}...{pr_ref}", f"{base_branch}...{pr_ref}"]
    for spec in git_attempts:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "diff", spec],
            capture_output=True,
            text=True,
            encoding="utf-8",
            shell=False,
            check=False,
        )
        if result.returncode == 0:
            output_path.write_text(result.stdout, encoding="utf-8")
            return output_path
        attempts.append({"method": f"git diff {spec}", "stderr": result.stderr[:200]})

    raise ReviewerError(
        "PR_DIFF_FETCH_FAILED",
        f"All diff fetch methods failed for pr_ref={pr_ref!r}",
        pr_ref=pr_ref,
        attempts=attempts,
    )
