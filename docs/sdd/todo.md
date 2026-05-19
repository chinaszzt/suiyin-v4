# 碎银 v4 SDD — TODO List

> **新 context 入口文档**。读完这份就有完整的下一步选项。
>
> 当前 main commit: 见 `git log --oneline -10`。
> 完整文档总览见 `docs/sdd/` 目录。

---

## 〇、当前状态（截至 2026-05-20）

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
| **C2 Task Executor spec** | `components/c2-task-executor.md` v0.1 | ✅ (P1.1 阶段 1) |
| **C4 Verify Contract spec** | `components/c4-verify-contract.md` v0.1 | ✅ (P1.1 阶段 1) |

### v5 dogfood 第一次验证

User 在 v5 跑 `/sy-constitution`，发现 v0.1 层次混淆问题（SDD 通用规则塞进 constitution），手动改 v0.2 解决。这是工具链第一次 end-to-end 验证。

**重要 insight**: constitution **只放项目独有约束**，SDD 通用规则归 methodology。可能要：
- 更新 `runtime/templates/constitution-template.md`（防止 v6/v7 项目跑 generator 时又踩同样的层次混淆）
- 见 §P0.1

---

## P0 — 立刻该做的（小工作量、高价值）

### P0.1 修 constitution-template 防止 v0.1 层次混淆复现 ✅ (2026-05-20)

User 改 v0.2 时去掉了 5 铁律和量化指标（属于 SDD 通用 / 业务 specific，不该塞 constitution）。**当前 v4 提供给 v5 的模板可能让下个项目踩同样坑**。

- [x] 审查 `runtime/templates/constitution-template.md`
- [x] 把"5 principles 引导"改成"项目独有约束引导"（NC-* 不可妥协 + PC-* 偏好约束）
- [x] AI collaboration profile section 直接 reference role-profile.yml（不重复内容）
- [x] 加防御性指引："禁止塞 SDD 通用规则 / 业务 specific 量化指标"

**改动**：按 v0.2 dogfood 结构重写 template — 顶部加 `extends: methodology.md` + 边界教戒 callout（三问法 + v0.1 历史教训）；删 §5 Core Principles + §6 Quantitative Standards；加 §5 Project Identity / §6 NC-PC Constraints / §7 AI Collaboration Profile (含 Bootstrap 特例引用) / §8 Governance；保留完整 component-spec 结构（§0-4 + §5b/6b/7b）。

**下游校验**：plan-template.md 的 Constitution Check 章节用抽象引用，不绑旧 Principle I-V 名字 → 不断；speckit.manifest.json hash 不更新（manifest 无消费者，保留 spec-kit 0.8.10 上游指纹意义）。

### P0.2 第一个 ADR ✅ (2026-05-20)

User v0.2 提交属于"修改 constitution 的重大变更"，按 governance 应该有 ADR。

- [x] 创建 `docs/sdd/adrs/` 目录
- [x] 写 ADR-0001：constitution v0.1 → v0.2 层次混淆修正（追溯文档）
- [x] 创建 `0000-adr-template.md` 模板（MADR 风格 8 章节）

实际：commit d932078

### P0.3 ADR-0002：v4 技术栈 = Python（Q-C-2 拍板）

P1.1 阶段 1 时拍 Q-C-2 = Python（C2 §0 / C4 §7 已记录）。按 governance §8.1，关闭 constitution Open Question 属于 substantive 变更，应有 ADR。

- [ ] 写 ADR-0002：v4 工具链 CLI = Python 3.11+（理由 + 候选对比 shell / Bun / Go）
- [ ] 更新 `constitution.md` §6b Q-C-2 状态为 "已拍：见 ADR-0002"，bump v0.2.0 → v0.2.1 (PATCH，关 Q 不改 NC)
- [ ] PR 走人审（constitution 不允许 AI 自动 merge）

预估：1 小时

---

## P1 — 工具链组件（imperative，要写代码）

按落地优先级（toolchain.md §6）：

### P1.1 P0 MVP — 跑通"AI 写一个 task + 测试通过"最小闭环

**阶段 1：写 spec** ✅ (2026-05-20)

