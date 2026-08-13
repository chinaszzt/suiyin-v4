"""Acceptance criteria for lane isolation spec v0.1.0."""

from __future__ import annotations

import json
import os
import socket
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import psutil
import pytest

from suiyin_flow.lane import acquire_lane, build_slot, release_lane
from suiyin_flow.lane.allocator import lane_status, load_config
from suiyin_flow.lane.cli import main as lane_cli_main
from suiyin_flow.lane.schema import LaneError


def _write_config(repo_root: Path, **overrides: object) -> None:
    values: dict[str, object] = {
        "schema_version": "v0.1.0",
        "max_lanes": 4,
        "port_base": 38100,
        "db_suffix_template": "lane{n}",
        "max_build_slots": 2,
        "stale_after_seconds": 7200,
    }
    values.update(overrides)
    config_path = repo_root / ".suiyin" / "lanes" / "config.yml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        "\n".join(f"{key}: {json.dumps(value)}" for key, value in values.items()) + "\n",
        encoding="utf-8",
    )


@pytest.mark.ac
def test_AC_1_sequential_lanes_are_distinct_and_reusable(tmp_path: Path) -> None:
    first = acquire_lane(tmp_path)
    second = acquire_lane(tmp_path)

    assert (first.lane_id, second.lane_id) == (0, 1)
    assert first.port != second.port
    assert first.db_suffix != second.db_suffix
    assert first.tmp_dir != second.tmp_dir

    release_lane(tmp_path, first.lane_id)
    replacement = acquire_lane(tmp_path)
    assert replacement.lane_id == first.lane_id
    release_lane(tmp_path, second.lane_id)
    release_lane(tmp_path, replacement.lane_id)


@pytest.mark.ac
def test_AC_2_concurrent_acquire_has_four_unique_winners(tmp_path: Path) -> None:
    _write_config(tmp_path, max_lanes=4)
    barrier = threading.Barrier(8)

    def attempt() -> tuple[str, int | str]:
        barrier.wait()
        try:
            lease = acquire_lane(tmp_path, timeout_seconds=0.15)
        except LaneError as exc:
            return "error", exc.code
        return "ok", lease.lane_id

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: attempt(), range(8)))

    winners = [value for kind, value in results if kind == "ok"]
    errors = [value for kind, value in results if kind == "error"]
    assert len(winners) == 4
    assert len(set(winners)) == 4
    assert errors == ["LANE_EXHAUSTED"] * 4
    for lane_id in winners:
        assert isinstance(lane_id, int)
        release_lane(tmp_path, lane_id)


@pytest.mark.ac
def test_AC_3_dead_pid_lease_is_reclaimed(tmp_path: Path) -> None:
    _write_config(tmp_path, max_lanes=1)
    dead_pid = 2**22
    while psutil.pid_exists(dead_pid):
        dead_pid += 1
    lease_dir = tmp_path / ".suiyin" / "lanes" / "leases" / "lane-0"
    lease_dir.mkdir(parents=True)
    (lease_dir / "lease.json").write_text(
        json.dumps(
            {
                "pid": dead_pid,
                "hostname": socket.gethostname(),
                "acquired_at": datetime.now(UTC).isoformat(),
                "purpose": "dead holder",
            }
        ),
        encoding="utf-8",
    )

    lease = acquire_lane(tmp_path, timeout_seconds=1.2)
    assert lease.lane_id == 0
    assert lease.pid == os.getpid()
    release_lane(tmp_path, lease.lane_id)


@pytest.mark.ac
def test_AC_4_live_lease_is_not_reclaimed(tmp_path: Path) -> None:
    _write_config(tmp_path, max_lanes=1)
    held = acquire_lane(tmp_path)
    with pytest.raises(LaneError, match="LANE_EXHAUSTED") as exc_info:
        acquire_lane(tmp_path, timeout_seconds=0.05)
    assert exc_info.value.code == "LANE_EXHAUSTED"
    assert lane_status(tmp_path).lanes[0].holder == held
    release_lane(tmp_path, held.lane_id)


