# 碎银 v4 项目宪法 (Constitution)

> v4 项目最高约束。**所有 spec / plan / task 必须符合本宪法**。
>
> 修改本宪法须走 ADR + PR 流程（见 §7 Governance）。
>
> 本宪法用 `component-spec-template.md` 格式写——dogfood 该模板（principles 是一种 spec，统一格式便于 AI 跑 review）。

---

## 0. Type

**Meta-spec**（项目级约束，非 C 编号工具链组件）

- [x] 行为契约（declarative — 定义"什么算合规"，但本身没 imperative logic）

实现谱系不适用——constitution 是 spec / plan / task 的判定依据，由 C4 L4 (Constitution compliance) 和 C5 AI Reviewer 在它们各自实现里 enforce。

## 1. Purpose

一句话：**定义碎银 v4 项目的不可妥协原则、项目身份、治理流程，作为所有 spec / plan / task 的最高约束。**

## 2. Public API

### 2.1 Input Schema（什么触发宪法的"使用"或"修改"）

```yaml
type: object
oneOf:
  - description: Spec/plan/task 请求合规校验
    required: [type, target_doc]
    properties:
      type: { const: compliance_check }
      target_doc: { type: string, description: "被校验的 spec/plan/task 路径" }

  - description: 宪法修改请求
    required: [type, proposed_change, adr_ref, version_bump_type]
    properties:
      type: { const: amendment }
      proposed_change: { type: string }
      adr_ref: { type: string, description: "ADR 文档路径" }
      version_bump_type:
        enum: [MAJOR, MINOR, PATCH]
```

### 2.2 Output Schema（宪法当前状态 + 校验结果）

```yaml
type: object
oneOf:
  - description: Compliance 校验结果
    required: [target_doc, verdict, violated_principles]
    properties:
      target_doc: { type: string }
      verdict:
        enum: [pass, warn, block]
      violated_principles:
        type: array
        items:
          type: object
          properties:
            principle_id: { type: string, pattern: '^P-[IVX]+$' }
            severity:
              enum: [non_negotiable_violation, preference_violation]
            details: { type: string }

  - description: 宪法当前文档状态
    required: [version, principles, governance, last_amended]
    properties:
      version: { type: string, pattern: '^v\d+\.\d+\.\d+$' }
      principles: { type: array, items: { type: object } }
      governance: { type: object }
      last_amended: { type: string, format: date }
```

### 2.3 Error Schema

```yaml
type: object
required: [code, message]
properties:
  code:
    enum:
      - PRINCIPLE_NOT_FOUND        # 引用了不存在的 principle id
      - INVALID_VERSION_BUMP        # 版本 bump 类型不匹配实际变更
      - MISSING_ADR                 # 修改没附 ADR
      - CIRCULAR_REFERENCE          # constitution 引用了下层文档（应单向）
  message: { type: string }
  details: { type: object }
```

## 3. Behavior Contract

### 3.1 Invariants

- **I1**: 所有 spec / plan / task 必须 reference 至少一条 principle（隐式或显式）
- **I2**: principles 之间正交，无重复（review 时校验）
- **I3**: principles 可证伪（违反时能被发现，否则不是 principle 而是装饰）
- **I4**: NON-NEGOTIABLE 标签的 principle 违反 = 阻断 PR（不可 override）
- **I5**: 非 NON-NEGOTIABLE 违反 = warn（可走 ADR 解释 override）
- **I6**: 一年内 principle 数量稳定（频繁改的不是 principle，是 plan）

### 3.2 Side Effects

- 写入 `docs/sdd/constitution.md`（本文件）
- 写入 `docs/sdd/adrs/NNN-{slug}.md`（修改时）
- 触发 C4 L4 + C5 finding rule 更新（principles 改变后）

### 3.3 Failure Modes

| 失败类型 | 触发条件 | 处理 |
|---|---|---|
| `PRINCIPLE_NOT_FOUND` | spec 引用未定义的 principle id | block PR，提示补 principle |
| `INVALID_VERSION_BUMP` | PATCH 改动改了 principle 语义 | block PR，要求改 MINOR / MAJOR |
| `MISSING_ADR` | 修改本文件但 PR 无 ADR | block PR |
| `CIRCULAR_REFERENCE` | constitution 引用 spec/plan | block PR，constitution 是 root 单向 |

