# T-007 Results — Audit trail (补 evidence)

> **Context**: PR #36 已经把 C6 Bug 1+2+3 修好并 merge 进 main。原 T-007 README 计划"用 PR #36 修好的 C6 自动 merge PR #36 本身"，但 PR #36 merge 时这份 results/ 还没落盘。本 PR 补这一步证据。

## 命令

从 worktree 内（**子 worktree**，父 worktree 占着 `main` checkout —— 就是 Bug 1 当年 fail 的场景）：

```bash
suiyin-flow gate run \
  --pr-ref HEAD \
  --verify-report dogfood/T-007/inputs/verify_report.json \
  --review-report dogfood/T-007/inputs/review_report.json \
  --repo-root .
```

## 结果

[`gate_report.json`](gate_report.json):

```json
{
  "gate_result": "merged",
  "rules": {
    "verify_all_pass": true,
    "review_approved": true,
    "ff_mergeable": true,
    "not_human_blocked": true
  },
  "merged_sha": "4844259288cabd0e2ab743b51503a02352180442",
  "timestamp": "2026-05-28T12:17:18.230017+00:00"
}
```

## 关键验证点

| 检验 | 结果 |
|---|---|
| **Bug 1 fix 实际跑过** — `ff_merge_to_main` 在子 worktree 内不再 `git checkout main` | ✅ 走 refs-direct (`git push <sha>:main` + `git update-ref refs/heads/main`)，**零 error** |
| **Bug 2 fix 跑过** — `resolve_pr_sha` gh 失败 / fallback 链 | ✅ pr_ref=HEAD 直接走 git rev-parse 路径成功 |
| **NC-4 worktree 兼容** | ✅ 父 worktree `/Users/zhangtuo/Documents/suiyin-v4` 仍占着 main，本 worktree 一直在 `claude/determined-knuth-39baaf` 分支上没动 |

## 为什么是 idempotent（不可伪造性说明）

跑 gate 时 worktree HEAD 已经 == `origin/main` HEAD（`4844259...`，因 PR #36 早已 merge）：

- `git push origin <sha>:main` → "Everything up-to-date"（no-op，但 server-side ff 检查通过）
- `git update-ref refs/heads/main <sha>` → no-op（local main 已在该 ref）

但 **refs-direct 代码路径真被走通了**，没有触发 `git checkout main`（旧 impl 在此处必 fail）→ Bug 1 fix 在子 worktree 上下文下成立。

如果想要"非 idempotent 真前进 main HEAD"形式的 evidence，看 PR #37、#38 在 main history 上的 ff-only first-parent commit 链（无 "Merge pull request" merge commit）—— 那是 C6 自动 merge 真把 main 推前进的实证。
