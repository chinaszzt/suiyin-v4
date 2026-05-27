# 碎银 v4 工具链需求 — AI Native 开发引擎设计

> 本文档定义 v4 项目所需的工具链。**给开发者读**（含 AI 主写 session），作为后续 spec / plan 的开发依据。跟 `methodology.md` 同级但目标读者不同：
>
> - `methodology.md` → 团队所有参与者（含产品、设计师）— 讲方法论
> - **`toolchain.md`（本文档）→ 工具链开发者（含 AI 主写 session）— 讲工程依据**

---

## 〇、为什么要这套工具链

我们的开发模式跟传统 SDD 工具（spec-kit / Kiro）的目标用户画像有一个根本差异：

| | 传统 SDD 工具 | v4 模式 |
|---|---|---|
| 用户能力 | 专业开发者，能审代码 | 业务专家 + 后端老兵，**前端代码看不懂** |
| AI 角色 | 辅助加速 | 主写主体 |
| 人介入点 | spec + plan + PR review + merge + deploy | 仅 spec/plan 协商 + spec 漂移仲裁 + deploy |
| Merge gate | 人按按钮 | 自动化 gate（CI 绿 + AI 双 review） |

业界没有为这套模式优化的工具链。**Layer 1（协商）借用 spec-kit，Layer 2-6 部分自建 + 部分声明式契约**。本文档定义两者的规约。

---

## 〇.5、组件 vs 契约：判定原则

设计每个工具链节点前，必须先问 2 层问题。

### 第 1 层：是 imperative logic 还是 declarative contract？

```
工具链节点 → 是什么？
  ├─ Imperative Logic（要写代码）       → 自建组件
  └─ Declarative Contract（声明式约束） → 行为契约
        └─ 实现选项谱系: 本地 hook / 通用 CI / SaaS 集成
              ↑ v4 文档只定 contract，用户落地时选实现
```

**判定锚点**：

- 节点的核心职责是"读取规则 + 执行声明式判定"？→ **契约**
- 节点是"编排 / 决策 / 计算 / 生成产物"？→ **组件**

### 第 2 层：行为契约的实现选项谱系（轻 → 重）

| 选项 | 性质 | 适合场景 |
|---|---|---|
| (a) **本地 git hook + lefthook** | 纯本地，零 SaaS | 单人 / 小团队 / 离线 |
| (b) **通用 CI**（GitLab / CircleCI / Jenkins） | 集中跑，CI 权威 | 中等规模 |
| (c) **SaaS 集成**（GitHub Branch Protection + Merge Queue） | 完整集成 | 重度 SaaS 用户 |
| (d) **混合**（本地 hook 反馈 + CI 权威） | 双层 | **推荐** |

工具链文档**不绑定任何一种实现**，只定 contract。

### 重审：v4 工具链 11 个节点分类

| 类型 | 节点 | 数量 |
|---|---|---|
| **自建组件**（imperative） | C1 / C2 / C3 / C5 / C7 / C9 / C10 / C11 | **8** |
| **行为契约**（declarative） | **C4 / C6 / C8** | **3** |

8 个组件 + 3 个契约。**真正要写 imperative logic 的就 8 个**。C4/C6/C8 是契约，落地时按谱系选实现，工具链文档不规定怎么跑。

### AI 提案审查清单 — 最简实现优先

AI 提出工具/组件时，**必须先问**：

1. 这是 imperative logic 还是 declarative contract？
2. 如果是 contract，最轻实现是什么（本地 hook? 已有 CI? SaaS?）
3. 现成工具能覆盖多少？
4. 真正需要写代码的是哪一小块？

**禁止默认重型 SaaS**。先列最简方案，再讨论是否升级到重型。

(本条来自工具链设计中 C6 经历"过度设计 → thin layer → 配置 → 契约"三次降级的反思——把配置当组件、把契约当实现，会人为放大 P0 范围。)

---

## 一、整体定位

