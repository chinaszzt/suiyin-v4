# ADR-0001: Constitution v0.1 → v0.2 — 文档层次混淆修正

---

## Status

`Accepted (2026-05-19)`

## Context

v4 工具链初版 constitution.md v0.1 在 PR #4（commit `361ba5e`）引入，内容包括：

- **§5 Core Principles** — 直接搬 methodology.md §10 的 5 条铁律
- **§6 Quantitative Standards** — Fork J 拍板的量化阈值（函数 ≤ 80 行 / 文件 ≤ 600 行 / 嵌套 ≤ 5 层 / 圈复杂度 ≤ 18）

User 在 v5 项目跑 `/sy-constitution` 做 end-to-end dogfood 时（2026-05-19），暴露了**文档层次混淆**：

1. **5 铁律是 SDD 通用方法论原则**，不是 v4 项目独有约束。constitution 是项目最高约束，应该只放"这个项目独有的、不可妥协的事"。
2. **量化阈值是业务 specific**：80/600/5/18 是前端 UI 项目的合理值，但 v4 工具链项目（Python / Bash 居多）可能需要不同阈值。应该由各业务项目协商生成自己的阈值，不该 hardcode 进通用 constitution。

层次混淆后果：

- constitution 变成"什么都装"的杂物间
- 跟 methodology.md 重复（5 铁律）
- 下个用 v4 跑出来的业务项目 constitution 会照搬同样的杂物间结构

## Decision

constitution.md 重新定位为**项目独有约束记录**（commit `fc74e00`）：

去掉：

- ❌ §5 Core Principles（5 铁律）— 归 methodology.md（早就在那里）
- ❌ §6 Quantitative Standards（具体数字）— 业务 specific，由各项目协商时拍板

加入：

- ✅ **§5 Project Identity** — v4 是 SDD 工具研发项目，**不是业务产品**
- ✅ **§6 NC-1/2/3**（NON-NEGOTIABLE constraints）+ **PC-1/2/3**（Preference constraints）— v4 项目独有约束
- ✅ **§7 AI Collaboration Profile** — v4 = `autonomous`（D 档），见 `role-profile.yml`

保留（PR #6 的内容）：

- ✅ Role-profile 边界说明（§7.2.1）
- ✅ Constitution bootstrap 特例（auto-commit + push 所有档）

## Rationale

| 候选方案 | 选 / 弃 | 理由 |
|---|:---:|---|
| **A. 保留 v0.1 杂物间结构** | ✗ | 持续误导下游项目；跟 methodology.md 重复 |
| **B. 把 5 铁律从 methodology 删除，统一放 constitution** | ✗ | methodology 是给团队读的，constitution 是 AI/工具消费的；削弱 methodology |
| **C. 把 constitution 改成"项目独有"layer，5 铁律和量化指标归各自合理位置** | **✓** | 层次清晰，各 doc 单一职责 |

层次模型确立：

```
methodology.md      （SDD 通用方法论，给团队读 — 不变）
       │
       ↓ 引用
toolchain.md        （工具链规约：节点 + 契约 — 不变）
       │
       ↓ 引用
constitution.md     （项目独有约束 — 本次重新定位的 ★）
       │
       ↓ 引用
role-profile.yml    （AI 工作模式配置 — PR #6 引入）
```

## Consequences

### Positive

- **每个文档单一职责**，跟 layering 一致：方法论 → 工具链 → 项目宪法 → 工作模式
- **下个业务项目（v5+）不踩同样坑** — 但前提是 `constitution-template.md` 也修（见 Cascade）
- **constitution 更紧凑**：少了泛 SDD 内容，剩下的都是 v4 项目独有约束，invariants 明确
- **守护 I5 + SDD_RULE_DUPLICATION error**：constitution 自己定义检测规则，未来 reviewer 自动阻断同类层次混淆

### Negative / Trade-off

- **v4 自身 constitution 从"理论参考"变成"工程契约"**，要求更严格
- **短期 constitution 看起来"短了"**——但实际是 invariants 提纯
- **现有 PRs / docs 里引用 constitution.md §5/§6 的链接可能 broken**——目前仅 internal references，已同步修正

### Cascade（影响范围）

| 文件 / 模块 | 修改类型 | 状态 |
|---|---|---|
| `docs/sdd/constitution.md` | 重写 §5/§6/§7 | ✅ 已改（commit `fc74e00`） |
| `runtime/templates/constitution-template.md` | 同步修：去通用规则引导，加项目独有约束引导 | ⏳ **P0.1 待做**（防止 v6 业务项目踩同样坑） |
| `docs/sdd/methodology.md` | 加一段 explicit 说明 methodology vs constitution 边界 | ⏳ 可选 |
| `docs/sdd/component-spec-template.md` | meta-spec 用本模板时的 5b/6b/7b 编号问题 | ⏳ v0.2 调整时考虑 |

## Alternatives Considered

见 Rationale 表格（已穷举）。

## References

- Related ADRs: 无（第一个 ADR）
- PRs: `PR #4`（v0.1 引入）, `PR #6`（role-profile + bootstrap 特例）
- Commits: `361ba5e`（v0.1）, `fc74e00`（v0.2 修订）
- Relevant Docs:
  - `docs/sdd/constitution.md` v0.2（本 ADR 的落地产物）
  - `docs/sdd/methodology.md` §10（5 铁律的正确归属）
  - `docs/sdd/role-profiles.md`（§7 引用的 AI 工作模式）
  - `docs/sdd/todo.md` P0.1（cascade 待做项）
- Discussion: 2026-05-19 session（v5 dogfood 反馈）

## Author + Date

- **Author**: 张佗 + Claude
- **Decided**: 2026-05-19
- **Recorded**: 2026-05-20（追溯文档：决策已落地后补 ADR）
- **Last Updated**: 2026-05-20

---

## Note: 追溯 ADR 的姿态

本 ADR 是追溯文档（决策 5 月 19 日已落地，ADR 5 月 20 日才写）。**未来应该按 Constitution §7 governance 流程**：

```
触发讨论 → 写 ADR Proposed → 提 PR（含 ADR 修改 + constitution 修改）
       → AI Reviewer review → 人审拍板 → merge → ADR Accepted
```

本 ADR 倒序记录的原因：constitution 修改在 ADR 流程建立之前完成。**今后修宪法不再允许这样**。
