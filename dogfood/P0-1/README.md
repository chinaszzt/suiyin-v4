# P0-1 canonical identity — dogfood evidence (2026-08-12)

场地: `~/suiyin-desk-v4lab`（desk 真仓 clone，8-08 002·T001 实验沙盒），零 token（不起 claude session）。
脚本: [run.sh](run.sh)（跑完 reset 回实验基线 `6753721`，A/B 产物未动）。

| # | 场景 | 结果 | evidence |
|---|---|---|---|
| 1 | r4 时代 v0.1.0 manifest + `T-001B`（旧 pattern 拒收案例）dry-run | exit 0，schema 放行 | `results/1-dryrun-v010.json` |
| 2 | manifest 未提交 → 真跑 | exit 2 fail-fast（session 前），指明 commit /sy-tasks artifact | `results/2-uncommitted.err` |
| 3 | 提交后 precheck 放行（派生提示 from feature_name）→ 盘上追加一行 | exit 2 漂移拒（C1 写回忘 commit 的坑关门） | `results/3-drift.err` |
| 4 | v0.2.0 显式 feature_id → phase dry-run | state 落盘 `p0-1-dogfood-<ts>.json` 新键；latest 不写（dry-run 边界）；输出带 feature_id | `results/4-phase-dryrun.json` |
| 5 | 真 git worktree 双段命名 | `worktrees/p0-1-dogfood/T-001B` + 分支 `task/p0-1-dogfood/T-001B`，清理干净 | run.sh 输出（对话记录）|

关联: PR #64（impl）；CI 附带抓到 Windows autocrlf 漂移误判真 bug（行尾归一化修复，commit 6dceb3c）。
