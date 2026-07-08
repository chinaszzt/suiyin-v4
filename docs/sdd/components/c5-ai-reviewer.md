# C5 AI Reviewer — Component Spec

> 独立 AI session reviewer。平行于 C2 implementer：**不读** implementer 的 session log / 工作过程，只读最终产物（spec / plan / constitution / PR diff / verify_report.json），产出结构化 `verdict` + `findings` 列表供 C6 Gate Contract 判 merge / hold。**v4 工具链 P1.2 自闭环 merge 的核心组件之一**（另一个是 C6 Gate Contract）。

## 0. Type

- [x] 自建组件 (imperative logic — 需要写代码)
- [ ] 行为契约（declarative contract — 配置 + 编排）

**实现栈**: Python 3.11+（同 C2/C4, 见 ADR-0002）。CLI 入口拟为 `suiyin-flow review run <pr_ref>`，复用顶层 unified dispatcher（见 C2 §7 "Unified CLI"）。

## 1. Purpose

接收一个 PR + 关联 spec/plan/constitution + （可选）verify_report.json，启动独立 AI session 做**意图对齐审查**，输出结构化 `verdict` + `findings`，供 C6 Gate Contract 自动判 merge / hold。**核心隔离**: C5 session 全新 context，**不**继承 C2 implementer 的任何 log / state，避免被 implementer 视角污染。

## 2. Public API

### 2.1 Input Schema

```yaml
type: object
required: [pr_ref, spec_ref, plan_ref, constitution_ref, task_id, criticality, repo_root]
properties:
  pr_ref:
    type: string
    description: PR URL（gh 可达时）或本地分支名（无 remote 时降级）
  spec_ref:
    type: string
    description: spec.md 路径（相对 repo_root 或绝对）
  plan_ref:
    type: string
    description: plan.md 路径
  constitution_ref:
    type: string
    description: constitution.md 路径，默认 '.specify/memory/constitution.md'
  verify_report_path:
    type: string
    description: |
      optional；C4 verify_report.json **绝对路径**。
      存在 → review 时纳入 ac_summary / failure 信息辅助判断；
      缺失 → C5 仅基于 spec/plan/diff review（仍 work，但 AC 覆盖判断变弱）
  task_id:
    type: string
    pattern: '^T-\d{3,}$'
    description: |
      **required (v0.1.1)**：所有 PR 必须来自 task（含 hotfix / Initiative），
      C5 强制要求 task_id 关联回 origin task。让 finding 可回链 task、跨 attempt
      audit、verify_report 关联。设计上 C5 不审"非 task PR"（这种情况应当先
      把任务 task 化, 而非走 C5 ad-hoc review）。
  criticality:
    enum: [low, medium, high]
    description: |
      决定 review 模式 (见 §6 Q5)；
      low/medium → 单次 review；high → N=2 + 分歧仲裁（P1.2 待 spike 验证）
  repo_root:
    type: string
    description: 业务项目根目录绝对路径
  session_timeout_seconds:
    type: integer
    default: 1800
    description: 单 review session 上限，超时强制 kill（默认 30 min）
  max_retries:
    type: integer
    minimum: 0
    maximum: 2
    default: 2
```

### 2.2 Output Schema

