# 碎银 v4 项目宪法 (Constitution)

> **v4 工具链项目自身的宪法**。约束 v4 这个 **SDD 研发工具项目本身**的开发。
>
> **不是** v5 / v6 业务项目的 constitution——业务项目的 constitution 应由 v4 提供的 `/sy-constitution` generator 在各自仓里交互生成。
>
> **`extends: methodology.md`** —— SDD 流派规则（5 铁律 + 流程）隐式继承，本文档**不重复定义**。

---

## 0. Type

**Meta-spec**（项目级约束，非 C 编号工具链组件）

- [x] 行为契约（declarative — 定义"什么算合规"，本身没 imperative logic）

实现谱系不适用——constitution 是 spec / plan / task 的判定依据，由 C4 L4 (Constitution compliance) 和 C5 AI Reviewer 在它们各自实现里 enforce。

## 1. Purpose

定义 **v4 工具链项目本身**的：

- 项目身份（v4 是什么 / 不是什么）
- 项目独有约束（业务 NON-NEGOTIABLE / preference）
- AI 协作 profile（role-profile 选择）
- Governance（修改本宪法的流程）

**这些都是 v4 独有的，跟 v5 / v6 等业务项目无关**。SDD 通用规则在 methodology.md。

## 2. Public API

### 2.1 Input Schema（什么触发宪法的"使用"或"修改"）

