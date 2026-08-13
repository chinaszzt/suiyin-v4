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

from suiyin_flow.acgate import cli as acgate_cli
from suiyin_flow.authz import cli as authz_cli
from suiyin_flow.c1_planning import cli as c1_cli
from suiyin_flow.c2_executor import cli as c2_cli
from suiyin_flow.c4_verify import cli as c4_cli
from suiyin_flow.c5_reviewer import cli as c5_cli
from suiyin_flow.c6_gate import cli as c6_cli
from suiyin_flow.c7_coordinator import cli as c7_cli
from suiyin_flow.close_harness import cli as close_cli
from suiyin_flow.lane import cli as lane_cli
from suiyin_flow.mutation import cli as mutation_cli
from suiyin_flow.seamlint import cli as seamlint_cli
from suiyin_flow.testauthor import cli as testauthor_cli

_USAGE = """\
usage: suiyin-flow {plan,verify,task,review,gate,phase,acgate,authz,mutation,testauthor,close} ...

Subcommands:
  plan     C1 Planning Engine (tasks.yaml → execution_plan 依赖分层 + 并行组, P1.3)
  verify   C4 Verify Contract (L1 lint + L2 tests)
  task     C2 Task Executor (单 task 自动从 spec 到 PR)
  review   C5 AI Reviewer (独立 session 审 PR, P1.2)
  gate     C6 Gate Contract (自动 merge gate, P1.2 阶段 3.2)
  phase    C7 Phase Coordinator (逐 phase 调度 + ff-merge 回 feature, P1.3)
  acgate   AC 冻结闸 (行为/守卫测试 diff 拦截, gen4-plan P0-2)
  authz    Authorization manifest 静态写权闸 (gen4-plan M3 件 3)
  mutation Mutation 探针 (冻结测试证伪力验证, gen4-plan P0-3)
  testauthor 独立测试作者 (契约驱动红测试 + AC freeze, M5 前置 1)
  close    Feature 收口 harness (C4→C5→C6 确定性串接, gen4-plan P0-4)

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
    if cmd == "plan":
        return c1_cli.main(args)
    if cmd == "verify":
        return c4_cli.main(args)
    if cmd == "task":
        return c2_cli.main(args)
    if cmd == "review":
        return c5_cli.main(args)
    if cmd == "gate":
        return c6_cli.main(args)
    if cmd == "phase":
        return c7_cli.main(args)
    if cmd == "acgate":
        return acgate_cli.main(args)
    if cmd == "authz":
        return authz_cli.main(args)
    if cmd == "mutation":
        return mutation_cli.main(args)
    if cmd == "testauthor":
        return testauthor_cli.main(args)
    if cmd == "seamlint":
        return seamlint_cli.main(args)
    if cmd == "close":
        return close_cli.main(args)
    if cmd == "lane":
        return lane_cli.main(args)

    print(f"suiyin-flow: error: unknown subcommand: {cmd}", file=sys.stderr)
    print(_USAGE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
