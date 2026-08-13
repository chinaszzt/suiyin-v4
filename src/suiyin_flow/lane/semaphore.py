"""Repository-local build semaphore based on atomic directory creation."""

from __future__ import annotations

import os
import socket
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from suiyin_flow.lane.allocator import (
    _holder_state_for_scan,
    _lanes_root,
    _reclaim,
    _utc_now,
    load_config,
)
from suiyin_flow.lane.schema import LaneError, SlotHolder


@contextmanager
def build_slot(
    repo_root: str | Path,
    cmd: str | None = None,
    timeout_seconds: float = 1800.0,
) -> Iterator[int]:
    """Acquire one build slot and always release it when the context exits."""
    config = load_config(repo_root)
    slots_root = _lanes_root(repo_root) / "slots"
    slots_root.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + max(timeout_seconds, 0.0)
    acquired_slot: tuple[int, Path] | None = None

    while acquired_slot is None:
        reclaimed = False
        for slot_id in range(config.max_build_slots):
            slot_dir = slots_root / f"slot-{slot_id}"
            try:
                slot_dir.mkdir()
            except FileExistsError:
                _, _, stale = _holder_state_for_scan(
                    slot_dir, "holder.json", config.stale_after_seconds
                )
                if stale:
                    reclaimed = _reclaim(slot_dir, "holder.json") or reclaimed
                continue
            except OSError:
                continue

            holder = SlotHolder(
                pid=os.getpid(),
                hostname=socket.gethostname(),
                acquired_at=_utc_now(),
                cmd=cmd,
            )
            try:
                (slot_dir / "holder.json").write_text(
                    holder.model_dump_json(), encoding="utf-8"
                )
            except FileNotFoundError:
                _reclaim(slot_dir, "holder.json")
                continue
            except OSError:
                _reclaim(slot_dir, "holder.json")
                raise
            acquired_slot = (slot_id, slot_dir)
            break

        if acquired_slot is not None:
            break
        if reclaimed:
            continue
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise LaneError(
                "SLOT_TIMEOUT",
                f"no build slot became available within {timeout_seconds} seconds",
                timeout_seconds=timeout_seconds,
                max_build_slots=config.max_build_slots,
            )
        time.sleep(min(1.0, remaining))

    slot_id, slot_dir = acquired_slot
    try:
        yield slot_id
    finally:
        _reclaim(slot_dir, "holder.json")
