"""Cross-platform lane allocation using atomic directory creation."""

from __future__ import annotations

import json
import os
import shutil
import socket
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psutil
import yaml
from pydantic import ValidationError

from suiyin_flow.lane.schema import (
    LaneConfig,
    LaneError,
    LaneLease,
    LaneState,
    LaneStatus,
    SlotHolder,
    SlotState,
)


def _lanes_root(repo_root: str | Path) -> Path:
    return Path(repo_root).resolve() / ".suiyin" / "lanes"


def load_config(repo_root: str | Path) -> LaneConfig:
    """Load lane config, using defaults when the config file is absent."""
    config_path = _lanes_root(repo_root) / "config.yml"
    if not config_path.exists():
        return LaneConfig(schema_version="v0.1.0")

    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        if raw is None:
            raw = {}
        if not isinstance(raw, dict):
            raise ValueError("config root must be a mapping")
        return LaneConfig.model_validate(raw)
    except (OSError, UnicodeError, yaml.YAMLError, ValidationError, ValueError) as exc:
        raise LaneError(
            "LANE_CONFIG_INVALID",
            f"invalid lane config: {config_path}",
            path=str(config_path),
            reason=str(exc),
        ) from exc


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _holder_state(
    holder_path: Path,
    stale_after_seconds: float,
) -> tuple[dict[str, Any] | None, bool | None, bool]:
    """Return parsed holder, local-process liveness, and stale state."""
    try:
        raw: Any = json.loads(holder_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return None, None, True
        pid = raw["pid"]
        hostname = raw["hostname"]
        acquired_at = datetime.fromisoformat(raw["acquired_at"])
        if not isinstance(pid, int) or isinstance(pid, bool) or not isinstance(hostname, str):
            return None, None, True
        if acquired_at.tzinfo is None or acquired_at.utcoffset() is None:
            return None, None, True
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None, None, True

    is_local = hostname == socket.gethostname()
    alive = psutil.pid_exists(pid) if is_local else None
    age_seconds = (_utc_now() - acquired_at.astimezone(UTC)).total_seconds()
    stale = (is_local and alive is False) or age_seconds > stale_after_seconds
    return raw, alive, stale


def _holder_state_for_scan(
    directory: Path,
    holder_name: str,
    stale_after_seconds: float,
) -> tuple[dict[str, Any] | None, bool | None, bool]:
    """Read holder state, allowing an atomic-mkdir winner a brief write window."""
    holder_path = directory / holder_name
    state = _holder_state(holder_path, stale_after_seconds)
    if state[0] is not None:
        return state
    try:
        directory_age = time.time() - directory.stat().st_mtime
    except OSError:
        return state
    initialization_grace = 0.05
    if directory_age < initialization_grace:
        time.sleep(initialization_grace - max(directory_age, 0.0))
        return _holder_state(holder_path, stale_after_seconds)
    return state


def _reclaim(directory: Path, holder_name: str) -> bool:
    """Best-effort stale cleanup; failure means another actor won the race."""
    try:
        (directory / holder_name).unlink(missing_ok=True)
        directory.rmdir()
    except OSError:
        return False
    return True


def _lease_for(
    *,
    config: LaneConfig,
    lanes_root: Path,
    lane_id: int,
    pid: int,
    hostname: str,
    acquired_at: datetime,
    purpose: str | None,
) -> LaneLease:
    return LaneLease(
        lane_id=lane_id,
        port=config.port_base + lane_id,
        db_suffix=config.db_suffix_template.format(n=lane_id),
        tmp_dir=str(lanes_root / "tmp" / f"lane-{lane_id}"),
        pid=pid,
        hostname=hostname,
        acquired_at=acquired_at,
        purpose=purpose,
    )


def _write_lease_metadata(lease_dir: Path, lease: LaneLease) -> None:
    payload = {
        "pid": lease.pid,
        "hostname": lease.hostname,
        "acquired_at": lease.acquired_at.isoformat(),
        "purpose": lease.purpose,
    }
    (lease_dir / "lease.json").write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )


