"""Unified CLI dispatcher for `suiyin-flow`.

Routes top-level subcommand to module-specific CLI:
- `verify` → c4_verify.cli  (C4 Verify Contract)
- `task`   → c2_executor.cli (C2 Task Executor)
- `review` → c5_reviewer.cli (C5 AI Reviewer)  — P1.2 加

Bug 3 fix (v0.1.3, P0 spike 2026-05-24 dogfood):
旧 `pyproject.toml` 只把 `suiyin-flow` 绑 `c4_verify.cli:main`, 导致
`suiyin-flow task run ...` 命令报 "invalid choice: 'task' (choose from verify)".
v0.1.3 把 entry point 改成 `suiyin_flow.cli:main` (本模块), 用 dispatcher 路由.
"""

from __future__ import annotations

import sys

from suiyin_flow.c2_executor import cli as c2_cli
from suiyin_flow.c4_verify import cli as c4_cli
from suiyin_flow.c5_reviewer import cli as c5_cli

_USAGE = """\
usage: suiyin-flow {verify,task,review} ...

Subcommands:
  verify   C4 Verify Contract (L1 lint + L2 tests)
  task     C2 Task Executor (单 task 自动从 spec 到 PR)
  review   C5 AI Reviewer (独立 session 审 PR, P1.2)

详细帮助: `suiyin-flow <subcommand> --help`
"""


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print(_USAGE, file=sys.stderr)
        return 2
    if args[0] in ("-h", "--help"):
        print(_USAGE)
        return 0

    cmd = args[0]
    if cmd == "verify":
        return c4_cli.main(args)
    if cmd == "task":
        return c2_cli.main(args)
    if cmd == "review":
        return c5_cli.main(args)

    print(f"suiyin-flow: error: unknown subcommand: {cmd}", file=sys.stderr)
    print(_USAGE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
