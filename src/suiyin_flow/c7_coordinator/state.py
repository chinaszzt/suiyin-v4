"""C7 phase-state 落盘 (spec I3).

- versioned: <repo_root>/.suiyin/phase-state/<safe_base_branch>-<run_id>.json
  (run 内每次状态转移后原子覆写: temp + os.replace)
- latest 镜像: latest-<safe_base_branch>.json (resume 入口)
- dry_run 边界 (spec §3.2): versioned 照写 (audit), latest 不更新 (保护 resume)
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from suiyin_flow.c7_coordinator.schema import CoordinatorAbort, CoordinatorState
from suiyin_flow.identity import safe_ref

__all__ = [
    "StateStore",
    "latest_path_for",
    "load_latest",
    "make_run_id",
    "phase_state_dir",
    "safe_ref",  # P0-1: 权威实现移居 suiyin_flow.identity, 此处 re-export 兼容
]


def make_run_id() -> str:
    """时间戳 + pid; 文件名安全且足够唯一."""
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{ts}-{os.getpid()}"


def phase_state_dir(repo_root: Path) -> Path:
    p = repo_root / ".suiyin" / "phase-state"
    p.mkdir(parents=True, exist_ok=True)
    return p


def latest_path_for(repo_root: Path, safe_key: str) -> Path:
    return phase_state_dir(repo_root) / f"latest-{safe_key}.json"


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


class StateStore:
    """单 run 的落盘句柄. write() 在每次状态转移后调用 (先落盘再下一动作)."""

    def __init__(self, repo_root: Path, safe_key: str, run_id: str) -> None:
        self.versioned = phase_state_dir(repo_root) / f"{safe_key}-{run_id}.json"
        self.latest = latest_path_for(repo_root, safe_key)

    def write(self, state: CoordinatorState) -> None:
        state.updated_at = datetime.now(UTC).isoformat()
        text = state.model_dump_json(indent=2)
        _atomic_write(self.versioned, text)
        if not state.dry_run:
            _atomic_write(self.latest, text)


def load_latest(repo_root: Path, safe_key: str) -> CoordinatorState | None:
    """读 latest 镜像; 不存在 → None; 解析失败 → STATE_CORRUPTED."""
    path = latest_path_for(repo_root, safe_key)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return CoordinatorState.model_validate(data)
    except (OSError, ValueError, ValidationError) as e:
        raise CoordinatorAbort(
            "STATE_CORRUPTED",
            f"latest phase-state unreadable: {e}. "
            "Fix or remove it, or rerun with --no-resume.",
            path=str(path),
        ) from e
