# 碎银 v4 SDD — 进行中讨论笔记 (WIP)

> 本文档是 wip 笔记。Session 后半段（复杂度治理 + 代码复用治理）的零散讨论点集合，**后续 2 天讨论后会消化到正式文档**：toolchain.md / workflows.md / methodology.md / 未来的 constitution.md / domain-glossary.md。
>
> 跟正式文档的本质区别：本文档是**讨论中**状态，结论可能再变；正式文档是**已拍板**状态。

---

## 〇、当前进度

| 文档 | 状态 |
|---|---|
| `methodology.md` | ✅ 已 merged（commit `ca1f7c5`） |
| `toolchain.md` (8 个组件 C1-C8) | ⏳ PR #1 |
| `workflows.md` (主流程 + bug + Initiative + C9) | ⏳ PR #1 |
| **`discussion-notes.md` (本文档)** | ⏳ PR #1 |
| `constitution.md` | 未开始 |
| `domain-glossary.md` | 未开始 |

**下一步**：2 天画明确流程，然后实现核心部分（P0）。

---

## 一、主题：代码复杂度治理

### 1.1 为什么 v4 特别需要

AI native 流程下复杂度治理**特别难**：

- 传统靠人审 PR 时喊停，v4 拿掉人审 → **没人喊停**
- AI 偏好写更多代码（defensive / 抽象 / 重复实现）
- 不主动建机制 = 半年后冗余代码淹没

### 1.2 复杂度 4 个维度

| 维度 | 例子 | 最佳治理节点 |
|---|---|---|
| **结构** | 函数 200 行、嵌套 6 层 | Verify L1 Static（自动硬阻断） |
| **认知** | 读 10 遍才懂 | AI Reviewer（LLM 判断） |
| **架构** | 不必要的抽象层 | Plan + AI Reviewer |
| **重复实现** | AI 重写已有功能 | AI Reviewer 语义检测 + C11 |

### 1.3 6 层防御机制（不需要新组件，扩展现有节点）

1. **Constitution** — NON-NEGOTIABLE `"简单 > 完整 > 优雅"` + 量化指标
2. **Plan 阶段** — 强制一节 `"Could this be simpler?"`
3. **Task 拆解** — task 改 > 500 行 / > 5 文件 自动拆分
4. **Verify L1 Static** — 复杂度阈值硬阻断 + jscpd 重复代码检测
5. **AI Reviewer** — 加 `complexity` finding 类别（含重复实现检测）
6. **季度复杂度盘点** — 全 codebase audit 找热点 → refactor backlog

### 1.4 量化指标（候选）

TigerBeetle 风：函数 ≤ 70 行 / 文件 ≤ 500 行 / 嵌套 ≤ 4 层 / 圈复杂度 ≤ 15。

**待决策 — Fork J**：严格 / 折中 / v4 自定义。

### 1.5 AI Reviewer "重复实现"检测的特殊要求

Reviewer 不能只看 PR diff，必须有**跨文件 awareness**：

- 读 PR diff **+** codebase index（function names / key abstractions）
- 找语义相似度高的已有实现
- 借 `codebase-memory-mcp` 的 search 能力

flutter-suiyin / suiyin-go 的 CLAUDE.md 都没明确这条 — 这是 v4 比前 3 个项目要补强的点。

---

## 二、主题：代码复用治理（业务层 + 实现层）

### 2.1 spec-level 重复 vs code-level 重复

| 维度 | spec-level（业务逻辑重复） | code-level（实现重复） |
|---|---|---|
| **粒度** | 业务概念级（"客户" vs "联系人"） | 函数实现级（`sortCustomerList()`） |
| **检测时机** | spec 阶段 | plan 阶段 |
| **防的是** | 概念漂移 / 业务重复 | 实现重复 / 抽象不足 |
| **AI 检索** | 语义检索（embedding） | 直接 lookup + 语义检索 |
| **维护成本** | 中（业务概念变化少） | 高，但**可全自动**（CI 触发） |