```
[人 + AI 协商]                  [AI 主写 + 自动化 Gate]              [人按按钮]

Layer 1  业务协商              Layer 2-5  执行引擎                  Layer 6  发布
- constitution                 - 规划 (C1 组件)                      - C8 契约
- spec (用户行为)              - 执行 (C2, C3 组件)                  - 灰度 / 全量
- clarify                      - 验证 (C4 契约 + C5 组件)            - 触发 CD
- plan (技术方案)              - Gate (C6 契约)
- constraints/                 - 横跨调度 (C7 组件)

[借用 spec-kit]               [8 组件 + 3 契约]                      [契约：多种 CD 实现]
```

人介入点（按频率从高到低）：

1. **协商阶段**（constitution / spec / plan）— 高频，每个 feature 都过一遍
2. **Spec 漂移 / 跨 spec 仲裁** — 中频，AI 执行中触发
3. **Deploy 按钮** — 按发版节奏
4. **不审 PR、不按 merge** — 零（依赖 AI 双审 + 自动化 gate）

---

## 二、Layer 划分细则

### Layer 1 业务协商 — 借用 spec-kit（前 4-5 阶段）

- **谁干**：人 + AI 协商，人主导拍板
- **工具**：`spec-kit` 的 `/speckit.constitution` `/speckit.specify` `/speckit.clarify` `/speckit.plan` `/speckit.analyze`
- **产物**：
  - `.specify/memory/constitution.md` — 项目宪法
  - `.specify/specs/NNN-feature-name/spec.md` — 单能力 spec（自然语言 + 自然语言 AC）
  - `.specify/specs/NNN-feature-name/plan.md` — 技术方案（业务架构层人审，前端技术细节让 AI 双审）
  - `.specify/specs/NNN-feature-name/constraints/` — 上游外部契约副本（OpenAPI / event schema），**不是这个项目自己定义的 spec，是要消费的外部约束**
  - `.specify/specs/NNN-feature-name/tasks.yaml` — Task 拆解（**改用 yaml，不用默认 md**）
- **必要配置变更**：`.specify/extensions.yml` 关掉 spec-kit 的 git auto-commit hooks（与我们 worktree 铁律冲突）

### Layer 2 规划 — 自建（C1 组件）

- **谁干**：AI 主导，人审"phase 划分是否合理"
- **能力**：依赖图分析、文件冲突检测、并行 phase 划分
- **产物**：`tasks.yaml` 升级版（含 `execution_plan`）

### Layer 3 执行 — 自建（C2 + C3 组件）

- **谁干**：AI 自闭环（worktree 隔离）
- **能力**：worktree 创建、AI session 启动（Claude Code headless）、prompt 模板、双 AI 独立实现（high criticality）+ 仲裁
- **产物**：可 merge 的 PR per task

### Layer 4 验证 — C4 契约 + C5 组件

- **谁干**：自动化工具 + AI session（独立）
- **能力**：5 层 check（C4 契约定义）+ AI Reviewer 独立审（C5 组件）
- **产物**：`verify_report.json` + `ai_review.json`

### Layer 5 Gate — C6 契约 + C7 组件

- **谁干**：自动化（人通过 `human:block` 标签可紧急 override）
- **能力**：gate 规则评估（C6 契约）+ phase 调度（C7 组件）
- **产物**：merge to main / hold

### Layer 6 发布 — C8 契约（+ 1 个 imperative 子能力）

- **谁干**：人按按钮触发，AI 提供决策辅助
- **能力**：release summary（imperative 子能力）、灰度选项、对接 CD
- **产物**：production deploy

---

## 三、工具链节点（8 组件 + 3 契约）

**自建组件**（imperative logic）和**行为契约**（declarative contract）分开列。组件给 6 字段；契约多一个"实现选项谱系"字段。

### 自建组件（imperative）

#### C1. Planning Engine（Layer 2）

| 项 | 内容 |
|---|---|
| **性质** | 自建组件 |
| **作用** | 把扁平 task 列表升级成"phase + 并行组"执行计划 |
| **输入** | `tasks.yaml`（spec-kit 初版）+ `spec.md` + `plan.md` |
| **输出** | `tasks.yaml`（新增 `execution_plan: [{phase, parallel: [ids]}]`） |
| **核心能力** | 静态依赖分析（task.depends_on）／ 文件级冲突检测（task.context_seeds / modifies 重叠）／ 语义冲突分析（AI 读 task 描述判断"会不会动同一资源"）／ 并行 phase 划分 |
| **依赖** | tasks.yaml schema、文件路径解析 |
| **未决 Q1** | 语义冲突分析的精度（false positive 会过度串行化） |

