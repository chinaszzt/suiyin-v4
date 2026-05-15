# 碎银 v4 SDD — 流程图集

> 把所有讨论过的流程图集中在一处，方便打开慢慢思考。Mermaid 在 GitHub 自动渲染。
> 语义和细节参见 `workflows.md` / `toolchain.md` / `discussion-notes.md`。

---

## 1. 4 层级关系

**回答**: v4 项目的产物分几层？每层修改频率和影响面如何？

```mermaid
flowchart TD
    A[Constitution<br/>项目原则<br/>一次性 + ADR 修订<br/>极稀有] --> B[Initiative<br/>跨多 feature 大型变更<br/>年 1-2 次]
    B --> C[Feature spec<br/>单能力契约<br/>每个 feature 跑一遍流程]
    C --> D[Task<br/>单 PR<br/>每个 feature 拆 N 个]
```

修改自下而上传染：改 Constitution 可能 cascade 到所有；改 Initiative cascade 到多个 feature；改 feature cascade 到自己的 tasks。

---

## 2. Feature 主流程 - 完整状态机（含 Plan 内部循环 + 异常）

**回答**: 一个 feature 从想法到生产，AI 和人怎么走？

```mermaid
flowchart TD
    A([Constitution]) -.->|约束所有 feature| B
    B[Feature Trigger<br/>新想法 / bug / change] --> C[Specify]
    C --> D[Clarify]
    D -->|still ambiguous| C
    D -->|all clear| E[Plan v0]
    E --> RS[C11 Reuse Scan<br/>语义检索 function registry]
    RS --> RD{overlap?}
    RD -->|< 50%| F[Plan final]
    RD -->|50-80%| RV[Plan v1: 抽片段 Y 为 helper]
    RD -->|80%+| RV2[Plan v1: 改造 X 为公共函数]
    RV --> F
    RV2 -.->|可能扩大 scope| RS
    RV2 --> F
    F -->|发现 spec 漏意图| C
    F --> G[Tasks]
    G --> H[Planning Engine C1<br/>分 phase + 并行组]
    H --> I[Phase Coordinator C7]
    I -->|per task in phase| J[Task Executor C2]
    J --> K[Verify Engine C4<br/>5 层 check]
    K -->|fail, retry ≤3| J
    K -->|pass| L[AI Reviewer C5<br/>独立 session]
    L -->|block| J
    L -->|approve| M[Merge Gate C6<br/>全绿自动 merge]
    M -->|merged| N{phase 完成?}
    N -->|no, next task| J
    N -->|yes| O{所有 phase done?}
    O -->|no, next phase| I
    O -->|yes| P[Deploy Gate C8<br/>人按按钮]
    P --> Q([Production])

    style C fill:#e1f5ff
    style D fill:#e1f5ff
    style E fill:#e1f5ff
    style RS fill:#fff3cd
    style P fill:#ffe0e0
```

**颜色**: 蓝 = 协商阶段（人参与）；黄 = 重复检查；红 = 人按按钮。

异常退出（任何节点都可能触发）见 §7。

---

## 3. Plan 内部循环放大 - plan ⇌ reuse-scan + 抽取 3 档决策

**回答**: Plan 阶段不是单次起草，是带循环的子流程。抽取决策的 3 档怎么走？

```mermaid
flowchart TD
    A[Plan v0 起草<br/>AI 写要具体怎么实现] --> B[C11 Reuse Scan<br/>语义检索 function registry<br/>返回 top-N 候选 + overlap %]
    B --> C{overlap?}
    
    C -->|< 50%| D[独立实现<br/>plan 不修订]
    
    C -->|50-80%| E[AI 识别重叠片段]
    E --> F{重叠片段<br/>有抽取价值?}
    F -->|yes| G[Plan v1:<br/>抽片段 Y 为 helper<br/>双方各保留差异]
    F -->|no| D
    
    C -->|80%+| H[改造 X 为公共函数<br/>差异参数化<br/>调用方迁移]
    H --> I{改造扩大<br/>plan scope?}
    I -->|yes| B
    I -->|no| J[Plan v1:<br/>使用改造后的公共函数]
    
    D --> K[Plan final]
    G --> K
    J --> K
    K --> L[进 Tasks]
    
    style B fill:#fff3cd
    style C fill:#d4edda
    style F fill:#d4edda
    style I fill:#d4edda
```

