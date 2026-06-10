"""C7 整合原语 — ff 判定 / refs-direct 前进 / rebase / 重 verify / 清理.

spec §3.2 + §7:
- ff-merge 零 checkout (学 C6 v0.1.3 教训): merge-base --is-ancestor 判定 +
  update-ref CAS (带 old-value) 前进 base ref. base_branch 几乎必然被某个
  worktree checkout, 一切 checkout 路径禁用.
- rebase 在 task 自己的 worktree 内; conflict → rebase --abort 还原.
- verify_cmd: shlex.split + shell=False, cwd=worktree (同 NC-5 工程约定).
"""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

from suiyin_flow.c2_executor.worktree import remove_worktree
from suiyin_flow.c7_coordinator.schema import CoordinatorAbort


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        shell=False,
        check=False,
    )


def rev_parse(repo: Path, ref: str) -> str | None:
    result = _git(repo, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def is_ancestor(repo: Path, maybe_ancestor: str, descendant: str) -> bool:
    result = _git(repo, "merge-base", "--is-ancestor", maybe_ancestor, descendant)
    return result.returncode == 0


def ff_advance(repo: Path, base_branch: str, new_sha: str, expected_old: str) -> bool:
    """refs-direct ff 前进 base ref. CAS (old-value) 防 race; 失败返回 False.

    caller 必须先用 is_ancestor 确认 ff 可达 (I7).
    """
    result = _git(
        repo, "update-ref", f"refs/heads/{base_branch}", new_sha, expected_old
    )
    return result.returncode == 0


def rebase_onto(worktree: Path, base_branch: str) -> bool:
    """task worktree 内 rebase 到 base HEAD. clean → True; conflict → abort 还原 → False.

    Raises:
        CoordinatorAbort(GIT_ERROR): rebase 和 abort 双双失败 (仓库异常).
    """
    result = _git(worktree, "rebase", base_branch)
    if result.returncode == 0:
        return True
    abort = _git(worktree, "rebase", "--abort")
    if abort.returncode != 0:
        raise CoordinatorAbort(
            "GIT_ERROR",
            f"rebase failed AND abort failed in {worktree}: "
            f"{(result.stderr or '').strip()[-500:]}",
            retryable=True,
            worktree=str(worktree),
        )
    return False


def run_verify(worktree: Path, verify_cmd: str) -> bool:
    """rebase 后重跑 task 的 verify_cmd (I10). 绿 = True."""
    try:
        result = subprocess.run(
            shlex.split(verify_cmd),
            cwd=str(worktree),
            capture_output=True,
            text=True,
            encoding="utf-8",
            shell=False,
            check=False,
        )
    except (OSError, ValueError):
        return False
    return result.returncode == 0


def cleanup_merged(repo: Path, task_id: str) -> None:
    """merged task 清理 (I11): worktree 删 + 本地 task/<id> 分支删.

    best-effort — 清理失败不影响 merge 已成立的事实, 不抛.
    force=True: worktree 内 node_modules 等未跟踪产物属预期.
    """
    try:
        remove_worktree(repo, task_id, force=True)
    except (subprocess.CalledProcessError, OSError):
        pass
    _git(repo, "branch", "-D", f"task/{task_id}")
