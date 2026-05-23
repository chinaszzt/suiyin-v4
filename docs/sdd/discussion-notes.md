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

## 八、工具链定位二次修正（2026-05-16）

把 C4 / C6 / C8 重新定位为**行为契约**（declarative），不是组件。已写入 `toolchain.md` v0.2.0。

### 8.1 三次过度设计的反思（以 C6 为例）

| 阶段 | 误判 | 修正 |
|---|---|---|
| 第 1 次 | 当 verify 延续，fail 代价 = C2 + C4 + C5 白跑 | 实际是 thin policy layer，到 C6 时代码已过关 |
| 第 2 次 | 当组件，给出"作用 / 输入 / 输出 / 核心能力" | 实际是 GitHub 原生配置，没代码要写 |
| 第 3 次 | 默认绑定 GitHub Branch Protection + Merge Queue | 实际是行为契约，可本地 git hook 5 行 shell |

根因：**没问"最简实现是什么"，默认重型 SaaS**。

### 8.2 判定原则升级（3 层）

详见 `toolchain.md` §0.5。

```
工具链节点 → 是什么？
  ├─ Imperative Logic（写代码）        → 自建组件
  └─ Declarative Contract              → 行为契约
        └─ 实现选项: 本地 hook / 通用 CI / SaaS 集成
              ↑ v4 文档只定 contract，用户落地时选实现
```

### 8.3 重新分类结果

11 节点 = **8 自建组件 + 3 行为契约**：

- **自建组件**（imperative）: C1 / C2 / C3 / C5 / C7 / C9 / C10 / C11
- **行为契约**（declarative）: **C4 / C6 / C8**

真正要写 imperative logic 的就 8 个。C4 / C6 / C8 是契约，按实现选项谱系（本地 / CI / SaaS）落地。

### 8.4 落地优先级调整

| 之前 | 现在 |
|---|---|
| P0: C2 + C4 (L1+L2) | P0: C2 + C4 Contract (lefthook + L1+L2 工具) |
| P1: C5 + C6 Gate（当组件实现） | P1: C5 + C6 Contract（git hook 配齐 5 行 shell） |
| P4: C8 Deploy Gate UI | P4: C8 release summary generator（imperative）+ CD 配置 |

**关键变化**：

- C6 不再单独占 P 优先级 — 跟 C5 一起配齐（半天工作量）
- C4 拆两步：L1/L2 在 P0（lefthook），L3/L4 imperative 在 P3
- C8 拆两步：CD 配置 + summary generator，后者才是真要写代码的

P0 启动门槛大幅降低，**不依赖任何 SaaS** 也能跑起来。

### 8.5 新增 Fork S（工具链整体实现栈）

| Fork | 选项 |
|---|---|
| **S. 工具链整体实现栈** | (a) 本地 git hook + lefthook / (b) 通用 CI（GitLab / CircleCI / Jenkins）/ (c) GitHub 原生（Branch Protection + Merge Queue + Actions）/ (d) **混合**（本地 hook 反馈 + CI 权威，推荐）|

每个契约（C4 / C6 / C8）可独立覆盖 S 选项 — 比如 C4 用 (a) 本地，C6 用 (c) GitHub。

### 8.6 AI 提案审查清单（新增方法论原则）

已写入 `toolchain.md` §0.5 末尾。下次提工具组件前必须走：

1. 是 imperative 还是 declarative？
2. 如果 declarative，最轻实现是什么（本地 hook? 已有 CI? SaaS?）？
3. 现成工具能覆盖多少？
4. 真正需要写代码的是哪一小块？

**禁止默认重型 SaaS**。

未来应该把这条提炼进 `methodology.md` 或 `constitution.md`，作为 v4 SDD 工具链设计的硬约束。

---

## 九、流程图 Review 推演结论（2026-05-18）

第一轮限时 review 完成。原列出 7 个潜在漏洞，逐条决策：

### 9.1 推演决策