**通用循环模式**:

| 阶段 | 单次产出？ | 反向触发 |
|---|---|---|
| specify ⇌ clarify | ❌ 多版本 | clarify 找漏 → specify 修订 |
| **plan ⇌ reuse-scan** | ❌ **多版本** | reuse-scan 找重复 → plan 修订 |
| implement → verify | ✅ 单次 + retry | verify 失败 → 修 impl |

---

## 4. Bug 流程 - 4 种 Type 分流

**回答**: 报告一个 bug，根据 type 走不同路径？

```mermaid
flowchart TD
    A[Bug Report] --> B[Bug Triage<br/>强制第一步：找相关 spec 对照 AC]
    B -->|Type A<br/>impl 偏离 spec| C[Create fix task<br/>task.kind = bugfix<br/>必含 regression test]
    C --> D[标准 feature 流程<br/>C2 → C4 → C5 → C6]
    B -->|Type B<br/>spec 没覆盖这个边界| E[回 Specify 补 AC]
    E --> F[走正常 feature 流程]
    B -->|Type C<br/>spec 写错了| G[写 ADR<br/>+ 回 Specify 修订]
    G --> F
    B -->|Type D<br/>P0 紧急| H[Hotfix 直接修 main<br/>唯一允许绕过 worktree 铁律]
    H --> I[24h 内必须补 spec PR<br/>超时阻断下一次 deploy]
    
    style H fill:#ffe0e0
    style I fill:#ffe0e0
```

---

## 5. Initiative 流程 - 大型变更（跨多 spec）

**回答**: 技术栈切换 / 重构这种跨多个 feature 的变更怎么走？

```mermaid
flowchart TD
    A[Change Trigger<br/>例: IndexedDB → SQLite] --> B[Initiative Spec<br/>why + 影响范围 + 成功标准]
    B --> C[Initiative Plan<br/>migration sequence + rollback<br/>+ 灰度 + 向后兼容期]
    C --> D{触动 Constitution<br/>principle?}
    D -->|yes| E[Constitution Amendment<br/>ADR + 版本 bump]
    D -->|no| F[Affected Specs Cascade C9<br/>自动列出受影响的 feature spec]
    E --> F
    F --> G[for each affected spec]
    G --> H[Spec Migration Sub-Feature<br/>走标准 feature 流程]
    H --> I{所有 affected spec<br/>迁移完?}
    I -->|no| G
    I -->|yes| J[Initiative Validation<br/>跨 spec 集成测试<br/>数据一致性 / 性能]
    J --> K([Initiative Complete])
    
    style B fill:#e1f5ff
    style C fill:#e1f5ff
    style E fill:#ffe0e0
```

---

## 6. 异常退出 - 任何节点都可能触发

**回答**: AI 跑到一半发现不对怎么办？

```mermaid
flowchart TD
    A[任何节点检测到异常] --> B{异常类型?}
    B -->|spec drift<br/>AI 发现 spec 不清楚 / 有歧义| C[标 spec-drift issue<br/>暂停 task]
    C --> D[找人仲裁]
    D --> E[回 Specify 修订]
    B -->|cross-spec impact<br/>改动影响别的 spec| F[标 cross-spec issue<br/>暂停 task]
    F --> G[找人 prioritize<br/>决定是否扩大 scope]
    B -->|retry exhausted ≥3| H[标 human:needs-attention]
    H --> I[人审 fail 原因]
    
    style C fill:#fff3cd
    style F fill:#fff3cd
    style H fill:#fff3cd
    style D fill:#ffe0e0
    style G fill:#ffe0e0
    style I fill:#ffe0e0
```

3 种异常都需要**人介入**——这跟 L1.D-business profile 一致：执行阶段 AI 自闭环，异常时人才出来。

---

## 7. 复杂度治理 - 6 层防御机制（覆盖整个流程）

**回答**: 代码复杂度在每个流程节点怎么被治理？