#### C2. Task Executor（Layer 3）

| 项 | 内容 |
|---|---|
| **性质** | 自建组件（核心） |
| **作用** | 单个 task 从 spec 到 PR 的全自动实现 |
| **输入** | 单个 task（id + spec_ref + plan_ref + context_seeds + verify_cmd 等） |
| **输出** | 可 merge 的 PR + verify report |
| **核心能力** | worktree 创建（命名 `worktrees/<task_id>`） ／ AI session 启动（Claude Code headless mode）／ prompt 模板（注入 task context）／ 失败重试（≤N 次）／ 超时保护 |
| **依赖** | `git worktree`、Claude Code SDK / CLI、`.specify/` 目录 |
| **未决 Q2** | 单 AI session 长度上限（>2h 自动 kill？） |

#### C3. Multi-Implementation Arbiter（Layer 3，高 criticality）

| 项 | 内容 |
|---|---|
| **性质** | 自建组件 |
| **作用** | 双 AI 独立实现 + 交叉审 + 仲裁出最终版本 |
| **输入** | 1 个 high criticality task + 2 个独立 session 的 impl + 双向 review |
| **输出** | 1 个仲裁后的最终 PR |
| **核心能力** | 并行启 2 个 Task Executor ／ 交叉 review（impl_1 审 impl_2，反之）／ 仲裁 AI session 输出最终版 |
| **依赖** | C2 + C5 |
| **未决 Q3** | 仲裁 AI 是第 3 个独立 session 还是其中一个 reviewer 兼任 |

**criticality 路由规则**：

- `low`：纯 UI 微调、测试补全、文档更新 → C2 单 AI 写 + C5 单 AI review
- `medium`（默认）：C2 单 AI 写 + C5 单 AI review
- `high`：触碰 NON-NEGOTIABLE 原则的代码（认证、支付、数据迁移）／跨 module ／新模式引入 → **C3 双 AI 独立实现 + 仲裁**

#### C5. AI Reviewer（Layer 4）

| 项 | 内容 |
|---|---|
| **性质** | 自建组件 |
| **作用** | 独立 AI session 评估 PR 是否实现意图 |
| **输入** | spec + plan + constitution + PR diff（**不读 implementer 工作过程**） |
| **输出** | 结构化 verdict（`approve` / `request_changes` / `block`）+ findings 列表 |
| **核心能力** | 独立 session（context 干净）／ findings 分类（severity + category + location + suggested_fix；**含 `complexity` 类**：过度设计 / 重复实现 / 不必要抽象 / 函数超长）／ Verdict 规则（high → block；medium → request_changes；low → approve） |
| **依赖** | Claude Code SDK；`complexity` 类查重时**调用 C11 query 接口** |
| **未决 Q5** | 单次还是 N=2 + 分歧仲裁（按 task.criticality 路由？） |

#### C7. Phase Coordinator（横跨 Layer 2-5）

| 项 | 内容 |
|---|---|
| **性质** | 自建组件 |
| **作用** | 按 execution_plan 调度 phase，**phase 间逐次 merge to main** |
| **输入** | tasks.yaml 含 execution_plan |
| **输出** | 所有 task 完成 / phase 失败标记 |
| **核心能力** | 按 phase 顺序触发 task batch ／ phase 内并行触发 multiple Task Executor ／ phase 完成等所有 task merge → 进下一 phase ／ 失败处理 |
| **依赖** | C2 + C6 |
| **未决 Q7** | phase 内某 task 卡住、其他已 merge——卡住的回滚还是隔离 |

### 行为契约（declarative）

#### C4. Verify Contract（Layer 4）

