"""C6 ff_mergeable 检测 + human:block label 检测.

按 c6 spec §3.1 I1: `ff_mergeable(pr_branch, main)` — base 是否 ff 可达;
`pr.has_label("human:block")` — PR 是否已 human-blocked.

NC-5 跨平台: shutil.which / subprocess.run shell=False.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from suiyin_flow.c6_gate.contract import GateContractError


def _require_tool(name: str) -> str:
    """shutil.which + 异常包装 (NC-5 跨平台 — 跟 C5 同模式).

    Error code 按 tool 分类 (§3.3 b):
      - git 不在 PATH → GIT_ERROR (跟 actions.py 同步)
      - gh 不在 PATH → GH_ERROR
      - 其他 → MISSING_INPUT (退化默认)
    """
    path = shutil.which(name)
    if not path:
        if name == "git":
            code = "GIT_ERROR"
        elif name == "gh":
            code = "GH_ERROR"
        else:
            code = "MISSING_INPUT"
        raise GateContractError(
            code,  # type: ignore[arg-type]
            f"required CLI tool not found on PATH: {name}",
            details={"tool": name},
            retryable=(code != "MISSING_INPUT"),  # GIT/GH_ERROR retryable
        )
    return path


def is_ff_mergeable(
    *,
    pr_ref: str,
    repo_root: Path,
    base: str = "origin/main",
) -> bool:
    """检 pr_ref 是否能 ff-merge 到 base.

    用 `git merge-base --is-ancestor <base> <pr_ref>` —
    base 是 pr_ref 的祖先 → ff 可达 → 返回 True。

    pr_ref 可以是:
      - 本地分支名 (rev-parse OK)
      - PR URL (需要先解析 — 当前 fallback 到 branch lookup via gh)
      - PR 编号 (同上)

    Args:
        pr_ref: PR 引用
        repo_root: 仓库根
        base: 目标 base，默认 origin/main

    Returns False 当 ff 不可达 / pr_ref 解析失败 (caller 用 reason=NOT_FF_MERGEABLE)
    """
    git = _require_tool("git")
    # 先 fetch base 保证 origin/main 是最新的 (race condition 防御 — AC-9 race comment).
    subprocess.run(
        [git, "fetch", "origin", "main"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        shell=False,
        check=False,
    )

    sha = resolve_pr_sha(pr_ref=pr_ref, repo_root=repo_root)
    if sha is None:
        return False

    result = subprocess.run(
        [git, "merge-base", "--is-ancestor", base, sha],
        cwd=repo_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        shell=False,
        check=False,
    )
    # merge-base --is-ancestor exit 0 = is ancestor (ff 可达).
    # exit 1 = not ancestor. exit > 1 = git error.
    if result.returncode > 1:
        raise GateContractError(
            "GIT_ERROR",
            f"git merge-base failed: {result.stderr.strip()}",
            details={"cmd": "git merge-base --is-ancestor", "stderr": result.stderr},
            retryable=True,
        )
    return result.returncode == 0


def resolve_pr_sha(
    *,
    pr_ref: str,
    repo_root: Path,
) -> str | None:
    """把 pr_ref 解析成 commit SHA.

    优先级:
      1. gh pr view <ref> --json headRefOid (URL / 编号都 OK)
      2. git rev-parse <ref> (本地 / 远程 branch name)
      3. 解析失败 → None
    """
    git = _require_tool("git")
    gh = shutil.which("gh")

    # 1. gh CLI 路径 (PR URL / 编号 用)
    if gh and (pr_ref.startswith("http") or pr_ref.lstrip("#").isdigit()):
        result = subprocess.run(
            [gh, "pr", "view", pr_ref.lstrip("#"), "--json", "headRefOid", "-q", ".headRefOid"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            shell=False,
            check=False,
        )
        if result.returncode == 0:
            sha = result.stdout.strip()
            if sha:
                return sha

    # 2. branch name 路径
    for candidate in (pr_ref, f"origin/{pr_ref}"):
        result = subprocess.run(
            [git, "rev-parse", "--verify", candidate],
            cwd=repo_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            shell=False,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip()

    return None


def has_human_block_label(
    *,
    pr_ref: str,
    repo_root: Path,
) -> bool:
    """检 PR 是否有 `human:block` 标签.

    gh 不可用 / pr_ref 不是 URL 或编号 → 退化返回 False (本地 branch 测试场景).
    """
    gh = shutil.which("gh")
    if not gh:
        return False
    if not (pr_ref.startswith("http") or pr_ref.lstrip("#").isdigit()):
        return False

    result = subprocess.run(
        [gh, "pr", "view", pr_ref.lstrip("#"), "--json", "labels", "-q", ".labels[].name"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        shell=False,
        check=False,
    )
    if result.returncode != 0:
        return False
    labels = [ln.strip() for ln in result.stdout.splitlines() if ln.strip()]
    return "human:block" in labels