| # | 漏洞 | 决策 | 落地 |
|---|---|---|---|
| 1 | **Plan 死锁**（80%+ 改造扩大 scope → 又触发 80%+ → 循环） | **80%+ 一次循环 break，不再 re-scan** | diagrams.md 图 3 加注释 |
| 2 | **Bug Type B/C 重做粒度**（走完整 feature 流程是否太重）| **记 TODO，以后优化**（小 bug 走 mini-spec 探索） | 本文档 §9.2 TODO |
| 3 | **C11 跟 C1 概念重叠** | **不重叠**（C1 = task 间冲突；C11 = 函数间重复） | toolchain.md / 本文档 §9.3 澄清 |
| 4 | **异常退出恢复路径** | **不画完整恢复**，遵循"按需补"原则；显式列 C4/C5/spec drift 三个入口 | diagrams.md 图 6 加入口说明 + 恢复说明 |
| 5 | **C11 双引擎一致性** | **Plan Lookup 强制 sync main**；开发并行重复靠 post-merge audit 兜底 | toolchain.md §四 Forks 后约束记录 |
| 6 | **Task Retry 时机** | 三处触发：C2 fail / C4 fail / C5 block；session 策略优先**同 session 复用**（context 保留），满 / kill 时新开 + 前次 summary | 本文档 §9.4 解释；细节属于 Q2 |
| 7 | （review 圈出只有以上 6 个有价值的，C9/C10/C11 粒度问题留待 v0.4 整理） | — | — |

### 9.2 Bug Type B/C 重做粒度 — TODO

当前 Bug Type B/C 走"完整 feature 流程"。但对小 bug（比如 spec 漏了一个边界 case，AC 加一条），跑完整 spec → clarify → plan → tasks 太重。

**TODO**：定义 "mini-feature" 流程：
- 触发：Bug Type B/C，但 spec 改动 < N 条 AC
- 跳过：clarify（如果 AC 改动够清楚）
- 简化：plan 可以是"沿用现有 plan + 补一段"
- 验证：仍然走 verify/review/gate

留待 P2/P3 阶段定义。

### 9.3 C11 vs C1 不重叠（澄清）

| | C1 Planning Engine | C11 Function Registry |
|---|---|---|
| 输入 | tasks.yaml + spec/plan | plan v0 描述 |
| 输出 | tasks.yaml + `execution_plan` | `reuse_candidates` |
| 分析维度 | **task 间冲突**（要不要并行）| **函数间重复**（要不要复用） |
| 时机 | tasks 拆完后 | plan 阶段 AI 查询 |

都在 Plan 阶段附近触发，但**分析维度完全不同**。可能共享 codebase indexing 基础设施。

### 9.4 Task Retry 时机解释

发生在 3 处：

| 触发 | retry 内容 |
|---|---|
| C2 自己 fail（session crash / timeout） | 重启 C2，新 session |
| C4 verify fail（lint / test 不过） | C2 修代码 → 重 verify |
| C5 review block（high finding） | C2 修代码 → 重 review |

**Session 策略**（初步）：

- 优先 **同 session 复用**（context 保留前次失败信息）
- session 已 kill / context 满时新开 session + 前次 summary 作为 context anchor

细节属于 Q2（C2 spec 阶段决定）。

### 9.5 Fork J-S 全部拍板（合并进 toolchain.md v0.3）

| Fork | 决策 |
|---|---|
| **J** 复杂度量化阈值 | 函数 ≤ 80 / 文件 ≤ 600 / 嵌套 ≤ 5 / 圈复杂度 ≤ 18（折中，前端 UI 嵌套天然深）|
| **K** Plan 简单性节 | 不强制，依赖 C5 reviewer `complexity` finding |
| **L** Reviewer 扫重复 | 复用 C11 query 接口 + jscpd 语法兜底 |
| **M** 季度盘点触发 | TODO stub，迭代版决定 |
| **N** 领域词典位置 | `docs/sdd/domain-glossary.md` 独立文件 |
| **Q** embedding 模型 | 本地 sentence-transformers |
| **R** missed reuse 处理 | 标 issue + 额外记录原因分析（C11 迭代反馈数据）|
| **S** 工具链整体实现栈 | (d) 混合（本地 hook + CI），每个契约可独立覆盖 |

详见 toolchain.md §四。

### 9.6 进入下一阶段

Review + Fork 全部拍完。下一阶段候选（按 leverage 排序）：