| 项 | 内容 |
|---|---|
| **性质** | **行为契约** — 定义 PR/working state 必须通过的 5 层 check |
| **输入** | PR / working state |
| **输出契约** | `verify_report.json`（每层 check 各自 pass/fail + details） |
| **5 层 check（必须实现）** | **L1 Static** (lint + tsc + formatter) ／ **L2 Tests** (unit + integration) ／ **L3 Spec compliance** (每个 AC 是否有对应 passing test，命名映射) ／ **L4 Constitution compliance** (AI 读 constitution + diff 输出违反项) ／ **L5 Coverage delta** (覆盖率不下降，warning，不阻断) |
| **实现选项谱系** | (a) **本地 lefthook + 各语言工具**（最轻）／ (b) 通用 CI（GitLab / CircleCI）／ (c) GitHub Actions ／ (d) **混合**（本地快反馈 + CI 权威，推荐） |
| **真正 imperative 部分** | L3 (AC ↔ test 映射查询) + L4 (AI constitution check) — 这两个是脚本，挂在选定实现下跑 |
| **依赖** | 项目 toolchain（dart analyze / flutter test / eslint / jest）+ AI session (L3/L4) |
| **未决 Q4** | AC ↔ test 映射强制方式（命名约定 `test('AC-1', ...)` ／ metadata file ／ 显式注解） |

#### C6. Gate Contract（Layer 5）

| 项 | 内容 |
|---|---|
| **性质** | **行为契约** — 所有职责都是配置 / 编排，**没有 imperative logic** |
| **输入** | PR + C4 verify_report + C5 review verdict |
| **输出** | merge / hold |
| **契约规则** | `verify_report.overall_verdict == pass && review_report.verdict == approve && ff_mergeable(pr,main) && !pr.has_label("human:block")` — 4 条全 AND（精确字段名见 components/c6-gate-contract.md §3.1 I1） |
| **失败处理** | `ff_mergeable false` → rebase（仅 rebase 干净时不重做 C2/C4/C5，conflict resolution 必须重投，见 c6 §3.3），`review block` → R1 加 `human:block` + comment findings（c6 §3.1 I7/I9），`human:block` 已存在 → 按 I8 precedence 优先，等人解锁 |
| **实现选项谱系** | (a) **standalone Python CLI `suiyin-flow gate run`**（最轻，零 SaaS；P1.2 默认；**不挂 pre-push** —— 见 c6 §7 / Q6-7）／ (b) 通用 CI + 仓库规则 ／ (c) GitHub Branch Protection + Merge Queue（最完整）／ (d) 混合 |
| **依赖** | git + （C4/C5 report） + gh CLI（label / comment） |
| **~~未决 Q6~~** | ~~失败升级通知渠道~~ → **P1.2 关闭**（决议: PR comment + `human:block` 标签作为通知通道；邮件 / IM webhook 留 P3+，详 c6 §6） |

#### C8. Deploy Contract（Layer 6）

| 项 | 内容 |
|---|---|
| **性质** | **大部分行为契约 + 1 个 imperative 子能力**（release summary generator） |
| **输入** | 本次发版 PR 列表 + change history |
| **输出** | 触发 deploy pipeline / 暂缓 |
| **契约规则** | 人按按钮 → AI 生成 release summary → 人决定灰度 / 全量 / 暂缓 |
| **实现选项谱系** | (a) **本地脚本 + 手动 deploy**（最轻）／ (b) 通用 CD（CircleCI / GitLab CI / Jenkins）／ (c) GitHub Actions + Vercel ／ (d) 混合 |
| **唯一 imperative 子能力** | release summary generator（AI 跑一次 prompt 生成发版摘要）|
| **依赖** | 既有 CD 或本地脚本 |
| **未决 Q8** | 风险 summary 格式（人 30s 读完） |

---

## 四、关键设计决策（Forks 已定）

本节记录已拍板的所有 fork，便于未来回顾决策依据。

