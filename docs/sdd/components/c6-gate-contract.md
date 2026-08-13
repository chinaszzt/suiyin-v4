# C6 Gate Contract — Component Spec

> 自动化 merge gate。接收 PR + C4 `verify_report.json` + C5 `review_report.json`，按 4 条规则纯逻辑评估 → `merged` / `held`。**v4 P1.2 自闭环 merge 的最后一公里**：C5 出 verdict 后由 C6 决定是否 ff-merge to main，不让人按 merge 按钮。

## 0. Type

- [ ] 自建组件 (imperative logic — 需要写代码)
- [x] 行为契约（declarative contract — 配置 + 编排）

**契约性质**：规则评估纯逻辑（4 条 boolean AND），无 AI、无策略推断、无可调参数。所有"实现"都是把规则评估挂到某种执行容器上（hook / CI / merge queue）。

**实现谱系优先级**：(d) 混合 — 默认 (a) 本地 git pre-push hook 兜底，(c) GitHub Branch Protection 在 SaaS 用户场景兜底。v4 P1.2 阶段仅落地 (a) + 一个 Python CLI（`suiyin-flow gate run`）做规则评估宿主。

**实现栈**: Python 3.11+（同 C2/C4/C5，见 ADR-0002）。CLI 入口 `suiyin-flow gate run <pr_ref>`，复用顶层 unified dispatcher（见 C2 §7 "Unified CLI"）。

## 1. Purpose

接收一个 PR + 关联 verify_report.json + review_report.json，按 **4 条 gate 规则全 AND** 判定 → 满足则 `ff-merge to main` + 删 branch；任何一条 false → `hold` + 触发对应 recovery（Block Recovery R1 / rebase 子流程 / 等人解锁）。**核心特性**: 纯规则评估、可重复、零 AI 不确定性、main 历史保 fast-forward 线性。

## 2. Public API

### 2.1 Input Schema

```yaml
type: object
required: [pr_ref, verify_report_path, review_report_path, repo_root]
properties:
  pr_ref:
    type: string
    description: PR URL（gh 可达时）或本地分支名（无 remote 时降级）
  verify_report_path:
    type: string
    description: C4 verify_report.json 路径（相对 repo_root 或绝对）
  review_report_path:
    type: string
    description: C5 review_report.json 路径（相对 repo_root 或绝对）
  repo_root:
    type: string
    description: 业务项目根目录（绝对路径）
  dry_run:
    type: boolean
    default: false
    description: true 时仅评估规则、输出 gate_report，不执行 merge / label / comment 副作用
```

### 2.2 Output Schema

**Schema 形态约定**：
- 可选字段（held 时才出现 / merged 时才出现等）一律 **omit-when-absent**（不 emit 该 key），**不**使用 `null` 占位。
- 字段定义里的 "absent when ..." 表达"key 不出现"语义。consumer 用 `"reason" in payload` 判存在，不用 `payload["reason"] is None`。
- 这个约定避免 `nullable / null / 缺字段` 三义混淆（v0.1.0 → v0.1.1 修正，见 §6 Q6-7）。

```yaml
type: object
required: [gate_result, rules, timestamp]
properties:
  gate_result:
    type: string
    enum: [merged, held]
    description: 终判
  rules:
    type: object
    description: 4 条规则的 pass/fail breakdown（debug 必备）
    required: [verify_all_pass, review_approved, ff_mergeable, not_human_blocked]
    properties:
      verify_all_pass:    { type: boolean }
      review_approved:    { type: boolean }
      ff_mergeable:       { type: boolean }
      not_human_blocked:  { type: boolean }
  reason:
    type: string
    enum: [VERIFY_NOT_PASS, REVIEW_NOT_APPROVE, NOT_FF_MERGEABLE, HUMAN_BLOCKED]
    description: held 时必填，标 §3.1 I8 precedence 选中的规则；**merged 时此字段 absent**（omit-when-absent）
  recovery_action:
    type: object
    required: [kind]
    description: held 时必填触发的 side effect 记录；**merged 时此字段 absent**（omit-when-absent）
    properties:
      kind:
        type: string
        enum: [r1_label_and_comment, no_op]
        description: r1_label_and_comment = REVIEW_NOT_APPROVE 触发 R1; no_op = 其他 held 原因 (VERIFY_NOT_PASS / NOT_FF_MERGEABLE / HUMAN_BLOCKED)
      label_added:    { type: boolean, description: kind=r1_label_and_comment 时必填；kind=no_op 时 absent }
      comment_posted: { type: boolean, description: 同上 }
      comment_url:    { type: string, description: comment_posted=true 时必填；其他情况 absent }
      partial_failure: { type: string, description: I9 atomicity — label/comment 任一失败时填错误码 (GH_ERROR / PERMISSION_DENIED 等)；全成功 absent }
  merged_sha:
    type: string
    description: gate_result=merged + dry_run=false 时必填 main 的新 HEAD sha；dry_run=true 时 absent；held 时 absent
  timestamp:
    type: string
    description: ISO8601 UTC（每次调用都 emit；不参与 §3.1 I6 determinism 等价判定）
```

### 2.3 Error Schema

