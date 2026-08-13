"""CLI for lane allocation and the build semaphore."""

from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
from pathlib import Path

from suiyin_flow.lane.allocator import acquire_lane, lane_status, release_lane
from suiyin_flow.lane.schema import LaneError
from suiyin_flow.lane.semaphore import build_slot


def _make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="suiyin-flow", description="Lane isolation")
    top = parser.add_subparsers(dest="top_command", required=True)
    lane_parser = top.add_parser("lane", help="allocate isolated execution lanes")
    lane_commands = lane_parser.add_subparsers(dest="lane_command", required=True)

    acquire_parser = lane_commands.add_parser("acquire", help="acquire a lane")
    acquire_parser.add_argument("--repo-root", required=True)
    acquire_parser.add_argument("--purpose")
    acquire_parser.add_argument("--timeout", type=float, default=60.0)

    release_parser = lane_commands.add_parser("release", help="release a lane")
    release_parser.add_argument("--repo-root", required=True)
    release_parser.add_argument("--lane-id", type=int, required=True)

    status_parser = lane_commands.add_parser("status", help="show lane and slot status")
    status_parser.add_argument("--repo-root", required=True)

    slot_parser = lane_commands.add_parser("slot", help="build semaphore operations")
    slot_commands = slot_parser.add_subparsers(dest="slot_command", required=True)
    run_parser = slot_commands.add_parser("run", help="run a command while holding a slot")
    run_parser.add_argument("--repo-root", required=True)
    run_parser.add_argument("--timeout", type=float, default=1800.0)
    run_parser.add_argument("cmd", nargs=argparse.REMAINDER)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _make_parser()
    args = parser.parse_args(argv)
    try:
        repo_root = Path(args.repo_root).resolve()
        if args.lane_command == "acquire":
            lease = acquire_lane(repo_root, purpose=args.purpose, timeout_seconds=args.timeout)
            print(lease.model_dump_json())
            return 0
        if args.lane_command == "release":
            release_lane(repo_root, args.lane_id)
            return 0
        if args.lane_command == "status":
            print(lane_status(repo_root).model_dump_json(indent=2))
            return 0
        if args.lane_command == "slot" and args.slot_command == "run":
            command: list[str] = args.cmd
            if command and command[0] == "--":
                command = command[1:]
            if not command:
                parser.error("lane slot run requires a command after --")
            with build_slot(
                repo_root,
                cmd=shlex.join(command),
                timeout_seconds=args.timeout,
            ):
                return subprocess.run(command, shell=False, check=False).returncode
    except LaneError as exc:
        print(f"ERROR {exc.code}: {exc.message}", file=sys.stderr)
        return 2

    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
