# Spec: P1.2.5 tasks.yaml → C2 batch adapter mini-dogfood (T-006)

## 1. Purpose

T-006 是 P1.2.5 的 mini-dogfood — **跑 C2 `task batch` 对代表性 tasks.yaml 做 4 个场景验证**：3 个 CLI 入口场景（happy dry-run / 缺字段 / 反序依赖）+ 1 个真 `run_batch → execute_task → success` 主路径场景（fake claude script, 2 个连续 task）。

对比 T-005（C6 跨阶段 dogfood，跑真实 4 场景评估 PR），T-006 同时覆盖 CLI 入口 + 程序化主路径，留下双形态 evidence（CLI stdout/stderr/exit_code 落盘 + `BatchOutput` JSON 落盘）。

**真跑 Claude session 的全闭环测试**（用 /sy-tasks 真生成 yaml + 真起 N 个 ~2h session → merge）留给用户 spawn 下一 session 在 v4/v5 真业务场景里验证 —— 那是 D-autonomous 用户验收，不是 implementer self-dogfood scope。

## 2. Public API

N/A — dogfood task，不是 imperative 代码。验证脚本 + 落盘 fixture + evidence。

## 3. Behavior Contract

文档 / 验证脚本类，无 imperative logic。AC 全部基于 "fixture 已落盘 + `suiyin-flow task batch` 真跑 4 个场景 + 输出落点正确"。

## 5. Acceptance Criteria

> 用 AC-501..AC-506 避免跟 T-001..T-005 已有 AC 冲突。

- **AC-501**: `dogfood/T-006/fixtures/tasks-happy.yaml` 存在 — 代表 `/sy-tasks` 输出的合法 tasks.yaml（3 个 task，含 depends_on 链 `T-201 ← T-202 ← T-203`）。

- **AC-502** (happy dry-run): 跑 `suiyin-flow task batch --tasks-yaml fixtures/tasks-happy.yaml --repo-root <worktree> --dry-run`：
  - exit 0
  - stdout JSON `status == "dry_run"`
  - `tasks[]` 顺序 `T-201, T-202, T-203`，全部 `status: dry_run`
  - `stopped_at_task_id == null`

- **AC-503** (missing required field): `fixtures/tasks-missing-verify.yaml` 故意去掉 `verify_cmd`：
  - exit 2
  - stderr JSON `code == "INVALID_MANIFEST"`，message 含 "verify_cmd"

- **AC-504** (order violation): `fixtures/tasks-order-violation.yaml` 让 T-201 depends_on T-202（反序）：
  - exit 2
  - stderr JSON `code == "INVALID_MANIFEST"`，message 含 "BATCH_ORDER_VIOLATION"

- **AC-505**: dogfood evidence — `dogfood/T-006/results/` 含 4 个场景的 stdout/stderr/exit_code/BatchOutput 落盘 + 汇总 README（跟 T-005 一致风格）。

- **AC-506** (real run_batch 主路径, round-2 add): 跑通完整 `run_batch → execute_task → success` 主路径，2 个连续 task (T-601 + T-602, depends_on 链)，用 fake claude script (Python, 跟 `tests/c2_executor/conftest.py mock_claude_success` 同套路) 模拟成功 session：
  - 临时 git repo (main + 1 commit + spec/plan/context/constitution) 由 run.py 内置 `_setup_throwaway_repo` 造
  - `BatchOutput.status == "all_success"`, `stopped_at_task_id == null`
  - 每 task `attempts == 1` (fake claude 一次过) / `pr_created == False` (NC-1 无 remote) / `pr_url_or_branch` startswith `task/` (branch fallback)
  - evidence `dogfood/T-006/results/4-real-run-success-batch_output.json` 落盘
  - 这一条覆盖原 spec "跑通 2-3 个连续 task" 的真主路径要求 (round-1 C5 finding #1 medium spec_drift)

## 6. Open Questions

- **Q-T006-1**: 是否要在 CLI 加 `--claude-cmd` / `SUIYIN_FLOW_CLAUDE_CMD` env override 让 scenario 4 也走 CLI subprocess？
  - 当前决定: **不加**。AC-506 用程序化 API 调 `run_batch(claude_cmd=...)` —— 这条注入路径在 C2 里属于内部 API (test 用), 不必为单次 dogfood 加新 feature surface。CLI 入口已由 scenarios 1-3 覆盖。

- **Q-T006-2**: 是否要 `/sy-tasks` 真生成一份 yaml 进 fixtures？
  - 当前决定: **不真调 /sy-tasks**。fixtures 手写一份代表性 yaml（schema 符合 v0.1.0 + 字段齐全），等价于 /sy-tasks 输出。/sy-tasks 改造的正确性靠用户在 v4/v5 真业务场景下用一次验证 —— 那是 P1.2.5 merge 之后的事，不是 implementer dogfood scope。

## 7. Implementation Notes

- 用 Python `run.py`（跟 T-005 一致）
- Scenarios 1-3 用 `subprocess.run` 调 `sys.executable -m suiyin_flow.cli task batch ...`，evidence 落 `<scenario>-{stdout,stderr,exit_code}.txt`
- Scenario 4 用程序化 `run_batch(manifest, repo_root=..., claude_cmd=[python, fake_claude.py])`，evidence 落 `4-real-run-success-batch_output.json`
- 退出码 0 = 全场景 actual = expected；非 0 = 至少一个场景偏离