@pytest.mark.ac
def test_AC_5_tmp_directory_is_empty_on_delivery(tmp_path: Path) -> None:
    old_tmp = tmp_path / ".suiyin" / "lanes" / "tmp" / "lane-0"
    old_tmp.mkdir(parents=True)
    (old_tmp / "residue.txt").write_text("old", encoding="utf-8")
    nested = old_tmp / "nested"
    nested.mkdir()
    (nested / "residue.bin").write_bytes(b"old")

    lease = acquire_lane(tmp_path)
    delivered = Path(lease.tmp_dir)
    assert delivered.is_dir()
    assert list(delivered.iterdir()) == []
    release_lane(tmp_path, lease.lane_id)


@pytest.mark.ac
def test_AC_6_build_slots_limit_concurrency_to_two(tmp_path: Path) -> None:
    _write_config(tmp_path, max_build_slots=2)
    lock = threading.Lock()
    events: list[tuple[str, float]] = []
    active = 0
    peak = 0

    def hold_slot() -> None:
        nonlocal active, peak
        with build_slot(tmp_path, cmd="probe", timeout_seconds=2.0):
            with lock:
                active += 1
                peak = max(peak, active)
                events.append(("enter", time.monotonic()))
            time.sleep(0.05)
            with lock:
                events.append(("exit", time.monotonic()))
                active -= 1

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: hold_slot(), range(4)))

    assert peak <= 2
    assert [kind for kind, _ in events].count("enter") == 4
    assert [kind for kind, _ in events].count("exit") == 4


@pytest.mark.ac
def test_AC_7_slot_run_propagates_exit_and_releases_slot(tmp_path: Path) -> None:
    _write_config(tmp_path, max_build_slots=1)
    result = lane_cli_main(
        [
            "lane",
            "slot",
            "run",
            "--repo-root",
            str(tmp_path),
            "--",
            sys.executable,
            "-c",
            "raise SystemExit(7)",
        ]
    )
    assert result == 7
    assert lane_status(tmp_path).slots[0].held is False


@pytest.mark.ac
def test_AC_8_release_is_idempotent(tmp_path: Path) -> None:
    lease = acquire_lane(tmp_path)
    release_lane(tmp_path, lease.lane_id)
    release_lane(tmp_path, lease.lane_id)
    release_lane(tmp_path, 999)
    assert lane_status(tmp_path).lanes[lease.lane_id].held is False


@pytest.mark.ac
def test_AC_9_config_defaults_and_unknown_version(tmp_path: Path) -> None:
    assert load_config(tmp_path).model_dump() == {
        "schema_version": "v0.1.0",
        "max_lanes": 4,
        "port_base": 38100,
        "db_suffix_template": "lane{n}",
        "max_build_slots": 2,
        "stale_after_seconds": 7200,
    }

    _write_config(tmp_path, schema_version="v9.9.9")
    with pytest.raises(LaneError) as exc_info:
        load_config(tmp_path)
    assert exc_info.value.code == "LANE_CONFIG_INVALID"


@pytest.mark.ac
def test_AC_10_status_reports_holder_pid_and_alive_state(tmp_path: Path) -> None:
    lease = acquire_lane(tmp_path, purpose="status probe")
    with build_slot(tmp_path, cmd="status probe"):
        status = lane_status(tmp_path)
        lane = status.lanes[lease.lane_id]
        slot = next(item for item in status.slots if item.held)
        assert lane.holder is not None
        assert lane.holder.pid == os.getpid()
        assert lane.alive is True
        assert lane.stale is False
        assert slot.holder is not None
        assert slot.holder.pid == os.getpid()
        assert slot.alive is True
        assert slot.stale is False
    release_lane(tmp_path, lease.lane_id)
