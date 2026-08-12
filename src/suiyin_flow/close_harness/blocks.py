"""本地 human:block 状态管理 (P0-4 拍板: GitHub label 只是可选 adapter).

`.suiyin/blocks/<safe_feature>.json` — versioned (history append-only),
原子覆写 (temp + os.replace, 同 C7 state pattern)。
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from suiyin_flow.close_harness.schema import BlockEvent, BlockState, CloseError
from suiyin_flow.identity import safe_ref


def block_path(repo_root: Path, feature_id: str) -> Path:
    return repo_root / ".suiyin" / "blocks" / f"{safe_ref(feature_id)}.json"


def load_block(repo_root: Path, feature_id: str) -> BlockState:
    path = block_path(repo_root, feature_id)
    if not path.exists():
        return BlockState(feature_id=feature_id)
    try:
        return BlockState.model_validate(
            json.loads(path.read_text(encoding="utf-8"))
        )
    except (OSError, ValueError, ValidationError) as e:
        # 损坏的 block 文件 fail-closed: 当作 blocked, 逼人来看
        raise CloseError(
            "STEP_ERROR",
            f"block state unreadable (treat as blocked, fix or remove): {e}",
            path=str(path),
        ) from e


def _write(repo_root: Path, state: BlockState) -> Path:
    path = block_path(repo_root, state.feature_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(state.model_dump_json(indent=2), encoding="utf-8")
    os.replace(tmp, path)
    return path


def set_block(
    repo_root: Path, feature_id: str, *, reason: str, by: str = ""
) -> BlockState:
    state = load_block(repo_root, feature_id)
    state.blocked = True
    state.reason = reason
    state.history.append(
        BlockEvent(
            action="block",
            reason=reason,
            by=by or os.environ.get("USER", "unknown"),
            ts=datetime.now(UTC).isoformat(),
        )
    )
    _write(repo_root, state)
    return state


def clear_block(
    repo_root: Path, feature_id: str, *, reason: str = "", by: str = ""
) -> BlockState:
    state = load_block(repo_root, feature_id)
    state.blocked = False
    state.reason = ""
    state.history.append(
        BlockEvent(
            action="unblock",
            reason=reason,
            by=by or os.environ.get("USER", "unknown"),
            ts=datetime.now(UTC).isoformat(),
        )
    )
    _write(repo_root, state)
    return state
