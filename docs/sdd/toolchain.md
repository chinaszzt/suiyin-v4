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

业界没有为这套模式优化的工具链。**Layer 1（协商）借用 spec-kit，Layer 2-5（规划/执行/验证/Gate）自建，Layer 6（发布）用既有 CD**。本文档定义自建部分的需求。

---

## 一、整体定位

```
[人 + AI 协商]                  [AI 主写 + 自动化 Gate]              [人按按钮]

Layer 1  业务协商              Layer 2-5  执行引擎                  Layer 6  发布
- constitution                 - 规划 (C1)                          - Deploy Gate (C8)
- spec (用户行为)              - 执行 (C2, C3)                      - 灰度 / 全量
- clarify                      - 验证 (C4, C5)                      - 触发 CD
- plan (技术方案)              - Gate (C6)
- constraints/                 - 横跨调度 (C7)

[借用 spec-kit]               [自建 — 本文档]                       [既有 CD]
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

### Layer 2 规划 — 自建（C1）

- **谁干**：AI 主导，人审"phase 划分是否合理"
- **能力**：依赖图分析、文件冲突检测、并行 phase 划分
- **产物**：`tasks.yaml` 升级版（含 `execution_plan`）

### Layer 3 执行 — 自建（C2 + C3）

- **谁干**：AI 自闭环（worktree 隔离）
- **能力**：worktree 创建、AI session 启动（Claude Code headless）、prompt 模板、双 AI 独立实现（high criticality）+ 仲裁
- **产物**：可 merge 的 PR per task

### Layer 4 验证 — 自建（C4 + C5）

- **谁干**：自动化工具 + AI session（独立）
- **能力**：5 层 check + AI Reviewer 独立审
- **产物**：`verify_report.json` + `ai_review.json`

### Layer 5 Gate — 自建（C6 + C7）

- **谁干**：自动化（人通过 `human:block` 标签可紧急 override）
- **能力**：gate 规则评估、自动 retry、失败升级
- **产物**：merge to main / hold

### Layer 6 发布 — 既有 CD + Deploy Gate（C8）

- **谁干**：人按按钮触发，AI 提供决策辅助
- **能力**：release summary、灰度选项、对接 CD
- **产物**：production deploy

---

## 三、工具链组件需求

每个组件给 6 个字段：作用 / 输入 / 输出 / 核心能力 / 依赖 / 未决问题。

### C1. Planning Engine（Layer 2）

| 项 | 内容 |
|---|---|
| **作用** | 把扁平 task 列表升级成"phase + 并行组"执行计划 |
| **输入** | `tasks.yaml`（spec-kit 初版）+ `spec.md` + `plan.md` |
| **输出** | `tasks.yaml`（新增 `execution_plan: [{phase, parallel: [ids]}]`） |
| **核心能力** | 静态依赖分析（task.depends_on）／ 文件级冲突检测（task.context_seeds / modifies 重叠）／ 语义冲突分析（AI 读 task 描述判断"会不会动同一资源"）／ 并行 phase 划分 |
| **依赖** | tasks.yaml schema、文件路径解析 |
| **未决 Q1** | 语义冲突分析的精度（false positive 会过度串行化） |

### C2. Task Executor（Layer 3）

| 项 | 内容 |
|---|---|
| **作用** | 单个 task 从 spec 到 PR 的全自动实现 |
| **输入** | 单个 task（id + spec_ref + plan_ref + context_seeds + verify_cmd 等） |
| **输出** | 可 merge 的 PR + verify report |
| **核心能力** | worktree 创建（命名 `worktrees/<task_id>`） ／ AI session 启动（Claude Code headless mode）／ prompt 模板（注入 task context）／ 失败重试（≤N 次）／ 超时保护 |
| **依赖** | `git worktree`、Claude Code SDK / CLI、`.specify/` 目录 |
| **未决 Q2** | 单 AI session 长度上限（>2h 自动 kill？） |

### C3. Multi-Implementation Arbiter（Layer 3，高 criticality）

| 项 | 内容 |
|---|---|
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

### C4. Verify Engine（Layer 4）

| 项 | 内容 |
|---|---|
| **作用** | 5 层独立 check 串成可解析报告 |
| **输入** | PR / 当前 working state |
| **输出** | `verify_report.json`（每个 check 各自 pass/fail + details） |
| **核心能力** | **L1 Static**: lint + type check + formatter ／ **L2 Tests**: unit + integration ／ **L3 Spec compliance**: 每个 AC 是否有对应 passing test（命名映射）／ **L4 Constitution compliance**: AI 读 constitution + diff 输出违反项 ／ **L5 Coverage delta**: 覆盖率不下降（warning，不阻断） |
| **依赖** | 项目 toolchain（dart analyze / flutter test / eslint / jest）／ AI session |
| **未决 Q4** | AC ↔ test 映射的强制方式（命名约定 `test('AC-1', ...)` ／ metadata file ／ 显式注解） |

### C5. AI Reviewer（Layer 4）

| 项 | 内容 |
|---|---|
| **作用** | 独立 AI session 评估 PR 是否实现意图 |
| **输入** | spec + plan + constitution + PR diff（**不读 implementer 工作过程**） |
| **输出** | 结构化 verdict（`approve` / `request_changes` / `block`）+ findings 列表 |
| **核心能力** | 独立 session（context 干净）／ findings 分类（severity + category + location + suggested_fix）／ Verdict 规则（high → block；medium → request_changes；low → approve） |
| **依赖** | Claude Code SDK |
| **未决 Q5** | 单次还是 N=2 + 分歧仲裁（按 task.criticality 路由？） |

### C6. Auto Merge Gate（Layer 5）

| 项 | 内容 |
|---|---|
| **作用** | 所有 check 通过自动 merge，否则 retry / 升级 |
| **输入** | PR + verify_report + review verdict |
| **输出** | merge / hold（带 reason） |
| **核心能力** | Gate 规则评估：`verify.all.pass && review.verdict == approve && pr.ff_mergeable && !pr.has_label("human:block")` ／ 自动 retry（≤3 次）／ 失败升级（标 `human:needs-attention` + 通知）／ 紧急 override 监听（`human:block` 标签） |
| **依赖** | GitHub API、C4 + C5 |
| **未决 Q6** | 失败升级通知渠道（issue comment / Slack / email） |

### C7. Phase Coordinator（横跨 Layer 2-5）

| 项 | 内容 |
|---|---|
| **作用** | 按 execution_plan 调度 phase，**phase 间逐次 merge to main** |
| **输入** | tasks.yaml 含 execution_plan |
| **输出** | 所有 task 完成 / phase 失败标记 |
| **核心能力** | 按 phase 顺序触发 task batch ／ phase 内并行触发 multiple Task Executor ／ phase 完成等所有 task merge → 进下一 phase ／ 失败处理 |
| **依赖** | C2 + C6 |
| **未决 Q7** | phase 内某 task 卡住、其他已 merge——卡住的回滚还是隔离 |

### C8. Deploy Gate（Layer 6）

| 项 | 内容 |
|---|---|
| **作用** | 人按按钮触发 deploy，AI 提供决策辅助 |
| **输入** | 本次发版 PR 列表 + change history |
| **输出** | 触发 deploy pipeline / 暂缓 |
| **核心能力** | AI 自动生成 release summary（spec 实现状况 + 风险 hint）／ 灰度 / 全量 / 暂缓 选项 ／ 触发 CD（GitHub Actions / Vercel / 自建） |
| **依赖** | 既有 CD |
| **未决 Q8** | 风险 summary 的格式（人 30 秒读完） |

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

---

## 五、命名建议

整套工具链需要一个代号便于后续讨论。候选：

- **`suiyin-flow`** ← 推荐：平实、跟项目绑定
- `spec-runner` — 强调"执行 spec"
- `forge` — AI native CI/CD 隐喻
- `conductor` — 强调编排

未来开源时再起 catchy 名字。

---

## 六、落地优先级

| 优先级 | 组件 | 价值 |
|---|---|---|
| **P0 MVP** | C2 Task Executor + C4 Verify Engine（仅 L1 + L2） | 跑通"AI 写 1 个 task + 测试通过"最小循环 |
| **P1** | C5 AI Reviewer + C6 Auto Merge Gate | 自闭环 merge（不要人审 PR） |
| **P2** | C1 Planning Engine + C7 Phase Coordinator | 并行加速 |
| **P3** | C3 Arbiter + C4 Verify Engine 补 L3/L4 | 强化关键路径 |
| **P4** | C8 Deploy Gate UI | 收尾 |

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
       │                            │      C4 Verify (L1-5)      │
       │                            │      C5 AI Review (独立)   │
       │                            │          │                 │
       │                            │          ▼                 │
       │                            └─► C6 Auto Merge Gate       │
       │                                       │                 │
       │                                       ▼                 │
       │                                  merge to main          │
       │                                                         │
       └─────────────────────────────────────────────────────────┘
                                       │
                                       ▼
                                  C8 Deploy Gate (人按按钮)
```