## 4. AI Prompt Template

**N/A** — constitution 是 declarative meta-spec，不跑 AI prompt。它由 C4 L4 (Constitution compliance check) 和 C5 AI Reviewer (`constitution_breach` finding) 在它们各自的 prompt 里被 reference。

## 5. Core Principles

5 条核心原则，来自 `methodology.md §10` 的 5 条铁律。每条都可证伪、正交、稳定。

### Principle I: Spec 先于代码 (NON-NEGOTIABLE)

**Statement**: 任何新能力必须先写 spec 再写代码——不允许跳过。

**Rationale**: AI 主写项目中 spec 是 AI 的长期记忆和意图契约，跳过会导致多 session 间漂移。

**Test**: 任何 PR 必须 reference 一个 spec.md（含 spec_ref anchor）。无 spec_ref 的 PR → C4 L3 block。

**Severity**: NON-NEGOTIABLE — 违反 = block PR，不可 override。

### Principle II: Spec 范围 = 用户/外部观察者可观察行为

**Statement**: Spec 只写用户/外部观察者可观察的行为（含异常、边界、外部约束传染）。实现细节归 plan。

**Rationale**: 意图与实现分离让 spec 在重写实现时仍然成立——它是行为契约，不是技术方案。

**Test**: C5 AI Reviewer 跑 review 时检查 spec.md 是否含实现术语（widget / SQL / API path 等）。含 → finding `severity: medium`。

**Severity**: Preference（违反 → warn，需走 ADR 说明）。

### Principle III: Bug 必须先翻 spec

**Statement**: 每个 bug 第一步是找相关 spec → 对照 AC 分类（Type A/B/C/D）→ 按 type 处理。**找不到 spec 不能绕过**。

**Rationale**: Bug 是 spec 最高频的鲜活机制；跳过 = spec rot 的入口。

**Test**: bug ticket 模板第一项必填"相关 spec 路径"（未填阻断 issue 提交）。

**Severity**: NON-NEGOTIABLE — issue 模板硬约束。

### Principle IV: 代码改 = spec 改 (NON-NEGOTIABLE)

**Statement**: 任何修改代码 MUST 在同一个 PR 内同步修改对应 spec。CI 校验代码注释里的 `spec_ref` 锚点。

**Rationale**: Spec rot 是 SDD 最大失败模式；硬约束是唯一防御手段，自律靠不住。

**Test**: PR diff 含代码改动但无对应 spec 改动 → C4 L4 check 标 `spec_drift` finding → block。

**Severity**: NON-NEGOTIABLE — 违反 = block PR。

### Principle V: 拍板前移到 spec / plan 层

**Statement**: 资深判断力用在 Constitution / Spec / Plan 层；PR 层只对照验收标准（自动化 + AI Review）。

**Rationale**: 改 spec 比改代码便宜 100 倍——在更高杠杆点做决定。

**Test**: PR review 阶段如果出现 plan 级以上的设计争议 → 标 `spec-drift` issue 回 Plan 阶段（不在 PR 阶段决策）。

**Severity**: Preference（违反 → warn）。

## 6. Quantitative Standards（v0.1 暂定，spike 后调整）

**这些是 v0.1 暂定值**，来自 Fork J 决策。**P0 spike 后视实际跑出来的结果调整到 v1.0**。

| 维度 | 阈值 | 来源 | Enforce 位置 |
|---|---|---|---|
| 函数长度 | ≤ 80 行 | Fork J | C4 L1 Static |
| 文件长度 | ≤ 600 行 | Fork J | C4 L1 Static |
| 嵌套深度 | ≤ 5 层 | Fork J | C4 L1 Static |
| 圈复杂度 | ≤ 18 | Fork J | C4 L1 Static |

**Severity**: Preference（v0.1 阶段）— warn 但不 block。v1.0 阶段重新评估是否升 NON-NEGOTIABLE。

## 7. Governance

### 7.1 修改流程

修改本宪法须：