### 2.2 4 层防御

| 层 | 工具 | 防什么 | 时机 |
|---|---|---|---|
| **L1** | 领域词典 `domain-glossary.md` | 业务概念重复 | 写 spec 时 reference |
| **L2** | C10 Spec Overlap Detector | spec 整体重叠 | spec 写完，clarify 前 |
| **L3** | C11 双引擎（Function Registry + Plan Lookup） | 实现重复 | **plan 阶段 lookup（被动）+ post-merge agent（主动维护）** |
| **L4** | 季度领域 + 函数 audit | 漂移兜底 | 季度定时 |

### 2.3 领域词典 (Domain Glossary)

`docs/sdd/domain-glossary.md` — 业务概念的标准定义。

**每个 spec 必须 reference 词典里的概念**。引入新概念必须走 ADR（"为什么这不是已有概念的别名"）。

例子：

```
## 客户 (Customer)
- 定义: 跟我们有/曾有交易关系的微信用户
- 标识: wcId
- 跟「联系人」(Contact) 区别:
  联系人 = 销售微信里所有好友
  客户 = 其中购买过 / 咨询过的
- 字段: ...
```

**待决策 — Fork N**：放哪？(a) 独立文件 / (b) 嵌入 constitution / (c) `.specify/memory/glossary.md`

### 2.4 函数表 + 调用链（关键修正：全员进表）

**修正前的 systematic bug**：

> "≥2 处引用才进表" → 第一次永不进表 → 第二次找不到 → 又新建 → 永远循环失效

**修正后：全员进表 + 语义检索**：

| 旧方案（有 bug） | 修正后 |
|---|---|
| 私有 helper 不进表 | **所有非内联私有的函数都进表** |
| 进表门槛 = 调用次数 | 进表门槛 = "是否 named function" |
| 检索靠名字 lookup | 检索靠**语义 description + embedding** |
| 描述由人写或没有 | **强制描述**（AI 自动 + public API docstring 校验） |

表会变大（数千 entries），但**只有大才有用**。语义检索能 handle 大规模。

### 2.5 抽取阈值 3 档（Fork P 已定 ✅）

| overlap | 行动 |
|---|---|
| **< 50%** | 默认独立实现 |
| **50-80%** | AI 识别**部分重叠的片段**，评估是否能抽出"可复用片段"。能 + 有价值 → 抽 helper；不能 → 独立 |
| **80%+** | 强制改造复用（差异参数化）|

### 2.6 部分复用 (Partial Reuse) 概念

50-80% 时**不是整体抽取**，是抽取**重叠片段**当 helper 函数，调用方各保留自己的差异。这是 refactor 精细化。

### 2.7 Plan 阶段内部循环（plan ⇌ reuse-scan）

**Plan 不是单次产出**，是带循环的子流程：

```
[Plan v0 起草]
   AI 写"我要具体怎么实现"
       ↓
[C11 Reuse Scan]
   语义检索 function registry
   返回 top-N 候选 + overlap %
       ↓
[决策]
   ├─ 全 < 50%       → 无修订，进 Tasks
   ├─ 50-80% match   → Plan v1: 标 "抽片段 Y 为 helper" → 进 Tasks
   └─ 80%+ match     → Plan v1: 标 "改造 X 为公共函数"
                         ↓
                      (改造方案可能扩大 plan scope → 回 reuse-scan 再扫一遍)
       ↓
[Plan final] → Tasks
```

这是 SDD 的**通用循环模式**：

| 阶段 | 单次产出？ | 反向触发 |
|---|---|---|
| specify ⇌ clarify | ❌ 多版本 | clarify 找漏 → specify 修订 |
| **plan ⇌ reuse-scan** | ❌ **多版本（v4 新增）** | reuse-scan 找重复 → plan 修订 |
| implement → verify | ✅ 单次 + retry | verify 失败 → 修 impl，不修 plan |

specify ⇌ clarify 是 spec-kit 原生的；plan ⇌ reuse-scan 是 v4 新加的对称循环。**结构同源**。