---

## 附录 A：跟 methodology.md / constitution.md 的关系

- **methodology.md**：方法论原则（spec 怎么写、bug 怎么分类、spec rot 怎么防御）— 给团队所有参与者
- **toolchain.md（本文档）**：工具链需求（要做哪些工具、各自接什么输入输出）— 给工具链开发者
- **constitution.md（未来）**：项目宪法（不可妥协的原则 + 治理）— 团队对齐用，principles 引用 methodology 和 toolchain

未来如果 methodology 和 toolchain 冲突，constitution 仲裁。Constitution 还没写，预期在工具链 P0 落地前定。

## 附录 B：未决问题清单

汇总 C1-C8 的"未决"字段，便于追踪。每个未决问题在该组件做 spec 阶段时解决。

| 编号 | 问题 | 涉及组件 |
|---|---|---|
| **Q1** | 语义冲突分析的精度（false positive 风险） | C1 |
| **Q2** | 单 AI session 长度上限（>2h kill？） | C2 |
| **Q3** | 仲裁 AI 是第 3 个独立 session 还是 reviewer 兼任 | C3 |
| **Q4** | AC ↔ test 映射强制方式（命名约定 vs metadata vs 注解） | C4 |
| **Q5** | AI Reviewer 单次还是 N=2 分歧仲裁 | C5 |
| **Q6** | Merge Gate 升级通知渠道（issue / Slack / email） | C6 |
| **Q7** | phase 内某 task 卡住，已 merge 的回滚还是隔离 | C7 |
| **Q8** | Deploy Gate 风险 summary 格式（人 30s 读完） | C8 |

---

**Version**: 0.1.0-draft（与 methodology.md 一起作为 v4 协作框架的基线，未来正式 ratify 后升 1.0.0）
**Last Updated**: 2026-05-15
