# 碎银 v4 SDD — TODO List

> **新 context 入口文档**。读完这份就有完整的下一步选项。
>
> 当前 main commit: 见 `git log --oneline -10`。
> 完整文档总览见 `docs/sdd/` 目录。

---

## 〇、当前状态（截至 2026-05-19）

### v4 工具链已具备的能力

| 能力 | 文档 | 状态 |
|---|---|---|
| SDD 方法论 | `methodology.md` | ✅ |
| 工具链规约（节点 + 契约） | `toolchain.md` v0.3 | ✅ |
| 工作流状态机 + 流程图 | `workflows.md` + `diagrams.md` | ✅ |
| Component spec meta-template | `component-spec-template.md` | ✅ |
| v4 项目宪法 v0.2 | `constitution.md` | ✅ (user dogfood 更新) |
| 4 档 AI 角色定义 | `role-profiles.md` | ✅ |
| 独立 installer（不依赖 spec-kit CLI） | `bin/init.sh` | ✅ |
| 14 个 `/sy-*` slash commands | `skills/` | ✅ |
| Constitution bootstrap 特例（auto-commit + push） | `runtime/extensions.yml` | ✅ |
| Git 类命令 allowlist | `runtime/claude-settings.json` | ✅ |

### v5 dogfood 第一次验证

User 在 v5 跑 `/sy-constitution`，发现 v0.1 层次混淆问题（SDD 通用规则塞进 constitution），手动改 v0.2 解决。这是工具链第一次 end-to-end 验证。

**重要 insight**: constitution **只放项目独有约束**，SDD 通用规则归 methodology。可能要：
- 更新 `runtime/templates/constitution-template.md`（防止 v6/v7 项目跑 generator 时又踩同样的层次混淆）
- 见 §P0.1

---

## P0 — 立刻该做的（小工作量、高价值）

### P0.1 修 constitution-template 防止 v0.1 层次混淆复现

User 改 v0.2 时去掉了 5 铁律和量化指标（属于 SDD 通用 / 业务 specific，不该塞 constitution）。**当前 v4 提供给 v5 的模板可能让下个项目踩同样坑**。

- [ ] 审查 `runtime/templates/constitution-template.md`
- [ ] 把"5 principles 引导"改成"项目独有约束引导"（NC-* 不可妥协 + PC-* 偏好约束）
- [ ] AI collaboration profile section 直接 reference role-profile.yml（不重复内容）
- [ ] 加防御性指引："禁止塞 SDD 通用规则 / 业务 specific 量化指标"

预估：2-3 小时

### P0.2 第一个 ADR

User v0.2 提交属于"修改 constitution 的重大变更"，按 governance 应该有 ADR。

- [ ] 创建 `docs/sdd/adrs/` 目录
- [ ] 写 ADR-001：constitution v0.1 → v0.2 层次混淆修正（追溯文档）
- [ ] 创建 `adr-template.md` 模板

预估：1-2 小时

---

## P1 — 工具链组件（imperative，要写代码）

按落地优先级（toolchain.md §6）：

### P1.1 P0 MVP — 跑通"AI 写一个 task + 测试通过"最小闭环

- [ ] **C2 Task Executor** — 单 task 从 spec 到 PR 自动实现
  - 子任务：写 component spec (`components/c2-task-executor.md`)
  - 子任务：worktree 创建 + Claude Code headless session
  - 子任务：prompt 模板 + task context 注入
  - 子任务：失败重试 (≤3) + timeout
  - 见 `toolchain.md` C2 节，未决 Q2
- [ ] **C4 Verify Contract**（仅 L1 + L2）
  - 子任务：写 contract spec (`components/c4-verify-contract.md`)
  - 子任务：lefthook 配置 lint + tests
  - 子任务：verify_report.json schema
  - 见 `toolchain.md` C4 节，未决 Q4

预估：3-5 天 dogfood，1-2 周打磨

### P1.2 P1 — 自闭环 merge

- [ ] **C5 AI Reviewer** — 独立 session 评估 PR
  - 子任务：component spec
  - 子任务：reviewer prompt + verdict schema
  - 子任务：findings 分类（含 complexity 类，跨文件查重）
  - 见 `toolchain.md` C5 节，未决 Q5
- [ ] **C6 Gate Contract** — git hook 或 GitHub merge queue
  - 子任务：contract spec
  - 子任务：gate 规则评估
  - 子任务：retry / 升级逻辑
  - 见 `toolchain.md` C6 节，未决 Q6

预估：1-2 周

### P1.3 P2 — 并行加速

- [ ] **C1 Planning Engine** — task 依赖图 + 并行分组
  - 见 `toolchain.md` C1 节，未决 Q1
- [ ] **C7 Phase Coordinator** — phase 调度 + 逐 phase merge
  - 见 `toolchain.md` C7 节，未决 Q7

预估：1 周

### P1.4 P3 — 强化关键路径

- [ ] **C3 Multi-Implementation Arbiter** — 双 AI 独立实现 + 仲裁
  - 见 `toolchain.md` C3 节，未决 Q3
- [ ] **C4 Verify Contract L3/L4** — Spec compliance + Constitution compliance（AI checks）
- [ ] **C11 Function Registry Steward** — post-merge agent
  - 子任务：sentence-transformers 本地 embedding (Fork Q)
  - 子任务：函数表 schema
  - 见 `discussion-notes.md` §3，未决 Q11/Q13/Q14