```yaml
type: object
required: [verdict, findings, reviewed_at, session_id, contract_version]
properties:
  verdict:
    enum: [approve, block]
    description: |
      always；按 invariants I3-I5 由 finding **category** 决定 (v0.1.1 改"按 category"
      替代旧"按 severity"): block 集合 (硬契约违反) = nc_violation / security /
      spec_drift / ac_uncovered；其他 (complexity / pc_violation / cross_platform /
      reusable_knowledge_not_captured) → approve + finding 留 audit trail。

      去掉 `request_changes` (v0.1.1)：v4 D-autonomous 流派 "人只干 spec/plan/deploy"，
      没人介入 PR review 中间档。verdict 二元化与 C6 Gate Contract 简化一致。
  findings:
    type: array
    description: |
      always；每条 finding 必须 4 字段齐 (severity/category/location/suggested_fix)。
      空数组合法（一个 issue 没发现 → approve）。
    items:
      type: object
      required: [severity, category, location, suggested_fix]
      properties:
        severity:
          enum: [low, medium, high, critical]
        category:
          enum:
            - complexity                       # 过度设计 / 重复实现 / 函数超长（Fork L: 调 C11 query 跨文件查重）
            - spec_drift                       # PR diff 跟 spec 意图不对齐
            - ac_uncovered                     # spec AC 缺对应 test
            - nc_violation                     # 违反 constitution NC-1..NC-5
            - pc_violation                     # 违反 PC-1..PC-3
            - cross_platform                   # NC-5 跨平台违规（路径手拼等；shell=True 对用户命令字符串是例外不 flag——ADR-0005）
            - security                         # 安全问题（hardcoded secret / injection / 等）
            - reusable_knowledge_not_captured  # C12: spike 学到的知识没沉淀到 spec/constitution
        location:
          type: string
          description: 'file:line 或 spec section reference，例 src/foo.py:42 或 spec.md §3.1'
        suggested_fix:
          type: string
          description: 具体可操作的修复建议（不是泛泛 "改进代码"）
  reviewed_at:
    type: string
    format: date-time
    description: 'always；ISO 8601 时间戳'
  session_id:
    type: string
    description: 'always；本次 review session 唯一 ID（UUID）'
  task_id:
    type: string
    pattern: '^T-\d{3,}$'
    description: 'conditional（when input.task_id 非空）；透传'
  pr_ref:
    type: string
    description: 'always；回传 input.pr_ref'
  contract_version:
    type: string
    pattern: '^v\d+\.\d+\.\d+$'
    description: 'always；本 spec 版本号，schema breaking change → MAJOR bump'
  arbitration:
    type: object
    description: 'conditional（when criticality=high 走 N=2 模式）'
    properties:
      mode: { enum: [single, n2_consensus, n2_arbitrated] }
      reviewer_count: { type: integer }
      arbiter_session_id: { type: string }
```

### 2.3 Error Schema

```yaml
type: object
required: [code, message]
properties:
  code:
    enum:
      - SESSION_CRASHED          # claude CLI 非 0 退出
      - TIMEOUT                  # review 超 session_timeout_seconds
      - SPEC_NOT_FOUND           # spec_ref / plan_ref / constitution_ref 路径不存在
      - PR_DIFF_FETCH_FAILED     # gh / git 获取 PR diff 失败
      - INVALID_PR_REF           # pr_ref 既不是 URL 也不是合法分支名
      - VERIFY_REPORT_PARSE_FAILED  # verify_report_path 存在但 JSON 解析失败
      - ARBITRATION_DEADLOCK     # N=2 模式下两个 reviewer + 仲裁者全部 crash / timeout
      - REPO_ROOT_NOT_FOUND      # repo_root 路径不存在
  message: { type: string }
  details:
    type: object
    properties:
      attempt: { type: integer }
      stderr_tail: { type: string }
      pr_ref: { type: string }
  retryable: { type: boolean }
```

## 3. Behavior Contract

### 3.1 Invariants

- **I1**: C5 session 独立, fresh context, 不继承 C2 implementer 的任何 log / state / stdout。隔离边界：仅读 spec / plan / constitution / PR diff / verify_report.json，禁止读 `.suiyin/sessions/attempt-*.log`。**这是 C5 区别于 C2 self-review 的核心价值**——避免被 implementer 视角污染。
- **I2**: 每条 finding 四字段齐 (`severity` / `category` / `location` / `suggested_fix`)。缺任一字段 → finding 无效，review 整体视为 schema violation。
- **I3** (v0.1.1 重写): verdict **按 finding category 决定**, 不按 severity:
  - **block 集合** (硬契约违反, 不可 override): `nc_violation` / `security` /
    `spec_drift` / `ac_uncovered`
  - **approve + finding audit** (软违规): `complexity` / `pc_violation` /
    `cross_platform` / `reusable_knowledge_not_captured`