```yaml
type: object
oneOf:
  - description: 工具链 spec/plan/task 请求合规校验
    required: [type, target_doc]
    properties:
      type: { const: compliance_check }
      target_doc: { type: string, description: "被校验的 v4 仓内 spec/plan/task 路径" }

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

- **I1**: v4 仓相关 spec / plan / task 必须 reference 本 constitution 的至少一条 constraint
- **I2**: project_constraints (NC/PC) 之间正交，无重复
- **I3**: NON-NEGOTIABLE 约束违反 = 阻断 PR（不可 override）
- **I4**: Preference 约束违反 = warn（可走 ADR 解释 override）
- **I5**: **本宪法不重复 SDD 通用规则** — 5 铁律在 methodology.md，本宪法 `extends` 它
- **I6**: 一年内 NC 数量稳定（频繁改的不是 NC，是 plan）

### 3.2 Side Effects

- 写入 `docs/sdd/constitution.md`（本文件）
- 写入 `docs/sdd/adrs/NNN-{slug}.md`（修改时）
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

### v4 是什么

**碎银 SDD 工具链研发项目**。**不是业务产品**——是给业务项目（v5 / v6 / ...）用的 SDD 流程引擎。

### 用户画像

- 业务专家 + 后端老兵（前端代码看不懂）
- AI 主写、人在 spec/plan 层拍板
- 多 session 并行开发

### 核心交付物

| 交付物 | 性质 |
|---|---|
| `suiyin-flow` CLI（installer + spec-kit fork + 自建 C1-C11） | 工具二进制 |
| Skill templates / Prompt templates（给业务项目生成 SDD 产物） | 数据 |
| 文档（methodology / workflows / diagrams / 本 constitution） | 知识 |

### v4 不是什么

- ❌ 不是业务产品（碎银业务在 v5/v6）
- ❌ 不是 spec-kit 替代品（v4 用 spec-kit 当 Layer 1 backbone）
- ❌ 不是 SaaS（必须能零 SaaS 跑）

## 6. Project-Specific Constraints

v4 独有的约束。**SDD 通用规则在 methodology.md，本节不重复**。

### NC-1: 零 SaaS 依赖（NON-NEGOTIABLE）

v4 工具链必须能在零 SaaS 环境下跑。GitHub / GitLab / 其他 SaaS 是**可选实现谱系**之一，不是 hard dependency。

**Rationale**: 业务项目可能在内网 / 私有部署 / 离线环境用 v4。绑死任何 SaaS = 失去这部分市场。

**Test**: 任何引入 SaaS 调用的 PR 必须提供 fallback 实现，否则 C5 finding `severity: high` → block。

### NC-2: spec-kit 作为 Layer 1 backbone（NON-NEGOTIABLE）

v4 不重造协商阶段轮子。spec-kit fork（`sy-*` 命名空间）是 Layer 1 唯一实现。

**Rationale**: spec-kit 是 GitHub 官方维护的成熟工具；重造没意义、维护成本高、跟 spec-kit 上游脱节。

**Test**: 任何在 Layer 1 自建新机制的 PR 必须解释为什么不能用 spec-kit fork → block by default。

### NC-3: 业务项目独立性（NON-NEGOTIABLE）

v4 工具的输出（v5 等业务项目的 SDD 产物）必须**独立于 v4 自身**。业务项目 clone 下来后不依赖 v4 仓存在也能跑（除了 update v4 时）。

**Rationale**: v4 是工具，业务项目不该耦合到工具仓的目录结构。

**Test**: v5 init 后 `cd v5 && rm -rf <v4 路径>`，业务项目自身命令仍可跑（除了 update）。

### NC-4: 隔离 worktree 是自动化执行的安全边界（NON-NEGOTIABLE）

所有 v4 自动化执行类组件（C2 Task Executor / C3 Multi-Implementation Arbiter / C5 AI Reviewer / 未来 imperative 组件）必须在隔离的 git worktree 内运行，**严禁直接对主仓 working tree 写入**。

**Rationale**: C2 等组件用 `--permission-mode bypassPermissions` 给 AI 全权 Write/Edit/Bash 工具访问。这套授权模型**只有 AI 隔离在 worktree 内才安全** — 一旦 AI 能动主仓 working tree，整个安全模型崩塌（写 git history / 切 branches / 改 settings）。引入 ADR-0003。

**Test**:
- C2 spec §3.1 I1/I2 已强制 worktree 路径命名 `worktrees/<task_id>` + AI session 必须在 worktree 内
- 未来 C3/C5/etc 组件 spec 必须延续这个 invariant
- 任何引入"主仓 working tree 写入"代码的 PR → C5 finding `severity: critical` → block，**不可 override**

### NC-5: 跨平台支持（NON-NEGOTIABLE）

v4 工具链（CLI / runner / installer / 任何 imperative 组件）必须在 **macOS / Linux / Windows** 三个 platform 都能跑。

**Rationale**: 业务项目可能跑各种 dev box（macOS / Linux / Windows 含 WSL）。v4 工具绑死 POSIX-only 等于丢这部分市场。跨平台代码成本不高（pathlib / psutil / shell=False / utf-8 explicit / shutil.which fallback），设计期付小成本 vs 长期重构代价大。引入 ADR-0003。

**Test**:
- 路径处理：`pathlib.Path`，**不**手拼 `/` 或 `os.sep`
- 进程管理：`psutil.Process.kill()`（跨平台），**不**用 `os.kill(SIGKILL)`（Windows 没 SIGKILL）
- subprocess：`shell=False` + `list[str]` args（避免 Windows shell 语义差异）
- 文件读写：显式 `encoding="utf-8"`（避免 Windows 默认 cp936/cp1252）
- 工具探测：`shutil.which` + venv binary fallback（PR #22 修过 venv PATH bug）
- 任何 POSIX-only 调用必须有 Windows fallback → 否则 C5 finding `severity: high` → block
- **P0 阶段**：macOS + Linux 必跑通；Windows ≥ smoke（手测一次）
- **P1+ 阶段**：Windows CI matrix 必须（升级到 runtime enforcement）

### PC-1: 最简实现优先（Preference）

设计新组件时必须先问"最简实现是什么"。**禁止默认重型 SaaS**。

**Rationale**: 见 toolchain.md §0.5 AI 提案审查清单。来自 C6 三次过度设计的反思。

**Test**: 新组件 spec 必须含"最简实现" + "为什么不选最简"两节。

### PC-2: 组件 vs 契约明确分离（Preference）

每个工具链节点必须明确标 imperative 组件还是 declarative 契约。详见 toolchain.md §0.5。

### PC-3: 中文优先双语支持（Preference）

所有面向用户的产物（CLI 提示、README、错误信息）以中文为主、英文为辅。

**Rationale**: 项目主用户是中文工程师，但工具应能 onboard 英文社区。

## 7. AI Collaboration Profile

**v4 自身用 `D-autonomous`** —— 4 档 role-profile 中的最高自治档。

详见 `role-profiles.md`。4 档简介：

| 档 | AI 自治程度 | v4 选择 |
|---|---|---|
| A assistant | 工具 | ❌ |
| B junior | AI 起草 + 人审 | ❌ |
| C collaborator | 自审 + 自动 merge | ❌ |
| **D autonomous** | 自治微调 | ✅ v4 default |

实际配置见 `runtime/role-profile.yml`（即 v4 仓内的 role-profile 实例）。

### Constitution 与 role-profile 的边界

- **constitution** 约束**行为原则**（NC/PC 不可妥协 / 项目身份）
- **role-profile** 配置**工作模式**（AI 自治程度 / git automation / 人介入点）

**两者不重叠**。constitution 引用 role-profile（"v4 用 D-autonomous"），但不内嵌 role-profile 内容。

修改 role-profile 不需要 ADR；修改 constitution 才需要。

### Constitution Bootstrap 特例

`/sy-constitution` 是 chicken-and-egg 入口——constitution 没立 → role-profile 没意义。所以：

- **所有 role-profile 档**强制 auto-commit + auto-push constitution 立基产物
- 协商可能多轮 → 每轮 commit + push 防丢失
- 实现：`runtime/extensions.yml` 的 `after_constitution` hook = `optional: false`（mandatory）

详见 `role-profiles.md`。

## 8. Governance

### 8.1 修改流程

修改本宪法须：

1. **写 ADR**（`docs/sdd/adrs/NNN-{slug}.md`）说明：为什么改 / 改前→改后 / 影响范围 / 兼容性
2. **提 PR**（修改 constitution.md + 加 ADR，同一 PR）
3. **C5 AI Reviewer review**（检查 invariants I1-I6，特别 I5 — 不能塞 SDD 通用规则）
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
constitution.md (本文档 — v4 项目独有)
       │
       │ 引用
       ↓
┌──────────────────────────────────┐
│ toolchain.md       (工具链规约)   │
│ workflows.md       (状态机)       │
│ diagrams.md        (流程图)       │
│ role-profiles.md   (AI 角色 4 档) │
│ component-spec-template.md       │
│ components/        (C 模块 spec)  │
│ adrs/              (决策记录)     │
└──────────────────────────────────┘

runtime/role-profile.yml (v4 自身 = autonomous)
```

