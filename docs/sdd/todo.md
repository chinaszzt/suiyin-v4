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
| **v4 项目宪法 v0.2.2** | `constitution.md` | ✅ NC v1.0 (+NC-4 worktree +NC-5 跨平台, ADR-0003) |
| 4 档 AI 角色定义 | `role-profiles.md` | ✅ |
| 独立 installer（不依赖 spec-kit CLI） | `bin/init.sh` | ✅ |
| 14 个 `/sy-*` slash commands | `skills/` | ✅ |
| Constitution bootstrap 特例（auto-commit + push） | `runtime/extensions.yml` | ✅ |
| Git 类命令 allowlist | `runtime/claude-settings.json` | ✅ |
| **ADR 体系**（template + ADR-0001/0002/0003） | `docs/sdd/adrs/` | ✅ |
| **C2 Task Executor spec v0.1.2** | `components/c2-task-executor.md` | ✅ (PR #28 反推 6 impl 发现) |
| **C2 Task Executor impl v0.1.3** | `src/suiyin_flow/c2_executor/` | ✅ (PR #21 + #23 + #25) |
| **C4 Verify Contract spec v0.1.2** | `components/c4-verify-contract.md` | ✅ (PR #28 反推 venv 等) |
| **C4 Verify Contract impl v0.1.2** | `src/suiyin_flow/c4_verify/` | ✅ (PR #20 + #22) |
| **C5 AI Reviewer spec v0.1.1** | `components/c5-ai-reviewer.md` | ✅ (PR #29 v0.1.0 + v0.1.1 反馈修订) |
| **C5 AI Reviewer impl v0.1.1** | `src/suiyin_flow/c5_reviewer/` | ✅ (PR #30, mini-dogfood 自审通过) |
| **Unified CLI** `suiyin-flow {verify,task,review}` | `src/suiyin_flow/cli.py` | ✅ (PR #25 + #30) |
| **MkDocs Cloudflare preview + PR diff** | `mkdocs.yml` / `.github/workflows/` | ✅ (PR #12, #13) |
| **真 dogfood × 3 跑通** | T-001 ADR / T-002 C5 spec / T-003 C5 自审 | ✅ (PR #24, #29, evidence in PR #30) |

### dogfood 历史

1. **2026-05-18**: v5 跑 `/sy-constitution` 发现 v0.1 层次混淆 → user 改 v0.2 → ADR-0001
2. **2026-05-24 T-001**: C2 自动生成 ADR-0002（Python 拍板）+ 升 constitution v0.2.1（PR #24）— P0 MVP 里程碑
3. **2026-05-24 T-002**: C2 自动生成 C5 AI Reviewer spec v0.1.0（PR #29）— 一次成功
4. **2026-05-24 T-003**: C5 自审 PR #29 → verdict=approve + 3 `reusable_knowledge_not_captured` finding（C12 I6 实证，evidence 在 PR #30）

### P0 spike 发现汇总（P1.1 dogfood 期间，全部 fixed）

| Bug | Fix PR | 反推到 spec |
|---|---|---|
| C4 `require_tool` venv PATH | PR #22 | C4 spec §7 Venv portability (PR #28) |
| C2 `session.py` stream-json 多 event 解析 | PR #23 | C2 spec §7 Session 调用模式 (PR #28) |
| C2 默认 cmd 缺 `--permission-mode bypassPermissions` | PR #25 | C2 spec §7 Session 调用模式 (PR #28) |
| C2 默认 cmd 缺 `--verbose` | PR #25 | C2 spec §7 Session 调用模式 (PR #28) |
| `suiyin-flow` entry point 缺 task dispatcher | PR #25 | C2 spec §7 Unified CLI (PR #28) |
| C2 `_compute_diff_stats` origin/base fallback | PR #25 | C2 spec §3.2 (PR #28) |

---

## P0 — 已完成（保留 audit trail）

### P0.1 修 constitution-template ✅ (2026-05-20)

详见 commit `cfdf412`。

### P0.2 第一个 ADR ✅ (2026-05-20)

`docs/sdd/adrs/` + `0000-adr-template.md` + `0001-constitution-v0.1-to-v0.2-layering-fix.md`。详见 commit `d932078`。

### P0.3 ADR-0002 ✅ (2026-05-24，dogfood 生成)

ADR-0002 (Python 技术栈) + constitution v0.2.0 → v0.2.1 + tests/dogfood/test_adr_0002.py。**实施方式**: 用 C2 真起 Claude session 自动生成 (PR #24)。

### P0.4 ADR-0003：NC v1.0 ✅ (2026-05-24, PR #27)

- 加 NC-4 worktree 隔离即安全边界
- 加 NC-5 跨平台支持 (macOS / Linux / Windows)
- 关 Q-C-1 (NC v1.0 集合宣告完成 = NC-1..NC-5 + PC-1..PC-3)
- constitution v0.2.1 → v0.2.2 (MINOR)

### P0.5 NC-6 候选 review（待 user 拍）

**起因**：C5 spec v0.1.1 §2.1 description 暗示"所有 PR 必须来自 task（含 hotfix / Initiative）"，这其实是隐性 NC 候选。

- [ ] 跑三问法验证 NC-6 候选："所有 PR 必须来自 task"
- [ ] 如成立 → ADR-0004 + constitution v0.2.2 → v0.2.3 (MINOR)
- [ ] 如不成立 → 保留为 PC 或仅工作流约定

预估：15-30 分钟讨论 + 30-45 分钟 ADR PR（如要立）

---

## P1.1 P0 MVP — 全部完成 ✅ (2026-05-24)

跑通"AI 写一个 task + 测试通过"最小闭环。

### 阶段 1 — Spec ✅ (PR #11)
- C2 Task Executor spec v0.1.1
- C4 Verify Contract spec v0.1.1

### 阶段 2 — Impl ✅

| 子阶段 | 输出 | PR |
|---|---|---|
| 2.A C4 impl | Python L1+L2 runner / CLI / lefthook / 10 AC tests | #20 |
| 2.B C2 impl | worktree / prompt / session / retry / cli / 10 AC tests | #21 |
| 2.C real dogfood | 用 C2 真起 Claude session 写 ADR-0002 + bump constitution | **#24** |

### 配套修复 ✅

| PR | 内容 |
|---|---|
| #22 | C4 venv PATH fallback — v0.1.1 → v0.1.2 |
| #23 | C2 stream-json parse 多 event 格式 — v0.1.1 → v0.1.2 |
| #25 | C2 P0 spike triage bundle (permission-mode / verbose / unified CLI / diff_stats) — v0.1.2 → v0.1.3 |

### P1.1 后续 prep ✅

- **P1.1.1** constitution v0.2.1 review ✅ (PR #27, +NC-4/NC-5/v1.0)
- **P1.1.2** C2 + C4 spec 反推 v0.1.2 ✅ (PR #28)

---

## P1.2 P1 — 自闭环 merge

**阶段 1 spec** ✅ + **阶段 2 C5 impl** ✅ + **阶段 3.1 C6 spec** ⏳ (draft v0.1.0, spec PR pending)。剩 C6 impl + mini-dogfood T-005。

### 阶段 1 — C5 spec ✅ (PR #29)

- C5 spec v0.1.0 → v0.1.1（user 审反馈修订）
  - task_id required (所有 PR 走 task)
  - verdict 简化 `{approve, block}` (去 request_changes)
  - I3-I5 按 finding category 决定 verdict（block 集合 = nc/security/spec_drift/ac_uncovered）
  - §7 加 Block Recovery 节: R1 (P1.2 human:block 标签) / R2 (P1.3 retry-with-feedback) / R3 (P3+ Codex)

### 阶段 2 — C5 impl ✅ (PR #30)

- contract.py + prompt.py + findings.py + session.py + diff.py + report.py + cli.py
- unified CLI 加 review subcommand
- 12 AC tests passed (含 mock claude pipeline)
- **mini-dogfood T-003**: C5 自审 PR #29 → approve + 3 `reusable_knowledge_not_captured` finding (C12 I6 实证)

### 阶段 3 — C6 Gate Contract spec + impl

- [x] **C6 spec** `components/c6-gate-contract.md` v0.1.0-draft（spec PR pending）
  - gate 规则 4 条 (`verify.all.pass && review.verdict == approve && pr.ff_mergeable && !pr.has_label("human:block")`)
  - 失败处理: VERIFY_NOT_PASS / REVIEW_NOT_APPROVE (→ R1) / NOT_FF_MERGEABLE / HUMAN_BLOCKED
  - 实现谱系: P1.2 落地 (a) git pre-push hook + Python CLI `suiyin-flow gate run`
  - §6 新增 Q6-2/Q6-3/Q6-4/Q6-5
  - 见 `toolchain.md` C6 节，关 Q6 = P1.2 阶段降级为 "通知通道 = PR comment"
- [x] **Block Recovery invariant promote 到 workflows.md** v0.1.1 → v0.1.2 (Insight C ✅)
  - §二 主流程图 C5 block 边重绘（R1 P1.2 / R2 P1.3 dotted）
  - 新增 "Block Recovery（D-autonomous 流派硬约束）" 小节
  - 边判定表 review block 行修正（去 request_changes，分阶段）
  - §六 加 Q6-2..Q6-5
- [ ] **C6 impl** (按 P1.1 / C5 双 PR 模式) — 待 spec PR 通过
- [ ] **mini-dogfood T-005**: 用 C6 对 PR #30 mock pre-merge gate 评估 4 条规则（T-004 改作本 spec PR 编号，原 T-004 mini-dogfood 顺移 T-005）

预估：1 周

---

## P1.2.5 — tasks.yaml → C2 adapter（窄义 MVP 真可用）

**为什么**: C6 完成后窄义 MVP 闭环达成（C2→C4→C5→C6），但 task 来源仍是**人手写** `dogfood/T-NNN/{spec.md, plan.md}` + 手敲 `suiyin-flow task run` CLI args。用户不应该这样用。spec-kit Layer 1 `/sy-tasks` 已经能生成 `tasks.yaml`（Fork A 拍板 yaml 是 task 真相载体），但跟 C2 还没 wire。

**做完后**: 用户能从 `/sy-specify → /sy-plan → /sy-tasks → 一行命令跑 batch` 全自动到 merge，无需手敲每个 task input。

### 子任务

- [ ] **读 spec-kit `/sy-tasks` 输出 schema** — 确认 tasks.yaml 当前结构（id / depends_on / context_seeds / verify_cmd / 等字段）
- [ ] **写 `src/suiyin_flow/c2_executor/batch.py`** — yaml → TaskInput list 转换 + 顺序调度
- [ ] **加 CLI subcommand `suiyin-flow task batch --tasks-yaml <path>`**
  - 顺序跑（不并行，那是 P1.3 C1+C7）
  - 每 task 完成 → 下一个; 中间 fail → 全停 + 报错（无 phase 回滚, P1.3 加）
- [ ] **AC tests**: tasks.yaml 解析 / 顺序调度 / 中间 fail 行为 / dry-run mode (列出要跑的 task 不真跑)
- [ ] **mini-dogfood**: 在 v4 自身或 v5 仓里写 1 个 spec + 跑 `/sy-tasks` → 生成 tasks.yaml → `suiyin-flow task batch` 跑通 2-3 个连续 task
- [ ] **不 bump C2 spec major**: 只是新增 batch CLI subcommand, contract / behavior 不变

预估：1-2 天

**触发**: P1.2 阶段 3 (C6) merge 后立即启动

### P1.3 P2 — 并行加速 + R2

- [ ] **R2: C2 retry-with-feedback** — C2 v0.2 加 `--review-feedback` flag, C5 block 后 C2 拿 findings 作为新 context 重 attempt (C5 §6 Q5-5 + §7 Block Recovery R2)
  - 预估：2-3 天 (C2 spec bump v0.2 + impl + AC test)
- [ ] **C1 Planning Engine** — task 依赖图 + 并行分组（toolchain.md C1，Q1）
- [ ] **C7 Phase Coordinator** — phase 调度 + 逐 phase merge（C7，Q7）

预估：2 周

### P1.4 P3 — 强化关键路径

- [ ] **C3 Multi-Implementation Arbiter** — 双 AI 独立实现 + 仲裁（Q3）
- [ ] **C4 Verify Contract L3/L4** — Spec compliance + Constitution compliance（AI checks）
- [ ] **C11 Function Registry Steward** — post-merge agent（Q11/Q13/Q14）
- [ ] **C10 Spec Overlap Detector** — 新 spec 跟已有比对（Q12）
- [ ] **R3: Codex co-review + 仲裁** — Claude + Codex 双 reviewer 取交集 (C5 §6 Q5-6, 跟 N=2 仲裁 Q5 合并)
  - 需 codex CLI 集成基础设施

预估：2-3 周

### P1.5 P4 — 收尾

- [ ] **C8 Deploy Contract** — release summary generator + CD 配置（Q8）
- [ ] **C9 Affected Specs Cascade** — Initiative 时跨 spec 影响分析

预估：1 周

---

## P2 — Slash commands / Templates

- [ ] **`/sy-role` slash command** — 协商 role-profile — 半天
- [ ] **`/sy-domain-glossary`** — 业务概念词典协商（待 C10/C11）
- [ ] **`runtime/templates/domain-glossary-template.md`** — 2-3 小时
- [ ] **`component-spec-template.md` v0.2** — 5b/6b/7b 问题，2 小时
- [ ] **14 个 SKILL.md prompt v4 化** — 1-2 周

---

## P3 — Testing / 工程化

- [ ] init.sh 加 `--dry-run` flag
- [ ] init.sh 加 CI 自动化测试（装→卸→重装 reproducibility）
- [ ] role-profile.yml schema 校验（init.sh 内置）
- [ ] PR description template（提示标 spec_ref + role-profile 影响）
- [ ] CI workflow（v4 仓自检）

---

## P3 — 已知 issues / 后续优化

### v4 流派改进

- [ ] **Bug Type B/C mini-feature 流程** — 小 bug 不走完整 spec → plan → tasks（`discussion-notes.md` §9.2）
- [ ] **Constitution bootstrap special cases 集合扩展** — 加 `sy-domain-glossary`
- [ ] **季度复杂度盘点 trigger 机制**（Fork M）
- [ ] **C11 missed reuse 原因分析记录格式**（Fork R）

### C5 mini-dogfood sinks (待复现或机会触发再 promote)

> 历次 C5 self-review 产出的 `reusable_knowledge_not_captured` finding（C12 I6 实证）汇总。
> 单次发现，**等复现 pattern 或顺手机会再 promote**，避免 over-fit single occurrence.
>
> - 2026-05-24 T-003 (C5 自审 PR #29) → Insight A / B / C (Insight C 已 promote in PR #33)
> - 2026-05-25 T-004 (C5 自审 PR #33) → Insight D (待 C8 spec 阶段触发)

- [ ] **Insight A**: AC-102 timeline-stable 测试原则 → `methodology.md`
  - **当前**: `tests/dogfood/test_adr_0002.py:26-56` inline docstring
  - **触发**: 下次写 dogfood test 又踩"snapshot current state 阻塞后续 bump"坑时 → promote
  - **建议位置**: methodology.md SDD 通用规则 / toolchain.md §C4 dogfood 测试编写约定
- [ ] **Insight B**: `_CHAPTER_RE = re.compile(r'^## \d+\. ')` numbered chapter regex → `component-spec-template.md`
  - **当前**: `tests/dogfood/test_c5_spec.py:23-46` inline regex + 注释
  - **触发**: 下次写 spec section parser 时
  - **建议位置**: component-spec-template.md 顶部"AC 测试编写注意" 节 / 或 C4 spec parser 文档
- [x] **Insight C**: Block Recovery invariant ("verdict 二元化后必须配自动 recovery") → `workflows.md` ✅ 2026-05-24
  - **promoted**: workflows.md v0.1.1 → v0.1.2 — §二 加 "Block Recovery（D-autonomous 流派硬约束）" 小节 + 主流程图重绘 + 边判定表修正
  - **触发**: 写 C6 spec 时顺手 (P1.2 阶段 3.1 合一 PR)
  - **C6 spec 引用**: §3.1 I7 (硬约束) + §7 "Block Recovery R1 协作约定"
- [ ] **Insight D**: "Contract Gate Re-evaluation Economics" → `workflows.md` 或 `methodology.md`
  - **当前**: C6 spec §3.3 关键设计点注释 "NOT_FF_MERGEABLE 不重跑 C2/C4/C5 — rebase 后代码 tree 不变, verify/review report 仍 valid"
  - **触发**: 下次 C 模块 spec（特别是 C8 Deploy Contract — release tag preserves tree）出现"上游 artifact 仍 valid 不重新评估"类逻辑时 promote
  - **建议位置**: workflows.md 加跨契约 invariant 节 / methodology.md 加 "Tree-Preserving Operations" 原则
  - **来源**: C5 self-review of PR #33 (T-004 mini-dogfood, finding category=reusable_knowledge_not_captured low)

### C2 / C5 已知 bug

- [ ] **C2 `pr_created: false` dogfood 时复现** (T-001 + T-002 都触发)
  - **现象**: C2 内嵌 `_open_pr_or_branch` 跑完后 `pr_created=false`, 手动 `git push -u origin task/<id>` + `gh pr create` 才有 PR
  - **疑似**: branch 没 upstream tracking → push 静默失败 / 或 gh auth 在 subprocess context 不可达
  - **影响**: 不阻塞 (dogfood 仍可手动开 PR), 但破坏 C2 端到端自闭环
  - **优先级**: 中（影响真 dogfood 体验，但有 workaround）
  - **修法候选**: C2 hotfix PR — `_open_pr_or_branch` 加 stderr 日志 + retry / 或预先 `git push -u` 单独成步
- [ ] **C12 Knowledge Capture Prompt**（post-MVP follow-up，2026-05-20 识别）
  - 起因：审 spec 时发现"非 post-merge 反思时刻"沉淀 gap
  - **已部分落地**: C5 finding category `reusable_knowledge_not_captured` (PR #29 spec + PR #30 impl) + C5 invariant I6 (即使 low 也输出) + T-003 实证（C5 自审 3 finding 全是这类）
  - **剩余**: C12 作为通用 ritual / prompt 是否扩展到 spec 阶段、debug 复盘等 — 见 `discussion-notes.md` §十、`diagrams.md` 图 11 C12 placeholder

---

## Pending Forks（未拍 / 待 spike 后定）

已拍的不在此列。剩余：

| Fork | 内容 | 见 |
|---|---|---|
| **Q1** | C1 语义冲突分析精度 | toolchain.md C1 |
| **Q3** | C3 仲裁 AI 是第 3 个 session 还是兼任 | C3 |
| **Q4-3** | lefthook 修改非代码文件时 L1/L2 跳过 | C4 §6 |
| **Q4-6** | 跨语言 toolchain monorepo 探测 | C4 §6 |
| **Q5** | C5 单次还是 N=2 分歧仲裁 (跟 R3 整合) | C5 |
| **Q5-2** | complexity 在 C11 未落地阶段降级 jscpd | C5 §6 |
| **Q5-3** | review 失败时 C6 视为 block 还是人介入 | C5 §6 |
| **Q5-4** | verify_report 缺失时 C5 是否输出 ac_uncovered | C5 §6 |
| **Q6** | C6 失败升级通知渠道 | C6 |
| **Q7** | phase 内某 task 卡住, 已 merge 回滚还是隔离 | C7 |
| **Q8** | C8 风险 summary 格式 | C8 |
| **Q11/Q13/Q14** | C11 embedding / function description / 部分抽取 | C11 |
| **Q12** | spec overlap threshold | C10 |
| **Q-Constitution-3** | 性能/安全/可观察性硬指标 | constitution Q3 |
| **Q-Constitution-4** | 项目身份精确措辞 | constitution Q4 |
| **Q-Role-1/2/3** | 自定义 profile / 跨 feature 不同 profile / profile 切换 ADR | role-profiles.md |

**已关闭**:
- Q2-1 (2h timeout, PR #21)
- Q2-2/Q2-3 (CLI 实际 work + retry 续命, dogfood T-001/T-002/T-003 实证)
- Q2-4/Q2-5 (gh 降级 + gitignore, 已实施)
- Q4-1 (Fork G 命名约定, PR #20)
- Q4-2/Q4-4/Q4-5 (C4 impl 决策已落地, PR #20)
- Q-C-1 (NC v1.0 集合, ADR-0003)
- Q-C-2 (Python 技术栈, ADR-0002)
- Q-C-5 (ADR template 已定型, PR #19)

---

## 新 Context 入口建议

复制下面这段作为新 context 的 starter prompt：

```
我在 /Users/zhangtuo/Documents/suiyin-v4 项目里。
v4 是 SDD 工具链开发项目本身（不是业务项目，业务在 suiyin-v5）。

P1.1 P0 MVP + P1.2 阶段 1 spec + 阶段 2 C5 impl 都已 done。
真 dogfood × 3 跑通 (T-001/T-002/T-003)。

先读 docs/sdd/todo.md 了解全貌和下一步选项。
也可以读 docs/sdd/constitution.md v0.2.2 (NC v1.0)。

我打算先做：__________
```

## 关键文件速查

| 想做 | 读哪份 |
|---|---|
| 了解 SDD 方法论 | `methodology.md` |
| 了解工具链节点定义（C1-C11 是啥）| `toolchain.md` |
| 看流程图 | `diagrams.md` v0.1.1（11 张 Mermaid + C12 placeholder） |
| 看状态机 + Bug / Initiative 流程 | `workflows.md` |
| 了解项目宪法 | `constitution.md` v0.2.2（NC v1.0 完整 = NC-1..NC-5 + PC-1..PC-3） |
| 写 C 模块 spec | `component-spec-template.md` |
| 了解 AI 角色 4 档 | `role-profiles.md` |
| 看一堆未决和讨论 | `discussion-notes.md` v0.3.1 |
| **用 v4 工具链跑 task** | `src/suiyin_flow/` impl + `suiyin-flow {verify,task,review}` CLI |
| 装 v4 到新业务项目 | `bin/init.sh` |
| 14 个 slash command 实现 | `skills/sy-*/SKILL.md` |
| 给 v5 项目的 README 模板 | `templates/README-v5.md` |
| 看 ADR | `docs/sdd/adrs/` (template / 0001 layering / 0002 Python / 0003 NC v1.0) |
| **看 C5 mini-dogfood 自审 evidence** | `PR #30` description + `.suiyin/reviews/<uuid>/latest.json` (T-003) |

---

**Version**: v0.3.1
**Last Updated**: 2026-05-24
**Status**: Living document — P1.1 P0 MVP ✅ + P1.2 阶段 1/2 ✅。下一步: P1.2 阶段 3 (C6) → P1.2.5 (tasks.yaml adapter，**窄义 MVP 真可用**)。