```mermaid
flowchart LR
    subgraph SP[Spec / Plan 阶段]
        L1[L1 Constitution<br/>简单 优先<br/>量化指标]
        L2[L2 Plan<br/>Could this<br/>be simpler?]
        L3[L3 Task 拆解<br/>500行 5文件<br/>自动拆分]
    end
    
    subgraph EV[执行 / 验证阶段]
        L4[L4 Verify L1 Static<br/>复杂度阈值阻断<br/>+ jscpd]
        L5[L5 AI Reviewer<br/>complexity findings<br/>过度设计 / 重复实现 / 不必要抽象]
    end
    
    subgraph PE[周期性]
        L6[L6 季度复杂度盘点<br/>refactor backlog]
    end
    
    SP --> EV
    EV -.周期触发.-> PE
    PE -.refactor task.-> SP
    
    style L1 fill:#d4edda
    style L2 fill:#d4edda
    style L3 fill:#d4edda
    style L4 fill:#fff3cd
    style L5 fill:#fff3cd
    style L6 fill:#e1f5ff
```

**颜色**: 绿 = 协商时介入（最早）；黄 = 执行时介入（自动）；蓝 = 周期介入（兜底）。

---

## 8. 代码复用治理 - 4 层防御机制

**回答**: spec / code 两个层级的重复怎么各管各的，又互相配合？

```mermaid
flowchart TB
    subgraph Spec[Spec 阶段]
        L1[L1 Domain Glossary<br/>业务概念词典<br/>spec 必须 reference]
        L2[L2 C10 Spec Overlap Detector<br/>新 spec 比对已有 spec<br/>spec 写完，clarify 前触发]
    end
    
    subgraph PlanMerge[Plan / Merge 阶段]
        direction LR
        L3a[L3a C11 Plan Lookup<br/>plan 阶段被动查询<br/>函数表 + 语义检索]
        L3b[L3b C11 Post-Merge Agent<br/>merge 后主动维护<br/>+ overlap audit]
    end
    
    subgraph Periodic[周期性]
        L4[L4 季度领域 + 函数 audit<br/>漂移兜底]
    end
    
    Spec --> PlanMerge
    L3a <-->|双引擎| L3b
    PlanMerge -.周期.-> Periodic
    Periodic -.refactor proposals.-> Spec
    
    style L1 fill:#d4edda
    style L2 fill:#d4edda
    style L3a fill:#fff3cd
    style L3b fill:#fff3cd
    style L4 fill:#e1f5ff
```

L3 是工具链最复杂的一层——**双引擎**互相喂数据。

---

## 9. C11 双引擎流程 - Plan Lookup + Post-Merge Agent

**回答**: C11 的两个查询接口具体怎么跑？谁喂谁？

```mermaid
flowchart TB
    subgraph E1[引擎 1 - Plan 阶段 Lookup 被动]
        P1[Plan v0 起草] --> P2[AI 写实现意图]
        P2 --> P3[C11 query: 语义检索 registry]
        P3 --> P4[返回 top-N 候选 + overlap %]
        P4 --> P5[Plan 模板填入<br/>Reuse Check 节]
    end
    
    subgraph E2[引擎 2 - Post-Merge Agent 主动]
        M1[Merge to main] --> M2[CI hook 启动 Agent]
        M2 --> M3[扫 diff<br/>函数 add / modify / delete]
        M3 --> M4[AI 生成 / 更新 description]
        M4 --> M5[更新 embedding index]
        M5 --> M6[全 codebase overlap audit]
        M6 --> M7{发现 missed reuse?}
        M7 -->|yes| M8[标 issue:<br/>potentially missed reuse]
        M7 -->|no| M9[完成]
        M8 --> M9
    end
    
    Registry[(function-registry.yaml<br/>+ embedding index)]
    
    E1 -->|查询| Registry
    E2 -->|维护| Registry
    
    style E1 fill:#e1f5ff
    style E2 fill:#fff3cd
    style Registry fill:#f8d7da
```

**关键**: 两个引擎共享 `function-registry.yaml` 这个**单一数据源**。维护引擎写入，查询引擎读取，永远保持一致。

---

## 10. Spec ↔ Code 双向追踪 - 锚点网络

**回答**: 改一个函数，怎么知道影响哪些 spec？反过来：spec 改了，怎么找到对应代码？

