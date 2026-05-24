"""C5 AI Reviewer 实现.

按 docs/sdd/components/c5-ai-reviewer.md v0.1.1 spec 落地.
独立 AI session 评估 PR — 读 spec + plan + constitution + PR diff (不读 implementer
session log), 给 verdict (approve / block) + structured findings.

模块布局 (c5 spec §7):
- contract.py   — Pydantic schema (§2.1/2.2/2.3) + Category / Verdict enum
- prompt.py     — §4 prompt template 填充
- findings.py   — BLOCK_SET category + verdict 推导 + 4-field validation
- session.py    — claude CLI headless (复用 C2 §7 4-flag pattern)
- diff.py       — gh pr diff / git diff 拉取
- report.py     — review_report.json 落盘 + Block Recovery R1 (human:block label)
- cli.py        — `suiyin-flow review run` argparse 入口
"""
