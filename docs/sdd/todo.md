# 碎银 v4 SDD — TODO List

> **新 context 入口文档**。读完这份就有完整的下一步选项。
>
> 当前 main commit: 见 `git log --oneline -10`。
> 完整文档总览见 `docs/sdd/` 目录。

---

## 〇、当前状态（截至 2026-05-24）

### v4 工具链已具备的能力

| 能力 | 文档 / 实现 | 状态 |
|---|---|---|
| SDD 方法论 | `methodology.md` | ✅ |
| 工具链规约（节点 + 契约） | `toolchain.md` v0.3 | ✅ |
| 工作流状态机 + 流程图 | `workflows.md` + `diagrams.md` v0.1.1 | ✅ |
| Component spec meta-template | `component-spec-template.md` | ✅ |
| **v4 项目宪法 v0.2.1** | `constitution.md` | ✅ (Q-C-2 已 ADR-0002 拍板关闭) |
| 4 档 AI 角色定义 | `role-profiles.md` | ✅ |
| 独立 installer（不依赖 spec-kit CLI） | `bin/init.sh` | ✅ |
| 14 个 `/sy-*` slash commands | `skills/` | ✅ |
| Constitution bootstrap 特例（auto-commit + push） | `runtime/extensions.yml` | ✅ |
| Git 类命令 allowlist | `runtime/claude-settings.json` | ✅ |
| **ADR 体系**（template + ADR-0001 + ADR-0002） | `docs/sdd/adrs/` | ✅ |
| **C2 Task Executor spec v0.1.1** | `components/c2-task-executor.md` | ✅ (待 v0.1.2 反推 impl 发现) |
| **C2 Task Executor impl v0.1.3** | `src/suiyin_flow/c2_executor/` | ✅ (PR #21, #23, #25) |
| **C4 Verify Contract spec v0.1.1** | `components/c4-verify-contract.md` | ✅ (待 v0.1.2 反推 impl 发现) |
| **C4 Verify Contract impl v0.1.2** | `src/suiyin_flow/c4_verify/` | ✅ (PR #20, #22) |
| **Unified CLI** `suiyin-flow {verify,task}` | `src/suiyin_flow/cli.py` | ✅ (PR #25) |
| **MkDocs Cloudflare preview + PR diff** | `mkdocs.yml` / `.github/workflows/` | ✅ (PR #12, #13) |
| **真 dogfood 跑通**：C2 自动生成 ADR-0002 + 升 constitution v0.2.1 | PR #24 | ✅ |

### dogfood 历史

1. **2026-05-18**: v5 跑 `/sy-constitution` 发现 v0.1 层次混淆 → user 改 v0.2 → 见 ADR-0001
2. **2026-05-24**: **v4 自身**用 C2 自动生成 ADR-0002（Python 拍板）+ 升 constitution v0.2.1（PR #24）— 工具链**真正可用**的里程碑

### P0 spike 发现汇总（P1.1 dogfood 期间）

| Bug | Fix PR | 类型 |
|---|---|---|
| C4 `require_tool` venv PATH | PR #22 | impl 健壮 |
| C2 `session.py` 解析 Claude stream-json 多 event | PR #23 | impl 健壮 |
| C2 默认 cmd 缺 `--permission-mode bypassPermissions` | PR #25 | impl 健壮 |
| C2 默认 cmd 缺 `--verbose` | PR #25 | impl 健壮 |
| `suiyin-flow` entry point 缺 task dispatcher | PR #25 | impl 健壮 |
| C2 `_compute_diff_stats` origin/base fallback | PR #25 | impl 健壮 |

→ 这 6 个 fix 都没改 spec。需要 **P1.1 后续 prep** 反推到 spec §7（见 §P1.1.2）。

---

## P0 — 已完成（保留 audit trail）

### P0.1 修 constitution-template ✅ (2026-05-20)

User 改 v0.2 时去掉 5 铁律和量化指标。审查 + 重写 `runtime/templates/constitution-template.md` 防止 v6/v7 项目踩同样坑。详见 commit `cfdf412`。

### P0.2 第一个 ADR ✅ (2026-05-20)

创建 `docs/sdd/adrs/` 目录 + `0000-adr-template.md` (MADR 8 章节) + `0001-constitution-v0.1-to-v0.2-layering-fix.md`。详见 commit `d932078`。

### P0.3 ADR-0002 ✅ (2026-05-24，dogfood 生成)

- ADR-0002 (`0002-python-tech-stack.md`) — v4 技术栈 Python 3.11+ 拍板，对比 Shell / Bun / Go
- constitution v0.2.0 → v0.2.1 (§6b Q-C-2 关闭 + §9 Version History bump)
- `tests/dogfood/test_adr_0002.py` (AC-101 + AC-102) — C4 verify pass
- **实施方式**: 用 C2 真起 Claude session 自动生成 (PR #24) — v4 自身 dogfood 验证

---

## P1.1 P0 MVP — 全部完成 ✅ (2026-05-24)

跑通"AI 写一个 task + 测试通过"最小闭环。

### 阶段 1 — Spec ✅ (PR #11, 2026-05-20)

- C2 Task Executor spec v0.1.1（含 v0.1.0 → v0.1.1 user 反馈修订）
- C4 Verify Contract spec v0.1.1

### 阶段 2 — Impl ✅

| 子阶段 | 输出 | PR |
|---|---|---|
| 2.A C4 impl | Python L1+L2 runner / CLI / lefthook / 10 AC tests | #20 |
| 2.B C2 impl | worktree / prompt / session / retry / cli / 10 AC tests | #21 |
| 2.B mini-dogfood | 用 C2 mock + C4 真 CLI 重跑 C2 9 AC → bidirectional self-bootstrap | (#21 内) |
| 2.C real dogfood | 用 C2 真起 Claude session 写 ADR-0002 + bump constitution | **#24** |

### 配套修复

| PR | 内容 |
|---|---|
| #22 | C4 venv PATH fallback (`require_tool`) — v0.1.1 → v0.1.2 |
| #23 | C2 stream-json parse 真 Claude 多 event 格式 — v0.1.1 → v0.1.2 |
| #25 | C2 P0 spike triage bundle (permission-mode / verbose / unified CLI / diff_stats) — v0.1.2 → v0.1.3 |

**总体 verify**: 56 passed (10 C2 AC + 10 C4 AC + 3 venv + 15 stream-json + 5 cmd flags + 7 unified CLI + 3 diff_stats + 1 smoke + 2 dogfood AC) / mypy strict 32 source files / ruff clean。

---

## P1.1 后续 prep（启动 dogfood 进阶前）

dogfood 进阶（写代码类 task）要 spec 撑住，不然 AI 没准确 contract 跟。**顺序: P1.1.1 → P1.1.2 → dogfood 进阶。**

### P1.1.1 constitution v0.2.1 review

P1.1 跑通后回头审 constitution：

- [ ] 跑 v4 流派"边界教戒"（三问法）重检 §6 NC-1/2/3 + PC-1/2/3
- [ ] 看 P1.1 经验是否暴露 NC/PC 缺口（候选: 跨平台 / venv portability / Claude CLI 依赖 / impl 健壮性约束 / etc）
- [ ] 看 §6b Open Questions 是否还有应在 P1 阶段拍的
- [ ] 如有 substantive 变更 → ADR-0003 + bump v0.2.2 + PR 走人审（governance §8.1）
- [ ] 如无变更 → 关闭本 task，记录"已审无新约束"

预估：30-60 分钟

### P1.1.2 C2 + C4 spec 反推 v0.1.2

PR #22/#23/#25 6 个 fix 都是 impl 健壮性，应该 promote 到 spec §7 Implementation Notes 让未来 v6 项目用 v4 时知道。

- [ ] **C2 spec §7** 加 "Session 调用模式" 节
  - claude CLI 必需 flags: `--print --output-format stream-json --verbose --permission-mode bypassPermissions`
  - stream-json event 解析（result.result / assistant.text）
  - subprocess venv PATH fallback (link C4)
- [ ] **C2 spec §7** 加 "Unified CLI" 节（如保留架构）
  - `suiyin-flow {verify,task}` 单 binary 多 subcommand
- [ ] **C2 spec §3.2 Side Effects** 加 "diff_stats fallback" 说明
- [ ] **C4 spec §7** 加 "Venv portability" 节
  - `require_tool` 用 `Path(sys.executable).parent` fallback
  - Windows .exe / .bat shim 覆盖
- [ ] 两 spec 各 PATCH bump v0.1.1 → v0.1.2
- [ ] PR 走 review（不动 NC/PC，只是 impl note）

预估：30-45 分钟

---

## P1.2 P1 — 自闭环 merge

> **当前关注（P1.1 后续 prep 完成后启动）**：C5 AI Reviewer + C6 Gate Contract 让 PR 自动 merge 不要人审。

- [ ] **C5 AI Reviewer 阶段 1 spec** （走 PR #11 一样的人审 spec 流程）
  - 子任务: 写 `components/c5-ai-reviewer.md`
  - 子任务: review prompt + verdict schema (`approve` / `request_changes` / `block`)
  - 子任务: findings 分类（severity / category / location / suggested_fix；**含 `complexity` 类**：过度设计 / 重复实现 / 不必要抽象 / 函数超长）
  - 子任务: Verdict 规则（high → block; medium → request_changes; low → approve）
  - 子任务: **`reusable_knowledge_not_captured` finding category**（C12 引入点，见 P3 C12）
  - 见 `toolchain.md` C5 节，未决 Q5（单次还是 N=2 分歧仲裁）
- [ ] **C5 AI Reviewer 阶段 2 impl**（按 P1.1 双 PR 模式）
  - 子任务: impl + AC tests + 逐 AC 审计表
  - 子任务: mini-dogfood（用 C2 实现 + C4 verify + 自审）
  - 子任务: real dogfood（用 C5 审 C2/C4 历史 PR，看 verdict 是否合理）
- [ ] **C6 Gate Contract spec + impl**
  - 子任务: 写 `components/c6-gate-contract.md`
  - 子任务: gate 规则评估 (`verify.all.pass && review.verdict == approve && pr.ff_mergeable && !pr.has_label("human:block")`)
  - 子任务: 失败处理 (rebase / 等人解锁)
  - 子任务: 实现谱系: (a) git pre-push hook 最轻 / (d) 混合（默认 a）
  - 见 `toolchain.md` C6 节，未决 Q6

预估：1-2 周

### P1.3 P2 — 并行加速

- [ ] **C1 Planning Engine** — task 依赖图 + 并行分组（见 `toolchain.md` C1 节，未决 Q1）
- [ ] **C7 Phase Coordinator** — phase 调度 + 逐 phase merge（见 `toolchain.md` C7 节，未决 Q7）

预估：1 周

### P1.4 P3 — 强化关键路径

- [ ] **C3 Multi-Implementation Arbiter** — 双 AI 独立实现 + 仲裁（C3 节，未决 Q3）
- [ ] **C4 Verify Contract L3/L4** — Spec compliance + Constitution compliance（AI checks）
- [ ] **C11 Function Registry Steward** — post-merge agent（embedding 语义检索，未决 Q11/Q13/Q14）
- [ ] **C10 Spec Overlap Detector** — 新 spec 跟已有比对（未决 Q12）

预估：2-3 周

### P1.5 P4 — 收尾

- [ ] **C8 Deploy Contract** — release summary generator + CD 配置（C8 节，未决 Q8）
- [ ] **C9 Affected Specs Cascade** — Initiative 时跨 spec 影响分析（`workflows.md` §4）

预估：1 周

---

## P2 — Slash commands / Templates

- [ ] **`/sy-role` slash command** — 协商 role-profile（替代手动 vim `.specify/role-profile.yml`）— 半天
- [ ] **`/sy-domain-glossary`** — 业务概念词典协商（待 C10/C11 实现后接入）
- [ ] **`runtime/templates/domain-glossary-template.md`** — 业务词典模板（2-3 小时）
- [ ] **`component-spec-template.md` v0.2** — 处理 meta-spec 不适配 imperative 章节的 5b/6b/7b 问题（2 小时）
- [ ] **14 个 SKILL.md prompt v4 化** — 当前是 sed 改名的 spec-kit 原文，应按 v4 流派改写 prompt（含 role-profile context 注入）— 1-2 周

---

## P3 — Testing / 工程化

- [ ] init.sh 加 `--dry-run` flag
- [ ] init.sh 加 CI 自动化测试（装→卸→重装 reproducibility）
- [ ] role-profile.yml schema 校验（init.sh 内置）
- [ ] PR description template（提示标 spec_ref + role-profile 影响）
- [ ] CI workflow（v4 仓自检）

---

## P3 — 已知 issues / 后续优化

- [ ] **Bug Type B/C mini-feature 流程** — 小 bug 不走完整 spec → plan → tasks（见 `discussion-notes.md` §9.2）
- [ ] **Constitution bootstrap special cases 集合扩展** — 当前只有 `sy-constitution`，未来加 `sy-domain-glossary`（团队立基）
- [ ] **季度复杂度盘点 trigger 机制**（Fork M 是 TODO stub）
- [ ] **C11 missed reuse 原因分析记录格式**（Fork R）
- [ ] **C12 Knowledge Capture Prompt**（post-MVP follow-up，2026-05-20 识别）
  - 起因：审 spec 时发现"非 post-merge 反思时刻"沉淀 gap
  - 性质：prompt / ritual / lint 规则
  - 设计：触发时刻 + 沉淀目标层 mapping protocol + **C5 finding category `reusable_knowledge_not_captured`**
  - 触发点：P1.2 C5 Reviewer spec 设计前（C5 finding enum 需要这条时拍）→ 见 P1.2 子任务
  - 详见 `discussion-notes.md` §十、`diagrams.md` 图 11 C12 dashed placeholder

---

## Pending Forks（未拍 / 待 P0 spike 后定）

已拍的不在此列。剩余：

| Fork | 内容 | 见 |
|---|---|---|
| **Q1** | C1 语义冲突分析精度 (false positive 风险) | toolchain.md C1 |
| **Q2-2** | claude CLI 实际 work（P1.1 spike 验证） / SDK 备选 | C2 §6（dogfood 已证 CLI work）|
| **Q2-3** | retry 续命 vs reset worktree | C2 §6（dogfood 阶段 2.C 验证续命 OK）|
| **Q2-4** | gh 失败降级 (已实施: pr_created=false fallback) | C2 §6 — **可关** |
| **Q2-5** | gitignore 大目录策略 | C2 §6（业务项目自管 .gitignore，已实施）— **可关** |
| **Q3** | C3 仲裁 AI 是第 3 个 session 还是兼任 | C3 |
| **Q4-2** | P0 阶段 ac_summary.missing 非空 overall_verdict 是否阻断 | C4 §6（实施: 不阻断）— **可关** |
| **Q4-3** | lefthook 修改非代码文件时 L1/L2 是否跳过 | C4 §6 |
| **Q4-4** | Dart group 嵌套 test name 解析 | C4 §6（实施: `\bAC-\d+\b` 正则跨 group work）— **可关** |
| **Q4-5** | multi_ac_violation 是 L2 期阻断还是 L3 期 | C4 §6（实施: L2 期 ac_summary 标记不阻断 overall）— **可关** |
| **Q4-6** | 跨语言 toolchain monorepo 探测 | C4 §6 |
| **Q5** | C5 单次还是 N=2 分歧仲裁 | C5 |
| **Q6** | C6 失败升级通知渠道 | C6 |
| **Q7** | phase 内某 task 卡住, 已 merge 回滚还是隔离 | C7 |
| **Q8** | C8 风险 summary 格式（人 30s 读完） | C8 |
| **Q11/Q13/Q14** | C11 embedding / function description / 部分抽取 | C11 |
| **Q12** | spec overlap threshold | C10 |
| **Q-Constitution-1** | NON-NEGOTIABLE 严格规则集合（v1.0） | constitution §6b |
| **Q-Constitution-3** | 性能/安全/可观察性硬指标 | constitution Q3 |
| **Q-Constitution-4** | 项目身份精确措辞 | constitution Q4 |
| **Q-Role-1/2/3** | 自定义 profile / 跨 feature 不同 profile / profile 切换历史是否纳入 ADR | role-profiles.md |

**已关闭**: Q2-1 (2h timeout 拍, PR #21), Q-C-2 (Python 拍, ADR-0002), Q4-1 (Fork G 命名约定拍, PR #20), Q-C-5 (ADR template 已定型, PR #19)。**可关闭** 的待 P1.1.1 / P1.1.2 review 时落实。

---

## 新 Context 入口建议

复制下面这段作为新 context 的 starter prompt：

```
我在 /Users/zhangtuo/Documents/suiyin-v4 项目里。
v4 是 SDD 工具链开发项目本身（不是业务项目，业务在 suiyin-v5）。
v4 工具链 P0 MVP 已经可用 (PR #24 dogfood 跑通真自动生成 ADR-0002).

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
| 看流程图 | `diagrams.md` v0.1.1（11 张 Mermaid + C12 placeholder） |
| 看状态机 + Bug / Initiative 流程 | `workflows.md` |
| 了解项目宪法 | `constitution.md` v0.2.1（含 ADR-0002 引用） |
| 写 C 模块 spec | `component-spec-template.md` |
| 了解 AI 角色 4 档 | `role-profiles.md` |
| 看一堆未决和讨论 | `discussion-notes.md` v0.3.1（WIP，含 §十 C12 placeholder） |
| **用 v4 工具链跑 task** | `src/suiyin_flow/` impl + `suiyin-flow {verify,task}` CLI |
| 装 v4 到新业务项目 | `bin/init.sh` |
| 14 个 slash command 实现 | `skills/sy-*/SKILL.md` |
| 给 v5 项目的 README 模板 | `templates/README-v5.md` |
| 看 ADR | `docs/sdd/adrs/` (0000 template, 0001 layering fix, 0002 Python tech stack) |

---

**Version**: v0.2.0
**Last Updated**: 2026-05-24
**Status**: Living document — P1.1 P0 MVP 全部 done (PR #11-25), 当前 prep 阶段 (P1.1.1 + P1.1.2), 然后进 P1.2 自闭环 merge