```mermaid
flowchart LR
    subgraph SL[Spec 层]
        SP1[spec.md<br/>AC-1: 客户列表<br/>按拼音排]
        SP2[spec.md<br/>AC-2: 联系人列表<br/>按拼音排]
        DG[domain-glossary.md<br/>客户排序规则<br/>联系人排序规则]
    end
    
    subgraph CL[Code 层]
        FN1[sortCustomerList<br/>// spec_ref:...]
        FN2[sortContactList<br/>// spec_ref:...]
    end
    
    subgraph RG[Registry 层]
        REG[function-registry.yaml<br/>description + embedding<br/>每个函数 implemented_by]
    end
    
    DG -.implemented_by.-> FN1
    DG -.implemented_by.-> FN2
    FN1 -.spec_ref 注释.-> SP1
    FN2 -.spec_ref 注释.-> SP2
    FN1 -.自动注册.-> REG
    FN2 -.自动注册.-> REG
    REG -.语义检索.-> DG
    
    style DG fill:#d4edda
    style REG fill:#f8d7da
    style FN1 fill:#fff3cd
    style FN2 fill:#fff3cd
```

**追踪方向**:

- **改函数** → 看注释里的 `spec_ref` → 知道影响哪些 spec
- **改 spec** → 看 glossary 的 `implemented_by` → 知道改哪些函数
- **写新 spec** → 语义检索 registry → 知道有没有重复

这是 spec rot 防御的**最强形态** —— 不靠"季度对账"，靠"改代码时就知道影响哪个 spec"。

---

## 11. 完整工具链组件全景 - Layer 1-6 + 8+3 个组件

**回答**: v4 工具链有多少组件？各在哪一层？谁依赖谁？

```mermaid
flowchart TB
    subgraph L1[Layer 1 - 协商 - 借用 spec-kit]
        S1[Constitution]
        S2[Specify ⇌ Clarify]
        S3[Plan ⇌ Reuse-Scan]
        S4[Tasks 拆解]
        S5[C10 Spec Overlap Detector<br/>新]
        S2 -.触发.-> S5
    end
    
    subgraph L2[Layer 2 - 规划 - 自建]
        C1[C1 Planning Engine<br/>phase + 并行组]
    end
    
    subgraph L3[Layer 3 - 执行 - 自建]
        C2[C2 Task Executor]
        C3[C3 Arbiter<br/>high criticality]
    end
    
    subgraph L4[Layer 4 - 验证 - 自建]
        C4[C4 Verify Engine<br/>L1-L5 check]
        C5[C5 AI Reviewer<br/>独立 session]
    end
    
    subgraph L5[Layer 5 - Gate - 自建]
        C6[C6 Auto Merge Gate]
        C7[C7 Phase Coordinator]
    end
    
    subgraph L6[Layer 6 - 发布]
        C8[C8 Deploy Gate]
    end
    
    subgraph Cross[跨层级 - 自建]
        C9[C9 Affected Specs Cascade<br/>Initiative 触发]
        C11[C11 Function Registry Steward<br/>双引擎]
    end
    
    S3 <-->|查询| C11
    L1 --> L2
    L2 --> L3
    L3 --> L4
    L4 --> L5
    L5 --> L6
    
    C11 -.post-merge.-> L5
    C9 -.Initiative 时.-> S3
    C3 -.high crit task.-> C2
    
    style C10 fill:#d4edda
    style C11 fill:#d4edda
    style C9 fill:#d4edda
```

**统计**: 11 个组件 = 8 个原方案 + 3 个本次讨论新增（C9 / C10 / C11）。

---

## 索引

| 图 | 回答的问题 |
|---|---|
| 1. 4 层级关系 | 产物分几层？修改频率？|
| 2. Feature 主流程完整图 | 一个 feature 怎么走完？|
| 3. Plan 内部循环放大 | 抽取决策 3 档具体动作？|
| 4. Bug 流程 | 4 种 Type 分别怎么走？|
| 5. Initiative 流程 | 大型变更怎么管？|
| 6. 异常退出 | AI 跑偏怎么办？|
| 7. 复杂度治理 6 层 | 每个流程节点怎么治复杂度？|
| 8. 代码复用治理 4 层 | spec / code 重复各管什么？|
| 9. C11 双引擎流程 | 函数表怎么查 + 怎么维护？|
| 10. Spec ↔ Code 双向追踪 | 怎么知道改函数影响哪些 spec？|
| 11. 完整组件全景 | 11 个组件都在哪？谁依赖谁？|

---

**Version**: 0.1.0-WIP
**Last Updated**: 2026-05-15
