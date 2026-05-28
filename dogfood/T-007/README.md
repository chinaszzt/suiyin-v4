# T-007 — C6 Bug Fix Self-Merge Dogfood

> **目标**: 用本 PR (#36) 修好的 C6 自己 auto-merge 本 PR。**自指验证 Bug 1 真修了** (NC-4 worktree 兼容)。

## 范围

**C6-only auto-merge** (用户 explicit choice，省真 C5 session 成本 + 时间)：
- C4 已实证: 98/98 pytest + ruff + mypy clean → mock `overall_verdict=pass`
- C5 跳过: mock `verdict=approve` (C5 真 review 留 P1.3 自动化做)
- C6: **从本 worktree 跑真 gate run → 真 ff-merge PR #36 到 main**

## 输入

- [`inputs/verify_report.json`](inputs/verify_report.json) — overall_verdict=pass
- [`inputs/review_report.json`](inputs/review_report.json) — verdict=approve

## 命令

```bash
cd /Users/zhangtuo/Documents/suiyin-v4/.claude/worktrees/c6-bug-fixes
.venv/bin/python -m suiyin_flow.cli gate run \
  --pr-ref claude/c6-bug-fixes \
  --verify-report dogfood/T-007/inputs/verify_report.json \
  --review-report dogfood/T-007/inputs/review_report.json \
  --repo-root .
```

**关键路径** (Bug 1 fix 验证):
1. 子 worktree 跑 gate → ff_merge_to_main 被调
2. **旧 impl**: `git checkout main` → fail (父 worktree 占着 main)
3. **新 impl** (本 PR): `git push <sha>:main` + `git update-ref refs/heads/main` → 零 checkout, worktree-safe

## Acceptance evidence

C6 gate_result=merged + main HEAD 真前进到本 PR 的 HEAD sha → Bug 1 fix 成立。

输出 gate_report 落盘: `.suiyin/gates/claude-c6-bug-fixes-<ts>.json` + `latest-claude-c6-bug-fixes.json` (audit trail，跟 T-005 同模式)。

## Why this is meaningful

**self-reference**: 本 PR 的 C6 code 自己 merge 自己。如果 Bug 1 没修好，C6 跑到 `git checkout main` 会 fail；自动 merge 失败 → T-007 失败 → 我得回头继续修。Bug 1 修好 → 自己把自己 merge 进 main → T-007 evidence 是不可伪造的（merge commit 在 main history 上）。
