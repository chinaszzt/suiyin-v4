# T-005 mini-dogfood results

PR #34 (C6 impl v0.1.1) → 4 个 mock pre-merge gate 评估场景。

| # | Scenario | Expected | Actual | Pass |
|---|---|---|---|---|
| 1-baseline-merged | merged/- | merged/- | ✅ |
| 2-verify-fail | held/VERIFY_NOT_PASS | held/VERIFY_NOT_PASS | ✅ |
| 3-review-block | held/REVIEW_NOT_APPROVE | held/REVIEW_NOT_APPROVE | ✅ |
| 4-not-ff-mergeable | held/NOT_FF_MERGEABLE | held/NOT_FF_MERGEABLE | ✅ |
| AC-407 safe_pr_ref direct unit verify | (safe_pr_ref unit) | all cases | ✅ |

## 详细 evidence

### 1-baseline-merged

- evidence: `dogfood/T-005/results/1-baseline-merged-gate_report.json`
- rules: `{"verify_all_pass": true, "review_approved": true, "ff_mergeable": true, "not_human_blocked": true}`

### 2-verify-fail

- evidence: `dogfood/T-005/results/2-verify-fail-gate_report.json`
- rules: `{"verify_all_pass": false, "review_approved": true, "ff_mergeable": true, "not_human_blocked": true}`
- recovery_action: `{"kind": "no_op"}`

### 3-review-block

- evidence: `dogfood/T-005/results/3-review-block-gate_report.json`
- rules: `{"verify_all_pass": true, "review_approved": false, "ff_mergeable": true, "not_human_blocked": true}`
- recovery_action: `{"kind": "r1_label_and_comment"}`

### 4-not-ff-mergeable

- evidence: `dogfood/T-005/results/4-not-ff-mergeable-gate_report.json`
- rules: `{"verify_all_pass": true, "review_approved": true, "ff_mergeable": false, "not_human_blocked": true}`
- recovery_action: `{"kind": "no_op"}`

### AC-407 safe_pr_ref direct unit verify

- evidence: `(none)`
- rules: `{}`

## I8 precedence + safe_pr_ref 验证

- **AC-406 I8 precedence**: dogfood 跳过场景 5 (本地无真 PR API 测 human:block label)，降级到 unit test `tests/c6_gate/test_acceptance_criteria.py::test_AC_5_i8_precedence_human_block_wins_over_verify_fail` 实证 (PR #34 已绿)。
- **AC-407 safe_pr_ref**: 由独立直接单元验证（'AC-407 safe_pr_ref direct unit verify' 行），覆盖 URL → `pull-N` / branch → 扁平 / `#N` 去 hash 等 case，断言输出**不含** `/` `:` `?` 等 unsafe chars。原计划场景 3 用真 URL 走 gh API，但本地 tmp repo 没真 PR sha 会触发 GIT_ERROR；改为本地 branch + 直接调 safe_pr_ref unit verify 保留 AC-407 evidence。

## 跟 spec AC 映射

| spec AC | 场景 / unit-test 来源 |
|---|---|
| AC-401, 402 | `.suiyin/fixtures/T-005/{verify,review}_report.json` |
| AC-403 | 4 场景全跑 |
| AC-404 | gate_report 文件名扁平验证 (evidence dir 所有文件名) |
| AC-405 | 场景 3 dry_run + review=block → recovery_action.kind=r1 但 label/comment 字段 absent |
| AC-406 | 降级 unit test (AC-5 in c6_gate tests) |
| AC-407 | 'AC-407 safe_pr_ref direct unit verify' 行 (run.py verify_safe_pr_ref_ac_407) |
| AC-408 | 本目录 dogfood/T-005/results/ |
| AC-409 | run.py 全在 tmpdir + .suiyin/ + dogfood/T-005/results/ 操作 |
| AC-410 | post-dogfood 改 todo.md (caller) |