### 2.8 Spec ↔ code 双向追踪

词典 + 函数表 + comments 一起，自然形成**双向锚点**：

```
domain-glossary.md
  └── "客户排序规则"
        └─ implemented_by: [sortCustomerList(), sortContactList()]
              ↑                                ↓
              └─ 函数表 ──→ comments: spec_ref = customer-list-sort
                                       contact-list-sort
```

修改函数时**反向告诉你"影响了 spec X 和 Y"**。是 spec rot 防御的最强形态——不靠"季度对账"，靠"改代码时就知道影响哪个 spec"。

### 2.9 codebase 当问答库（RAG 模式）

**全员进表 + 语义检索**本质上是把 codebase 当**问答库**：

- 每次 plan 都问："已经有人做过这个吗？"
- AI 不再凭记忆，而是**主动检索**
- 上下文压力小 + 大规模 scale + description 可解释

**v4 工具链 = AI 的工作记忆系统**，不只是开发流程。

---

## 三、新组件需求（追加到 toolchain.md C1-C9 之后）

### C10. Spec Overlap Detector

| 项 | 内容 |
|---|---|
| **作用** | 检测新 spec 跟现有 spec 的业务逻辑重复 |
| **输入** | 新 spec.md + 所有现有 spec.md + 领域词典 |
| **输出** | `overlap_report.yaml`（每个已有 spec 的 overlap % + 重复点列表） |
| **核心能力** | 业务概念抽取 / 语义相似度计算 / 跨 spec 视野 |
| **依赖** | `codebase-memory-mcp`（语义索引）+ 领域词典 |
| **触发** | spec 写完，clarify 之前 |
| **未决 Q12** | overlap threshold（多少 % 算重复？50? 70? 90?） |

### C11. Post-Merge Function Registry Agent

| 项 | 内容 |
|---|---|
| **作用** | Post-merge 自动维护函数表 + 语义索引 + 反向重复检测 |
| **触发** | merge to main 之后（GitHub Actions hook 启动 agent） |
| **运行模式** | 后台 agent（非 feature 主线，**不阻断 merge**） |
| **职责** | (a) 扫 merge diff，更新函数表（add / modify / delete）<br>(b) AI 生成或更新 description + embedding<br>(c) 跑全 codebase **overlap audit**<br>(d) 发现 overlap > 50% → 标 issue `potentially missed reuse` |
| **输入** | merge commit + 现有 `function-registry.yaml` + embedding index |
| **输出** | 更新后的 registry + 可能的 reuse issue |
| **依赖** | `codebase-memory-mcp`（call graph）+ embedding service + CI hook |
| **未决 Q13** | function description 由谁生成（AI 自动 / 强制 docstring / 组合 — 已部分由 Fork O 回答） |
| **未决 Q14** | 部分抽取的具体片段识别算法（50-80% 时如何精确定位重叠片段） |

**两个查询接口**：

- **Plan 阶段 lookup**（被动）：plan 阶段 AI 主动查"已经有人做过这个吗"
- **Post-merge audit**（主动）：merge 后维护 + 检测 missed reuse

---

## 四、Fork 清单更新（J-R）

### 已拍 ✅

| Fork | 决策 |
|---|---|
| **O. 函数表 description 谁填** | (c) AI 自动 + public API 强制 docstring |
| **P. 抽取阈值** | (你方案) 50%/50-80%/80%+ 三档 |

### 待拍 ⏳

