"""C7 coordinator 单实例锁 (spec I9, 关 dogfood 发现 #8 coordinator 半边).

pid file lock: O_CREAT|O_EXCL 原子创建; 持有者 pid 活 → COORDINATOR_LOCKED 拒跑;
pid 死 (stale) → 确定性接管. 跨平台: psutil.pid_exists.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import psutil

from suiyin_flow.c7_coordinator.schema import CoordinatorAbort


def lock_path_for(repo_root: Path, safe_key: str) -> Path:
    return repo_root / ".suiyin" / "locks" / f"coordinator-{safe_key}.lock"


def _payload(run_id: str) -> str:
    return json.dumps(
        {
            "pid": os.getpid(),
            "run_id": run_id,
            "start_ts": datetime.now(UTC).isoformat(),
        }
    )


def acquire_lock(repo_root: Path, safe_key: str, run_id: str) -> Path:
    """取锁; 活跃持有者存在时 raise COORDINATOR_LOCKED.

    stale 判定: lock file 内 pid 已死, 或内容损坏到无法识别持有者 → 接管.
    """
    lock_path = lock_path_for(repo_root, safe_key)
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
        if holder_pid is not None and psutil.pid_exists(holder_pid):
            raise CoordinatorAbort(
                "COORDINATOR_LOCKED",
                f"another coordinator (pid {holder_pid}) holds the lock for "
                f"this repo + base_branch: {lock_path}. Refusing to run — "
                "concurrent coordinators on the same feature silently race "
                "on task worktrees (dogfood finding #8).",
                lock_path=str(lock_path),
                holder_pid=holder_pid,
            ) from None
        # stale → 接管 (覆写)
        lock_path.write_text(_payload(run_id), encoding="utf-8")
        return lock_path
    try:
        os.write(fd, _payload(run_id).encode("utf-8"))
    finally:
        os.close(fd)
    return lock_path


def release_lock(lock_path: Path) -> None:
    """释放锁 (幂等)."""
    try:
        lock_path.unlink(missing_ok=True)
    except OSError:
        pass