def acquire_lane(
    repo_root: str | Path,
    purpose: str | None = None,
    timeout_seconds: float = 60.0,
) -> LaneLease:
    """Acquire the lowest available lane, blocking until timeout."""
    config = load_config(repo_root)
    lanes_root = _lanes_root(repo_root)
    leases_root = lanes_root / "leases"
    leases_root.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + max(timeout_seconds, 0.0)

    while True:
        reclaimed = False
        for lane_id in range(config.max_lanes):
            lease_dir = leases_root / f"lane-{lane_id}"
            try:
                lease_dir.mkdir()
            except FileExistsError:
                _, _, stale = _holder_state_for_scan(
                    lease_dir, "lease.json", config.stale_after_seconds
                )
                if stale:
                    reclaimed = _reclaim(lease_dir, "lease.json") or reclaimed
                continue
            except OSError:
                continue

            lease = _lease_for(
                config=config,
                lanes_root=lanes_root,
                lane_id=lane_id,
                pid=os.getpid(),
                hostname=socket.gethostname(),
                acquired_at=_utc_now(),
                purpose=purpose,
            )
            try:
                _write_lease_metadata(lease_dir, lease)
                tmp_dir = Path(lease.tmp_dir)
                if tmp_dir.exists():
                    shutil.rmtree(tmp_dir)
                tmp_dir.mkdir(parents=True)
            except FileNotFoundError:
                _reclaim(lease_dir, "lease.json")
                continue
            except OSError:
                _reclaim(lease_dir, "lease.json")
                raise
            return lease

        if reclaimed:
            continue
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise LaneError(
                "LANE_EXHAUSTED",
                f"no lane became available within {timeout_seconds} seconds",
                timeout_seconds=timeout_seconds,
                max_lanes=config.max_lanes,
            )
        time.sleep(min(1.0, remaining))


def release_lane(repo_root: str | Path, lane_id: int) -> None:
    """Release a lane; releasing an absent lane is a successful no-op."""
    lease_dir = _lanes_root(repo_root) / "leases" / f"lane-{lane_id}"
    _reclaim(lease_dir, "lease.json")


def lane_status(repo_root: str | Path) -> LaneStatus:
    """Return a non-mutating snapshot including holder liveness and staleness."""
    config = load_config(repo_root)
    lanes_root = _lanes_root(repo_root)
    lanes: list[LaneState] = []
    slots: list[SlotState] = []

    for lane_id in range(config.max_lanes):
        lease_dir = lanes_root / "leases" / f"lane-{lane_id}"
        if not lease_dir.is_dir():
            lanes.append(LaneState(lane_id=lane_id, held=False))
            continue
        raw, alive, stale = _holder_state(
            lease_dir / "lease.json", config.stale_after_seconds
        )
        lane_holder = None
        if raw is not None:
            try:
                lane_holder = _lease_for(
                    config=config,
                    lanes_root=lanes_root,
                    lane_id=lane_id,
                    pid=raw["pid"],
                    hostname=raw["hostname"],
                    acquired_at=datetime.fromisoformat(raw["acquired_at"]),
                    purpose=raw.get("purpose"),
                )
            except (KeyError, TypeError, ValueError, ValidationError):
                stale = True
        lanes.append(
            LaneState(
                lane_id=lane_id,
                held=True,
                holder=lane_holder,
                alive=alive,
                stale=stale,
            )
        )

    for slot_id in range(config.max_build_slots):
        slot_dir = lanes_root / "slots" / f"slot-{slot_id}"
        if not slot_dir.is_dir():
            slots.append(SlotState(slot_id=slot_id, held=False))
            continue
        raw, alive, stale = _holder_state(
            slot_dir / "holder.json", config.stale_after_seconds
        )
        slot_holder = None
        if raw is not None:
            try:
                slot_holder = SlotHolder.model_validate(raw)
            except ValidationError:
                stale = True
        slots.append(
            SlotState(
                slot_id=slot_id,
                held=True,
                holder=slot_holder,
                alive=alive,
                stale=stale,
            )
        )

    return LaneStatus(lanes=lanes, slots=slots)
