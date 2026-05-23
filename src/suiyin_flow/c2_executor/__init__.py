"""C2 Task Executor 实现.

按 docs/sdd/components/c2-task-executor.md v0.1.1 spec 落地.
单 task 从 spec 到 PR 的全自动实现, 含闭环 verify (调 C4 作为 verify_cmd).

模块布局 (c2 spec §7):
- schema.py     — Pydantic schema (§2.1/2.2/2.3)
- worktree.py   — git worktree add/remove 包装
- prompt.py     — §4 prompt template 填充
- session.py    — Claude headless + stream-json + psutil kill
- retry.py      — 失败重试策略
- cli.py        — `suiyin-flow task run` argparse 入口
"""
