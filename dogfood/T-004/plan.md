# Plan: C6 Gate Contract Spec + Insight C Promote (T-004)

## Steps

1. **读 context**（按顺序）:
   - `docs/sdd/component-spec-template.md` — **严格按 8 章节顺序**
   - `docs/sdd/toolchain.md` §C6 节 — 契约定义 + 实现谱系 + 未决 Q6
   - `docs/sdd/components/c4-verify-contract.md` — declarative 契约 spec **范例**（最相近）
   - `docs/sdd/components/c2-task-executor.md` — imperative 组件 spec 反向对照
   - `docs/sdd/components/c5-ai-reviewer.md` — 最近一份 spec + §7 Block Recovery（Insight C 源头）
   - `docs/sdd/workflows.md` v0.1.0 — 主流程状态机现状（要 promote Insight C）
   - `docs/sdd/constitution.md` v0.2.2 — 引用 NC-1..NC-5 + PC-1..PC-3
   - `docs/sdd/todo.md` §P1.2 阶段 3 + §P3 follow-up — Insight C 触发条件

2. **写 `docs/sdd/components/c6-gate-contract.md`** v0.1.0-draft，严格 8 章节:
   - §0 Type: **行为契约**（[x] declarative contract），声明实现谱系优先 (d) 混合，P1.2 落地 (a) git pre-push hook + Python CLI
   - §1 Purpose: 一句话核心职责（接 verify + review report → 4 条 AND → merge/hold）
   - §2 Public API: yaml schema Input (pr_ref / verify_report_path / review_report_path / repo_root + dry_run) / Output (gate_result + rules breakdown + reason + recovery_action + merged_sha + timestamp) / Error (MISSING_INPUT / INVALID_REPORT / GIT_ERROR / GH_ERROR / PERMISSION_DENIED)
   - §3 Behavior Contract:
     - 3.1 Invariants ≥7 条（I1 Gate Rule / I2 Hold Default / I3 Reasoned Hold / I4 Hold≠Permanent / I5 ff-only / I6 Determinism / **I7 Block Recovery R1 硬约束**）
     - 3.2 Side Effects（merge / label / comment / 落盘）
     - 3.3 Failure Modes 表 ≥6 行（4 hold + 5 Error）
   - §4 AI Prompt Template: **N/A — 此模块是契约，规则评估纯 boolean 逻辑，不跑 AI prompt**
   - §5 Acceptance Criteria: ≥10 条（4 hold + merged + dry-run + determinism + ff-only race + report 落盘）
   - §6 Open Questions: 关 Q6 (P1.2 通道降级为 PR comment+label) + 加 Q6-2/Q6-3/Q6-4/Q6-5
   - §7 Implementation Notes: 实现谱系表 / CLI 入口 / 模块拆分 (c6_gate/{cli,contract,rules,ff_check,actions,report}) / 跨平台 (NC-5) / 跟其他 C 协作 / 跟 constitution NC-1..NC-5 对照 / Block Recovery R1 协作约定 / mini-dogfood T-005 设计

3. **修改 `docs/sdd/workflows.md`** v0.1.0 → v0.1.2（promote Insight C）:
   - §二 主流程图 mermaid: `K -->|block| I` 替换为 `K --> BR[Block Recovery] -.->|R2 P1.3| I` + `BR --> L`（R1 P1.2 等人解锁）
   - **新增**章节 `### Block Recovery（D-autonomous 流派硬约束）` 在 §二 "异常退出" 与 "边的判定规则" 之间，含 R1/R2/R3 阶段表 + 反向 link C6 spec §3.1 I7
   - §二 边判定表 "review block" 行：去掉过期的 `request_changes`、改 "→ Block Recovery"、指向新章节
   - §六 未决问题表加 Q6-2/Q6-3/Q6-4/Q6-5（C6 spec 派生）
   - 版本号 bump v0.1.0 → v0.1.2（直跳跨号，附 Changelog 说明跳号原因 per ADR-0001 SemVer）

4. **更新 `docs/sdd/todo.md`**:
   - P1.2 阶段 3.1 spec ⏳ 标记进行中（spec PR pending）
   - P3 follow-up #6 (Insight C) 打 ✅ + promote 落点引用
   - 阶段 3.2 (impl + T-005 mini-dogfood) 列为待启动
   - T-004 / T-005 编号说明：T-004 = 本 spec 写作 dogfood；T-005 = 用 C6 评估 PR #30 mini-dogfood（原 todo 中 T-004 编号顺移）

5. **不跑 verify_cmd**（spec 类 task，无 Python 代码变化；只是文档写作）。但应跑 lefthook pre-commit（ruff / mypy on tests/）以确保不破坏既有测试。

6. **不写 dogfood test**（spec 类 task，AC 在 spec PR review 中由 C5 验证；不像 T-002 那样写 test_c5_spec.py，因为 C6 是契约文档结构验证可由 C5 直接 check spec headings 完成，不需要额外 Python test）。

## 关键设计点（写 spec 时必须 hit）

1. **契约 vs 组件区分**: §0 标 `[x] 行为契约`、§4 = `N/A` — 这两点是 C6/C8 跟 C2/C5 的核心反向区别（PC-2 "组件 vs 契约明确分离"）。
2. **NOT_FF_MERGEABLE 不重跑 C2/C4/C5**: rebase 后代码 tree 不变，verify/review report 仍 valid — §3.3 关键设计决策注释。
3. **Block Recovery R1 P1.2 硬约束**: §3.1 I7 + §7 R1 协作约定双向呼应；不允许静默 hold。
4. **ff-only enforcement**: §3.1 I5 + §3.3 GIT_ERROR retryable=true（race condition 不 fallback merge-commit）。
5. **dry_run 一切副作用跳过**: §3.2 + AC-308（验证 contract 内的副作用 gate）。

## 风险 / 注意

- workflows.md 改动是状态机变更，可能影响别处引用：扫一遍 toolchain.md / diagrams.md 看是否需要联动（**当前判定**: diagrams.md 11 张 mermaid 没有强引用 C5→C6 边的具体形态，可暂不改；如 reviewer 提出再补）。
- task_id = T-004 = 本 spec PR；T-005 留给 impl PR 的 mini-dogfood。
- C5 self-review 时若 verdict=block → 触发 R1（加 human:block 标签）— 这是设计预期，不算"测试失败"。