**冲突时**：methodology > constitution > toolchain > 其他。methodology 是 root（SDD 流派本身），constitution 在它之上叠 v4 独有内容。

### 8.3 单向引用

- constitution **可以引用**：methodology.md（extends）
- constitution **不能引用**：具体 spec / plan / task / 代码（避免 circular reference）
- 下层文档**可以引用** constitution（constraint id）

违反 → `CIRCULAR_REFERENCE` error。

## 5b. Acceptance Criteria

constitution 的"AC"是**跨 PR 维度的 invariants 校验**，不是单点 AC。

- **AC-1**: v4 仓相关 PR 都 reference 本 constitution 至少一条 constraint (I1)
- **AC-2**: NC/PC 之间 logical orthogonality (I2，C5 季度 review)
- **AC-3**: NON-NEGOTIABLE 违反 100% 被 C4/C5 阻断 (I3)
- **AC-4**: 修改本宪法的 PR 100% 含 ADR (I4 governance)
- **AC-5**: **本宪法不重复 methodology.md 内容**（I5，C5 specific check）— 这条 AC 由 `SDD_RULE_DUPLICATION` error 触发
- **AC-6**: 一年内 NC 数量变化 ≤ 2 条 (I6)

## 6b. Open Questions

- **Q-C-1**: 完整 NON-NEGOTIABLE 集合 — 已拍 v1.0: 见 ADR-0003（NC-1..NC-5 + PC-1..PC-3）
- **Q-C-2**: v4 自身技术栈（CLI 用什么语言：Python / Shell / Bun / ...）— 已拍: 见 ADR-0002 (Python 3.11+)
- **Q-C-3**: ADR template 详细格式 — 第一个 ADR 写完后定型
- **Q-C-4**: NC-3 (业务项目独立性) 的具体 test 实现 — P0 spike 验证

## 7b. Implementation Notes

- 本宪法用 `component-spec-template.md` 格式写——template 的第一个 dogfood
- 章节 5/6/7 适用 imperative 组件；meta-spec 用 5b/6b/7b 区分
- **v0.1 → v0.2 重大重构**：
  - 删除 5 铁律内容（搬走，那是 methodology.md 的）
  - 删除通用量化阈值（业务项目 specific，应该由 generator 在 v5/v6 各自的 constitution 里生成）
  - 加 §5 Project Identity（v4 自身定义）
  - 加 §6 NC/PC 项目独有约束
  - 加 §7 AI Collaboration Profile（含 PR #6 引入的 role-profile 引用）
  - 加 §8 Constitution Bootstrap 特例（PR #6 引入）
  - 明确 `extends: methodology.md`

## 9. Version History

| Version | Date | Changes |
|---|---|---|
| v0.1.0 | 2026-05-18 | 初版（含 5 铁律复述，**层次混淆**）|
| v0.2.0 | 2026-05-18 | **重大重构**：去 SDD 通用内容、加 v4 项目独有约束（NC-1/2/3 + PC-1/2/3）；明确 extends methodology.md；保留 PR #6 引入的 role-profile 边界章节 |
| v0.2.1 | 2026-05-24 | PATCH: 关闭 Q-C-2 open question (v4 技术栈 = Python 3.11+, 见 ADR-0002) |
| v0.2.2 | 2026-05-24 | **MINOR**: NC v1.0 — 加 NC-4 (worktree 隔离安全边界) + NC-5 (跨平台支持); 关 Q-C-1 (NC-1..NC-5 + PC-1..PC-3); 见 ADR-0003 |

---

**Version**: v0.2.2
**Last Updated**: 2026-05-24
**Status**: NC v1.0 完整（5 NC + 3 PC），待 Q-C-3/Q-C-4 解决后整体稳态
