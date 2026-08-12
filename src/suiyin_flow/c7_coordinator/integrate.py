"""C7 整合原语 — ff 判定 / refs-direct 前进 / rebase / 重 verify / 清理.

spec §3.2 + §7:
- ff-merge 零 checkout (学 C6 v0.1.3 教训): merge-base --is-ancestor 判定 +
  update-ref CAS (带 old-value) 前进 base ref. base_branch 几乎必然被某个
  worktree checkout, 一切 checkout 路径禁用.
- rebase 在 task 自己的 worktree 内; conflict → rebase --abort 还原.
- verify_cmd: shell=True, cwd=worktree (用户 shell 命令含 && 等, 必须 shell 跑;
  发现 #2 根因 — shlex.split + shell=False 不解释 &&).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from suiyin_flow.c2_executor.worktree import remove_worktree
from suiyin_flow.c7_coordinator.schema import CoordinatorAbort
from suiyin_flow.identity import task_branch


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


def run_verify(worktree: Path, verify_cmd: str) -> tuple[bool, str]:
    """rebase 后重跑 task 的 verify_cmd (I10). 返回 (绿?, 输出尾部).

    **shell=True 跑 verify_cmd 字符串**（不 shlex.split）——verify_cmd 是
    用户 / sy-tasks 定义的 shell 命令, 常含 `&&` / `|` 等操作符（例
    `npm install && npm run typecheck && npx vitest`）。C2 阶段由 AI 在 bash 内
    跑, C7 reverify 必须等价用 shell 跑；否则 shlex.split + shell=False 会把
    `&&` 当**字面参数**（实测 `echo a && echo b` → 输出 `a && echo b`）→ 复合
    命令必失败 → REVERIFY_FAILED 误 park 健康代码（**r4 真闭环发现 #2 根因**）。
    与 C2 §7「shell=False + list args」约定不冲突：那约定针对 C7 自己构造的固定
    args（git / claude CLI），verify_cmd 是用户 shell 字符串, 性质不同。跨平台:
    shell=True POSIX 走 /bin/sh、Windows 走 cmd, `&&` 两边都支持。

    返回 output tail（发现 #3）: park REVERIFY_FAILED 时存进 TaskRecord 供诊断,
    不再只留 bool（旧版失败只能人去 worktree 手动复现）。
    """
    try:
        result = subprocess.run(
            verify_cmd,
            cwd=str(worktree),
            capture_output=True,
            text=True,
            encoding="utf-8",
            shell=True,  # verify_cmd 是受信 shell 命令 (见 docstring)
            check=False,
        )
    except OSError as e:
        return False, f"reverify failed to start: {e}"
    tail = ((result.stdout or "") + (result.stderr or ""))[-2000:]
    return result.returncode == 0, tail


def cleanup_merged(repo: Path, feature_id: str, task_id: str) -> None:
    """merged task 清理 (I11): worktree 删 + 本地 task/<feature>/<id> 分支删.

    best-effort — 清理失败不影响 merge 已成立的事实, 不抛.
    force=True: worktree 内 node_modules 等未跟踪产物属预期.
    """
    try:
        remove_worktree(repo, feature_id, task_id, force=True)
    except (subprocess.CalledProcessError, OSError):
        pass
    _git(repo, "branch", "-D", task_branch(feature_id, task_id))