**与 Output Schema 互斥**：Error 响应是**独立 top-level shape**（不含 `gate_result` / `rules` / `reason`），不要把 Error 嵌进 §2.2 schema。consumer 优先按 `"code" in payload` 区分 — 有 `code` 字段即 Error 响应、无则 Output 响应。CLI exit code 也对应：merged/held=0/1，Error=2（见 §7）。

```yaml
type: object
required: [code, message]
properties:
  code:
    type: string
    enum: [MISSING_INPUT, INVALID_REPORT, GIT_ERROR, GH_ERROR, PERMISSION_DENIED]
  message: { type: string }
  details:
    type: object
    description: 错误上下文（哪个文件 / 哪个命令 / stderr）
  retryable: { type: boolean }
```

**Error 与 held 的区别**：`held` 是契约的正常结果（规则评估成功但未全 pass）；`Error` 是契约自身无法评估（缺 input / git 失效）。`held` 不算异常，`Error` 才算。

## 3. Behavior Contract

### 3.1 Invariants

跨调用必须成立的事实：

- **I1 Gate Rule（核心）**: gate_result == `merged` ⟺ `verify_report.overall_verdict == pass && review_report.verdict == approve && ff_mergeable(pr_branch, main) && !pr.has_label("human:block")`。**4 条全 AND，缺一不可**。字段名严格按 C4 §2.2 (`overall_verdict`) 和 C5 §2.2 (`verdict`) — 不是 `overall` / `result` 等同义词。
- **I2 Hold Default**: 任何一条规则 false → 必 `held`，**绝不 force-merge / 绕过任何一条**。
- **I3 Reasoned Hold**: `held` 时 output 必含 `reason`（按 I8 precedence 选中）+ `rules` 4 字段完整 breakdown，便于 debug。
- **I4 Hold ≠ Permanent Block**: `held` 是当时状态评估，不持久化；条件改善后（rebase / 解锁 / 重 verify / 重 review）下次 gate run 可重新评估。
- **I5 ff-only Main History**: merge 操作 = `git fetch origin && git push origin <pr_sha>:main`（ff-only push，远端拒非 ff 会失败）+ `git update-ref refs/heads/main <pr_sha>`（本地 ref 同步）。**main 永远线性**，禁止 merge-commit / squash 在此契约外触发（squash if any 由上游 PR review 时完成，不归 C6 管）。**`gh pr merge` 子命令不能用** — 它的 `--merge / --squash / --rebase` 均不产 ff-only main，没有 `--ff-only` 等价 flag。**`git checkout main && git merge --ff-only` 形式也不能用** — NC-4 worktree 模式下子 worktree 不能 checkout 主 worktree 占着的 main（v0.1.3 patch, PR #35 dogfood）。
- **I6 Determinism**: 同样 input（同 pr_ref + 同 verify_report + 同 review_report + 同 main HEAD）→ 同样的 `gate_result + reason + rules`（即 §2.2 必填核心字段）。`timestamp` 例外（每次新生成），`merged_sha` 例外（merge 时 git 决定，幂等性靠 ff-only 保证而非 deterministic value）。
- **I7 Block Recovery R1（D-autonomous 硬约束）**: 当 `reason == REVIEW_NOT_APPROVE` 时，必尝试 R1 副作用（加 `human:block` 标签 + comment review findings），由 I9 atomicity 定义"必尝试"的精确边界；**不允许静默 hold（即不允许 `reason=REVIEW_NOT_APPROVE` 同时 `recovery_action.kind != r1_label_and_comment`）**。这是 v4 D-autonomous profile "执行阶段 AI 自闭环、异常时人才出来" 的兜底（详见 `workflows.md` Block Recovery 节）。
- **I8 Reason Precedence**: 多条规则同时 false 时，`reason` 按**固定优先级**单选：
  1. `HUMAN_BLOCKED`（最高 — 人已介入，C6 不该 override 任何东西）
  2. `VERIFY_NOT_PASS`（其次 — 不通过 verify 的代码不该进 review 流转）
  3. `REVIEW_NOT_APPROVE`（再次 — review 是 verify 之后的人/AI 判断）
  4. `NOT_FF_MERGEABLE`（最低 — 只是机械的合并可达性，最便宜复检）

  **示例**：`verify=fail` + 已有 `human:block` → reason = `HUMAN_BLOCKED`，no_op（不重复加 label）。`rules` 字段仍记录 4 个 boolean 实情。
- **I9 R1 Side Effect Atomicity**: `reason == REVIEW_NOT_APPROVE` 时执行 label add → comment 顺序：
  - label add 成功 → comment 成功：`recovery_action = {kind: r1_label_and_comment, label_added: true, comment_posted: true, comment_url: <url>}`
  - label add 成功 → comment 失败：`recovery_action = {kind: r1_label_and_comment, label_added: true, comment_posted: false, partial_failure: <code>}` + 整体 gate_result 仍 `held`（不是 Error）。**视为 R1 已部分触发**，满足 I7 "必尝试"。
  - label add 失败：响应整体降级为 Error `GH_ERROR` / `PERMISSION_DENIED`（不 emit Output 形态）。R1 完全没触发，I7 兜底失效 → 由 caller 看到 Error 后人工介入。
  - label add idempotent — 已存在标签时视作成功（不 emit error），但此场景应被 I8 的 `HUMAN_BLOCKED` 优先级捕获、不会真走到 R1 路径。