- [ ] **C10 Spec Overlap Detector** — 新 spec 跟已有比对
  - 见 `discussion-notes.md` §2，未决 Q12

预估：2-3 周

### P1.5 P4 — 收尾

- [ ] **C8 Deploy Contract** — release summary generator + CD 配置
  - 子任务：summary generator prompt
  - 子任务：CD 配置模板
  - 见 `toolchain.md` C8 节，未决 Q8
- [ ] **C9 Affected Specs Cascade** — Initiative 时跨 spec 影响分析
  - 见 `workflows.md` §4

预估：1 周

---

## P2 — Slash commands / Templates

- [ ] **`/sy-role` slash command** — 协商 role-profile（替代手动 vim `.specify/role-profile.yml`）
  - 4 档引导问题 + 写 yaml
  - 预估：半天
- [ ] **`/sy-domain-glossary`** — 业务概念词典协商
  - 待 C10/C11 实现后接入
- [ ] **`runtime/templates/domain-glossary-template.md`** — 业务词典模板
  - 预估：2-3 小时
- [ ] **`component-spec-template.md` v0.2**
  - 处理 meta-spec 不适配 imperative 章节的 5b/6b/7b 问题
  - 见 discussion-notes 已记的 dogfood 反馈
  - 预估：2 小时
- [ ] **14 个 SKILL.md prompt v4 化**
  - 当前是 sed 改名的 spec-kit 原文
  - 应该按 v4 流派改写 prompt（含 role-profile context 注入）
  - 子任务：先在 sy-constitution / sy-specify 上试
  - 预估：1-2 周（14 个全做）

---

## P3 — Testing / 工程化

- [ ] init.sh 加 `--dry-run` flag
- [ ] init.sh 加 CI 自动化测试（装→卸→重装 reproducibility）
- [ ] role-profile.yml schema 校验（init.sh 内置）
- [ ] PR description template（提示标 spec_ref + role-profile 影响）
- [ ] CI workflow（v4 仓自检）

---

## P3 — 已知 issues / 后续优化

- [ ] **Bug Type B/C mini-feature 流程** — 小 bug 不走完整 spec → plan → tasks
  - 见 `discussion-notes.md` §9.2 TODO
- [ ] **Constitution bootstrap special cases 集合扩展**
  - 当前只有 `sy-constitution`，未来加 `sy-domain-glossary`（团队立基）
- [ ] **季度复杂度盘点 trigger 机制**（Fork M 是 TODO stub）
- [ ] **C11 missed reuse 原因分析记录格式**（Fork R）

---

## Pending Forks（未拍 / 待 P0 spike 后定）

汇总现有未决：

| Fork | 内容 | 见 |
|---|---|---|
| **Q1-Q11** | C1-C11 各自的未决细节 | `workflows.md` §六、`discussion-notes.md` §五 |
| **Q12** | spec overlap threshold | C10 |
| **Q13** | function description 精度 | C11 |
| **Q14** | 部分抽取片段识别算法 | C11 |
| **Q-Constitution-1** | NON-NEGOTIABLE 严格规则集合（v1.0） | `constitution.md` §6b/§8 |
| **Q-Constitution-2** | 技术栈选型（走 Initiative） | constitution Q2 |
| **Q-Constitution-3** | 性能/安全/可观察性硬指标 | constitution Q3 |
| **Q-Constitution-4** | 项目身份精确措辞 | constitution Q4 |
| **Q-Constitution-5** | ADR template 详细格式 | constitution Q5 |
| **Q-Role-1** | 自定义 profile 支持 | `role-profiles.md` |
| **Q-Role-2** | 跨 feature 不同 profile | role-profiles |
| **Q-Role-3** | profile 切换历史是否纳入 ADR | role-profiles |

---

## 新 Context 入口建议

复制下面这段作为新 context 的 starter prompt：

```
我在 /Users/zhangtuo/Documents/suiyin-v4 项目里。
v4 是 SDD 工具链开发项目本身（不是业务项目，业务在 suiyin-v5）。

先读 docs/sdd/todo.md 了解全貌和下一步选项。
也可以读 docs/sdd/constitution.md 了解项目独有约束。

我打算先做：__________（这里填你想做的 TODO 编号或具体任务）
```

或者更激进：让新 context 自己读 todo.md 后建议下一步。

---

## 关键文件速查

| 想做 | 读哪份 |
|---|---|
| 了解 SDD 方法论 | `methodology.md` |
| 了解工具链节点定义（C1-C11 是啥）| `toolchain.md` |
| 看流程图 | `diagrams.md`（11 张 Mermaid） |
| 看状态机 + Bug / Initiative 流程 | `workflows.md` |
| 了解项目宪法 | `constitution.md`（v0.2，user dogfood 更新） |
| 写 C 模块 spec | `component-spec-template.md` |
| 了解 AI 角色 4 档 | `role-profiles.md` |
| 看一堆未决和讨论 | `discussion-notes.md`（WIP，待消化）|
| 装 v4 到新业务项目 | `bin/init.sh` |
| 14 个 slash command 实现 | `skills/sy-*/SKILL.md` |
| 给 v5 项目的 README 模板 | `templates/README-v5.md` |

---

**Version**: v0.1.0
**Last Updated**: 2026-05-19
**Status**: Living document — 完成 TODO 项时打勾，新增需求加进对应 P 级