| Fork | 决策 | 备注 |
|---|---|---|
| **A** | tasks 的"真相"载体 = **yaml**（必要时渲染 md 给人） | AI native：约束性 + 工具消费 |
| **B** | Task 默认串行；Planning Engine 识别可并行的批 | 前端冲突风险高，安全优先 |
| **C** | 双 AI Review 默认 1 次；high criticality 用 C3 双独立实现 + 仲裁 | 平衡成本和强度 |
| **D** | 自然语言 AC（spec.md）+ 必配可执行测试（命名映射 `test('AC-1', ...)`） | 两层混合：spec 易写 + verify 可跑 |
| **E** | 紧急 human override = PR 标签 `human:block` | 简单实用，不需要额外 dashboard |
| **F** | Phase 间合并策略 = **逐 phase merge to main** | 配合 worktree 铁律，main 永远可发布 |
| **G** | AC ↔ test 映射 = 命名约定 `test('AC-1', ...)`，C4 L3 解析测试名 | 比 metadata file 简单 |
| **H** | 仲裁 AI = 独立第 3 个 session | 不沾染 implementer 或 reviewer 视角 |
| **I** | Spec 漂移触发动作 = AI 标 `spec-drift` issue + 暂停 task | 人介入仲裁后回到 Layer 1 |
| **J** | 复杂度量化阈值 = **函数 ≤ 80 行 / 文件 ≤ 600 行 / 嵌套 ≤ 5 层 / 圈复杂度 ≤ 18** | 折中（比 TigerBeetle 70/500/4/15 略松，前端 UI 嵌套天然深），先这个跑、问题再迭代 |
| **K** | Plan 不强制写 "Could this be simpler?" 节 | 依赖 C5 reviewer 的 `complexity` finding 兜底 |
| **L** | Reviewer 扫重复 = **复用 C11 query 接口**（embedding 语义检索）+ jscpd 语法级兜底 | 不引入新机制 |
| **M** | 季度复杂度盘点触发 = **TODO stub** | 工具包预留 stub，迭代版决定（人手动 / AI 自动 / merge 累积触发） |
| **N** | 领域词典位置 = `docs/sdd/domain-glossary.md` 独立文件 + 各处引用 | 跟 methodology / toolchain 同级 |
| **Q** | embedding 模型 = **本地 sentence-transformers** | 作为工具包一部分，轻量本地跑，无 SaaS 依赖 |
| **R** | C11 agent 发现 missed reuse 时 = 标 issue + **额外记录原因分析** | 作为 C11 迭代的反馈数据（context 缺失 / 描述不准 / 等） |
| **S** | 工具链整体实现栈 = **(d) 混合**（本地 hook 反馈 + CI 权威） | 每个契约 C4 / C6 / C8 可独立覆盖谱系选项 |

**Plan ⇌ reuse-scan 死锁防御**：80%+ 触发改造后**一次循环 break**，不再 re-scan（避免改造扩大 scope → 又触发 80%+ → 死循环）。来自图 3 推演结论。

**C11 一致性约束**（待 C11 spec 阶段细化）：
- Plan Lookup 时强制 sync main（确保 registry 是最新）
- 开发中并行产生的重复代码靠 post-merge audit 兜底

---

## 五、命名建议

整套工具链需要一个代号便于后续讨论。候选：

- **`suiyin-flow`** ← 推荐：平实、跟项目绑定
- `spec-runner` — 强调"执行 spec"
- `forge` — AI native CI/CD 隐喻
- `conductor` — 强调编排

未来开源时再起 catchy 名字。

---

## 六、落地优先级（修订版）

| 优先级 | 节点 | 价值 | 性质 |
|---|---|---|---|
| **P0 MVP** | C2 Task Executor + C4 Verify Contract（仅 L1+L2，本地 lefthook） | 跑通"AI 写 1 个 task + 测试通过"最小循环 | C2 组件 + C4 配置 |
| **P1** | C5 AI Reviewer + C6 Gate Contract（git hook 或 GitHub）| 自闭环 merge（不要人审 PR）| C5 组件 + C6 配置 |
| **P2** | C1 Planning Engine + C7 Phase Coordinator | 并行加速 | 组件 |
| **P3** | C3 Arbiter + C4 补 L3/L4 imperative 部分 | 强化关键路径 | C3 组件 + C4 imperative 子能力 |
| **P4** | C8 release summary generator + CD 配置 | 收尾 | C8 imperative 子能力 + 配置 |