- **I4** (v0.1.1 重写): findings 为空 → `verdict=approve`。
- **I5** (v0.1.1 重写): finding 含 block-set category 任一 (regardless of severity)
  → `verdict=block`。**block recovery 由 §7 "Block Recovery" 节定义** —
  P1.2 阶段 R1 (auto-label `human:block` + 等人介入), P1.3+ R2 (C2 retry with
  feedback), P3+ R3 (Codex 仲裁)。
- **I6**: `reusable_knowledge_not_captured` finding 即使 severity=`low` 也必须出现在 output（C12 Knowledge Capture 持续触发, 不阻断 merge 但持续提示沉淀, 见 discussion-notes.md §十）。
- **I7**: C5 跑在隔离 worktree 或临时 dir，**不**直接动主仓 working tree（**NC-4 worktree 隔离即安全边界** 的具体实现 — claude CLI `--permission-mode bypassPermissions` 的安全边界即 review 临时 dir 边界）。
- **I8**: 同一 PR 二次 review（attempt > 1）必须用全新 session_id；不允许复用上次 session 状态（避免缓存污染）。

### 3.2 Side Effects

- 创建临时 review dir（默认 `<repo_root>/.suiyin/reviews/<session_id>/`），存 session log + finding 中间产物
- 调用 `claude` CLI headless（同 C2 §7 "Session 调用模式" 4 个必需 flag）
- 调用 `gh pr diff <pr_ref>` 或 `git diff <base_branch>...<pr_ref>` 拉 PR diff
- `complexity` 类 finding 触发时调用 **C11 query 接口**（Fork L: embedding 语义查重 + jscpd 语法兜底），P1.2 阶段 C11 未落地时降级为只跑 jscpd
- 写 `review_report.json` 到 `<repo_root>/.suiyin/reviews/<session_id>/report.json`
- **不**修改源码、**不** commit、**不** push（C5 是只读审查）

### 3.3 Failure Modes

| 失败类型 | 触发条件 | 处理 |
|---|---|---|
| `SESSION_CRASHED` | claude CLI 非 0 退出（OOM / SIGSEGV / API 429） | 记录 stderr tail，重试（max_retries 默认 2） |
| `TIMEOUT` | review > session_timeout_seconds（默认 1800s） | `kill -9` 整棵进程树，重试 1 次（多次重试浪费） |
| `SPEC_NOT_FOUND` | 任一 input ref 路径不存在 | 立即报错，不启动 session |
| `PR_DIFF_FETCH_FAILED` | gh / git 拉 diff 失败（无 gh 且本地 base_branch 找不到） | 重试 ≤ 2 |
| `INVALID_PR_REF` | pr_ref 既不是合法 URL 也不是合法分支名 | 立即报错 |
| `VERIFY_REPORT_PARSE_FAILED` | verify_report_path 存在但 JSON 解析失败 | 立即报错（schema breaking 不容忍） |
| `ARBITRATION_DEADLOCK` | N=2 模式下 2 reviewer + 仲裁者全 crash / timeout | 立即报错，等人介入 |
| `REPO_ROOT_NOT_FOUND` | repo_root 路径不存在 | 立即报错 |

**重试策略**:
- `SESSION_CRASHED` / `PR_DIFF_FETCH_FAILED` → 重试（max_retries 默认 2）
- `TIMEOUT` → 重试 1 次
- 其他类型 → 不重试，立即终态

## 4. AI Prompt Template

````markdown
# C5 AI Reviewer — Independent Review Session

## Your Role

你是 C5 AI Reviewer。**独立审 PR**。**严禁读** implementer 的 session log（`.suiyin/sessions/*`），只读最终产物。你的核心价值是 fresh context — 避免被 implementer 视角污染，从 spec/plan 意图独立判断。

## Input

- **spec**: {spec_ref}（必读，理解意图）
- **plan**: {plan_ref}（必读，理解实施策略）
- **constitution**: {constitution_ref}（必读，NC-1..NC-5 + PC-1..PC-3）
- **PR diff**: {pr_diff_path}（实际产出）
- **verify_report**: {verify_report_path}（optional，含 ac_summary + L1/L2 结果）
- **task_id**: {task_id}（optional，回链）
- **criticality**: {criticality}（low/medium/high，high 走 N=2 仲裁模式）

## Steps

