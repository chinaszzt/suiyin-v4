"""C2 worktree management — git worktree add/remove wrappers + I8 pid 锁.

I1 invariant: worktree 命名严格 `worktrees/<task_id>`.
I2 invariant: AI session 在 worktree 内启动, 严禁在主仓库工作树跑.
I8 invariant (v0.3.0): 同一 worktree 同时至多一个活跃 C2 run —
`.suiyin/lock` pid 文件, 同 C7 coordinator 锁 pattern (lock.py):
O_CREAT|O_EXCL 原子创建 + psutil 探活 + stale/损坏锁确定性接管.
真闭环 dogfood 发现 #8 的 C2 半边 (C7 spec §7 联动需求 2).
跨平台: pathlib.Path + subprocess shell=False + psutil.pid_exists.
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import psutil

from suiyin_flow.c2_executor.schema import TaskExecutorError


def worktree_path_for(repo_root: Path, task_id: str) -> Path:
    """返回 task 对应的 worktree 绝对路径 (I1 invariant)."""
    return (repo_root / "worktrees" / task_id).resolve()


def worktree_branch_name(task_id: str) -> str:
    """对应分支名: task/<task_id>."""
    return f"task/{task_id}"


def _get_worktree_branch(wt_path: Path) -> str | None:
    """读 worktree 当前分支; 失败返回 None."""
    try:
        result = subprocess.run(
            ["git", "-C", str(wt_path), "branch", "--show-current"],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            shell=False,
        )
        return result.stdout.strip() or None
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def ensure_worktree(
    repo_root: Path,
    task_id: str,
    base_branch: str = "main",
) -> Path:
    """创建或复用 task 对应的 worktree (I1).

    - 不存在 → 从 base_branch 起新 worktree + 新分支 `task/<task_id>`
    - 已存在 + 分支匹配 → 复用 (返回路径)
    - 已存在 + 分支不匹配 → raise WORKTREE_CONFLICT (不覆盖)
    """
    wt_path = worktree_path_for(repo_root, task_id)
    expected_branch = worktree_branch_name(task_id)

    if wt_path.exists():
        actual = _get_worktree_branch(wt_path)
        if actual == expected_branch:
            return wt_path
        raise TaskExecutorError(
            "WORKTREE_CONFLICT",
            f"worktree {wt_path} exists with branch {actual!r}, expected {expected_branch!r}",
            task_id=task_id,
            existing_branch=actual,
            expected_branch=expected_branch,
        )

    # 创建 worktrees/ 父目录 (如果业务项目首次跑 task)
    wt_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(repo_root),
            "worktree",
            "add",
            "-b",
            expected_branch,
            str(wt_path),
            base_branch,
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        shell=False,
    )
    return wt_path


def lock_path_for(worktree_path: Path) -> Path:
    """I8 锁文件路径: <worktree>/.suiyin/lock."""
    return worktree_path / ".suiyin" / "lock"


def _lock_payload(task_id: str) -> str:
    return json.dumps(
        {
            "pid": os.getpid(),
            "task_id": task_id,
            "start_ts": datetime.now(UTC).isoformat(),
        }
    )


def acquire_worktree_lock(worktree_path: Path, task_id: str) -> Path:
    """取 I8 worktree 锁; 活跃持有者存在时 raise WORKTREE_LOCKED.

    同 C7 coordinator 锁语义 (c7_coordinator/lock.py):
    - O_CREAT|O_EXCL 原子创建
    - 已存在 → 读 pid; pid 存活 (psutil) → WORKTREE_LOCKED 拒跑
    - pid 已死 / 锁内容损坏到无法识别持有者 → stale, 确定性接管
    - 自己进程持有的旧锁 (同 pid) 也走接管 (重入安全)
    """
    lock_path = lock_path_for(worktree_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        holder_pid: int | None = None
        try:
            data = json.loads(lock_path.read_text(encoding="utf-8"))
            holder_pid = int(data["pid"])
        except (OSError, ValueError, KeyError, TypeError):
            holder_pid = None  # 损坏锁 = 无法识别持有者 → stale
        if (
            holder_pid is not None
            and holder_pid != os.getpid()
            and psutil.pid_exists(holder_pid)
        ):
            raise TaskExecutorError(
                "WORKTREE_LOCKED",
                f"another C2 run (pid {holder_pid}) is active in this "
                f"worktree: {lock_path}. Refusing to run — concurrent "
                "sessions in one worktree silently race (dogfood finding #8).",
                task_id=task_id,
                lock_path=str(lock_path),
                holder_pid=holder_pid,
            ) from None
        # stale / 自己的旧锁 → 接管 (覆写)
        lock_path.write_text(_lock_payload(task_id), encoding="utf-8")
        return lock_path
    try:
        os.write(fd, _lock_payload(task_id).encode("utf-8"))
    finally:
        os.close(fd)
    return lock_path


def release_worktree_lock(worktree_path: Path) -> None:
    """释放 I8 锁 (幂等; 只删自己 pid 持有的锁, 防误删并发新主)."""
    lock_path = lock_path_for(worktree_path)
    try:
        data = json.loads(lock_path.read_text(encoding="utf-8"))
        if int(data["pid"]) != os.getpid():
            return
    except (OSError, ValueError, KeyError, TypeError):
        pass  # 锁缺失/损坏 → unlink 兜底 (损坏锁没有合法持有者)
    try:
        lock_path.unlink(missing_ok=True)
    except OSError:
        pass


def remove_worktree(repo_root: Path, task_id: str, *, force: bool = False) -> None:
    """删除 worktree (P0 不自动删, 给 cleanup 阶段或人工调用).

    幂等: 不存在则 noop.
    """
    wt_path = worktree_path_for(repo_root, task_id)
    if not wt_path.exists():
        return
    args = ["git", "-C", str(repo_root), "worktree", "remove"]
    if force:
        args.append("--force")
    args.append(str(wt_path))
    subprocess.run(
        args,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        shell=False,
    )
