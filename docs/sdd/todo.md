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
| **Plan-quality: clarify 措辞约束 + failure-modes 契约** | `failure-modes-contract.md` / `sy-clarify`·`sy-plan`·`sy-analyze` + `runtime/memory/failure-modes.md` | ✅ (PR #41, 旁观 session 建议落地, 2026-06-09) — ⏳ C5 接线待接, 见 P1.2 阶段 2.5 |
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

**阶段 1 spec** ✅ + **阶段 2 C5 impl** ✅ + **阶段 3.1 C6 spec** ✅ (v0.1.1, PR #33) + **阶段 3.2 C6 impl + T-005 dogfood** ✅ (PR #34, C5 round-1 block → round-2 block → round-3 approve, 2 low advisories sinked as Insight F/G)。**窄义 MVP 闭环达成** (C2→C4→C5→C6)。下一步 P1.2.5 tasks.yaml → C2 adapter。

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

### 阶段 2.5 — Plan-quality failure-modes 契约接 C5（⏳ 待接, PR #41 留的 follow-up）

> PR #41 落了 failure-modes 契约：可选文件 `.specify/memory/failure-modes.md`（架构级/实现级两段）。plan 侧已接（`sy-plan` 软门 + `sy-analyze` pass G）；C5 侧的 hook 留作 follow-up。

- **待做**：C5 reviewer 读 `## Implementation-level (review stage)` 段，在 diff 里查 code-level 复发，flag 命中的失败模式。文件格式 / 契约见 `docs/sdd/failure-modes-contract.md`。
- **触发点**：下次动 C5 reviewer（spec 或 impl）时顺手接 —— C5 调度本来就要读项目 memory。
- **不阻塞**：文件缺省 / 空 / 仅占位 → 静默跳过；不接也不破坏现状（plan 侧已独立生效）。

### 阶段 3 — C6 Gate Contract spec + impl

- [x] **C6 spec** `components/c6-gate-contract.md` v0.1.1-draft（PR #33；C5 self-review round-1 block → round-2 approve+advisory → round-3 approve, 1 low knowledge finding → Insight E sinked）
  - gate 规则 4 条全 AND（字段名严格按 C4 §2.2 `overall_verdict` + C5 §2.2 `verdict`）
  - 失败处理: 拆 (a) Held cases (reason 枚举) / (b) Error cases (code 枚举) 两表
  - **I8 reason precedence** (HUMAN_BLOCKED > VERIFY > REVIEW > NOT_FF) + **I9 R1 atomicity** (label/comment 分级 partial_failure)
  - Schema 改 omit-when-absent (去 `nullable: true`)；recovery_action.kind 删死值 `rebase_required`
  - 实现谱系: P1.2 落地 (a) **standalone CLI** `suiyin-flow gate run`（**不挂 pre-push** — Q6-7 决议）
  - §3.2 merge 不用 `gh pr merge`，用本地 `git merge --ff-only` + push 或 `git push <sha>:main` ff-only
  - §3.2 pr_ref → safe_pr_ref 转义规则（NC-5 跨平台文件名安全）
  - §3.3 NOT_FF_MERGEABLE 复用 verify/review 仅限 rebase 干净；conflict resolution 必须重投
  - §6 新增 Q6-2/Q6-3/Q6-4/Q6-5/Q6-6/Q6-7；**关 Q6 + cascade toolchain.md**
- [x] **Block Recovery invariant promote 到 workflows.md** v0.1.1 → v0.1.2 (Insight C ✅)
  - §二 主流程图 C5 block 边重绘（R1 P1.2 / R2 P1.3 dotted）
  - 新增 "Block Recovery（D-autonomous 流派硬约束）" 小节
  - 边判定表 review block 行修正（去 request_changes，分阶段）
  - §六 加 Q6-2..Q6-5
- [x] **C6 impl** (PR #34, 6 modules + 16 AC tests, 93/93 tests + ruff + mypy 全过)
  - `src/suiyin_flow/c6_gate/{cli,contract,rules,ff_check,actions,report}.py`
  - unified CLI 加 `gate` subcommand
  - C5 round-1 review: block (2 medium + 3 low findings) → cascade fix in same PR (spec §3.2 dry_run 落盘边界 cascade v0.1.1 → v0.1.2 + AC-1 test prefix + Q6-8 cross-platform sink)
- [x] **mini-dogfood T-005**: 用 C6 跑 4 个 mock pre-merge gate 场景 + AC-407 safe_pr_ref unit verify (5/5 pass)
  - 1-baseline (4 全 pass dry_run → merged)
  - 2-verify-fail (overall_verdict=fail → held + VERIFY_NOT_PASS)
  - 3-review-block (verdict=block → held + REVIEW_NOT_APPROVE)
  - 4-not-ff-mergeable (diverged repo → held + NOT_FF_MERGEABLE)
  - AC-407 safe_pr_ref direct unit verify (URL/branch/编号 转义 5 case)
  - I8 precedence (AC-406) 降级到 unit test (本地无真 PR API 测 label，c6_gate AC-5 test 已实证)
  - evidence: `dogfood/T-005/results/{1..4}-gate_report.json` + `README.md`

预估：1 周

### C6 已知 bug（P1.2.5 PR #35 dogfooding 时露出）

> v4 自己开始跑窄义 MVP 闭环（C2→C4→C5→C6 自动 merge）时暴露的 3 个 C6 impl bug，全部影响 v4 自身 PR 的自动 merge 路径。**已全部修好**，evidence 在 PR #36 (本 PR)。

- [x] **Bug 1 (硬阻断) `ff_merge_to_main` 在 worktree 内 fail** ✅ (PR #36)
  - 现象: 子 worktree 跑 gate 时 `git checkout main` 报 `fatal: 'main' is already used by worktree at ...` → 自动 merge 整条路径 fail
  - 根因: `actions.py:48` 的 checkout-based 实现跟 NC-4 worktree 硬约束直接冲突
  - 修法: refs-direct ff push (`git push <sha>:base` + `git update-ref refs/heads/<base>`)，零 checkout
  - C6 spec v0.1.2 → v0.1.3：§3.2 + I5 收敛单一 merge 路径，删 checkout-based 选项
  - AC test: `test_AC_11_worktree_ff_merge_no_checkout_main` (父 worktree 占 main + 子 worktree 跑 merge)
- [x] **Bug 2 (中) `resolve_pr_sha` 对 gh 抖动零容错** ✅ (PR #36)
  - 现象: 本机代理下 `gh pr view --json headRefOid` 4/5 概率 EOF；失败 → fallback `git rev-parse "35"` (PR 编号当 ref 找不到) → 报 `MISSING_INPUT could not resolve pr_ref to SHA for merge`
  - 根因: `ff_check.py:103 resolve_pr_sha` + `has_human_block_label` 的 gh path 都无 retry
  - 修法: `_gh_with_retry` 3 次指数退避 (1s/2s/4s)；用完仍失败时 stderr 提示 "如果 pr_ref 是 PR 编号请改成本地 branch 名"
  - AC tests: `test_AC_12_*` 系列 (resolve + has_human_block 双路径 retry 恢复 + 退避耗尽 fallback)
- [x] **Bug 3 (低) gh pr merge 默认非 ff (workaround 副作用)** ✅ (Bug 1+2 修好后自动消失)
  - 现象: PR #35 临时用 `gh pr merge 35 --merge` workaround → merge commit `a691d0b`，跟 #33/#34 ff-only 风格不一致
  - 根因: Bug 1 阻断 C6 自动路径 → 退化到手动 `gh pr merge` → 产 merge commit
  - 修法: Bug 1+2 修好后，C6 自动走 ff-only 路径，Bug 3 自动消失。**未来加固候选** (留 Q): C6 spec §3.1 加 "main linear-history invariant" — `git log main --first-parent --merges` 应为空。本 PR 不做。

---

## P1.2.5 — tasks.yaml → C2 adapter（窄义 MVP 真可用）

**为什么**: C6 完成后窄义 MVP 闭环达成（C2→C4→C5→C6），但 task 来源仍是**人手写** `dogfood/T-NNN/{spec.md, plan.md}` + 手敲 `suiyin-flow task run` CLI args。用户不应该这样用。spec-kit Layer 1 `/sy-tasks` 已经能生成 `tasks.yaml`（Fork A 拍板 yaml 是 task 真相载体），但跟 C2 还没 wire。

**做完后**: 用户能从 `/sy-specify → /sy-plan → /sy-tasks → 一行命令跑 batch` 全自动到 merge，无需手敲每个 task input。

### 子任务

- [x] **读 spec-kit `/sy-tasks` 输出 schema** — 反向发现 spec-kit upstream 默认输出 `tasks.md` (md checklist)；v4 Fork A 决议改输出 `tasks.yaml`，需自定义 schema（见下条 batch.py）
- [x] **写 `src/suiyin_flow/c2_executor/batch.py`** — BatchManifest schema v0.1.0 + load_tasks_yaml + run_batch（顺序串行 + fail-stop + dry-run）+ BatchAdapterError
- [x] **加 CLI subcommand `suiyin-flow task batch --tasks-yaml <path>`**
  - 顺序跑（不并行，那是 P1.3 C1+C7）
  - 每 task 完成 → 下一个; 中间 fail → 全停 + 后续 skipped（无 phase 回滚, P1.3 加）
  - exit 0 = all_success / dry_run, 1 = partial_failed, 2 = INVALID_MANIFEST / MANIFEST_NOT_FOUND / REPO_ROOT_NOT_FOUND
- [x] **AC tests** (15 个, `tests/c2_executor/test_batch.py`): tasks.yaml 解析 / 缺字段 / 反序 depends_on / 顺序调度 / 中间 fail 行为 / dry-run mode / CLI smoke
- [x] **改造 `/sy-tasks` 输出格式 md → yaml**: `runtime/templates/tasks-template.md` 内容改为 yaml schema 指引 (resolver 仍按 `.md` 后缀查找)，`skills/sy-tasks/SKILL.md` 顶部加 v4 OVERRIDE 节，强制输出 `tasks.yaml`
- [x] **mini-dogfood T-006**: `dogfood/T-006/` (spec + 3 fixtures + run.py)；4 场景全 pass:
  - 1 happy dry-run (CLI subprocess) / 2 缺 verify_cmd → INVALID_MANIFEST / 3 depends_on 反序 → BATCH_ORDER_VIOLATION
  - **4 real run_batch → execute_task → success 主路径**: fake claude script (Python) + 2 个连续 task (T-601 + T-602, depends_on) + 临时 git repo, 走完整 worktree 创建 → prompt 渲染 → claude session → verify → commit → branch fallback, evidence 落 `results/4-real-run-success-batch_output.json` (round-2 add, 覆盖原 spec "跑通 2-3 个连续 task" 真主路径要求)
  - 真起 Claude session 的全闭环（用 /sy-tasks 真生成 yaml + N × ~2h session → merge）留给用户在 v4/v5 业务场景下验收, 那是 D-autonomous 用户验收而非 implementer dogfood scope
- [x] **不 bump C2 spec major**: 只是新增 batch CLI subcommand, contract / behavior 不变 (C2 SCHEMA_VERSION 仍 v0.1.3)

预估：1-2 天 → 实际 0.5 天 ✅

**触发**: P1.2 阶段 3 (C6) merge 后立即启动 — ✅ 完成于 PR #35 (本 PR)

### 落地形态

- **新依赖**: `pyyaml>=6.0` + `types-PyYAML` (dev)
- **新模块**: `src/suiyin_flow/c2_executor/batch.py` (schema + loader + orchestrator)
- **新 CLI**: `suiyin-flow task batch --tasks-yaml <path> --repo-root <p> [--dry-run]`
- **改 skill**: `skills/sy-tasks/SKILL.md` 顶部 v4 OVERRIDE + `runtime/templates/tasks-template.md` 内容大改 (yaml schema 指引)
- **新 dogfood**: `dogfood/T-006/` 3 场景 (happy / missing-field / order-violation)
- **现有 9 个 C2 AC 不变**; 新增 15 个 batch AC (B1a-B6b)。总 108 tests passed

### 下一步要做的事 (P1.3+ 触发点)

- **R2 retry-with-feedback** (C2 v0.2): 整合 review_report 到 batch retry context — 真实使用后看是否要把 manifest 里加 `review_attempts` 字段
- **C1 Planning Engine**: 在现有 tasks.yaml 上**增加** `execution_plan: [{phase, parallel: [task_ids]}]` 字段 — schema 不变, depends_on 已预留
- **真闭环用户验证**: ✅ 已跑 (2026-06-08~09, v5 `login-credential-core` feature) —— Stage 1 (specify→plan→tasks) 通过, Stage 2 (batch) 暴露头号能力错配。详见下方 **【真闭环 dogfood 实测发现】**。

#### 【真闭环 dogfood 实测发现】(2026-06-08~09, v5 login-core)

> 用 v5 真业务仓跑 `/sy-specify → /sy-plan → /sy-tasks → suiyin-flow task batch`。
> feature = 登录凭证核心 (validatePhone / hashPassword / selectEnterprise, TS+vitest, 照搬 react-suiyin authService)。

**Stage 1 (specify→plan→tasks) ✅** —— PR #35 没真跑过的部分,现在实证:
- `/sy-tasks` 真输出 `tasks.yaml`(非上游 `tasks.md`),Fork A override 生效。
- `batch --dry-run` exit 0,schema v0.1.0 解析 + 顺序断言全过;`depends_on`/`base_branch` 扩展字段不破 schema。

**Stage 2 (batch) 🔴 头号发现 —— batch 跑不了依赖链**:
- `/sy-tasks` 拆出 5 个**有真代码依赖**的 task(T-002/3/4 依赖 T-001 骨架,T-005 聚合),但 `run_batch` 对每个 task **从 `base_branch` HEAD 独立起 worktree → commit 到 `task/<id>` → 不 merge 回 base**(merge 是 C6 `gate` 的活,batch 不调;`depends_on` 仅顺序断言,见 batch.py docstring)。
- → 依赖 task 从 base 分叉看不到前序产物(T-002 的 worktree 没有 T-001 建的 package.json)→ **链断 / fail-stop 在 T-002**。
- **能力错配: `/sy-tasks` 会拆依赖链,P1.2.5 batch 执行不了依赖链。** 逐 phase merge 是 C7 (P1.3) 才有。
- **单 task 路径 (T-001 smoke) ✅**: worktree → claude session → scaffold(package.json/tsconfig/vitest.config + npm install)→ verify(`npx vitest run --passWithNoTests` pass)→ commit → **push + 开 v5 PR #1**。1 attempt / 194s / verify_pass=true / 5 files +1340。session 守住 task 边界(只 scaffold,没越界写 src/tests)。**单 task 自治闭环完整成立(含建 PR)。**
  - **附注**: C2 的"task → PR"是其自身契约,**会 autopush 到业务仓 remote + 开 PR**(独立于 role-profile `auto_push: false`,后者只管 `/sy-*` 交互层)。用户该知道 batch 会动 v5 remote。

**行动项**(择一/组合):
- **(A 短) 约束 `/sy-tasks` 输出**: C7 落地前,`skills/sy-tasks/SKILL.md` + `tasks-template.md` 加约束 —— **只拆单 task 或完全独立 task**(禁跨 task 代码依赖),否则用户拿到跑不通的 yaml。
- **(B 中) batch 加最小整合**: task 间 ff-merge `task/<id>` → base_branch —— 但这其实就是 C7 核心,等于提前做 C7 MVP。
- **(C 正) 直接上 C7 Phase Coordinator** (P1.3),逐 phase merge。

**附带环境/工具坑(真闭环才暴露,各自独立小修)**:
1. **venv 坏**: `suiyin-flow` 从旧 worktree editable 装 + 缺 `pyyaml` → `batch.py` `import yaml` 炸,开箱即坏。`pip install -e <v4>` from main 修。→ 装机文档/init 应提示 `pip install -e` + pyproject 已声明 pyyaml 但 venv 未同步。
2. **auto-commit 没触发**: autonomous 档跑 `/sy-specify|plan|tasks` 后 artifact **没自动 commit**(`after_*` hook optional + bypassPermissions 下没执行)→ batch 子 worktree 从 base HEAD 看不到 `spec_ref`。→ harness 应在 batch 前确保 spec/plan/tasks 已提交,或 batch 前置检查"`spec_ref` 在 base HEAD 可见"否则 fail-fast。
3. **proxy 不传播**: `session.py` 的 `Popen` 不设 `env=`(继承父进程)。代理网络下必须 `export https_proxy=... ` 再起 batch,否则子 claude 连不上 API 干等(本次撞到:`claude` 是带 proxy 的 alias,subprocess 不认 alias)。→ 文档化;或 session 起前自检 API 连通。
4. **allowlist python 取向**: `claude-settings.json` baseline 缺 `node/npm/npx`,TS 项目卡权限。→ init.sh/文档按栈补,或 P1.6 hooks 取代。
5. **init.sh PROJECT_NAME 用 worktree basename**: 在 worktree 内跑 init,`README.suggested` 名字取成 worktree 目录名(非项目名)。→ 用 `git rev-parse --show-toplevel` basename 或 remote 名。(小 bug)
6. **C2 task PR base 硬指 `main`**: C2 开 task PR 时 base 写死 `main`,无视 task 的 `base_branch`(本次 `claude/login-core`)→ worktree-centric 流里 PR 对错基线(diff 混入 base_branch 相对 main 的提交)。→ PR base 应取 `base_branch`。

#### 🔧 修复清单(下一轮 dogfood 前)—— 准备修

> 修完 P0+P1 再来一轮:`/sy-specify → /sy-plan → /sy-tasks → batch`,这次 `/sy-tasks` 出**独立 task** → batch 跑全 → 验证多 task(独立)闭环 + P0 修复生效。

**P0 快修(独立小 bug,修完下一轮顺滑)**: ✅ 全部完成 (2026-06-09)
- [x] **venv/pyyaml**: README「跑 batch 前」节 —— 从 v4 main checkout `pip install -e .`,勿用 worktree editable
- [x] **auto-commit 缺口**: `batch.py` 加 `precheck_refs_on_base` —— 真跑前校验 spec_ref/plan_ref 在 base_branch HEAD 可见,缺失 fail-fast INVALID_MANIFEST(AC-B8a~e ×5)
- [x] **proxy 不传播**: README 文档化 `export https_proxy` 再跑 batch(alias 对 subprocess 无效)
- [x] **allowlist 缺 node**: `claude-settings.json` 补 node/npm/npx/pnpm/yarn + mkdir/ls/cat 等文件工具
- [x] **init.sh PROJECT_NAME**: 用 `git-common-dir` 父目录名(worktree-safe,实测 worktree 内取主仓名)
- [x] **C2 PR base**: `_open_pr_or_branch` 加 `--base <base_branch>`(test_pr_base.py)

**P1 关键(让多 task 在 C7 之前可跑)**: ✅ 完成 (2026-06-09)
- [x] **约束 `/sy-tasks` 输出**(行动项 A): `skills/sy-tasks/SKILL.md` 输出契约加第 6 条「任务独立性 P1.2.5 硬约束」+ `tasks-template.md` 同步(self-contained / 顺序构建塌缩成 1 task / depends_on 不传递代码可见性)

**P2 大件(架构,留 P1.3)**:
- [ ] **C7 Phase Coordinator**(行动项 C): 逐 phase merge,真正支持依赖链 batch。见 P1.3 §C7。

#### ✅ 第二轮真闭环 (2026-06-10, v5 login-core-r2) — 修复全部生效实证

> 回退 v5 到 sy-* 之前 → 重装 (PR #44 工具链) → 同段 feature 输入重跑全链。

- **P1 约束生效**: `/sy-tasks` 这次输出 **1 个 self-contained task**(上轮 5 个依赖 task),yaml 顶部注释自带塌缩推理(引用 template 教训)+ `base_branch: claude/login-core-r2` 写对且带 rationale —— 约束被模型理解而非机械遵守
- **auto-commit 正常**: spec/plan/tasks 三个独立 commit(上轮缺口未复发)→ batch precheck 顺带通过
- **batch all_success**: 1 attempt / 330s / 14 files +1811 / `npx vitest run` 17 tests 全绿
- **merge 完成**: `task/T-001` ff-merge 回 feature 分支,merge 后全量 verify 仍绿 —— **`/sy-specify → /sy-plan → /sy-tasks → batch → merge` 全链首次真正闭环**(产出 v5 真实 login 凭证核心模块)
- **🆕 发现 #7 — PR-base fix 引出**: push `task/T-001` 成功,但 `gh pr create --base claude/login-core-r2` 失败 → **base 分支不在 remote**(worktree-centric local-first 流的常态)→ 优雅降级 `pr_created=false`(NC-1 兜底正确)。上轮"开出 PR"实为错基线碰巧能开。方向(待拍):
  - (a) C2 开 PR 前先 push base_branch —— 但 base 是否该上 remote 是用户的事,C2 越权
  - (b) **维持现状 + 文档化**(倾向): base 不在 remote = 不开 PR,task 分支留本地,feature 聚合后由人/C6 对 main 开 PR —— PR 本来就该开在 feature→main 一层,task→feature 是本地 merge 语义(C7 的逐 phase merge 就是这个)
  - 决策可留到 C6/C7 spec 时一起定
- **🆕 发现 #8 — batch 对 task worktree 无并发锁(静默竞态,第二轮意外实测)**:
  用户与 AI 各启动一次 batch(16:15:37 vs ~16:16,同一 tasks.yaml),第二个 batch **静默复用**
  第一个创建的 `worktrees/T-001`(worktree.py "存在则复用" 语义)→ 两个 claude session
  同时写同一 worktree ~5 分钟;先完成方 merge + 清理(16:22 删 worktree/分支)把后完成方的
  运行环境**从脚下抽掉**,后者 verify 早已 pass 故仍报 `success`,仅 finalize 元数据损坏
  (`diff_stats: null` / push 失败 `pr_created: false`)——**唯一痕迹,极易漏看**。这次走运
  代码没坏(活已干完,幂等重验),并发写阶段若重叠在编码期会互相踩脏。
  - **修复方向**: C2 起 worktree 前检测"已存在 + 有活跃 session"(`.suiyin/lock` pid 文件或
    git worktree 注册 + 进程探活)→ 拒跑并报清晰错误;batch 层同 manifest 加文件锁
  - **优先级**: P1.3 跟 C7 一起做(C7 调度多 task 时本来就要管 worktree 生命周期);
    短期缓解 = 文档约定"同一 feature 同时只跑一个 batch"
  - **附带验证 ✅**: 已完成代码上重跑同 task = 幂等重验通过(T-007 式),session 未画蛇添足

### P1.3 P2 — 并行加速 + R2

- [ ] **R2: C2 retry-with-feedback** — C2 v0.2 加 `--review-feedback` flag, C5 block 后 C2 拿 findings 作为新 context 重 attempt (C5 §6 Q5-5 + §7 Block Recovery R2)
  - 预估：2-3 天 (C2 spec bump v0.2 + impl + AC test)
- [ ] **C1 Planning Engine** — task 依赖图 + 并行分组（toolchain.md C1，Q1）
- [ ] **C7 Phase Coordinator** — phase 调度 + 逐 phase merge（C7，Q7）
  - **spec 预设 invariant**（2026-05-28 讨论沉淀，开 C7 spec PR 时作为锚点）：
    - C7 = **deterministic state machine**（同 C6 "行为契约"性质 — transition table 纯 Python，零 AI 在 routing path）
    - **路由集中**在 C7：C 组件输出只描述语义状态（`reason` / `recovery_action.kind`），**不**含 `next_action_owner` 等拓扑字段——拓扑会随阶段切换（P1.2 = 人 / P1.3+ = C7 / SaaS 场景 = merge queue），写进组件 schema 会引爆 churn
    - **状态持久化**到 `<repo_root>/.suiyin/phase-state/<safe_pr_ref>.json`（versioned + latest，同 C5/C6 落盘 pattern）；记录 retry_count / parked phases / 队列优先级
    - **harness 边界（先于 C7 落地）**：sy-* slash command / dogfood orchestrator 硬约束 "C 组件 exit ≠ 0 → stop + surface to human"，不许 LLM session 自由续跑；这条规则不依赖 C7，P1.2 阶段就该上
    - **关 Q6-2 cascade**: C7 spec 落地后回 [c6-gate-contract.md §6 Q6-2](components/c6-gate-contract.md) 翻牌 (b) "C7 重排队列" 为 default
  - **来源**: 2026-05-28 session 讨论 — 撞到 LLM 拿到 C6 `held + recovery_action.kind=no_op` 自由研究 merge → 反推"组件 vs 编排"分层 + 路由集中性

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

### P1.6 远期 — Governance 终态：运行时审批前置（hooks）

**为什么**: v4 终极治理目标 = 审批前置到 spec/plan 阶段，运行时零审批。当前 `runtime/claude-settings.json` baseline 的 4 条 deny 是 v0.x 对话式开发的 **reflection trigger 过渡态**——不是防墙（AI 用 `python -c '...'` 嵌套就能绕，settings.json 本身 AI 也能 Edit），等下面这套上线就该退场。

**做什么**: 用 Claude Code `hooks.PreToolUse` 给每个 tool call 挂一个 `agent` hook（小模型跑一行评审 prompt），按"这条命令在当前已批准的 spec/plan 里吗"判断 allow / block。超出 spec 范围 → block，主 Claude 拿 reason 重新规划。审批语义完全前置到 spec/plan，运行时按 spec 自动跑，零人工打断。

**子任务**:
- [ ] 调研 Claude Code hooks 实际语义（PreToolUse 上 `agent` 类型 hook 的 input/output 协议、blocking 效果、`if` filter 写法）
- [ ] 设计审查 prompt（小模型读 current spec/plan + 当前 tool call → verdict）
- [ ] 写到 `runtime/claude-settings.json` baseline 作为 opt-in 配置（默认关，业务项目 `bin/init.sh --strict` 或单独 flag 开）
- [ ] mini-dogfood：v4 自己开一个 spec 跑 C2，配合 hook 验证"超出 spec 的命令被 block"
- [ ] 跑通后讨论：要不要把 4 条 deny 从 baseline 完全移除（让 hooks 取代）

**依赖**: P1.2（C6 impl）+ P1.2.5（tasks.yaml→C2）+ P1.3（C1 + C2 retry-with-feedback）—— 需要 spec→plan→execute 链路完整、机器可解析，hook 评审才有"当前 spec/plan"可读。

**优先级**: 远期（governance 工程化基础设施，不影响 MVP 闭环）。先把 P1.2-P1.5 跑完再启动。

预估：2-3 天（spec + impl + 1 个 mini-dogfood）

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
  - **当前**: C6 spec §3.3 关键设计点注释 "NOT_FF_MERGEABLE 不重跑 C2/C4/C5 — rebase 后代码 tree 不变, verify/review report 仍 valid"（v0.1.1 round-3 加了 conflict-resolution 必须重投的 caveat + P1.3 `pr_head_sha` 加固预案）
  - **触发**: 下次 C 模块 spec（特别是 C8 Deploy Contract — release tag preserves tree）出现"上游 artifact 仍 valid 不重新评估"类逻辑时 promote
  - **建议位置**: workflows.md 加跨契约 invariant 节 / methodology.md 加 "Tree-Preserving Operations" 原则
  - **来源**: C5 self-review of PR #33 round-2 (T-004 mini-dogfood, finding category=reusable_knowledge_not_captured low)
- [ ] **Insight G**: 组件测试用真 git fixture 模式 → `tests/fixtures/git_fixture.py` shared util
  - **当前**: c6_gate/conftest.py `fixture_repo` / `fixture_repo_diverged` (~30 行 × 2) + dogfood/T-005/run.py `setup_baseline_repo` / `setup_diverged_repo` 各写一份 (重复)
  - **触发**: C7 Phase Coordinator / C8 Deploy 组件测试也会要 baseline / diverged repo + bare origin remote
  - **建议位置**: 抽 `tests/fixtures/git_fixture.py` 提供 `make_baseline_repo(tmp_path)` / `make_diverged_repo(tmp_path)`，conftest + dogfood 共用
  - **配对**: 跟 Insight F mock CLI 共组 "cross-platform test infrastructure" 主题，C7/C8 spec 阶段一起统一
  - **来源**: C5 self-review of PR #34 round-3 (session 84fb2bff, finding category=reusable_knowledge_not_captured low)
- [ ] **Insight F**: 跨平台 mock CLI test pattern (NC-5 hard constraint) → `tests/` shared util / `methodology.md` testing patterns 节
  - **当前**: c6_gate/conftest.py mock_gh_on_path 用 Python shebang + chmod 0o755 — macOS / Linux OK，Windows 不识 shebang → AC tests Windows 跑不过
  - **触发**: 下一个需要 mock CLI 的组件（C7 phase coordinator / C8 deploy 等都会要 mock git/gh/CD CLI）
  - **建议位置**: 抽 shared fixture `mock_cli_on_path(name, script_body)` 用 `monkeypatch.setattr(subprocess, 'run', ...)` 拦截 subprocess 调用，跨平台零 fs 依赖
  - **配对**: 跟 c6 §6 Q6-8 引用同一问题，形成 "cross-platform test infrastructure" 主题
  - **来源**: C5 self-review of PR #34 round-1 (T-005 mini-dogfood 阶段, finding category=cross_platform low, session c1298417)
- [ ] **Insight E**: "Contract Response Envelope — Error vs Output disjoint top-level shapes" → `methodology.md` 或 `component-spec-template.md`
  - **当前**: C6 spec §2.3 顶部 "与 Output Schema 互斥" 说明 + §2.2 omit-when-absent 约定（v0.1.1 round-3 引入）
  - **触发**: 下次 contract spec (C7 / C8) 出现 Error/Output 两形态时 promote 为通用 API 设计原则
  - **配对**: 跟 c6 §6 Q6-6（omit-when-absent vs nullable）形成 "response-shape" 主题，避免 spec drift
  - **来源**: C5 self-review of PR #33 round-3 (T-004 mini-dogfood, finding category=reusable_knowledge_not_captured low, session 261e3fa7)

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

**Version**: v0.3.2
**Last Updated**: 2026-05-28
**Status**: Living document — P1.1 P0 MVP ✅ + P1.2 阶段 1/2 ✅。下一步: P1.2 阶段 3 (C6) → P1.2.5 (tasks.yaml adapter，**窄义 MVP 真可用**)。
**Changelog**: v0.3.2 (2026-05-28) +P1.6 hooks-based 运行时 spec 审批（远期 governance 终态）+ baseline `runtime/claude-settings.json` 改为 9 allow + 4 deny（含 python/bash/git/gh 全开 + 4 条 reflection-trigger deny）。