1. 读 spec / plan / constitution 理解任务意图
2. 读 PR diff 看实际产出
3. 跨文件扫 complexity（调用 C11 query 做语义查重 + jscpd 语法兜底）
4. 逐项检查：
   - **AC coverage**: spec §5 每条 AC 在 diff 中是否有对应 test
   - **NC/PC 违规**: diff 是否违反 NC-1..NC-5 / PC-1..PC-3
   - **cross_platform**: 是否有 `os.sep` 手拼 / 等 Windows 不兼容写法（**例外**：对用户提供的整串 shell 命令如 verify_cmd 用 `shell=True` 是正确写法，不 flag——NC-5 v0.2.3 / ADR-0005）
   - **security**: hardcoded secret / SQL injection / 等
   - **spec_drift**: PR diff 是否引入 spec 未声明的能力 / 漏实现 spec 声明的能力
   - **reusable_knowledge_not_captured** (C12): spike 学到的 invariant 是否回流到 spec / constitution
5. 产生 findings 列表（每条 4 字段齐）
6. 按 invariant I3-I5 决 verdict (v0.1.1: **按 category 决定** — block 集合
   {nc_violation, security, spec_drift, ac_uncovered} 任一出现 → block;
   其他 / 空 → approve + audit)
7. 输出符合 §2.2 schema 的 JSON

## Output (session 最后一行必须输出 ```json``` code block)

```json
{
  "verdict": "approve | block",
  "findings": [
    {
      "severity": "low | medium | high | critical",
      "category": "complexity | spec_drift | ac_uncovered | nc_violation | pc_violation | cross_platform | security | reusable_knowledge_not_captured",
      "location": "src/foo.py:42 | spec.md §3.1",
      "suggested_fix": "具体可操作的修复建议"
    }
  ],
  "reviewed_at": "2026-05-24T10:30:00Z",
  "session_id": "...",
  "task_id": "T-042",
  "pr_ref": "...",
  "contract_version": "v0.1.0"
}
```

## Constraints (来自 Behavior Contract §3)

- **严禁读 implementer session log** (I1) — `.suiyin/sessions/*` 不在 review scope
- **严禁直接动主仓** (I7, NC-4) — review 临时 dir 是 bypassPermissions 的安全边界
- findings 必须 4 字段齐 (I2)，缺字段整 review 视为 schema violation
- verdict 严格按 I3-I5 **由 finding category 决定** (v0.1.1, 不按 severity), **不可降级**
- `reusable_knowledge_not_captured` finding 即使 low 也要列出 (I6, C12)
- 失败时输出符合 §2.3 error schema 的 JSON 而非自然语言
````

## 5. Acceptance Criteria

> C5 自身的 AC（不是 T-002 dogfood 的 AC-201..208）。每条必须能写出 test 验证。

- **AC-1**: 给定 valid input (含 required `task_id`)，返回 `verdict ∈ {approve, block}` 且 `findings` 满足 §2.2 schema（4 字段齐）
- **AC-2** (v0.1.1 重写): 给定 findings 含 1 条 `category=nc_violation` (任意 severity)，verdict 必为 `block`（I5 按 category，不可降级）
- **AC-3** (v0.1.1 重写): 给定 findings 全为 block 集合之外的 category (e.g. `complexity` / `pc_violation`)，verdict 必为 `approve`（I3，approve + finding audit）
- **AC-4**: 给定 spec.md 不存在路径，立即返回 error code `SPEC_NOT_FOUND`，不启动 session
- **AC-5**: review session 跑超 `session_timeout_seconds`，返回 `TIMEOUT` 且进程被 `kill -9`
- **AC-6**: C5 session 启动后**不读**任何 `.suiyin/sessions/attempt-*.log` 文件（I1 隔离，可通过 audit log 验证）
- **AC-7**: C12 触发场景 — spike PR 含新 invariant 但未更新 spec/constitution，必产生 1+ 条 `category=reusable_knowledge_not_captured` finding（即使 severity=low 也输出，I6）
- **AC-8**: `criticality=high` 时 output 含 `arbitration` 字段且 `mode ∈ {n2_consensus, n2_arbitrated}`（N=2 模式生效，P1.2 spike 后启用）
- **AC-9**: `complexity` 类 finding 必通过 C11 query（P1.2 阶段允许降级到 jscpd），不允许 reviewer 凭直觉空报 complexity
- **AC-10**: `review_report.json` 严格符合 §2.2 schema（schema validation 100% 通过，跨 100 次 sample）