1. **constitution.md v0.1 最小草稿** — 立项目身份 + 5 条核心原则（来自 methodology.md §10）+ governance。**量化指标 / NON-NEGOTIABLE 严格规则待 v1.0**（spike 后立）。
2. **domain-glossary.md 框架** — 空模板，第一个 spec 触发添加。
3. **第一个 feature spec dogfood** — 挑一个最小 feature 实际跑 spec-kit Layer 1 → C1 → ... 流程，暴露真实问题。
4. **C2/C4 P0 spike** — 直接动手实现 P0 MVP。

constitution 先于 spec 是 SDD 标准顺序，但 constitution v0.1 应该是**最小版**——避免没 spike 经验拍精确指标。

---

---

## 十、C12 Knowledge Capture Prompt（post-MVP follow-up，2026-05-20）

### 起因

P1.1 阶段 1 审 spec 时 user 提出："**一个知识图谱，完成项目时评估是否写入？plan 阶段读取，就很好了？**"

这本质是 v4 已有 C10 + C11 + domain-glossary 的设计动机 user 独立想到。但他的提法暴露**一个真 gap**。

### v4 现有的项目知识分层（已设计）

| 层 | 载体 | 触发 |
|---|---|---|
| 代码层 | C11 函数 registry + embedding | post-merge |
| spec 层 | C10 Spec Overlap Detector | plan 阶段 + post-merge |
| 概念层 | `docs/sdd/domain-glossary.md` | 人主写 + AI 辅助 |
| 决策层 | `adrs/NNNN-*.md` | 决策时人写 |
| 约束层 | constitution NC/PC | governance §8 ADR |
| 流派层 | methodology.md | 团队对齐 |

### Gap：非 post-merge 时刻的知识沉淀

C10/C11 都是 **post-merge trigger**。但很多 reusable 知识在**审 spec / debug / 设计反思**时显形——当前**没机制**让 AI/人停一下问"这是项目知识吗，沉淀去哪一层"。

**具体例子（PR #11 审 spec 时发生）**：user 提"Windows/macOS 兼容性要注意"——这是个 reusable 约束（不只 C2/C4，未来所有 v4 工具组件都该考虑）。理论上应升级为 constitution PC-4 或写进 toolchain.md AI 提案审查清单。但当前默默只活在 C2 §7 + C4 §7 两份 spec 里，下个组件 spec 写的人/AI 不一定看到。

### Trigger 全枚举

| Trigger | v4 现有 | 缺什么 |
|---|---|---|
| post-merge | C10 / C11 sweep | ✅ |
| spec amendment | ADR governance | ✅ |
| constitution amendment | ADR + 人审 | ✅ |
| **审 spec 发现 reusable 约束** | ❌ | **gap** |
| **debug 后复盘**（Bug Type B/C） | methodology §2 提了但流程未细化 | **gap** |
| **设计讨论显形隐性假设** | ❌ | **gap** |

### 候选设计：C12 Knowledge Capture Prompt

**性质**：不是图谱，是个 **prompt / ritual / lint 规则**。在反思时刻让 AI / 人主动问"是否沉淀，沉淀到哪一层"。

**最轻实现（PC-1 最简实现优先）**：
- 文档：`docs/sdd/knowledge-capture-protocol.md` 列触发时刻 + 沉淀目标层 mapping
- prompt 注入：`/sy-clarify` `/sy-analyze` 等加一句"若本轮发现 reusable 知识，请提示沉淀"
- C5 AI Reviewer finding category：`reusable_knowledge_not_captured`

### 决策（2026-05-20）

**先不做，集中精力出 P1.1 MVP**。但要"放好位置 + 相关信息"作为 known follow-up：
- 本节记录（discussion-notes.md §十）
- `diagrams.md` 图 11 加 C12 dashed placeholder（"post-MVP"）
- `todo.md` 加 P3 follow-up

待 P1.2 (C5 Reviewer) 设计前回头讨论——C5 finding category 需要这条 enum 时才必须拍。

---

**Version**: 0.3.1-WIP
**Last Updated**: 2026-05-20
**Status**: review 第一轮完成；待开 constitution.md v0.1 + 第一个 spec dogfood；C12 作为 post-MVP follow-up 记录在 §十
