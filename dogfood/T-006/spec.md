# Spec: P1.2.5 tasks.yaml → C2 batch adapter mini-dogfood (T-006)

## 1. Purpose

T-006 是 P1.2.5 的 mini-dogfood — **跑 C2 `task batch` CLI 对一份代表性 `tasks.yaml` 做 dry-run + 校验场景**，验证 batch adapter 端到端可用、schema 校验路径、order violation 报错、CLI exit code 全对。

对比 T-005（C6 跨阶段 dogfood，跑真实 4 场景评估 PR），T-006 收窄到「**batch CLI 入口 + 解析 + 顺序断言**」—— 不真起 Claude session（那要 2h × N 次，非 P1.2.5 验证 scope；真闭环留给"用 `/sy-tasks` 生成 yaml + 真 batch 跑 → merge"由用户 spawn 下一 session 验证）。

## 2. Public API

N/A — dogfood task，不是 imperative 代码。验证脚本 + 落盘 fixture + evidence。

## 3. Behavior Contract

文档 / 验证脚本类，无 imperative logic。AC 全部基于 "fixture 已落盘 + `suiyin-flow task batch` 真跑 4 个场景 + 输出落点正确"。

## 5. Acceptance Criteria

> 用 AC-501..AC-505 避免跟 T-001..T-005 已有 AC 冲突。

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

- **AC-505**: dogfood evidence — `dogfood/T-006/results/` 含 3 个场景的 stdout/stderr 捕获 + 汇总 README（跟 T-005 一致风格）。

## 6. Open Questions

- **Q-T006-1**: 是否要加"真起 1 个 task session"场景？
  - 当前决定: **不加**。Mock claude script 已在 `tests/c2_executor/test_acceptance_criteria.py` 覆盖单 task pipeline；batch.py 的责任在「顺序调度 + fail-stop + dry-run」，由 mock execute_task 的 AC-B2/B3 充分覆盖。真起 session 留给用户驱动的"全闭环"测试。

- **Q-T006-2**: 是否要 `/sy-tasks` 真生成一份 yaml 进 fixtures？
  - 当前决定: **不真调 /sy-tasks**。fixtures 手写一份代表性的 yaml（schema 符合 v0.1.0 + 字段齐全），等价于 /sy-tasks 输出。/sy-tasks 改造的正确性靠下一 session 的真实使用验证。

## 7. Implementation Notes

- 用 Python `run.py`（跟 T-005 一致），`subprocess.run` 调 `sys.executable -m suiyin_flow.cli task batch ...`
- 退出码 0 = 全场景 actual = expected；非 0 = 至少一个场景偏离
- 跑完 evidence 落 `dogfood/T-006/results/<scenario>-{stdout,stderr,exit_code}.txt`