## 6. Open Questions

- **Q5**: C5 reviewer **单次 review 还是 N=2 分歧仲裁**（按 task.criticality 路由）？候选方案：
  - low/medium: 单次 review（成本低）
  - high: N=2 独立 review + 分歧时第 3 个 AI 仲裁（类似 C3 模式，借 Fork H "仲裁 AI = 独立第 3 个 session"）
  - 待 P1.2 spike 验证后定（toolchain.md §六附录 B Q5）
- **Q5-2**: `complexity` finding 在 C11 未落地阶段是否完全降级为 jscpd 语法级查重？还是禁用 complexity 类直到 C11 就位？当前倾向降级以保持组件可用。
- **Q5-3**: review 失败（SESSION_CRASHED 重试用尽）时，C6 Gate Contract 应视为 `block` 还是触发人工介入？默认倾向 block + 标记 `c5-failed` 标签等人复审。
- **Q5-4**: `verify_report_path` 缺失时，C5 是否仍输出 `ac_uncovered` 类 finding？候选：可降级输出（基于 PR diff 中 test 文件名 prefix 解析），但置信度低。
- **Q5-5** (v0.1.1): **Block Recovery R2 设计** — C5 block 后, C2 自动 retry with C5 findings as feedback prompt (P1.3 阶段加 C2 v0.2 retry-with-feedback 子能力)。候选: findings 列表 → 新增 prompt section "上次 review 发现的问题" → C2 再 attempt → 仍 block 后退到 R1 (human:block 标签)。retry budget 待定 (≤2?)。见 §7 "Block Recovery" 节。
- **Q5-6** (v0.1.1): **Block Recovery R3 设计** — Codex 仲裁 (Claude + Codex 双 reviewer 取交集), 跟 Q5 N=2 仲裁可整合。需要 Codex CLI 集成基础设施 (P3+ todo)。

## 7. Implementation Notes

### 技术栈

- **Python 3.11+**（ADR-0002）
- 子进程管理：`subprocess` + `psutil`（跨平台 kill 进程树，见 C2 §7 跨平台节）
- session 调用：`claude` CLI headless 模式 — **复用 C2 §7 "Session 调用模式"** 节定义的 4 个必需 flag（`--print --output-format stream-json --verbose --permission-mode bypassPermissions`）
- diff 拉取：`gh pr diff <ref>`（gh 可用时） / `git diff <base>...<ref>`（降级）
- C11 查重：调用 `c11_query` 接口（P1.2 阶段未落地，降级到 `jscpd` CLI）

### Session 调用模式

C5 **不**重新设计 session 启动协议，**直接复用 C2 §7 "Session 调用模式"** —— 4 个必需 flag 缺一不可，stream-json event 解析按 result event > assistant event > top-level JSON 优先级。详情见 C2 spec。**唯一差异**：C5 prompt 注入的 `context_seeds` 严禁包含 `.suiyin/sessions/*`（I1 隔离）。

### Unified CLI

C5 CLI 入口通过顶层 unified dispatcher（同 C2/C4，见 C2 §7 "Unified CLI" 节）：

```python
# src/suiyin_flow/cli.py
def main(argv):
    cmd = argv[0]
    if cmd == "verify": return c4_verify.cli.main(argv)
    if cmd == "task":   return c2_executor.cli.main(argv)
    if cmd == "review": return c5_reviewer.cli.main(argv)   # C5 入口
    ...
```

`pyproject.toml` 已注册 `suiyin-flow = "suiyin_flow.cli:main"`，C5 只加 subcommand 路由。

### 跨平台兼容性（macOS / Linux / Windows）

**这是 constitution NC-5 的具体实现**。规则同 C2 §7 跨平台节（`pathlib.Path` / `psutil.Process.kill()` / `shell=False` / `shutil.which` + venv binary fallback / `encoding='utf-8'` 等），不重复。

