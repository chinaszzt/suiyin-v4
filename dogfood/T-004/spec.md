# Spec: C6 Gate Contract 组件 Spec + Insight C Promote (P1.2 阶段 3.1)

## 1. Purpose

写 `docs/sdd/components/c6-gate-contract.md` v0.1.0 — 即 C6 Gate Contract 的完整 spec。这是 v4 工具链 **P1.2 自闭环 merge 的最后一块 spec**（C2/C4/C5 已落地），同时顺手 promote C5 mini-dogfood T-003 留下的 **Insight C: Block Recovery invariant** 到 `workflows.md`（todo.md P3 follow-up #6）。

C6 角色简述: 行为契约，4 条 boolean AND 规则纯逻辑评估 — `verify.all.pass && review.verdict == approve && pr.ff_mergeable && !pr.has_label("human:block")`。任何一条 false → hold；REVIEW_NOT_APPROVE 时触发 Block Recovery R1（加 human:block 标签 + comment findings）。

## 2. Public API

N/A — 这是文档/spec 类 task，不是 imperative 代码（虽然产出物本身 C6 spec 描述的是契约的 API/Output 等）。

## 3. Behavior Contract

文档类，无 imperative logic。AC 全部基于"文件存在 + 内容含特定结构 + 引用正确 + workflows.md 联动正确"。

## 5. Acceptance Criteria

> 用 AC-301..AC-310 避免跟 C2/C4/C5/T-001/T-002 已有 AC-1..AC-208 冲突 (C4 parser 全局扫 AC-\d+)。

- **AC-301**: `docs/sdd/components/c6-gate-contract.md` 文件存在，含 8 章节 Markdown headings（严格按 `component-spec-template.md` 顺序：`## 0. Type` / `## 1. Purpose` / `## 2. Public API` / `## 3. Behavior Contract` / `## 4. AI Prompt Template` / `## 5. Acceptance Criteria` / `## 6. Open Questions` / `## 7. Implementation Notes`）。

- **AC-302**: §0 Type 标 `[x] 行为契约（declarative contract — 配置 + 编排）`（C6 是契约，不是 imperative 组件）。

- **AC-303**: §2 Public API 含至少 3 个 ```yaml``` schema block（Input / Output / Error）。Output schema 必须含 `gate_result` 字段（enum `merged` / `held`）+ `rules` 4 字段 breakdown。

- **AC-304**: §3.1 Invariants 至少 5 条 (I1..I5+)。必须含至少 1 条 "ff-only main 历史" 类的 git invariant，以及 1 条声明 "REVIEW_NOT_APPROVE 必触发 Block Recovery R1" 的 D-autonomous 硬约束（I7 或同等编号）。

- **AC-305**: §4 AI Prompt Template **是** `N/A` — C6 是 contract，没有 AI prompt（reviewer 必显式验证此项，因为这是契约和 imperative 组件的最关键区分点）。

- **AC-306**: §3.3 Failure Modes 表至少 6 行，必含: `VERIFY_NOT_PASS` / `REVIEW_NOT_APPROVE` / `NOT_FF_MERGEABLE` / `HUMAN_BLOCKED` 这 4 种 hold 类型。

- **AC-307**: §5 Acceptance Criteria 至少 8 条 AC，必含 1 条 "4 条全 pass → merged"（正向）+ 1 条每个 failure mode 各 1（4 条 hold）+ 1 条 dry-run 不触发副作用 + 1 条 determinism（同 input → 同 output）。

- **AC-308**: §6 Open Questions **必关 Q6**（从 toolchain.md 继承的 "升级通知渠道"），即明说 P1.2 阶段降级或决议；并新增至少 3 个派生 Q（Q6-2/Q6-3/Q6-4 等）。

- **AC-309**: `docs/sdd/workflows.md` 主流程图 mermaid 中不再有 `K -->|block| I` 直连边（已被 Block Recovery R1 节点 BR 替代）；存在 "Block Recovery" 节点 / "R1" 路径 / "R2" dotted 路径。

- **AC-310**: `docs/sdd/workflows.md` 新增 `### Block Recovery` 章节，含 R1/R2/R3 阶段表，**反向引用** `components/c6-gate-contract.md` 的某节（如 §3.1 I7 或 §7 R1 协作约定）。

## 6. Open Questions

无未决问题（spec 类 task，AC 都是结构性可验证）。

## 7. Implementation Notes

- 参考 `dogfood/T-002/spec.md`（C5 spec dogfood）的 meta-spec 模式
- C6 是契约不是组件 → §4 必为 N/A（这跟 C5 / C2 的 imperative pattern 是关键反向差异）
- workflows.md promote 是 **顺手** 完成 P3 follow-up #6（Insight C），不是单独 PR
- 双 PR 模式: 本 PR (spec) → C5 自审 → impl PR 后续（mini-dogfood T-005 = 用 C6 评估 PR #30）
