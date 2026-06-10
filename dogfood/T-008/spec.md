# T-008 mini-dogfood — C2 v0.3.0 R2 retry-with-feedback + I8 worktree 锁

> 对应 c2-task-executor.md v0.3.0 (P1.3 R2 + C7 联动需求 2)。
> 模式：programmatic execute_task + fake claude script（同 T-006 场景 4 套路 ——
> claude_cmd 注入只在 Python 层暴露）。真 R2 编排（C5 block → 自动重投）等
> Q7-2 / C7 v0.2，本 dogfood 只验 C2 半边的能力契约。

## 场景

| # | 场景 | 验什么 | 期望 |
|---|---|---|---|
| 1 | R2 链路（block → feedback retry） | round-1 普通跑（prompt 无 feedback 节）→ 伪造 C5 block report → round-2 带 `review_feedback` 同 worktree 重投 | round-2 prompt 含「上次 Review 发现的问题」+ findings（severity 降序）；`review_feedback_applied=true`；worktree 复用（I1）；CLI `--review-feedback` flag 存在 |
| 2 | 活跃锁拒跑（发现 #8） | worktree 锁被存活 pid 持有时再投 | `WORKTREE_LOCKED` + details.holder_pid；不写 session log；锁未被动 |
| 3 | stale 锁接管 | 锁持有者 pid 已死 | 正常跑完 success；终态锁释放（I8 + AC-14） |

## AC 映射

- 场景 1 → spec AC-10（注入 + applied 标记）
- 场景 2 → spec AC-12（活锁拒跑）
- 场景 3 → spec AC-13 + AC-14（stale 接管 + 终态释放）
- AC-11（REVIEW_FEEDBACK_INVALID 三态）在 unit AC tests 已覆盖
  （tests/c2_executor/test_review_feedback_and_lock.py），不重复

## Evidence

`dogfood/T-008/results/README.md` + 各场景 prompt dump / error JSON。