### Block Recovery（v0.1.1 新增）

C5 verdict 二元化后 (没 `request_changes` 缓冲), `verdict=block` = PR 不 merge。
v4 D-autonomous 流派 "人只干 spec/plan/deploy" → block 后必须有自动 recovery，
否则 task 死锁等人审。

**3 个 recovery 阶段** (按 P1.2 → P1.3 → P3+ 渐进落地):

| 阶段 | 路线 | 说明 |
|---|---|---|
| **R1** (P1.2) | C5 block → C6 自动给 PR 加 `human:block` 标签 **+ comment findings inline** → 用户介入 fix | 最简兜底, 短期可用. v4 当前阶段 acceptable. 详 [c6 §3.1 I7+I9](c6-gate-contract.md) atomicity 边界 |
| **R2** (P1.3) | C5 block → C2 retry with findings as feedback prompt (max 2 次) → 仍 block 退 R1 | 真 SDD 闭环, 见 §6 Q5-5; toolchain.md C2 v0.2 加 retry-with-feedback 子能力 |
| **R3** (P3+) | 加 Codex 仲裁 (双 reviewer 取交集) → 减小 single-reviewer false positive | 见 §6 Q5-6 + Q5 (N=2 仲裁) |

**当前 P1.2 阶段**: 实现 R1。C5 输出 verdict=block 时 caller (C6 Gate Contract 或
直接是 CLI) 必须:
1. 通过 `gh pr edit <pr> --add-label "human:block"` 标 PR
2. 在 PR comment 中 inline finding 列表 (`gh pr comment`)
3. 不重试 (R2 P1.3 加)

**未来 P1.3 R2 设计预览** (Q5-5):
- C2 v0.2 加 `--review-feedback` flag 接收 C5 findings JSON
- prompt 注入新 section "## 上次 review 发现的问题" 含 findings
- C2 重 attempt with this feedback
- Retry budget: ≤2 with feedback (跟原 max_retries 解耦)
- 仍 block → fall through R1

### Finding Category 设计要点

**必须包含的 2 类**（toolchain.md §C5 + discussion-notes.md §十）：

- `complexity` — 跨文件查重 / 过度设计 / 重复实现 / 函数超长。**实现**：调用 C11 query 接口做 embedding 语义检索 (Fork L) + jscpd 语法级兜底。**阈值参考 Fork J**：函数 ≤ 80 行 / 文件 ≤ 600 行 / 嵌套 ≤ 5 层 / 圈复杂度 ≤ 18。
- `reusable_knowledge_not_captured` — C12 Knowledge Capture 的设计触发点 (discussion-notes.md §十 + diagrams.md 图 11 C12 placeholder)。即使 severity=low 也必输出 (I6)，作为持续提示沉淀机制。

其他常用 category：`spec_drift` / `ac_uncovered` / `nc_violation` / `pc_violation` / `cross_platform` / `security`。

### 模块拆分建议

```
suiyin_flow/
  c5_reviewer/
    __init__.py
    cli.py            # `suiyin-flow review run`
    contract.py       # §2 schema (Pydantic)
    prompt.py         # §4 prompt 模板填充
    session.py        # claude CLI headless 调用 + timeout/kill (复用 C2 模式)
    findings.py       # category enum + 4-field validation
    diff.py           # gh / git diff 拉取
    arbitration.py    # N=2 模式 (P1.2 spike 后落地)
    report.py         # review_report.json 落盘
```

### 跟其他 C 模块协作

- **被 C6 Gate Contract 消费**：C6 读 `verdict` 字段决定 merge / hold（`verify.all.pass && review.verdict == approve && pr.ff_mergeable && !pr.has_label("human:block")` → merge）
- **被 C2 Task Executor 触发**：C2 闭环结束开 PR 后，下一步即调 C5（P1.2 阶段由 C7 Phase Coordinator 协调）
- **被 C3 Arbiter 间接调度**：high criticality 时 C3 起两个 C2 session 并行，C5 N=2 仲裁模式独立于 C3（C3 在实现层仲裁，C5 在 review 层仲裁）
- **调用 C11 Function Registry query**：`complexity` 类 finding 必经 C11 query (Fork L)；C11 未落地阶段降级到 jscpd
- **C12 Knowledge Capture 联动**：`reusable_knowledge_not_captured` finding 是 C12 的设计触发点（discussion-notes.md §十）

