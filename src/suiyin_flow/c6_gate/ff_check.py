"""C6 ff_mergeable 检测 + human:block label 检测.

按 c6 spec §3.1 I1: `ff_mergeable(pr_branch, main)` — base 是否 ff 可达;
`pr.has_label("human:block")` — PR 是否已 human-blocked.

NC-5 跨平台: shutil.which / subprocess.run shell=False.

**Bug 2 fix (PR #35 dogfood)**: gh CLI 在代理网络下 4/5 概率 `EOF` 报错。
`_gh_with_retry` 包了 3 次指数退避（1s/2s/4s），让 resolve_pr_sha /
has_human_block_label 对 gh 抖动有容错。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from suiyin_flow.c6_gate.contract import GateContractError

# Bug 2 fix: gh 抖动重试参数（指数退避 1s/2s/4s, 总 worst-case ~7s）
_GH_RETRY_ATTEMPTS = 3
_GH_RETRY_BACKOFF_SECONDS: tuple[float, ...] = (1.0, 2.0, 4.0)
# 测试 fixture 设 "1" 时跳过 sleep — 避免 unit test 跑 7s
_GH_RETRY_ENV = "C6_GH_RETRY_NO_SLEEP"


def _gh_with_retry(
    *,
    gh: str,
    args: list[str],
    repo_root: Path,
    label: str,
) -> subprocess.CompletedProcess[str]:
    """跑 `gh <args>`，失败时指数退避重试。

    任何 returncode != 0 都视作可重试（gh 在网络抖动下 EOF/timeout/503 都会非零
    退出；持久错误如 auth fail 重试 N 次也只多花 ~7s，不影响 UX）。最后一次失败
    返回最后那次 CompletedProcess（caller 决定怎么 fallback）。
    """
    no_sleep = os.environ.get(_GH_RETRY_ENV) == "1"
    last: subprocess.CompletedProcess[str] | None = None
    for attempt in range(_GH_RETRY_ATTEMPTS):
        last = subprocess.run(
            [gh, *args],
            cwd=repo_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            shell=False,
            check=False,
        )
        if last.returncode == 0:
            return last
        if attempt + 1 < _GH_RETRY_ATTEMPTS:
            backoff = _GH_RETRY_BACKOFF_SECONDS[attempt]
            print(
                f"[c6 gh retry] {label} attempt {attempt + 1}/{_GH_RETRY_ATTEMPTS} "
                f"failed (rc={last.returncode}); retrying in {backoff:.1f}s. "
                f"stderr: {last.stderr.strip()[:200]}",
                file=sys.stderr,
            )
            if not no_sleep:
                time.sleep(backoff)
    assert last is not None  # _GH_RETRY_ATTEMPTS >= 1
    return last


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
      1. gh pr view <ref> --json headRefOid (URL / 编号都 OK，Bug 2 fix: 带 3 次重试)
      2. git rev-parse <ref> (本地 / 远程 branch name)
      3. 解析失败 → None
    """
    git = _require_tool("git")
    gh = shutil.which("gh")
    is_pr_id = pr_ref.startswith("http") or pr_ref.lstrip("#").isdigit()

    # 1. gh CLI 路径 (PR URL / 编号 用) — Bug 2 fix: 抖动重试
    if gh and is_pr_id:
        result = _gh_with_retry(
            gh=gh,
            args=["pr", "view", pr_ref.lstrip("#"), "--json", "headRefOid", "-q", ".headRefOid"],
            repo_root=repo_root,
            label="resolve_pr_sha gh pr view",
        )
        if result.returncode == 0:
            sha = result.stdout.strip()
            if sha:
                return sha
        else:
            # 全部重试用完仍失败 — 给 caller 一条具体可操作的提示再 fallback
            print(
                f"[c6] gh pr view {pr_ref} failed after {_GH_RETRY_ATTEMPTS} retries; "
                "falling back to `git rev-parse`. If pr_ref is a PR number, the "
                "fallback won't find it — try passing the local branch name instead.",
                file=sys.stderr,
            )

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
    Bug 2 fix: gh 调用带 3 次重试抗抖动。
    """
    gh = shutil.which("gh")
    if not gh:
        return False
    if not (pr_ref.startswith("http") or pr_ref.lstrip("#").isdigit()):
        return False

    result = _gh_with_retry(
        gh=gh,
        args=["pr", "view", pr_ref.lstrip("#"), "--json", "labels", "-q", ".labels[].name"],
        repo_root=repo_root,
        label="has_human_block_label gh pr view",
    )
    if result.returncode != 0:
        # 重试用完仍失败 — 保守返回 False（视作 not blocked，让 4 条规则照常评估;
        # 真 blocked 的话下一次 gate run 会重新检）。打日志让 caller 知道。
        print(
            f"[c6] gh pr view {pr_ref} --json labels failed after {_GH_RETRY_ATTEMPTS} "
            "retries; assuming not human-blocked for this run.",
            file=sys.stderr,
        )
        return False
    labels = [ln.strip() for ln in result.stdout.splitlines() if ln.strip()]
    return "human:block" in labels