### 3.2 Side Effects

- **Merge to main**（gate_result == merged + dry_run == false）: **必须用单步 ff-push 形式** —— `git fetch origin main` → `git push origin <pr_sha>:main`（ff-only push，远端拒非 ff 会失败）→ `git update-ref refs/heads/main <pr_sha>`（本地 ref 同步前进）。**`git checkout main && git merge --ff-only` 形式禁用** —— v0.1.2 把它列为 "或等价" 选项是错的：NC-4 worktree 模式下子 worktree 不能 checkout 已被父 worktree 占着的 main（fatal: 'main' is already used by worktree at ...）→ 自动 merge 整条路径 fail（PR #35 dogfood Bug 1 实证）。v0.1.3 patch 收敛为单一路径。**不用 `gh pr merge`**（见 I5）。merge 后可选 `gh pr close <ref> --delete-branch` 收尾（也是 ff-only 后状态）。
- **Label add**（reason == REVIEW_NOT_APPROVE + dry_run == false）: `gh pr edit <ref> --add-label "human:block"`。已存在标签视作成功（I9 idempotent）。
- **Comment finding**（reason == REVIEW_NOT_APPROVE + dry_run == false + label 已成功）: `gh pr comment <ref> --body "<formatted findings>"` — inline C5 findings 用 §2.2 finding schema 字段（**`severity / category / location / suggested_fix` 四字段**，**严禁** 引用不存在的 `summary` 字段，见 C5 §2.2 finding required 列表）。
- **Gate report 落盘**: `<repo_root>/.suiyin/gates/<safe_pr_ref>-<ts>.json`（versioned 时间戳化）+ `<repo_root>/.suiyin/gates/latest-<safe_pr_ref>.json`（最新副本覆盖式写入，便于 dogfood / debug 直接读最新；跟 C5 review_report `latest.json` 同模式，跨平台不用 symlink）。**落盘是 audit trail 而非 side-effect**（详 dry_run 边界节）。
- `safe_pr_ref` = 把 `pr_ref` 中的 `/` `:` `?` 等文件系统不友好字符替换成 `-`（提取 `https://github.com/.../pull/33` 末段 → `pull-33` / 提取分支名 `claude/c6-spec` → `claude-c6-spec` / 跨平台兼容 NC-5）。

#### dry_run 副作用边界（v0.1.2 新增）

- **dry_run=true 跳过**: 真 merge (`git push origin <sha>:main`)、`gh pr edit --add-label`、`gh pr comment` — 即任何**对外可观察**的副作用（main 历史、PR 状态、PR comments）。
- **dry_run=true 仍执行**: gate_report.json 落盘（versioned + latest 副本）— 这是本地 audit trail，纯 fs 写入，不影响 PR / main / 外部观察者状态。**dogfood (T-005) 依赖 dry_run + 落盘组合**读取评估结果。
- **dry_run 下 Output 字段约定**: merged_sha / label_added / comment_posted / comment_url 一律 absent（per §2.2 omit-when-absent；gate_result=merged 时也 absent merged_sha 因为没真 merge）。`gate_result=merged` 仍 emit，表"假设真 run 会 merge"的预测。

