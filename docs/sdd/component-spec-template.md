# 碎银 v4 SDD — Component Spec Template

> 本模板定义每个 C 模块（C1-C11）的 spec 应该长什么样。统一形态让 AI/人 review 时有共同语言。
>
> **Constitution 也用此模板**（principles 本质是一种 spec，统一格式便于 AI 跑 review）。
>
> 后续所有 C 模块 spec 写在 `docs/sdd/components/c{N}-{kebab-name}.md`，遵守此模板。

---

## 使用方式

1. 创建 `components/c{N}-{kebab-case-name}.md`（例：`c2-task-executor.md`）
2. 按 8 个标准章节顺序填写
3. 缺章节 → 显式 `N/A` + 理由（不能默默跳过）
4. spec 完成后由 C5 AI Reviewer review

## 标准章节清单

| 章节 | 必填 | 适用 |
|---|---|---|
| **0. Type** | ✅ | 全部 |
| **1. Purpose** | ✅ | 全部 |
| **2. Public API**（Input / Output / Error Schema） | ✅ | 全部 |
| **3. Behavior Contract**（Invariants + Side Effects + Failure Modes） | ✅ | 全部 |
| **4. AI Prompt Template** | ⚠ | **仅 imperative 组件** |
| **5. Acceptance Criteria** | ✅ | 全部 |
| **6. Open Questions** | ⚠ 可空 | 全部 |
| **7. Implementation Notes** | ⚠ 可空 | 全部 |

---

## 模板正文（复制下面这块当新 spec 起点）

````markdown
# C{N} {Name} — Component Spec

> 一段 introduction：这个模块的 high-level 描述（2-4 行）。

## 0. Type

- [ ] 自建组件（imperative logic — 需要写代码）
- [ ] 行为契约（declarative contract — 配置 + 编排）

**如果是契约**，标注实现选项推荐：
- 实现谱系优先级：(a) 本地 hook / (b) 通用 CI / (c) SaaS / (d) 混合
- v4 推荐：(d) 混合（除非有特殊理由）

## 1. Purpose

一句话：这个模块**做什么**。

## 2. Public API

### 2.1 Input Schema

```yaml
type: object
required: [...]
properties:
  field_a:
    type: string
    description: ...
  field_b:
    type: array
    items: {...}
```

### 2.2 Output Schema

```yaml
type: object
required: [...]
properties: ...
```

### 2.3 Error Schema（失败时的结构化错误）

```yaml
type: object
required: [code, message]
properties:
  code:
    enum: [TIMEOUT, VERIFY_FAILED, SESSION_CRASHED, ...]
  message: { type: string }
  details: { type: object }
  retryable: { type: boolean }
```

## 3. Behavior Contract

### 3.1 Invariants（不变量）

跨调用必须成立的事实：

- 不变量 1: ...
- 不变量 2: ...

### 3.2 Side Effects

外部副作用（文件系统、git、网络、API 调用等）：

- side effect 1: ...
- side effect 2: ...

### 3.3 Failure Modes

可能的失败类型 + 对应处理：

| 失败类型 | 触发条件 | 处理动作 |
|---|---|---|
| `TIMEOUT` | ... | retry / kill / 升级 |
| `VERIFY_FAILED` | ... | ... |

## 4. AI Prompt Template

**仅 imperative 组件需要**。契约写 `N/A — 此模块是契约，不跑 AI prompt`。

````markdown
# {Module Name} — Execution Prompt

## Your Role
你是 C{N} {Name}。

## Input
{input_var} = <JSON/YAML，符合 §2.1 schema>

## Steps
1. ...
2. ...
3. ...

## Output
按 §2.2 schema 输出 JSON/YAML。

## Constraints (来自 §3 contract)
- 不能 ...
- 必须 ...
- 失败时输出符合 §2.3 error schema 的结构化错误
````

## 5. Acceptance Criteria

可证伪的 AC（每条必须能写出 test 验证）：

- **AC-1**: 给定 input X，输出符合 §2.2 schema 的 Y
- **AC-2**: 失败场景 Z 时输出 error code W
- **AC-3**: 不变量 N 始终成立（跨 100 次调用）

## 6. Open Questions

- **Q{N}-1**: 未决问题 1
- **Q{N}-2**: 未决问题 2

（无则写 `无未决问题`）

## 7. Implementation Notes

实现建议（非规范，但有用）：

- 技术栈建议
- 外部工具依赖
- 并发 / 性能注意
- 跟其他 C 模块的协作点

---

**Version**: v0.1.0-draft
**Last Updated**: YYYY-MM-DD
**Status**: draft / accepted / superseded
````

---

## 跟 Constitution / Methodology 的关系

| 文档 | 角色 | 跟本模板的关系 |
|---|---|---|
| **constitution.md** | 项目最高约束 | 本模板的元规则；constitution 自己也用此模板写 |
| **methodology.md** | 方法论原则 | 解释 spec 怎么写好 |
| **toolchain.md** | 工具链总览 | 列出 11 个 C 模块身份（节点定义）；细节由本模板写出的 component spec 补全 |
| **本模板** | meta-spec | 定义 C 模块 spec 形态 |
| **components/c{N}-*.md** | 单个 C 模块 spec | 按本模板填 |

---

## 11 个 C 模块的 spec 落地优先级

| 优先级 | 模块 | 备注 |
|---|---|---|
| **P0** | C2 Task Executor, C4 Verify Contract | MVP 必需 |
| **P1** | C5 AI Reviewer, C6 Gate Contract | 自闭环 |
| **P2** | C1 Planning Engine, C7 Phase Coordinator | 并行加速 |
| **P3** | C3 Arbiter, C11 Function Registry | 强化 |
| **P4** | C8 Deploy Contract, C9 Affected Specs Cascade, C10 Spec Overlap Detector | 收尾 |

每个 C 模块 spec 写完进入实施。

---

**Version**: v0.1.0-draft
**Last Updated**: 2026-05-18
**Status**: draft（meta-spec，需要先 dogfood 几个 C 模块再迭代）