1. **写 ADR**（`docs/sdd/adrs/NNN-{slug}.md`），说明：
   - 为什么改
   - 改前 → 改后 对比
   - 影响范围（哪些下层文档要 cascade）
   - 兼容性 / 迁移方案
2. **提 PR**（修改 constitution.md + 加 ADR 文件，同一 PR）
3. **C5 AI Reviewer review**（检查 invariants I1-I6）
4. **人审通过**（项目负责人拍板，宪法不允许 AI 自动 merge）
5. **merge**，版本号 bump：

| Bump | 触发 |
|---|---|
| **MAJOR** | 移除 / 重定义 principle，或修改 NON-NEGOTIABLE 性质 |
| **MINOR** | 新增 principle，或加 NON-NEGOTIABLE 标签 |
| **PATCH** | wording / 量化阈值微调 / 笔误修正 |

### 7.2 跟其他文档的关系

```
constitution.md  ← 最高约束（本文档）
       │
       ├─ methodology.md      （方法论实践细则，给团队读）
       ├─ toolchain.md        （工具链规约：组件 + 契约）
       ├─ workflows.md        （状态机和流程图）
       ├─ diagrams.md         （流程图集）
       ├─ domain-glossary.md  （业务概念词典，待建）
       ├─ component-spec-template.md  （C 模块 spec meta-template）
       ├─ components/         （各 C 模块 spec）
       └─ adrs/               （决策记录，待建）
```

**冲突时**：constitution > methodology > toolchain > 其他。constitution 修改触发 cascade 检查下层文档。

### 7.3 单向引用

- constitution **只能引用**：spec 行为契约、methodology 的方法论原则
- constitution **不能引用**：具体 spec / plan / task / 代码（避免 circular reference）
- 下层文档**可以引用** constitution（principle id）

违反 → `CIRCULAR_REFERENCE` error。

## 5b. Acceptance Criteria（合规验证）

constitution 的"AC"是跨 PR 维度的 invariants 校验。不是单点 AC。

- **AC-1**: 任何被 merge 的 PR，其对应 spec/plan/task 都 reference 至少一条 principle（I1）
- **AC-2**: 5 条 principles 之间无 logical overlap（I2，C5 季度 review）
- **AC-3**: NON-NEGOTIABLE 违反在 100% 的情况下被 C4/C5 阻断（I4）
- **AC-4**: 修改 constitution 的 PR 100% 含 ADR（I3 governance）
- **AC-5**: 一年内 principle 数量变化 ≤ 2 条（I6，否则 governance 失败）

## 6b. Open Questions

- **Q-C-1**: NON-NEGOTIABLE 严格规则完整集合 — P0 spike 后定 v1.0（当前只有 P-I, P-III, P-IV 是 NON-NEGOTIABLE）
- **Q-C-2**: 完整技术栈选型（Flutter / React 等）— 应该走 Initiative 决策，不在 constitution 里硬塞
- **Q-C-3**: 性能 / 安全 / 可观察性硬指标 — 业务场景跑过才知道
- **Q-C-4**: 项目身份描述（"碎银 v4 是什么"的精确措辞）— 待跟用户共建第一个 spec 时同步沉淀
- **Q-C-5**: ADR template 详细格式 — 第一个 ADR 写完后定型

## 7b. Implementation Notes

- 本宪法**用 `component-spec-template.md` 格式写**，作为 template 的第一个 dogfood
- 写完发现 template 有不适配 meta-spec 的地方（如 AI Prompt Template / 单点 AC）→ template 自身需要 v0.2 调整
- 章节编号有 5b/6b/7b — 因为前 4 章是 template 标准章节，5/6/7 适用于 imperative 组件；meta-spec 用 b 编号区分
- 跟 methodology.md 的 5 条铁律完全对齐 — methodology 是给团队读的叙事版，constitution 是给 AI/工具 read 的契约版

## 8. Version History

| Version | Date | Changes |
|---|---|---|
| **v0.1.0** | 2026-05-18 | 初版：5 principles + governance + 暂定量化阈值；NON-NEGOTIABLE 严格规则 / 技术栈 / 性能 等待 v1.0 |

---

**Version**: v0.1.0
**Last Updated**: 2026-05-18
**Status**: 暂定，待 P0 spike 跑过后升 v1.0