> **修正历史**: v0.1.1 把"落盘"列在 dry_run 跳过列表内，跟 AC-10 "每次非 Error 调用必落盘（含 dry_run 标志）" 直接矛盾。v0.1.2 (#34 C5 round-1 finding cascade) 拍板 audit trail 优先 — 落盘永远执行（除 Error abort 前未产 Output 的情形），dry_run 仅跳对外可观察副作用。

不触碰的：
- 不调 C4 重 verify
- 不调 C5 重 review
- 不调 C2 重写代码
- 不修改 spec / plan / constitution
- 不动 PR 描述（只加 label + 加 comment）

### 3.3 Failure Modes

分两类，**消费时只读对应字段** — `reason` ⊂ Output 形态、`code` ⊂ Error 形态，不复用：

**(a) Held cases**（rules 评估完成但未全 pass）— consumer 读 `output.reason`：

| `reason` 取值 | 触发条件 | recovery_action.kind | 处理动作 |
|---|---|---|---|
| `HUMAN_BLOCKED` | PR 已有 `human:block` label（按 I8 precedence 优先级最高） | `no_op` | hold + no-op；不重复加 label / 不再 comment；等人移标签后下次 gate run 重新评估 |
| `VERIFY_NOT_PASS` | `verify_report.overall_verdict != pass` | `no_op` | hold + 不重跑 C4；caller（C7 / 人）决定是 fix code 还是 fix verify_report；**不加 human:block 标签**（不是 reviewer 的判断） |
| `REVIEW_NOT_APPROVE` | `review_report.verdict == block` | `r1_label_and_comment` | hold + **Block Recovery R1**（I9 atomicity 决定 label/comment 是否全部成功）；不自动 retry C2（R2 在 P1.3 加） |
| `NOT_FF_MERGEABLE` | base (main) 已 advance，PR branch 不是 ff 可达 | `no_op` | hold + 不重跑 C2/C4/C5（在 rebase 干净的前提下；详见下方"关键设计点"）；触发 rebase 子流程（P1.2 = 让人 rebase；C7 落地后 = 重排队列，见 §6 Q6-2） |

**(b) Error cases**（C6 自身无法评估）— consumer 读 `error.code`：

| `code` 取值 | 触发条件 | retryable | 处理动作 |
|---|---|---|---|
| `MISSING_INPUT` | verify_report_path / review_report_path / repo_root 不存在 / 不可读 | false | abort，输出 Error；不触碰 PR |
| `INVALID_REPORT` | report JSON parse 失败 / schema 不符 / 必填字段缺失（如 `verify_report.overall_verdict` / `review_report.verdict`） | false | abort，输出 Error |
| `GIT_ERROR` | `git fetch / merge --ff-only / push` 失败（非 NOT_FF_MERGEABLE — 那是 held；这是 git binary / 仓库异常） | true | 外层可重试 |
| `GH_ERROR` | `gh` CLI 失败（auth 失效 / network / comment body > 65535 char 等） | true | 外层可重试；R1 partial failure 时也走此 code 嵌进 `recovery_action.partial_failure`（I9）而非顶层 Error |
| `PERMISSION_DENIED` | merge to main 被远程拒（branch protection 不允 ff push）/ gh CLI 权限不足 | false | 提示用户检查 GitHub branch protection 配置 |

**关键设计点（rebase 干净的前提）**：`NOT_FF_MERGEABLE` 不触发重跑 C2/C4/C5 — **仅当 rebase 是干净 fast-forward 友好的简单 base 推进**（即 PR branch 仍指向同一个 tree，只是父 commit 换了）时 verify_report / review_report 仍 valid。

**例外**：若 rebase 涉及 **conflict resolution**（手动编辑 hunk），合并产物 tree ≠ 原 PR head tree → **必须重跑 C4 + C5**。C6 自身无法判断 conflict 是否有 resolution（rebase 是 caller / 人做的）。**caller 的责任**：rebase 完成后若 commit_sha 变化（不是简单 ff），必须重投 C2/C4/C5 流水线再调 C6，**不能直接复用旧 verify/review**。**未来加固**（P1.3+）：verify_report / review_report 加 `pr_head_sha` 字段，C6 在 NOT_FF_MERGEABLE 后的下一次评估时比对，若发现 `pr_head_sha != current pr_branch HEAD` → 输出 `INVALID_REPORT`，强制 caller 重跑。当前 P1.2 暂用流程约定（caller 自觉），由 mini-dogfood 验证可行性。

## 4. AI Prompt Template

**N/A — 此模块是契约，规则评估纯 boolean 逻辑（4 条 AND），不跑 AI prompt。**

副作用执行（gh CLI / git CLI / 落盘）也不涉及 AI。任何"自然语言生成"的部分（如 PR comment 里 finding 渲染）都是模板化字符串拼接，不调 Claude session。

## 5. Acceptance Criteria

可证伪的 AC（每条对应一个 test）：

- **AC-1 4 条全 pass + dry_run=false → merged**：给定 `verify.overall_verdict=pass, review.verdict=approve, ff_mergeable=true, !has_label("human:block"), dry_run=false` → `gate_result=merged`，main HEAD 前进，`merged_sha` 字段必填。
- **AC-1b 4 条全 pass + dry_run=true → merged 预测**：同 AC-1 输入但 `dry_run=true` → `gate_result=merged`，main 不动，`merged_sha` 字段 absent（按 §2.2 schema "merged + dry_run=true 时 absent"）。验证 dry_run 不触发任何副作用。
- **AC-2 verify 失败 → held**：`verify.overall_verdict=fail` 其他全 pass → `gate_result=held, reason=VERIFY_NOT_PASS, recovery_action.kind=no_op`（不加 label / 不 comment / 不 push）；main 不动。
- **AC-3 review block → held + R1（成功）**：`review.verdict=block` 其他全 pass，gh CLI 调用全成功 → `gate_result=held, reason=REVIEW_NOT_APPROVE, recovery_action={kind: r1_label_and_comment, label_added: true, comment_posted: true, comment_url: <url>}`。comment body 严格按 C5 finding **四字段** 渲染（`severity / category / location / suggested_fix`，**不能引用 `summary` —— C5 contract 无此字段**）。
- **AC-3b R1 partial failure（I9）**：同 AC-3 但 `gh pr comment` 失败 → 仍 `gate_result=held, reason=REVIEW_NOT_APPROVE, recovery_action={kind: r1_label_and_comment, label_added: true, comment_posted: false, partial_failure: GH_ERROR}`。验证 I7 "必尝试 R1" 兜底（label 成功即视作已触发，不降级成 Error）。
- **AC-3c R1 label failure（I9）**：`gh pr edit --add-label` 失败 → 响应整体降级 Error `code=GH_ERROR` 或 `PERMISSION_DENIED`，**不再 emit Output 形态**。
- **AC-4 非 ff → held + 不重跑**：`ff_mergeable=false` 其他全 pass → `gate_result=held, reason=NOT_FF_MERGEABLE, recovery_action.kind=no_op`；不调 C4 / 不调 C5；main 不动。
- **AC-5 reason precedence (I8) — HUMAN_BLOCKED 优先**：PR 已有 `human:block` 标签 + verify=fail 同时成立 → `gate_result=held, reason=HUMAN_BLOCKED, recovery_action.kind=no_op`（**不**是 `VERIFY_NOT_PASS`）；`rules` 仍记录 `verify_all_pass=false, not_human_blocked=false` 两条实情；不重复加 label / 不重复 comment。
- **AC-6 MISSING_INPUT → Error**：verify_report_path 不存在 → 响应 Error 形态 `{code: MISSING_INPUT, ...}`，**不含** `gate_result / rules / reason` 字段；不动 PR / 不动 main。
- **AC-6b INVALID_REPORT 字段缺失**：verify_report.json 解析成功但缺 `overall_verdict` 字段（或 review_report 缺 `verdict`） → Error `code=INVALID_REPORT`，**不**被静默当成 fail / not-approve 走 held 路径。
- **AC-7 Determinism（I6 narrow）**：同一 input + dry_run=true 跑 N 次（N ≥ 3） → N 次 output 的 `gate_result + reason + rules` 完全一致（`timestamp` / `merged_sha` 不参与等价比较）。
- **AC-8 dry_run absent fields**：dry_run=true 时 review_approved=false → 输出 `reason=REVIEW_NOT_APPROVE, recovery_action={kind: r1_label_and_comment}`，**`label_added / comment_posted / comment_url` 字段全 absent**（不是 `null`，不是 `false`）；按 §2.2 schema 的 omit-when-absent 约定。
- **AC-9 ff-only enforce**：merge 路径必使用 `git merge --ff-only` 或 `git push origin <sha>:main` ff-only 语义；**绝不允许调 `gh pr merge --merge`**（会产 merge commit）。若 ff 失败（race condition：评估时 ff_mergeable=true 但 merge 时 base 移动）→ 输出 Error `code=GIT_ERROR, retryable=true`，**不 fallback** 到 merge-commit / squash。
- **AC-10 Gate report 落盘 + pr_ref 转义**：每次非 Error 调用必落盘 `<repo_root>/.suiyin/gates/<safe_pr_ref>-<ts>.json`，含完整 Output JSON（dry_run 标志亦在内）。`safe_pr_ref` 必经 §3.2 转义规则（`/` `:` `?` 等 → `-`）；给定 pr_ref=`https://github.com/owner/repo/pull/33` → 文件名包含 `pull-33`、不创建嵌套目录树。Error 形态调用不落盘（abort 前未产 Output）。

## 6. Open Questions

- **Q6**（从 `toolchain.md` C6 节继承）: Gate 失败升级通知渠道（取决于实现选项）。**P1.2 决议（本 PR 关闭 Q6）**: 仅落地 PR comment + `human:block` 标签作为通知通道；邮件 / IM webhook 留 P3+。**`toolchain.md` Q-table 同步更新**（cascade by ADR-0001 governance 要求，本 PR 一起改）。
- **Q6-6 (新)**: Schema 形态 — 可选字段是 `null` 占位还是 omit-when-absent？P1.2 阶段已拍板 omit（§2.2 顶部约定），但仍待 P1.3 跨 spec 统一（C4 / C5 现有 schema 是否一致？需要 sweep）。
- **Q6-7 (新)**: gate 触发时机 vs git push 关系 — P1.2 决议是 standalone CLI（不挂 pre-push 钩子）。Q6-5 (a) 选项保留，但显式排除 (b) pre-push（exit code 1 会 abort branch push，破坏 PR 创建流程，见 §7）。
- **Q6-8 (新, PR #34 C5 finding #4)**: 跨平台 mock gh CLI 测试模式 — tests/c6_gate/conftest.py 的 `mock_gh_on_path` fixture 用 Python shebang + chmod 0o755 写到 PATH，**Windows 不识别 shebang + chmod 无效** → c6_gate AC tests 在 Windows 上跑不过。候选修法：(a) 加 `gh.bat` Windows shim 调 Python 脚本；(b) 用 `monkeypatch.setattr(subprocess, "run", ...)` patch subprocess 不依赖 fs；(c) `pytest.mark.skipif(sys.platform=="win32")` 跳过（违 NC-5）。**P1.2 当前**: 跑通 macOS / Linux，Windows gap 留 P1.3 (b) 方案兜底（更通用 + 无 fs 副作用）。同 sink Insight F → todo.md（C5 mini-dogfood T-005 sinks 节）。
- **Q6-2**: `NOT_FF_MERGEABLE` 时 rebase 由谁触发？候选：
  - (a) C6 自动 rebase 后重新评估（contract 内嵌）— 复杂度高、有 merge conflict 风险
  - (b) hold + 等 C7 Phase Coordinator 重排队列（P1.3 加 C7 后）
  - (c) hold + 让人 rebase（P1.2 阶段最简兜底）
  - **P1.3 决议（C7 spec v0.1.0 落地，本 PR 翻牌 Q6-2 → (b) default）**: coordinator 在场时 default = (b)——"重排队列"的确定性定义见 [C7 spec §3.3 整合子流程](c7-phase-coordinator.md)（rebase → 重跑 verify → ff-merge；conflict → park 等人）。注意架构落点：C7 v0.1.0 的队列管 **task→feature 层**（该层无 PR，C6 不在 loop，见 C7 I6 / 发现 #7 决议）；**feature→main 层**（C6 直接消费场景）在 C7 接管收口前（C7 Q7-3）维持 (c) 人工 rebase 兜底。cascade: workflows.md Q-table 同步。
- **Q6-3**: `human:block` 标签被人移除后，是否自动 re-run gate？候选：
  - (a) GitHub webhook 触发（重型）
  - (b) 下一次 push 触发（依赖 push event 钩子）
  - (c) 手动 CLI `suiyin-flow gate run <pr>` 重跑（最简）
  - **当前倾向**: P1.2 = (c)；自动触发留 P3+ 决定。
- **Q6-4**: 多次 hold（同一 PR 不同 reason 反复）时 PR comment 策略？候选：
  - (a) thread to single root comment + reply 累加
  - (b) 每次 hold 新 comment（时间序列，简单不丢历史）
  - **当前倾向**: (b) 简单且 audit trail 清晰。
- **Q6-5**: gate 评估时机？候选：
  - (a) C5 review 完成后由 caller（C7 / 人）显式调
  - (b) git pre-push hook 自动调
  - (c) GitHub Actions on PR review event 自动调
  - **当前倾向**: P1.2 = (a) 显式调（先把闭环跑通），(b)/(c) 等 P1.3 C7 / Actions 集成后加。

## 7. Implementation Notes

### 实现谱系（toolchain.md C6 节复述 + v4 P1.2 选项）

| 选项 | 性质 | v4 阶段 |
|---|---|---|
| (a) **standalone Python CLI**（`suiyin-flow gate run`，显式调用） | 本地零 SaaS | **P1.2 默认** |
| (a') git pre-push hook 包装 (a) | 自动触发 | **不选**（见下方"为什么不挂 pre-push"） |
| (b) 通用 CI（GitLab/CircleCI/Jenkins）| 集中评估 | 留 |
| (c) GitHub Branch Protection + Merge Queue | SaaS 集成 | 留 |
| (d) 混合（本地 hook 反馈 + CI 权威） | 双层兜底 | 长期目标 |

**P1.2 落地形态**（standalone CLI，**不**挂 pre-push）：

```bash
# C5 review 完成后由 caller（C7 phase coordinator 或 人 / dogfood 脚本）显式调
suiyin-flow gate run \
  --pr <pr-url-or-branch> \
  --verify-report .suiyin/verify/<safe_pr>.json \
  --review-report .suiyin/reviews/<safe_pr>.json \
  [--dry-run]
```

CLI 内部跑规则评估 + 副作用执行，输出 gate_report.json + exit code（**0 = merged**, **1 = held**, **2 = Error**）。

**为什么不挂 pre-push hook（Q6-7 决议）**：pre-push 钩子 exit code 非 0 时 git 会 abort push。若 gate 在 PR 分支首次 push 时跑 → held (exit 1) → branch 永远推不到 origin → 没法开 PR → R1 也没目标 PR 加 label。**gate 评估的对象是已存在的 PR**（含 verify + review report），所以应该在 PR 已存在、verify+review 已完成之后**显式调用**，不依赖 git push 时机。CI 触发（选项 b/c）等 P1.3 引入 GitHub Actions 后再谈。

### pr_ref 转义（§3.2 落盘文件名规则）

input `pr_ref` 形态：
- PR URL: `https://github.com/owner/repo/pull/33`
- 本地分支名: `claude/c6-gate-contract-spec`
- PR 编号字符串: `33` / `#33`

转 `safe_pr_ref` 规则（实现于 `contract.py` 或 `report.py`）：

```python
import re
def safe_pr_ref(pr_ref: str) -> str:
    # https://github.com/.../pull/33 → 提 pull-33
    m = re.search(r'/pull/(\d+)', pr_ref)
    if m: return f'pull-{m.group(1)}'
    # branch name claude/c6-spec → claude-c6-spec
    return re.sub(r'[/\\:?"<>|\s]', '-', pr_ref.lstrip('#'))
```

落盘路径必经此规则：`<repo_root>/.suiyin/gates/<safe_pr_ref>-<iso8601_ts>.json`。跨平台 NC-5 安全（Windows 文件名不允许 `:` `<` `>` `|` `?` `"` `\` `/`）。

### CLI 入口 / Unified CLI

C6 通过顶层 unified dispatcher（同 C2/C4/C5，见 C2 §7 "Unified CLI"）注册 `gate` subcommand：

```python
# src/suiyin_flow/cli.py
def main(argv):
    cmd = argv[0]
    if cmd == "verify": return c4_verify.cli.main(argv)
    if cmd == "task":   return c2_executor.cli.main(argv)
    if cmd == "review": return c5_reviewer.cli.main(argv)
    if cmd == "gate":   return c6_gate.cli.main(argv)   # C6 入口
    ...
```

### 模块拆分建议

```
suiyin_flow/
  c6_gate/
    __init__.py
    cli.py            # `suiyin-flow gate run`
    contract.py       # §2 schema (Pydantic)
    rules.py          # §3.1 4 条 invariant 评估（纯函数）
    ff_check.py       # ff_mergeable 检测（git CLI 包装）
    actions.py        # merge / label / comment 副作用执行
    report.py         # gate_report.json 落盘
```

### 跨平台兼容性（NC-5）

规则同 C5/C2 跨平台节（`pathlib.Path` / `subprocess.run(shell=False)` / `gh` + `git` CLI 走 `shutil.which` 检测 / `encoding='utf-8'` 等）。不重复。

### 跟其他 C 模块协作

- **消费 C4 `verify_report.json`**：读 **`overall_verdict`** 字段（**严格按 C4 §2.2 schema 字段名 — 不是 `overall`**）判 verify_all_pass。`overall_verdict==pass` 才视作通过；`fail` / `warn_only` / 其他值均视作未通过（保守，未来若 C4 引入 `warn_only` 不阻断的语义可在此放宽，留 Q）。
- **消费 C5 `review_report.json`**：读 `verdict` 字段判 review_approved；当 verdict=block 时读 `findings` 数组（每条按 C5 §2.2 finding 四字段：`severity / category / location / suggested_fix`）渲染 PR comment（R1）。
- **被 C7 Phase Coordinator 调用（P1.3+）**：C7 在 phase 内每个 task 的 C5 完成后调 C6；C6 输出 `held + reason=NOT_FF_MERGEABLE` 时 C7 决定 rebase / 重排 / 升级。
- **跟 C8 Deploy Contract 间接关联**：C6 merge 后 main 进入"可发布状态"，C8 在 main 上挑 release 点。
- **不调用 C11**：C6 不查重；查重在 C5 内嵌。

### 跟 constitution NC-1..NC-5 对照

- **NC-1**（零 SaaS）：C6 本身用本地 git CLI + 本地 gh CLI（gh CLI 是 SaaS 客户端，但远端可换 GitLab / Gitea，CLI 抽象在 actions.py 后）✅
- **NC-2**（spec-kit Layer 1 backbone）：C6 不写 spec/plan，只消费 C5 review_report ✅
- **NC-3**（业务项目独立性）：gate_report 落盘 `<repo_root>/.suiyin/gates/`，不在 v4 仓 ✅
- **NC-4**（worktree 隔离即安全边界）：C6 不 spawn worktree，但 merge 操作只 ff-only，不会污染未提交 worktree ✅
- **NC-5**（跨平台支持）：见跨平台节 ✅
- **PC-1**（最简实现优先）：P1.2 仅 (a) hook + Python CLI，不引入 GitHub Actions / Merge Queue ✅
- **PC-2**（组件 vs 契约明确分离）：C6 明确标"行为契约"，无 imperative 推断逻辑（4 条 AND boolean） ✅

### Block Recovery R1 协作约定

C5 spec §7 已经定义了 Block Recovery 三阶段（R1/R2/R3）。C6 在 P1.2 阶段**只实现 R1**：

| C5 verdict | C6 触发 |
|---|---|
| `approve` | 评估其他 3 条规则；全 pass → merge |
| `block` | held + `human:block` 标签 + PR comment 渲染 findings |

R2（C2 retry-with-feedback）和 R3（Codex 仲裁）在 P1.3 / P3+ 阶段才会让 C6 加分支处理。当前 spec 不写 R2/R3 钩子，避免过度设计。

### v4 自身 dogfood

- **T-004（本 spec PR）**: C5 self-review C6 spec — 自举验证 spec 结构与 **C5 spec v0.1.1** contract 一致（注：v0.1.1 是 C5 contract 版本，本 C6 spec 自身版本是 v0.1.1-draft，见 footer）。
- **P1.2 mini-dogfood T-005（impl PR 阶段）**: 用 C6 对已 merged PR #30（C5 impl）做 mock pre-merge gate 评估 — 重跑 verify + review 落盘 fixture，再喂给 C6 验证 4 条规则评估正确。验证点：
  - 4 条全 pass 时 gate_result=merged（dry_run，merged_sha absent）
  - 人为篡改 verify_report 让 **`overall_verdict=fail`** → gate_result=held, reason=VERIFY_NOT_PASS
  - 人为篡改 review_report 让 verdict=block → gate_result=held, reason=REVIEW_NOT_APPROVE, comment 渲染按 finding 四字段（**不引用 summary**）
  - 模拟 base 前进 → ff_mergeable=false → reason=NOT_FF_MERGEABLE
  - I8 precedence 验证：同时设 verify=fail + 加 human:block 标签 → reason=HUMAN_BLOCKED（不是 VERIFY_NOT_PASS）
  - pr_ref 转义验证：传 `https://github.com/.../pull/30` → 落盘文件名含 `pull-30`、目录扁平
- **后续 dogfood**: P1.2.5 tasks.yaml → C2 adapter 跑通后，跑一次"真闭环" — `/sy-tasks` → 生成 tasks.yaml → batch 跑 → C2 → C4 → C5 → C6 全自动到 merge。

---

**Version**: v0.2.0-draft
**Last Updated**: 2026-08-13
**Status**: draft（v0.2.0 = M3 件 4 先验票再评门；v0.1.4 = C7 spec cascade 关 Q6-2；v0.1.3 = PR #35 dogfood 暴露 worktree+NC-4 不兼容后收敛单一 merge 路径）

### Changelog

- **v0.2.0** (2026-08-13, M3 件 4 报告新鲜度绑定): **MINOR — 先验票再评门**。rules 评估**之前**新增机械验票步：取被合 ref 当前 tree sha（`treesha.resolve_tree_sha`），verify_report / review_report 的 `target_tree_sha` 任一缺失、或与当前 tree sha 不一致、或被合 ref 本身解析不了 → 新 error code `STALE_REPORT`（exit 2，报错含 verify/review/current 三个 sha，缺失显示 "missing"），**不进入 rules 评估**——「旧 tree 的票给新 tree 过门」这条路焊死。CONTRACT_VERSION → v0.2.0。

- **v0.1.4** (2026-06-10, C7 spec v0.1.0 cascade): §6 Q6-2 翻牌 (b) "C7 重排队列" 为 default（todo.md P1.3 锚点既定动作）——队列语义由 C7 spec §3.3 整合子流程确定性定义；标注架构落点（C7 v0.1.0 队列在 task→feature 层，feature→main 层 C7 接管收口前维持 (c) 人工兜底）。**PATCH bump** per ADR-0001 SemVer（仅 Open Question 决议，C6 自身 invariant / schema / AC 零变化——held+no_op 输出不变，requeue 是 caller 行为）。
- **v0.1.3** (2026-05-27, P1.2.5 PR #35 dogfood Bug 1 fix): §3.2 Merge to main 收敛为**单一路径** `git push <sha>:main + git update-ref refs/heads/main` — 删 "或等价" 的 `git checkout main && git merge --ff-only` 选项。原因：NC-4 worktree 模式下子 worktree 不能 checkout 父 worktree 占着的 main，自动 merge 整条路径 fail（v4 自身所有 PR 都受阻）。I5 invariant 同步措辞。impl actions.py ff_merge_to_main 跟随重写为 refs-direct（zero checkout）。**PATCH bump** per ADR-0001 SemVer（措辞 + 路径收敛，invariant 含义不变 — 仍是 ff-only main history）。Bug 2 (gh 抖动重试) 是 impl-side 工程化加固，无 spec 表达需求，不入 changelog。
- **v0.1.2** (2026-05-25, PR #34 cascade): impl 期间 C5 self-review 暴露 §3.2 vs AC-10 内部矛盾（dry_run 是否落盘）+ latest 副本未文档化。**拍板 audit trail 优先** — 落盘永远执行（dry_run 也落），仅对外可观察副作用 (merge/label/comment) 跳过；新增 "dry_run 副作用边界" 节明确边界 + latest 副本文档化。AC-10 措辞不变（本来就对的，§3.2 跟上）。**PATCH bump** per ADR-0001 SemVer (措辞修正 + clarify，无 invariant 变化)。
- **v0.1.1** (2026-05-25): C5 self-review round-3 max-effort recall 反馈，15 项修订：
  - §2.2 schema: 引入 omit-when-absent 约定（去 `nullable: true`）；删 `recovery_action.kind.rebase_required` 死值；加 `partial_failure` 字段；明确 `gate_result` / `code` enum 加 `type: string`
  - §2.3 schema: 标 Error 与 Output 互斥 top-level shape
  - §3.1 字段名 `overall` → `overall_verdict`（同 C4 §2.2）；I5 改 `git push origin <sha>:main` ff push，禁用 `gh pr merge`；I6 缩窄到 `gate_result+reason+rules`；I7 配合 I9 atomicity；**新增 I8 reason precedence**（HUMAN_BLOCKED > VERIFY > REVIEW > NOT_FF）；**新增 I9 R1 side-effect atomicity**（label 成 + comment 失 仍 held + partial_failure；label 失则降级 Error）
  - §3.2 删错误的 `gh pr merge --merge --ff-only`；用本地 ff merge + push 或 ff-push；finding 渲染**严格 4 字段**（不引用 summary）；pr_ref 转义到 safe_pr_ref
  - §3.3 拆 (a) Held cases (`reason` 枚举) + (b) Error cases (`code` 枚举)；NOT_FF_MERGEABLE 复用前提改为 "rebase 干净"，加 conflict resolution 警告 + P1.3 `pr_head_sha` 加固预案
  - §5 AC 大改：AC-1/AC-1b 拆 dry_run；AC-3/3b/3c 拆 R1 atomicity；AC-5 重写为 I8 precedence；AC-6/6b 拆 file-missing vs field-missing；AC-7 narrow 到核心三字段；AC-8 改 absent；AC-9 显式禁 `gh pr merge`；AC-10 加 pr_ref 转义验证
  - §6 关 Q6（P1.2 决议，cascade toolchain.md）；新加 Q6-6 schema 形态、Q6-7 排除 pre-push
  - §7 落地形态去 pre-push 钩子（exit 1 abort branch push 反例）；加 safe_pr_ref 实现示意；消费字段 `overall` → `overall_verdict`；dogfood 字段名 + I8 验证 + pr_ref 转义验证；clarify "v0.1.1 contract" = C5 contract 版本
- **v0.1.0** (2026-05-24): 初版