**关键变化**：

- **C6 不在 P0/P1 单独列**——它是配置，跟着 C5 一起配齐即可，半天的工作量
- **C4 拆成两步**：L1/L2 在 P0（lefthook 配齐即可），L3/L4 的 imperative 部分在 P3
- **C8 拆成两步**：CD 配置 + summary generator，后者才是真要写代码的

P0 做出来就可用——单 task 单线程跑，AI 写完跑 verify 给你看结果。后面按价值往上叠。

---

## 七、组件依赖关系

```
       ┌─────────────────────────────────────────────────────────┐
       │                                                         │
       │  C7 Phase Coordinator                                   │
       │       │                                                 │
       │       ▼                                                 │
       │  C1 Planning ──► tasks.yaml ──► (loop per phase)        │
       │                                       │                 │
       │                                       ▼                 │
       │                            ┌─── C2 Task Executor ◄─── C3 Arbiter
       │                            │          │                 (high crit)
       │                            │          ▼                 │
       │                            │      worktree              │
       │                            │      AI session            │
       │                            │      open PR               │
       │                            │          │                 │
       │                            │          ▼                 │
       │                            │      C4 Verify Contract    │
       │                            │      (lefthook / CI)       │
       │                            │      C5 AI Review (独立)   │
       │                            │          │                 │
       │                            │          ▼                 │
       │                            └─► C6 Gate Contract         │
       │                                       │                 │
       │                                       ▼                 │
       │                                  merge to main          │
       │                                                         │
       └─────────────────────────────────────────────────────────┘
                                       │
                                       ▼
                              C8 Deploy Contract (人按按钮)
                              (CD 配置 + AI summary)
```

**节点性质标注**：

- **自建组件**：C1 / C2 / C3 / C5 / C7（标准矩形）
- **行为契约**：C4 / C6 / C8（应在图里用不同形状，但 ASCII 表达力有限，见 `diagrams.md` Mermaid 版）

---

## 附录 A：跟 methodology.md / constitution.md 的关系

- **methodology.md**：方法论原则（spec 怎么写、bug 怎么分类、spec rot 怎么防御）— 给团队所有参与者
- **toolchain.md（本文档）**：工具链需求（节点定义：组件 + 契约）— 给工具链开发者
- **constitution.md（未来）**：项目宪法（不可妥协的原则 + 治理）— 团队对齐用，principles 引用 methodology 和 toolchain

未来如果 methodology 和 toolchain 冲突，constitution 仲裁。Constitution 还没写，预期在工具链 P0 落地前定。

## 附录 B：未决问题清单

汇总 C1-C8 的"未决"字段，便于追踪。每个未决问题在该节点做 spec 阶段时解决。

| 编号 | 问题 | 涉及节点 |
|---|---|---|
| **Q1** | 语义冲突分析的精度（false positive 风险） | C1 |
| **Q2** | 单 AI session 长度上限（>2h kill？） | C2 |
| **Q3** | 仲裁 AI 是第 3 个独立 session 还是 reviewer 兼任 | C3 |
| **Q4** | AC ↔ test 映射强制方式（命名约定 vs metadata vs 注解） | C4 |
| **Q5** | AI Reviewer 单次还是 N=2 分歧仲裁 | C5 |
| ~~Q6~~ | ~~Gate Contract 失败升级通知渠道~~ → **closed P1.2** (通道 = PR comment + label; 邮件/IM 留 P3+) | C6 |
| **Q7** | phase 内某 task 卡住，已 merge 的回滚还是隔离 | C7 |
| **Q8** | Deploy Contract 风险 summary 格式（人 30s 读完） | C8 |

---

**Version**: 0.3.1-draft（v0.3 → v0.3.1 修订: C6 spec v0.1.1 落地后 cascade — C6 行表字段名 `verify.all.pass` → `verify_report.overall_verdict==pass`；契约规则改 R1/I8/I9 引用；实现谱系 (a) 改 standalone CLI（去 pre-push）；附录 B Q6 closed P1.2）
**Last Updated**: 2026-05-25
