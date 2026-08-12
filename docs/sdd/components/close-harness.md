# Close Harness — Component Spec

> Feature 收口 harness（gen4-plan P0-4）。**确定性脚本**串 feature HEAD 的
> `human_block → acgate → mutation(触发键) → verify(C4 全量) → review(C5 subject=feature) → gate(C6 ff-merge)`。
> Q7-3（feature→main 收口编排）完整实现前的过渡形态——**不宣称端到端全自动**：任一步失败即停 + surface to human。

## 0. Type

- [x] 自建组件（imperative logic）
- 无 C 编号（编排层；路由零 AI，AI 只在 C5 session 内部——C7 I2 同源纪律）

## 2. Public API

### 2.1 CLI

- `suiyin-flow close run --tasks <tasks.yaml> --repo-root <p> --verify-cmd <cmd> [--target-branch main] [--env K=V ...] [--gate-dry-run]` → CloseReport JSON；exit 0 merged / 1 held·blocked / 2 error
- `suiyin-flow close {block,unblock,status} --feature <id> --repo-root <p> [--reason ...]`——本地 human:block 管理

### 2.2 CloseReport

`{schema_version, feature_id, base_branch, target_branch, verdict: merged|held|blocked|error, held_at, steps[], run_id}`；
落盘 `.suiyin/close/<safe_feature>-<run_id>.json` + `latest-<safe_feature>.json`。
step = `{name, status: passed|failed|skipped|skipped_warning|not_reached, detail, report_path}`——每步产物（acgate/mutation/verify/review report）路径全记录。

### 2.3 本地 human:block（拍板：GitHub label 降级为可选 adapter）

`.suiyin/blocks/<safe_feature>.json` versioned（history append-only，原子覆写）。收口第一步查它，blocked → verdict=blocked，**零后续步骤**（优先级同 C6 I8 HUMAN_BLOCKED）。损坏的 block 文件 fail-closed 当作 blocked。

## 3. Invariants

- **I1（确定性步序 + fail-closed）**：步序固定；任一步 failed → 停 + held_at + 后续 not_reached；工件与 worktree 保留供人处置。
- **I2（工件约定 + 迁移期语义）**：ac-manifest.yaml / mutants.yaml 与 tasks.yaml 同目录；缺失 → `skipped_warning` 放行（M3 门内转强制——acgate QA-1 在此关闭为分阶段答案）。
- **I3（mutation 触发键，拍板 1）**：`AC/守卫测试变更 ∪ mutants.yaml 变更 ∪ 被测面（mutant target_file）变更` 与 feature diff 有交集才跑探针；未命中 → skipped（省时且留痕）。
- **I4（verify_cmd 兜底）**：feature HEAD 在 throwaway worktree 全量跑 `--verify-cmd`（C4 结构化 runner 只有 python/dart；Go 等按 gen4-plan P0-2 走 verify_cmd），合成 C4 §2.2 形状 verify_report（`overall_verdict` 由 exit code 决定，`synthesized_by` 字段留 audit），C6 照常消费。
- **I5（subject=feature review）**：C5 输入 `task_id=feature_id + task_ids=[成员 task]`（C5 v0.3.0）；criticality 取成员最高档。
- **I6（merge 权在 C6）**：harness 不自己动 git ref；ff-merge / held / R1 全部走 C6 既有契约（exit 0/1/2 映射）。

## 5. Acceptance Criteria

tests/close_harness/test_acceptance_criteria.py（真 git fixture + bare origin + mock claude，9 AC）：
AC-1 happy 全链 → C6 真 ff-merge / AC-2 本地 block → blocked 零步骤 / AC-3 verify 红 → held 且 review 不起 session（失败型）/ AC-4 review block → held / AC-5 acgate 拦弱化 → held 在 verify 前（失败型）/ AC-6(+6b) 触发键命中 survivor → held·未命中 → skipped / AC-7 block CLI 生命周期 + history / AC-8 gate dry-run 不真 merge。

## 6. Open Questions

- **QH-1**：C4 结构化 Go runner 落地后 verify 步切回 C4 API（保留 verify_cmd 作通用兜底）
- **QH-2**：M3 门内 skipped_warning → 强制 fail 的切换开关形态（配置 vs 硬编码按里程碑）
- **QH-3**：C4/C5 报告新鲜度绑定（target_tree_sha）接入后，harness 在 gate 前先验票（M3 门内条目）

---

**Version**: v0.1.0-draft
**Last Updated**: 2026-08-12
**Changelog**:
- v0.1.0 (2026-08-12): 初稿 + impl + 9 AC。来源 gen4-plan §三 P0-4。联动：C5 v0.3.0（task_ids[]，关 ADR-0005 记的"C5 审 feature/meta 级 subject 输入形态" open gap 的 feature 半边）；C4 task_id pattern 补 P0-1 cascade 漏网；safety v0.5.1（规则 4：`.suiyin/` 运行时工件入 diff → 拦，8 条 E4 blocker 中 hygiene 类的机械承接）。
