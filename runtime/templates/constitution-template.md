# [PROJECT_NAME] 项目宪法 (Constitution)

> [PROJECT_NAME] 项目最高约束。所有 spec / plan / task 必须符合本宪法。
>
> 修改本宪法须走 ADR + PR 流程（见 §7 Governance）。
>
> 本宪法用 [suiyin-flow component-spec-template](https://github.com/chinaszzt/suiyin-v4/blob/main/docs/sdd/component-spec-template.md) 格式写。

---

## 0. Type

**Meta-spec**（项目级约束，非工具链组件）

- [x] 行为契约（declarative — 定义"什么算合规"，本身没 imperative logic）

由 C4 L4 (Constitution compliance check) 和 C5 AI Reviewer 在它们的实现里 enforce。

## 1. Purpose

[PURPOSE]
<!-- Example: 定义 [PROJECT_NAME] 项目的不可妥协原则、项目身份、治理流程，作为所有 spec/plan/task 的最高约束。 -->

## 2. 项目身份

[PROJECT_IDENTITY]
<!-- Example: [PROJECT_NAME] 是 AI native [项目类型]，业务方向是 [业务描述]。
     技术栈 [TBD / 待 Initiative 决策]。
     开发模式：AI 主写代码 + 人协商 spec/plan + 自动化 gate（人不审 PR）+ 人按 deploy。 -->

## 5. Core Principles

**suiyin-flow 推荐起点**：直接采用 v4 methodology §10 的 5 条铁律。可酌情调整 NON-NEGOTIABLE / Preference 分级。

### Principle I: [PRINCIPLE_1_NAME]

**Statement**: [PRINCIPLE_1_STATEMENT]
**Rationale**: [PRINCIPLE_1_RATIONALE]
**Test**: [PRINCIPLE_1_TEST]
**Severity**: [PRINCIPLE_1_SEVERITY]
<!-- Suggested:
  Name: Spec 先于代码
  Statement: 任何新能力必须先写 spec 再写代码——不允许跳过。
  Rationale: AI 主写项目中 spec 是 AI 的长期记忆和意图契约，跳过会导致多 session 间漂移。
  Test: 任何 PR 必须 reference 一个 spec.md，无 spec_ref 的 PR → C4 L3 block。
  Severity: NON-NEGOTIABLE
-->

### Principle II: [PRINCIPLE_2_NAME]

**Statement**: [PRINCIPLE_2_STATEMENT]
**Rationale**: [PRINCIPLE_2_RATIONALE]
**Test**: [PRINCIPLE_2_TEST]
**Severity**: [PRINCIPLE_2_SEVERITY]
<!-- Suggested: Spec 范围 = 用户/外部观察者可观察行为 (Preference) -->

### Principle III: [PRINCIPLE_3_NAME]

**Statement**: [PRINCIPLE_3_STATEMENT]
**Rationale**: [PRINCIPLE_3_RATIONALE]
**Test**: [PRINCIPLE_3_TEST]
**Severity**: [PRINCIPLE_3_SEVERITY]
<!-- Suggested: Bug 必须先翻 spec (NON-NEGOTIABLE) -->

### Principle IV: [PRINCIPLE_4_NAME]

**Statement**: [PRINCIPLE_4_STATEMENT]
**Rationale**: [PRINCIPLE_4_RATIONALE]
**Test**: [PRINCIPLE_4_TEST]
**Severity**: [PRINCIPLE_4_SEVERITY]
<!-- Suggested: 代码改 = spec 改 (NON-NEGOTIABLE) -->

### Principle V: [PRINCIPLE_5_NAME]

**Statement**: [PRINCIPLE_5_STATEMENT]
**Rationale**: [PRINCIPLE_5_RATIONALE]
**Test**: [PRINCIPLE_5_TEST]
**Severity**: [PRINCIPLE_5_SEVERITY]
<!-- Suggested: 拍板前移到 spec/plan 层 (Preference) -->

## 6. Quantitative Standards

**v4 suiyin-flow 推荐起点**（先用，spike 后调整）：

| 维度 | 阈值 | Enforce 位置 |
|---|---|---|
| 函数长度 | ≤ [FUNCTION_MAX_LINES] 行 | C4 L1 Static |
| 文件长度 | ≤ [FILE_MAX_LINES] 行 | C4 L1 Static |
| 嵌套深度 | ≤ [NESTING_MAX] 层 | C4 L1 Static |
| 圈复杂度 | ≤ [CYCLOMATIC_MAX] | C4 L1 Static |

<!-- v4 default: 80 / 600 / 5 / 18 (Fork J, see suiyin-v4/docs/sdd/discussion-notes.md §9.5) -->

**Severity**: [QUANTITATIVE_SEVERITY]
<!-- Suggested: v0.1 阶段 Preference（warn 但不 block）；v1.0 spike 后视情况升 NON-NEGOTIABLE -->

## 7. Governance

### 7.1 修改流程

修改本宪法须：

1. **写 ADR**（`docs/adrs/NNN-{slug}.md`），说明：
   - 为什么改
   - 改前 → 改后 对比
   - 影响范围（哪些下层文档要 cascade）
2. **提 PR**（修改 constitution + 加 ADR，同一 PR）
3. **C5 AI Reviewer review**
4. **人审通过**（项目负责人拍板，宪法不允许 AI 自动 merge）
5. **merge**，版本号 bump：

| Bump | 触发 |
|---|---|
| MAJOR | 移除 / 重定义 principle，或修改 NON-NEGOTIABLE 性质 |
| MINOR | 新增 principle，或加 NON-NEGOTIABLE 标签 |
| PATCH | wording / 量化阈值微调 / 笔误修正 |

### 7.2 跟其他文档的关系

```
constitution.md  ← 最高约束（本文档）
       │
       ├─ specs/                   （能力 spec，待 specify 阶段产出）
       ├─ plans/                   （技术方案，待 plan 阶段产出）
       ├─ domain-glossary.md       （业务概念词典，待建）
       └─ adrs/                    （决策记录，待第一次 amendment）
```

**冲突时**：constitution > 其他所有。

### 7.3 单向引用

- constitution **只能引用**：spec 行为契约、suiyin-flow 方法论原则
- constitution **不能引用**：具体 spec / plan / task / 代码（避免 circular reference）

## 8. Open Questions

[OPEN_QUESTIONS]
<!-- 列出初版未决问题，待 spike / 经验积累后定 v1.0 -->

## 9. Version History

| Version | Date | Changes |
|---|---|---|
| **v0.1.0** | [RATIFICATION_DATE] | 初版 |

---

**Version**: [VERSION]
**Ratified**: [RATIFICATION_DATE]
**Last Updated**: [LAST_AMENDED_DATE]
**Status**: [STATUS]
<!-- Suggested: v0.1.0 / 2026-XX-XX / 2026-XX-XX / draft 或 ratified -->