| Fork | 选项 |
|---|---|
| **J. 复杂度量化阈值** | (a) TigerBeetle 严格 70/500/4/15 / (b) 折中 120/800/5/20 / (c) v4 自定义 |
| **K. Plan "Could this be simpler?" 节** | (a) 默认所有 plan / (b) 仅 medium+ task / (c) 不强制，靠 reviewer 兜底 |
| **L. Reviewer 扫重复用什么** | (a) codebase-memory-mcp / (b) jscpd / (c) AI 语义 / (d) 组合 |
| **M. 季度复杂度盘点触发** | (a) AI 自动季度 / (b) 人手动 / (c) merge 累积量触发 |
| **N. 领域词典放哪** | (a) `docs/sdd/domain-glossary.md` 独立文件 / (b) 嵌入 constitution / (c) `.specify/memory/glossary.md` |
| **Q. embedding 模型** | (a) Anthropic / (b) OpenAI / (c) 本地 sentence-transformers / (d) 都支持，配置选 |
| **R. agent 发现 missed reuse 时** | (a) 标 issue 等下次 plan 撞上 / (b) 自动开 refactor PR / (c) 标 issue + 累积 N 个开 batch refactor PR |

---

## 五、新未决问题（Q12-Q14，合并到 workflows.md 已有 Q1-Q11）

| 编号 | 问题 | 涉及 |
|---|---|---|
| **Q12** | spec overlap threshold（多少 % 算重复） | C10 |
| **Q13** | function description 维护成本（AI 自动精度 / 强制 docstring 负担） | C11 |
| **Q14** | 部分抽取的片段识别算法（50-80% 时如何定位重叠片段） | C11 |

合并后总未决：Q1-Q14，14 个。

---

## 六、后续 2 天工作清单

### 6.1 画明确流程图（消化进 workflows.md）

- **Plan 阶段内部循环子图** — 现有 `[Plan]` 单节点展开成 plan ⇌ reuse-scan 循环
- **复杂度治理 6 层工作流** — 新增章节
- **代码复用治理 4 层工作流** — 新增章节
- **函数表维护 + Plan lookup 子流程** — C11 详细 flowchart

### 6.2 消化进正式文档

| 内容 | 目标文档 |
|---|---|
| 复杂度治理（4 维度 + 6 层防御） | `toolchain.md`（扩展 C4/C5 描述）+ `workflows.md`（新流程图） |
| 量化指标 | `constitution.md`（待创建）|
| 领域词典原则 | `constitution.md` + 新建 `domain-glossary.md` |
| C10/C11 组件需求 | `toolchain.md`（新增 C10/C11 章节） |
| Plan 内部循环 | `workflows.md`（现有 Plan 节点展开） |
| 抽取阈值 / 部分复用 | C11 spec 内部 |
| Spec ↔ code 双向追踪 | `methodology.md`（扩展 spec rot 防御章节）+ C11 |

### 6.3 拍板 7 个待决 Fork

J / K / L / M / N / Q / R — 一次过完。

### 6.4 决定 P0 实现范围

候选 P0：

- **C2 Task Executor MVP**（前面 toolchain.md 给的 P0）
- **C4 Verify Engine L1+L2 MVP**（前面给的 P0 配套）
- **C11 Function Registry MVP**（本次新增，可能是其他工具的基础设施 — 优先级更高？）

待 2 天后讨论。

---

## 七、跟之前内容的关系总图

```
本 session 前半段 (已落到正式文档):
  methodology.md (commit ca1f7c5)
  toolchain.md (PR #1) — C1-C8 + 9 个 Fork (A-I)
  workflows.md (PR #1) — 主流程 + bug + Initiative + C9

本 session 后半段 (本文档):
  复杂度治理 (4 维度, 6 层, 量化指标)
  代码复用治理 (4 层, 领域词典, C10, C11)
  Plan 内部循环
  Fork J-R (含已拍 O, P + 待拍 7 个)
  Q12-Q14 新未决
  ↓
  待消化:
  - 部分进 toolchain.md (C10, C11 章节)
  - 部分进 workflows.md (Plan 内部循环, 复用治理图)
  - 部分进 methodology.md (复杂度治理 + spec ↔ code 追踪)
  - 部分进 (待建) constitution.md (量化指标 + 简单优先原则)
  - 部分进 (待建) domain-glossary.md (词典本身)
```

---

**Version**: 0.1.0-WIP
**Last Updated**: 2026-05-15
**Status**: 待后续 2 天讨论消化到正式文档
