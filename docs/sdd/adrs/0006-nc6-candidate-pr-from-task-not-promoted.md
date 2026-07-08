# ADR-0006: NC-6 候选（"所有 PR 必须来自 task"）三问法评审——不立

> P0.5 悬置账（2026-05-24 起）关账：隐性 NC 候选跑三问法，2/3 不过，不进 constitution。

---

## Status

`Accepted (2026-07-09)`

## Context

- C5 spec v0.1.1（PR #29 user 审）把 `task_id` 设为 required 时，§2.1 description 写了「所有 PR 必须来自 task（含 hotfix / Initiative）」——这实质是一条隐性 NC 候选，当时记入 todo P0.5「待 user 拍」。
- issue #60（Phase 0 关门）任务 3 顺手清账：跑 governance §8.1 三问法（v4 独有？项目原则？行为约束？——同 ADR-0003 用法）给出正式裁决。
- 现实基线：v4 自身 PR #44–#59（docs / todo / hotfix / 工具链迭代）**没有一个来自 task**；C5/C6 也未在 v4 自家 PR 上运行（2026-07-08 流程评估确认）。

## Decision

**不立 NC-6，也不立 PC。**「所有 PR 必须来自 task」维持为工具链**执行面语义** + 工作流约定，不进 constitution：

- 执行面已有落点：C5 §2.1 `task_id` required = **想走自动 review/merge 链的 PR 必须 task 化**（C5 拒审非 task PR）。
- 不走自动链的 PR（meta / docs / constitution / 紧急 hotfix）由人直接处理，本来就在 role-profile human gates 覆盖内。
- **复评触发点**：Phase 1 v4 自举成熟（自家 PR 天然全带 task_id）时，promote 成本为零，届时再议。

## Rationale

三问法逐问：

| 问 | 结论 | 依据 |
|---|:---:|---|
| **v4 独有？** | ✗ | 「PR 必须来自 task」是 SDD 工作流 / 工具链层的通用规则，对任何用 v4 工具链的项目同等适用。塞进 v4 constitution = 重蹈 ADR-0001 的层次混淆（通用规则应在 methodology / workflows 层）。 |
| **项目原则（稳定）？** | ✗ | 立 NC 即日起 v4 自身 100% 违宪（#44–#59 全部非 task PR），要么死信、要么立刻需要 hotfix/meta/docs/constitution 豁免清单并随阶段反复修订——按 I6「频繁改的不是 NC，是 plan」。其可行性依赖 Phase 1 自举 + Bug Type B/C mini-flow（仍在 P3 backlog），是**阶段性目标**不是恒定原则。 |
| **行为约束（可测试）？** | ～ | 可测（PR 关联 task_id），但恰因如此 C5 §2.1 已在执行面强制——constitution 层重复它违反 I2（NC/PC 正交）。 |

方案对比：

| 方案 | 选 / 弃 | 理由 |
|---|:---:|---|
| 立 NC-6 | ✗ | 三问 2 败（见上）；且 governance §8.1 step 3 要求 C5 审宪法 PR、而 C5 拒审非 task PR——宪法 PR 正是天然的"非 task PR"，NC-6 会造出自指死锁。 |
| 立 PC-4（warn 级） | ✗ | 与 C5 执行面强制重复（违 I2）；warn 对不走链的 PR 无增量价值（那些 PR 本来就人审）；违 PC-1 最简精神。 |
| **不立（chosen）** | ✓ | 执行面已闭环，宪法保持最小集；复评触发点显式记录，不丢账。 |

## Consequences

### Positive

- P0.5 关账；constitution 零膨胀（NC v1.0 = NC-1..5 + PC-1..3 维持稳态，I6 友好）。
- 「执行面语义 vs 宪法约束」的分界又一次被显式演练（ADR-0001 分层教训的延续）。

### Negative / Trade-off

- 「v4 自家 docs/meta PR 不走 task」的现状被**显式接受**——这正是 2026-07-08 流程评估指出的自举 gap 的一部分。风险由复评触发点兜底：Phase 1 自举成熟后回头看。

### Cascade（影响范围）

| 文件 / 模块 | 修改类型 | 状态 |
|---|---|---|
| `docs/sdd/constitution.md` | 无内容变更（本 ADR 不改宪法文本，v0.2.3 版本历史顺带记录裁决） | ✅ 本 PR |
| `docs/sdd/todo.md` P0.5 | 关账 + 附带发现记录 | ✅ 本 PR |
| `docs/sdd/components/c5-ai-reviewer.md` §2.1 | task_id description | ❌ 不改（其表述本就是执行面语义，无需动） |

## Alternatives Considered

N/A（Rationale 表已穷举）。

## References

- Related ADRs: ADR-0001（层次混淆教训）、ADR-0003（三问法用法先例）、ADR-0005（同 PR）
- Relevant Specs / Docs: `components/c5-ai-reviewer.md` §2.1、`docs/sdd/todo.md` P0.5
- Discussion: GitHub issue #60（Phase 0 关门）；2026-07-08 流程评估（v4 自家 PR 不走自家链的 dogfooding gap）

## Author + Date

- **Author**: Claude（Fable 5 session）+ user 拍板
- **Decided**: 2026-07-09
- **Last Updated**: 2026-07-09