### 跟 constitution 的关系

- **NC-1**（零 SaaS）：C5 用本地 `claude` CLI + 本地 jscpd / sentence-transformers，不依赖 SaaS API ✅
- **NC-2**（spec-kit Layer 1 backbone）：C5 输入 spec/plan 均为 spec-kit 产物，不重造协商 ✅
- **NC-3**（业务项目独立性）：review 临时 dir 落在业务项目 `<repo_root>/.suiyin/reviews/` 下，不在 v4 仓 ✅
- **NC-4**（worktree 隔离即安全边界）：I7 + Session 调用模式继承 C2 bypassPermissions 边界约束 ✅
- **NC-5**（跨平台支持）：上方跨平台节 + 复用 C2 跨平台规则 ✅
- **PC-1**（最简实现优先）：默认单次 review，N=2 仲裁仅 high criticality (Q5 待 spike) ✅
- **PC-2**（组件 vs 契约明确分离）：C5 明确标"自建组件 imperative"，不混 declarative ✅

### v4 自身 dogfood

- **P1.2 第一次 dogfood**：T-002 (本 spec) 自身就是 dogfood —— 验证 C2 能 handle "写 spec 类 task" + C5 自审本 spec（自举：C5 review C5 spec PR）
- P1.2 spike 项：Q5 N=2 仲裁的实际触发率 + 仲裁者第 3 个 session 的成本 / 收益

---

**Version**: v0.1.3-draft
**Last Updated**: 2026-07-09
**Status**: draft — P1.2 起步 spec, 待 spike 验证 Q5 / Q5-5 (R2 retry-with-feedback) 后转 v0.2

**Changelog**:
- v0.1.3 (2026-07-09): **PATCH** — §2.2 category 注释 + §4 checklist：cross_platform 的 `shell=True` 判定加"用户命令字符串"例外（ADR-0005，constitution v0.2.3 cascade；C7 v0.1.1 reverify 即该例外的合法使用）。`prompt.py` 同句同步。CONTRACT_VERSION 不变（report schema 未动）。
- v0.1.2 (2026-06-12): **PATCH** — §2.1 `constitution_ref` 默认值 `docs/sdd/constitution.md` → `.specify/memory/constitution.md`（业务项目 spec-kit 标准位置）。跟 C2 v0.3.1 同源修正（r4 真闭环发现 #1）：C5 在业务项目 review 时同样校验 ref 存在，旧默认是 v4 自身路径会误报 `SPEC_NOT_FOUND`。CONTRACT_VERSION 不变（review_report schema 未变，仅 input 默认值）。
- v0.1.1 (2026-05-24): **PR #29 review 反馈修订** (user 审 v0.1.0 后):
  - §2.1 `task_id` 进 required (所有 PR 必走 task, 含 hotfix / Initiative)
  - §2.2 verdict enum 简化 `{approve, request_changes, block}` → `{approve, block}` (v4 D-autonomous "人只干 spec/plan/deploy" → 没 request_changes 缓冲)
  - §3.1 I3/I4/I5 重写: verdict **按 category** 决定 (block 集合 = nc_violation/security/spec_drift/ac_uncovered；其他 → approve + audit), 替代旧"按 severity"
  - §4 prompt + Output JSON 同步去 request_changes
  - §5 AC-2/AC-3 同步重写 (按 category 验)
  - §6 加 Q5-5 (R2 C2 retry-with-feedback) + Q5-6 (R3 Codex 仲裁)
  - §7 加 "Block Recovery" 节: R1 (P1.2 human:block 标签) / R2 (P1.3 retry-with-feedback) / R3 (P3+ Codex) 渐进路线
- v0.1.0 (2026-05-24): 初稿 (T-002 dogfood 产出，dogfood/T-002/spec.md AC-201..AC-208 驱动)
