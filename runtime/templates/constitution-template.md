# [PROJECT_NAME] 项目宪法 (Constitution)

> [PROJECT_NAME] 项目最高约束。所有 spec / plan / task 必须符合本宪法。
>
> **`extends: methodology.md`** — SDD 流派通用规则（5 铁律、工作流 5 阶段、Bug 处理、spec rot 防御）由 suiyin-flow methodology 隐式继承，**本宪法不重复定义**。
>
> 修改本宪法须走 ADR + PR 流程（见 §8 Governance）。
>
> 本宪法用 [suiyin-flow component-spec-template](https://github.com/chinaszzt/suiyin-v4/blob/main/docs/sdd/component-spec-template.md) 格式写。

---

<!--
⚠️ 写宪法前必读 —— Constitution 边界（防 v0.1 层次混淆复现）

本文档**只放本项目独有的约束 + 项目身份 + 治理流程**。下列内容**禁止**塞入：

1. ❌ **SDD 通用规则** — 5 铁律（spec 先于代码 / spec 写可观察行为 / bug 先翻 spec / 改代码同步改 spec / 拍板前移）、工作流 5 阶段、Bug A/B/C/D 分类、spec rot 防御。这些在 methodology.md，本宪法 `extends` 它，不复述。
2. ❌ **业务/工程 specific 量化指标** — 函数长度、文件行数、嵌套深度、圈复杂度。这些应该放各项目的 plan.md 或 verify-contract spec，不是 constitution 级别。
3. ❌ **具体 spec / plan / task / 代码路径引用** — 避免 circular reference（详见 §8.3）。

某条规则是否该进 constitution？三问：
- 这条规则**在其他项目里也成立** → 是 → 归 methodology，不进
- 这条规则**只在本项目成立**且**严肃到 PR-level 阻断** → 是 → 写成 NC-*
- 这条规则**只在本项目成立**但**违反时只 warn / 允许 ADR override** → 是 → 写成 PC-*
- 都不是 → 不进 constitution

**历史教训**：suiyin-v4 constitution v0.1 把 5 铁律和 v4 specific 量化阈值（80 / 600 / 5 / 18）塞进 §5 §6，user dogfood 时一眼指出层次混淆，v0.2 大改。详见 v4 仓 `docs/sdd/adrs/`。
-->

## 0. Type

**Meta-spec**（项目级约束，非 C 编号工具链组件）

- [x] 行为契约（declarative — 定义"什么算合规"，本身没 imperative logic）

实现谱系不适用——constitution 是 spec / plan / task 的判定依据，由 C4 L4 (Constitution compliance) 和 C5 AI Reviewer 在它们各自实现里 enforce。

## 1. Purpose

定义 **[PROJECT_NAME] 项目**的：

- 项目身份（[PROJECT_NAME] 是什么 / 不是什么）
- 项目独有约束（NON-NEGOTIABLE / Preference）
- AI 协作 profile（role-profile 选择）
- Governance（修改本宪法的流程）

**这些都是 [PROJECT_NAME] 独有的，跟其他项目无关**。SDD 通用规则继承自 methodology.md。

## 2. Public API

### 2.1 Input Schema（什么触发宪法的"使用"或"修改"）

```yaml
type: object
oneOf:
  - description: spec/plan/task 请求合规校验
    required: [type, target_doc]
    properties:
      type: { const: compliance_check }
      target_doc: { type: string, description: "被校验的本仓内 spec/plan/task 路径" }

  - description: 宪法修改请求
    required: [type, proposed_change, adr_ref, version_bump_type]
    properties:
      type: { const: amendment }
      proposed_change: { type: string }
      adr_ref: { type: string }
      version_bump_type:
        enum: [MAJOR, MINOR, PATCH]
```

### 2.2 Output Schema

```yaml
type: object
oneOf:
  - description: Compliance 校验结果
    required: [target_doc, verdict, violated_constraints]
    properties:
      target_doc: { type: string }
      verdict:
        enum: [pass, warn, block]
      violated_constraints:
        type: array
        items:
          type: object
          properties:
            constraint_id: { type: string, pattern: '^(NC|PC)-\d+$' }
            severity:
              enum: [non_negotiable_violation, preference_violation]
            details: { type: string }

  - description: 宪法当前文档状态
    required: [version, extends, project_constraints, role_profile, last_amended]
    properties:
      version: { type: string, pattern: '^v\d+\.\d+\.\d+$' }
      extends: { type: string, description: "methodology.md 路径" }
      project_constraints: { type: array, items: { type: object } }
      role_profile: { type: string, enum: [assistant, junior, collaborator, autonomous] }
      last_amended: { type: string, format: date }
```

### 2.3 Error Schema

```yaml
type: object
required: [code, message]
properties:
  code:
    enum:
      - CONSTRAINT_NOT_FOUND       # spec 引用了不存在的 NC/PC id
      - INVALID_VERSION_BUMP       # 版本 bump 类型不匹配实际变更
      - MISSING_ADR                # 修改没附 ADR
      - CIRCULAR_REFERENCE         # constitution 引用了下层文档
      - SDD_RULE_DUPLICATION       # 本宪法重复定义了 methodology.md 的 SDD 通用规则
  message: { type: string }
  details: { type: object }
```

## 3. Behavior Contract

### 3.1 Invariants

- **I1**: 本仓相关 spec / plan / task 必须 reference 本 constitution 的至少一条 constraint
- **I2**: project_constraints (NC/PC) 之间正交，无重复
- **I3**: NON-NEGOTIABLE 约束违反 = 阻断 PR（不可 override）
- **I4**: Preference 约束违反 = warn（可走 ADR 解释 override）
- **I5**: **本宪法不重复 SDD 通用规则** — 5 铁律在 methodology.md，本宪法 `extends` 它
- **I6**: 一年内 NC 数量稳定（频繁改的不是 NC，是 plan）

### 3.2 Side Effects

- 写入 `.specify/memory/constitution.md`（本文件）
- 写入 `docs/adrs/NNN-{slug}.md`（修改时）
- 触发 C4 L4 + C5 finding rule 更新（constraints 改变后）

### 3.3 Failure Modes

| 失败类型 | 触发条件 | 处理 |
|---|---|---|
| `CONSTRAINT_NOT_FOUND` | spec 引用未定义的 NC/PC id | block PR |
| `INVALID_VERSION_BUMP` | PATCH 改动改了 constraint 语义 | block PR，要求 MINOR / MAJOR |
| `MISSING_ADR` | 修改本文件但 PR 无 ADR | block PR |
| `CIRCULAR_REFERENCE` | constitution 引用 spec/plan | block PR |
| `SDD_RULE_DUPLICATION` | 本宪法塞 SDD 通用规则（应在 methodology.md） | block PR，要求移出 |

## 4. AI Prompt Template

**N/A** — declarative meta-spec，不跑 AI prompt。由 C4 L4 + C5 AI Reviewer 在它们的 prompt 里 reference。

## 5. Project Identity

### [PROJECT_NAME] 是什么

[PROJECT_IDENTITY_WHAT]
<!-- Example (来自 suiyin-v4):
  **碎银 SDD 工具链研发项目**。**不是业务产品**——是给业务项目（v5 / v6 / ...）用的 SDD 流程引擎。
-->

### 用户画像

[USER_PERSONA]
<!-- Example:
  - 业务专家 + 后端老兵（前端代码看不懂）
  - AI 主写、人在 spec/plan 层拍板
  - 多 session 并行开发
-->

### 核心交付物

[CORE_DELIVERABLES]
<!-- Example (来自 suiyin-v4):
  | 交付物 | 性质 |
  |---|---|
  | suiyin-flow CLI（installer + spec-kit fork + 自建 C1-C11） | 工具二进制 |
  | Skill templates / Prompt templates | 数据 |
  | 文档（methodology / workflows / constitution） | 知识 |
-->

### [PROJECT_NAME] 不是什么

[PROJECT_IDENTITY_NOT]
<!-- Example (来自 suiyin-v4):
  - ❌ 不是业务产品（碎银业务在 v5/v6）
  - ❌ 不是 spec-kit 替代品（v4 用 spec-kit 当 Layer 1 backbone）
  - ❌ 不是 SaaS（必须能零 SaaS 跑）

  通常列 3-5 条常见误解，帮读者快速划清边界。
-->

## 6. Project-Specific Constraints

[PROJECT_NAME] 独有的约束。**SDD 通用规则继承自 methodology.md，本节不复述**。

约定：
- **NC-N**（NON-NEGOTIABLE Constraint）= 违反**阻断 PR**，不可 override
- **PC-N**（Preference Constraint）= 违反**仅 warn**，可走 ADR 解释 override

NC / PC 的数量按本项目实际需要，**不强求条数**。质量优于数量——空缺好过塞噪声。

<!-- 写一条 NC/PC 前先问 §0 顶部的"边界教戒"三问，确认它不归 methodology / plan.md / verify-contract。 -->

### NC-1: [NC_1_NAME] (NON-NEGOTIABLE)

[NC_1_STATEMENT]

**Rationale**: [NC_1_RATIONALE]

**Test**: [NC_1_TEST]

<!-- Example (来自 suiyin-v4 NC-1):
  Name: 零 SaaS 依赖
  Statement: v4 工具链必须能在零 SaaS 环境下跑。GitHub / GitLab / 其他 SaaS 是可选实现谱系之一，不是 hard dependency。
  Rationale: 业务项目可能在内网/私有部署/离线环境用 v4。绑死任何 SaaS = 失去这部分市场。
  Test: 任何引入 SaaS 调用的 PR 必须提供 fallback 实现，否则 C5 finding `severity: high` → block。
-->

### NC-2: [NC_2_NAME] (NON-NEGOTIABLE)

[NC_2_STATEMENT]

**Rationale**: [NC_2_RATIONALE]

**Test**: [NC_2_TEST]

<!-- 按项目需要增删 NC-3 / NC-4 ... 。空缺 NC 直接删掉本节即可，不要留 [PLACEHOLDER]。 -->

### PC-1: [PC_1_NAME] (Preference)

[PC_1_STATEMENT]

**Rationale**: [PC_1_RATIONALE]

**Test**: [PC_1_TEST]

<!-- Example (来自 suiyin-v4 PC-1):
  Name: 最简实现优先
  Statement: 设计新组件时必须先问"最简实现是什么"。禁止默认重型 SaaS。
  Rationale: 来自 C6 三次过度设计的反思。
  Test: 新组件 spec 必须含"最简实现" + "为什么不选最简"两节。
-->

### PC-2: [PC_2_NAME] (Preference)

[PC_2_STATEMENT]

**Rationale**: [PC_2_RATIONALE]

**Test**: [PC_2_TEST]

<!-- 按项目需要增删 PC-3 / PC-4 ... -->

## 7. AI Collaboration Profile

**[PROJECT_NAME] 用 `[ROLE_PROFILE]`** —— suiyin-flow 4 档 role-profile 之一。

实际配置见 `.specify/role-profile.yml`（本仓内的 role-profile 实例）。4 档定义见 suiyin-flow `role-profiles.md`：

| 档 | AI 自治程度 | 适用场景 |
|---|---|---|
| A assistant | 工具 | 学习 / 初探 |
| B junior | AI 起草 + 人审 | 严肃业务 / 多人协作 |
| C collaborator | 自审 + 自动 merge | 单人 + 中等风险 |
| D autonomous | 自治微调 | 工具链 / dogfood 项目 |

### Constitution 与 role-profile 的边界

- **constitution** 约束**行为原则**（NC/PC 不可妥协 / 项目身份）
- **role-profile** 配置**工作模式**（AI 自治程度 / git automation / 人介入点）

**两者不重叠**。constitution 引用 role-profile 名（如"用 D-autonomous"），但**不内嵌** role-profile 字段内容。

修改 role-profile 不需要 ADR；修改 constitution 才需要。

### Constitution Bootstrap 特例

`/sy-constitution` 是 chicken-and-egg 入口——constitution 没立 → role-profile 没意义。所以：

- **所有 role-profile 档**强制 auto-commit + auto-push constitution 立基产物
- 协商可能多轮 → 每轮 commit + push 防丢失
- 实现：`.specify/extensions.yml` 的 `after_constitution` hook = `optional: false`（mandatory）

详见 `role-profiles.md` 的 Bootstrap 特例集合。

## 8. Governance

### 8.1 修改流程

修改本宪法须：

1. **写 ADR**（`docs/adrs/NNN-{slug}.md`）说明：为什么改 / 改前 → 改后 / 影响范围 / 兼容性
2. **提 PR**（修改 constitution.md + 加 ADR，同一 PR）
3. **C5 AI Reviewer review**（检查 invariants I1-I6，**特别 I5 — 不能塞 SDD 通用规则**）
4. **人审通过**（项目负责人拍板，宪法不允许 AI 自动 merge）
5. **merge**，版本号 bump：

| Bump | 触发 |
|---|---|
| **MAJOR** | 移除 / 重定义 NC，或修改 NON-NEGOTIABLE 性质 |
| **MINOR** | 新增 NC / PC |
| **PATCH** | wording / 笔误修正 |

### 8.2 跟其他文档的关系

```
methodology.md (SDD 通用规则 — 5 铁律 + 流程)
       ↑
       │ extends
       │
constitution.md (本文档 — [PROJECT_NAME] 项目独有)
       │
       │ 引用
       ↓
┌──────────────────────────────────┐
│ specs/             (能力 spec)    │
│ plans/             (技术方案)     │
│ tasks/             (执行任务)     │
│ domain-glossary.md (业务词典)     │
│ adrs/              (决策记录)     │
│ role-profile.yml   (协作模式)     │
└──────────────────────────────────┘
```

**冲突时**：methodology > constitution > 其他。methodology 是 root（SDD 流派本身），constitution 在它之上叠 [PROJECT_NAME] 独有内容。

### 8.3 单向引用

- constitution **可以引用**：methodology.md（extends）
- constitution **不能引用**：具体 spec / plan / task / 代码路径（避免 circular reference）
- 下层文档**可以引用** constitution（constraint id）

违反 → `CIRCULAR_REFERENCE` error。

## 5b. Acceptance Criteria

constitution 的"AC"是**跨 PR 维度的 invariants 校验**，不是单点 AC。

- **AC-1**: 本仓相关 PR 都 reference 本 constitution 至少一条 constraint (I1)
- **AC-2**: NC/PC 之间 logical orthogonality (I2，C5 季度 review)
- **AC-3**: NON-NEGOTIABLE 违反 100% 被 C4/C5 阻断 (I3)
- **AC-4**: 修改本宪法的 PR 100% 含 ADR (governance §8.1)
- **AC-5**: **本宪法不重复 methodology.md 内容** (I5，C5 specific check) — 这条 AC 由 `SDD_RULE_DUPLICATION` error 触发
- **AC-6**: 一年内 NC 数量变化 ≤ 2 条 (I6)

## 6b. Open Questions

[OPEN_QUESTIONS]
<!-- Example:
  - **Q-1**: 完整 NON-NEGOTIABLE 集合 — P0 spike 后定 v1.0
  - **Q-2**: 本项目技术栈 — 待 Initiative 决策
  - **Q-3**: ADR template 详细格式 — 第一个 ADR 写完后定型
-->

## 7b. Implementation Notes

- 本宪法用 `component-spec-template.md` 格式写——meta-spec 的 dogfood
- 章节 5 / 6 / 7 / 8 适用 imperative 组件；meta-spec 用 5b / 6b / 7b 区分
- 顶部"边界教戒" callout 是防御性指引，禁止删除——防止下个项目 / 下个 session 又踩 v0.1 层次混淆坑

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