- [x] **C2 Task Executor spec** — `components/c2-task-executor.md` (v0.1.0-draft)
  - Q2-1 已拍：单 session > 2h 强制 kill
  - Q-C-2 已拍：技术栈 = Python
  - 暴露 Q2-2/3/4/5（CLI vs SDK / retry 策略 / push 降级 / gitignore）
- [x] **C4 Verify Contract spec** — `components/c4-verify-contract.md` (v0.1.0-draft)
  - Q4-1 已拍：AC↔test 命名约定 (Fork G)
  - I2 / I7 写入：1 test 名只能 1 AC prefix；AC 重命名 protocol
  - 实现谱系明确：(a) 本地 lefthook (P0) → (d) 混合 (P1+)
  - L3/L4/L5 留 schema 槽位但 P0 不实现（请求时报 LEVEL_NOT_IMPLEMENTED）

**阶段 2：实现**（P0 MVP，~3-5 天 dogfood + 1-2 周打磨）

- [ ] **C2 Task Executor impl**
  - 子任务：Python CLI 入口 `suiyin-flow task run` + Pydantic schema（C2 §2）
  - 子任务：worktree.py（git worktree add/remove 包装）
  - 子任务：session.py（Claude Code headless 调用 + `kill -9` 整树超时）
  - 子任务：prompt.py（C2 §4 模板填充）
  - 子任务：retry.py（VERIFY_FAILED/SESSION_CRASHED 重试 ≤3；TIMEOUT 重试 1）
  - 子任务：gh CLI 可选降级（无 gh → 返回本地分支名 + `pr_created: false`）
  - 子任务：跑通 C2 §5 AC-1..AC-9（pytest，test 命名 `test_AC_N_...`）
  - **P0 spike 待验证**：Q2-2 (CLI 还是 SDK) / Q2-3 (retry 策略)
- [ ] **C4 Verify Contract impl** (L1 + L2)
  - 子任务：Python CLI 入口 `suiyin-flow verify run` + Pydantic schema（C4 §2.2）
  - 子任务：toolchain 探测（package.json / pyproject.toml / pubspec.yaml）
  - 子任务：lefthook.yml 模板（P0 仅 Python + Dart 两套）
  - 子任务：pytest JSON reporter 适配 + Dart `flutter test --reporter json` 适配
  - 子任务：test name → AC prefix 解析 + multi_ac_violation 检测
  - 子任务：verify_report.json 落盘 + ac_summary 计算
  - 子任务：跑通 C4 §5 AC-1..AC-8
- [ ] **Dogfood task**：用 C2 + C4 实现 C5 AI Reviewer spec（自举验证）

#### 阶段 2 验证 protocol（dogfood 时执行）

P1.1 阶段 2 验证矩阵存在 bootstrap 缺位：C5 (独立 reviewer) / C6 (gate) 都未实现，AC 自检 +
人 final review 是仅有兜底。明确两条增强 protocol：

- [ ] **A. spec 冻结 + 逐 AC 审计表**
  - 阶段 2 PR 禁动 `components/c2-*.md` / `components/c4-*.md` spec（spec 已在阶段 1 PR
    人审过，实现期作为 source of truth 冻结）
  - 实现 + test 完成后，PR description 强制附逐 AC 审计表：

    | AC | spec 原文（摘） | test 函数 | test 实际验的行为 | 实现位置 |

  - 人 review 时按表 scan "spec ↔ test 实际对齐性"，半小时事
- [ ] **C. dogfood 选"产物可读"task**
  - 阶段 2 实现完后，用 C2 跑一个**文档类** task（产出人能直接判质量）
  - 候选：用 C2 实现 P0.3 ADR-0002（v4 技术栈 Python 拍板），人读 ADR 看是否合理
  - 不选"写代码"的 dogfood（产出太抽象，无法快速判质量）
- [ ] **B. C5 v0.1 简陋版（已决定 skip）**
  - 决策：不在 P1.1 提前做 C5，避免给 P1.2 设计透支锚定
  - 阶段 2 接受"AC 中间段自检"风险，靠 A + C + 人 final review 兜底

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

**Version**: v0.1.1
**Last Updated**: 2026-05-20
**Status**: Living document — 完成 TODO 项时打勾，新增需求加进对应 P 级
