# C2 Task Executor — Component Spec

> 单个 task 从 spec 到 PR 的全自动实现。worktree 隔离、Claude Code headless session、prompt 模板注入、失败重试与超时保护。**v4 工具链 P0 MVP 的核心组件之一**（另一个是 C4 Verify Contract）。

## 0. Type

- [x] 自建组件（imperative logic — 需要写代码）
- [ ] 行为契约（declarative contract — 配置 + 编排）

**实现栈**：Python（见 `constitution.md` Q-C-2 已拍）。CLI 入口拟为 `suiyin-flow task run <task_id>`。

## 1. Purpose

接收单个 task 描述，在隔离 worktree 内跑 Claude Code headless session 完成代码实现，**含闭环 verify**（worktree 内调用 `verify_cmd` 跑 C4 验证，不绿不 push、不开 PR），产出一个可被 C5/C6 流转的 PR。

verify 是 C2 闭环内的步骤，不是下一阶段：

```
AI session 写代码 → verify_cmd 跑 (C4) → 非绿 → 重试 session 让 AI 修
                                       → 绿   → commit + push + PR
```

## 2. Public API

### 2.1 Input Schema

```yaml
type: object
required: [task_id, spec_ref, plan_ref, context_seeds, verify_cmd, criticality, repo_root]
properties:
  task_id:
    type: string
    pattern: '^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$'   # LOCAL_ID_PATTERN (identity.py)
    description: >
      feature 内唯一 (local id)，例 'T-042' / 'T-001B'（v0.4.0 放宽——旧
      ^T-\d{3,}$ 在 002·T001 沙盒实验中拒收 T-001B，gen4-plan P0-1 转正）。
      全局身份 = feature_id + task_id (canonical key)
  feature_id:
    type: string
    pattern: '^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$'
    description: >
      optional; canonical key 上半（P0-1），约定 = spec-kit feature 目录名
      （例 '001-login-core'）。缺省从 base_branch 派生
      （identity.derive_feature_id，safe_ref 转义），向后兼容旧调用方
  spec_ref:
    type: string
    description: spec.md 路径（相对 repo_root），例 '.specify/specs/003-login/spec.md'
  plan_ref:
    type: string
    description: plan.md 路径
  constitution_ref:
    type: string
    description: constitution.md 路径，默认 '.specify/memory/constitution.md'
  context_seeds:
    type: array
    items:
      type: string
      description: 文件或目录路径（相对 repo_root），AI 必读
    description: AI session 启动时强制注入的文件清单
  verify_cmd:
    type: string
    description: C4 L1+L2 跑通的命令（worktree 内执行），例 'lefthook run pre-commit'
  criticality:
    enum: [low, medium, high]
    description: high 由 C3 Arbiter 调度，C2 不直接处理
  repo_root:
    type: string
    description: 业务项目根目录绝对路径
  ac_list:
    type: array
    items: { type: string, pattern: '^AC-\d+$' }
    description: 本 task 对应的 AC 编号集合（来自 spec），AI 必须产生对应 test
  max_retries:
    type: integer
    minimum: 0
    maximum: 3
    default: 3
  session_timeout_seconds:
    type: integer
    default: 7200
    description: 单 session 上限，超时强制 kill（Q2 已拍 2h）
  base_branch:
    type: string
    default: main
  open_pr:
    type: boolean
    default: true
    description: |
      false 时跳过 push + gh pr create，只留本地 task/<feature_id>/<id> 分支
      （pr_created=false，pr_url_or_branch=分支名）。
      C7 Phase Coordinator 调度时传 false —— task→feature 是本地 merge 语义，
      PR 只在 feature→main 层（C7 spec §3.1 I6，真闭环 dogfood 发现 #7 决议）。
      default true 向后兼容 standalone 直跑。
  review_feedback:
    type: string
    description: |
      可选；C5 review_report.json 路径（绝对路径，或相对 repo_root）。
      提供时 = R2 retry-with-feedback 模式（C5 spec §7 Block Recovery R2 / Q5-5）：
      C2 解析 report 的 findings，注入 prompt「上次 Review 发现的问题」节（§4），
      session 必须优先逐条处理后再走常规 Steps。
      语义要点：
      (1) R2 复用既有 worktree（I1 复用语义）—— 在被 block 的实现上修，不从头重写；
      (2) retry budget 由 caller 编排（Q5-5 预案 ≤2 轮后退 R1），C2 单次调用无状态；
      (3) 校验语义是**文件系统存在性** —— review report 是运行时 artifact
          （.suiyin/reviews/...，gitignored 不入库），不走 spec_ref 那套
          base_branch 可见性校验（区别于 v0.2.1 #9 修正的适用范围）；
      (4) findings 为空数组 → REVIEW_FEEDBACK_INVALID（block report 必有 ≥1
          finding，空反馈属 caller 调用错误，宁可 fail-fast 不静默跑普通模式）。
```

### 2.2 Output Schema

> **填写约定**：每字段标 `always` (终态必填) / `conditional` (条件填) / `optional` (尽量填)。所有 path 字段约定为**绝对路径**（避免 caller 跨 cwd 困惑）。

```yaml
type: object
required: [task_id, status, attempts, worktree_path, session_logs]
properties:
  task_id:
    type: string
    description: 'always；回传 input.task_id'
  status:
    enum: [success, failed]
    description: 'always；终态'
  attempts:
    type: integer
    description: 'always；实际跑的 session 轮数（含成功那轮，≤ max_retries+1）'
  worktree_path:
    type: string
    description: |
      always；**绝对路径**。这是 retain artifact 字段（不是主产物），
      用于：(1) 失败时人/上游去看现场；(2) 透传给 C4/C5 作为 verify/review input。
      主产物是 pr_url_or_branch。
  pr_url_or_branch:
    type: string
    description: |
      conditional（when status=success）；success 时必填：
      gh 可用 + remote 配置 → PR URL（如 'https://github.com/o/r/pull/42'）；
      gh 不可用 / 无 remote → 本地分支名（如 'task/004-auth/T-042'）。
      status=failed 时此字段为 null（应同时看 pr_created 字段）。
  pr_created:
    type: boolean
    description: |
      always；true = PR 真的开了；false = 只有本地分支或未推送。
      用来消歧 pr_url_or_branch 的两种语义。
  verify_report_path:
    type: string
    description: |
      conditional（when 至少跑过 1 次 verify_cmd）；C4 输出文件**绝对路径**。
      success 时指向最后一次（pass）的 report；
      failed 时指向最后一次（fail）的 report，供人看错因；
      verify 一次没跑（极早期失败如 SPEC_NOT_FOUND）时为 null。
  session_logs:
    type: array
    description: 'always；每次 attempt 一项，按时间顺序'
    items:
      type: object
      required: [attempt, log_path, duration_seconds, verify_pass]
      properties:
        attempt: { type: integer }
        log_path:
          type: string
          description: '绝对路径，指向 .suiyin/sessions/attempt-{N}.log'
        duration_seconds: { type: number }
        verify_pass:
          type: boolean
          description: '本 attempt 末次 verify 是否绿（未跑到 verify 阶段则为 false）'
  diff_stats:
    type: object
    description: 'conditional（when status=success）；git diff 统计'
    properties:
      files_changed: { type: integer }
      insertions: { type: integer }
      deletions: { type: integer }
  review_feedback_applied:
    type: boolean
    description: |
      always；true = 本次 run 注入了 review feedback
      （input.review_feedback 提供且解析通过）。R2 audit trail 字段。
```

#### Example outputs

**Success case**:

```json
{
  "task_id": "T-042",
  "status": "success",
  "attempts": 2,
  "worktree_path": "/Users/u/repo/worktrees/004-auth/T-042",
  "pr_url_or_branch": "https://github.com/o/r/pull/77",
  "pr_created": true,
  "verify_report_path": "/Users/u/repo/worktrees/004-auth/T-042/.suiyin/verify/latest.json",
  "session_logs": [
    {"attempt": 1, "log_path": "/Users/u/repo/worktrees/004-auth/T-042/.suiyin/sessions/attempt-1.log", "duration_seconds": 421.5, "verify_pass": false},
    {"attempt": 2, "log_path": "/Users/u/repo/worktrees/004-auth/T-042/.suiyin/sessions/attempt-2.log", "duration_seconds": 287.3, "verify_pass": true}
  ],
  "diff_stats": {"files_changed": 4, "insertions": 156, "deletions": 23}
}
```

**Failed case (RETRY_EXHAUSTED)**:

```json
{
  "task_id": "T-042",
  "status": "failed",
  "attempts": 4,
  "worktree_path": "/Users/u/repo/worktrees/004-auth/T-042",
  "pr_url_or_branch": null,
  "pr_created": false,
  "verify_report_path": "/Users/u/repo/worktrees/004-auth/T-042/.suiyin/verify/latest.json",
  "session_logs": [
    {"attempt": 1, "log_path": "...attempt-1.log", "duration_seconds": 380.0, "verify_pass": false},
    {"attempt": 2, "log_path": "...attempt-2.log", "duration_seconds": 412.1, "verify_pass": false},
    {"attempt": 3, "log_path": "...attempt-3.log", "duration_seconds": 396.7, "verify_pass": false},
    {"attempt": 4, "log_path": "...attempt-4.log", "duration_seconds": 405.2, "verify_pass": false}
  ]
}
```

### 2.3 Error Schema

```yaml
type: object
required: [code, message, task_id]
properties:
  code:
    enum:
      - TIMEOUT                # 单 session 超 session_timeout_seconds
      - SESSION_CRASHED        # Claude Code CLI 非 0 退出
      - VERIFY_FAILED          # verify_cmd 跑挂（attempt 内会重试，最终 RETRY_EXHAUSTED）
      - RETRY_EXHAUSTED        # 重试用完仍未 pass
      - WORKTREE_CONFLICT      # worktree 路径已存在且不属于本 task
      - SPEC_NOT_FOUND         # spec_ref / plan_ref 文件不存在
      - INVALID_TASK_ID        # 不符合 pattern
      - HIGH_CRITICALITY_REJECT  # criticality=high 应走 C3，C2 拒接
      - CONTEXT_SEEDS_MISSING  # 任一 context_seeds 文件不存在
      - WORKTREE_LOCKED        # worktree 有活跃 C2 run（.suiyin/lock pid 存活，I8）
      - REVIEW_FEEDBACK_INVALID  # review_feedback 不存在 / JSON 非法 / findings 缺失或为空
      - SAFETY_BLOCKED         # 安全闸命中；不起 session 或不采纳 commit，等待人工处置
  message: { type: string }
  task_id: { type: string }
  details:
    type: object
    properties:
      attempt: { type: integer }
      stderr_tail: { type: string }
      verify_report_path: { type: string }
  retryable: { type: boolean }
```

## 3. Behavior Contract

### 3.1 Invariants

- **I1**: 每个 task 对应**唯一** worktree `worktrees/<feature_id>/<task_id>`。同 task_id 复跑必须先清理或复用旧 worktree（按 `--clean` flag）。
- **I2**: AI session 在 worktree 内启动，**严禁在主仓库工作树跑**。**这是 constitution NC-4（隔离 worktree 是自动化执行的安全边界）的具体实现** — `--permission-mode bypassPermissions` 模型的安全边界即 worktree 边界。
- **I3**: `verify_cmd` 在 worktree 内绿才 push；非绿不 push、不开 PR。
- **I4**: 每次 attempt 都跑独立 session（fresh context），不继承上一轮 stdout/stderr，但**继承代码变更**（同 worktree）—— 让 AI 在已有半成品上继续。
- **I5**: `criticality=high` 直接报 `HIGH_CRITICALITY_REJECT`，调度责任在 C3，不在 C2。
- **I6**: PR 描述里必须包含 `spec_ref` + `ac_list` + `attempts`，便于 C5 Reviewer 关联回 spec。
- **I7**: 单 session 超 `session_timeout_seconds` 强制 `kill -9`，**不允许优雅退出超时**（避免假活）。
- **I8**: 同一 worktree 同时至多一个活跃 C2 run。run 起步（worktree 创建/复用后、session 启动前）在 `worktrees/<feature_id>/<task_id>/.suiyin/lock` 写 pid 锁（`O_CREAT|O_EXCL` 原子创建），终态（success / RETRY_EXHAUSTED 等一切退出路径）释放；已存在且持有者 pid 存活（`psutil.pid_exists`）→ `WORKTREE_LOCKED` 拒跑，不动 worktree 内容；pid 已死或锁内容损坏 = stale → 确定性接管。**真闭环 dogfood 发现 #8 的 C2 半边** —— C7 的 I9 coordinator 锁挡「同 manifest 双 coordinator」，本锁挡「coordinator 在跑 + 人又直跑单 task」的交叉竞态（C7 spec §7 联动需求 2）。锁文件与 C7 coordinator 锁同 pattern（pid + task_id + start_ts JSON）。
- **I9（安全闸）**: 以下三条规则任一命中即 `SAFETY_BLOCKED`：(1) 测试/验证命令或新增 diff 行出现生产 MongoDB 端口 `27017`；(2) 同一行内生产库账号 `bzds` 与写操作词共现（只读放行）；(3) 新增 diff 行含 private key、AWS/OpenAI 风格密钥或非占位符明文凭证。输入闸在 worktree/session 之前阻断，diff 闸在 commit 采纳、push/开 PR 前阻断并保留 worktree；全程零模型参与，仅用确定性正则扫描。

### 3.2 Side Effects

- 创建 `worktrees/<feature_id>/<task_id>/`（git worktree add）
- worktree 内产生 commits（每 attempt 至少 1 个 commit，便于 review）
- push 到 remote `origin/task/<feature_id>/<task_id>`（remote 配置时），否则停在本地分支
- 调用 `gh pr create`（gh CLI 可用时），否则只输出分支名
- 跑 `verify_cmd` 期间可能调用业务项目 toolchain（dart / pnpm / pytest / ...）
- 写 `verify_report.json`（C4 输出，C2 透传路径，不解析内容）
- 写 session log 到 `worktrees/<feature_id>/<task_id>/.suiyin/sessions/attempt-{N}.log`
- 写/删 `worktrees/<feature_id>/<task_id>/.suiyin/lock` pid 锁（I8；run 起步创建，终态释放；`.suiyin/` gitignored 不入库）
- 计算 `diff_stats` 时跑 `git diff --shortstat <base_ref>...HEAD`：**fallback 链** = 先试 `origin/<base_branch>`，origin 缺失则 fallback 到本地 `<base_branch>`（dogfood 场景常见 base_branch 未 push 到 remote；P0 spike 经验，见 PR #25）
- task 完成后 worktree **保留**（C6 merge 后由 cleanup 阶段或人工删，C2 不删）

### 3.3 Failure Modes

| 失败类型 | 触发条件 | 处理动作 |
|---|---|---|
| `TIMEOUT` | 单 session 跑超 `session_timeout_seconds` | `kill -9` 整棵进程树，本 attempt 计失败，进入重试（如有额度） |
| `SESSION_CRASHED` | Claude Code CLI 非 0 退出（含 OOM / SIGSEGV / API 429） | 记录 stderr tail，重试 |
| `VERIFY_FAILED` | session 结束但 `verify_cmd` 非 0 | 透传 verify_report.json，重试（attempt 内重启 session 让 AI 自己 fix） |
| `RETRY_EXHAUSTED` | `attempts > max_retries` 仍未 pass | 终态 failed，**worktree 保留**等人介入 |
| `WORKTREE_CONFLICT` | `worktrees/<feature_id>/<task_id>` 已存在且分支不是 `task/<feature_id>/<task_id>` | 立即报错，不覆盖 |
| `SPEC_NOT_FOUND` / `CONTEXT_SEEDS_MISSING` | 输入路径不存在 | 立即报错，不启动 session |
| `HIGH_CRITICALITY_REJECT` | `criticality=high` | 立即报错，提示调用 C3 |
| `INVALID_TASK_ID` | 不符合 `T-\d{3,}` | 立即报错 |
| `WORKTREE_LOCKED` | `worktrees/<feature_id>/<task_id>/.suiyin/lock` 存在且持有者 pid 存活 | 立即报错，不启动 session、不动 worktree（details 带 `holder_pid` + `lock_path`）|
| `REVIEW_FEEDBACK_INVALID` | `review_feedback` 路径不存在 / JSON 解析失败 / `findings` 缺失或为空 | 立即报错，不启动 session |
| `SAFETY_BLOCKED` | `verify_cmd` 或新增 git diff 行命中 I9 任一安全规则 | 输入阶段不起 session、不创建 worktree；采纳阶段不 push/不开 PR并保留 worktree，交由人工处置 |

**重试策略**：
- VERIFY_FAILED / SESSION_CRASHED → 重试（max_retries 默认 3）
- TIMEOUT → 重试 1 次（疑似 AI 死循环，多次重试浪费）
- 其他类型 → 不重试，立即终态

## 4. AI Prompt Template

````markdown
# Task Executor — Implementation Session

## Your Role
你是 C2 Task Executor 调度下的 implementer。**单 task 闭环实现**，从 spec 到通过 verify 的代码。

## Task Context

- **task_id**: {task_id}
- **spec**: 见 {spec_ref}（必读）
- **plan**: 见 {plan_ref}（必读）
- **constitution**: 见 {constitution_ref}（必读）
- **ac_list**: {ac_list}（你产出的代码必须能让对应 `AC-N: ...` 命名的测试通过）
- **context_seeds**（必读，先扫一遍再动手）:
{context_seeds_yaml}
{review_feedback_section}
## Steps

1. 读 spec / plan / constitution / 所有 context_seeds
2. 列出你要改的文件清单（先 plan，后写）
3. 实现代码 + 写测试（测试名必须 prefix `AC-N: ` 对应 ac_list）
4. 跑 `{verify_cmd}` 在 worktree 内（cwd = `{worktree_path}`）
5. verify 绿后 `git add` + `git commit`（commit message 含 task_id + 主要变更）
6. 输出 §Output 部分的 JSON 摘要

## Constraints（来自 Behavior Contract §3）

- 只在 worktree (`{worktree_path}`) 内改文件，**严禁** `cd` 到 repo 主仓 / 修改其他 worktree
- 测试命名约定：`test('AC-N: ...')` (JS/Dart) / `def test_AC_N_...` (Python) — 见 C4 spec §3.1
- 1 个 test 名只能 prefix 1 个 `AC-N`
- 失败时输出符合 C2 §2.3 error schema 的 JSON 而非自然语言
- 严禁修改 spec.md / plan.md / constitution.md（你是 implementer，不是 spec 协商者）
- 严禁引入 NC-1 / NC-2 / NC-3 违反项（见 constitution §6）

## Output（session 最后一行必须输出）

```json
{
  "task_id": "...",
  "files_changed": [...],
  "verify_cmd_exit_code": 0,
  "commit_sha": "..."
}
```

verify 没绿时不要 commit。你可以重复跑 verify_cmd 调试。
````

**`{review_feedback_section}` 渲染规则（v0.3.0 R2）**：

- `review_feedback` 未提供 → 渲染为空字符串（模板退化为 v0.2.x 形态）。
- 提供时渲染为下节（findings 按 severity 排序 high → medium → low，同级保持 report 原序）：

````markdown
## 上次 Review 发现的问题（R2 retry-with-feedback — 必须优先处理）

上一轮实现被独立 AI Reviewer (C5) block。当前 worktree 里已有上一轮的实现，
**不要从头重写** —— 逐条修复以下 findings（或在最终输出的 JSON 里加
`feedback_disputes` 字段说明为什么某条不需要改），然后再走常规 Steps：

1. [{severity}/{category}] {location}
   fix: {suggested_fix}
2. ...
````

## 5. Acceptance Criteria

- **AC-1**: 给定 valid input（spec/plan/seeds 都存在 + verify_cmd 可跑通），返回 `status=success` 且 `pr_url_or_branch` 非空
- **AC-2**: 给定 `criticality=high`，立即返回 `HIGH_CRITICALITY_REJECT`，不启动 worktree
- **AC-3**: 给定不存在的 `spec_ref`，返回 `SPEC_NOT_FOUND`，不启动 worktree
- **AC-4**: AI session 跑超 `session_timeout_seconds`，返回 `TIMEOUT` 且进程被 `kill -9`
- **AC-5**: verify_cmd 连续 `max_retries+1` 次非 0，返回 `RETRY_EXHAUSTED` 且 worktree 保留
- **AC-6**: 同 `task_id` 复跑且 `worktrees/<feature_id>/<task_id>/` 已存在异源分支，返回 `WORKTREE_CONFLICT`，不覆盖
- **AC-7**: `worktree_path` 命名严格为 `worktrees/<feature_id>/<task_id>`，跨 100 次调用 100% 满足
- **AC-8**: 成功时 PR / 分支描述含 `task_id` + `ac_list` + `attempts` 三个字段
- **AC-9**: 每个 attempt 在 `.suiyin/sessions/attempt-{N}.log` 留下完整 stdout/stderr
- **AC-10**: 给定 `review_feedback` 指向合法 C5 report（≥1 finding），渲染的 prompt 含「上次 Review 发现的问题」节及每条 finding 的 `location` + `suggested_fix`（severity 降序），且 output `review_feedback_applied=true`；未提供时该节不出现且 `review_feedback_applied=false`
- **AC-11**: 给定 `review_feedback` 路径不存在 / JSON 非法 / findings 缺失或为空，返回 `REVIEW_FEEDBACK_INVALID`，不启动 session
- **AC-12**: worktree `.suiyin/lock` 存在且持有者 pid 存活 → 返回 `WORKTREE_LOCKED`，不启动 session、不修改 worktree 内容
- **AC-13**: lock 持有者 pid 已死（stale）→ 确定性接管，run 正常跑完
- **AC-14**: run 终态后（success 与 RETRY_EXHAUSTED 两路径）lock 文件均被释放

## 6. Open Questions

- **Q2-1（已拍）**: 单 session 上限 = 2h 强制 kill ✅
- **Q2-2**: Claude Code CLI 是 `claude` headless 还是 SDK API 直调？默认 CLI（最轻），但需验证 headless 模式参数稳定性。P0 spike 时确认
- **Q2-3**: 重试是同 worktree 续命，还是清 worktree 从头？当前默认续命（I4），但有 corner case：AI 把代码搞乱后 worktree 状态不可恢复 → 后续考虑 `--reset-on-retry` flag
- **Q2-4**: remote push 失败（无 gh / 网络断）时的降级 —— 当前是停在本地分支返回 success（带 branch name），但 caller 可能误以为有 PR。考虑加 `pr_created: bool` 字段
- **Q2-5**: session 跑过程中产生的 `node_modules` / `.dart_tool` 等大目录是否纳入 worktree git ignore —— 跟业务项目自身 `.gitignore` 关系？暂定信任业务项目 `.gitignore`
- **Q2-6** (v0.3.0): R2 的 retry 编排（谁数 budget、仍 block 后退 R1 的触发）放哪一层？C2 单次调用无状态（§2.1 review_feedback 语义要点 2），编排候选 = C7 v0.2（Q7-2 parked→R2 联动）或独立 harness。**C2 侧能力本版关闭（Q5-5 的 C2 半边）**，编排留 Q7-2
- **Q2-7** (v0.3.0): prompt 给了 session `feedback_disputes` 出口（§4 渲染规则）——dispute 内容要不要回流给 C5 / 人？当前只落在 session final JSON 里等人看，结构化回流留 R3（Codex 仲裁）阶段一起设计

## 7. Implementation Notes

### 技术栈

- **Python 3.11+**（Q-C-2 已拍，见 ADR-0002）
- 子进程管理：`subprocess` + `psutil`（kill 整棵进程树）
- worktree 操作：直接 `git worktree add / remove` shell 命令
- session 调用：`claude` CLI headless 模式 — **P0 spike 已验证可行**，见下方 "Session 调用模式" 节
- PR 创建：`gh pr create`（gh CLI 已有 → NC-1 零 SaaS 兼容：无 gh 时降级本地分支）

### Session 调用模式（P0 spike 拍板，2026-05-24 dogfood 验证）

C2 必须用以下完整 claude CLI 命令启动 headless session，**任何 flag 缺失会导致整套机制不工作**：

```bash
claude --print --output-format stream-json --verbose \
  --permission-mode bypassPermissions
```

**每个 flag 都是必需 (P0 spike 各自发现)**:

| Flag | 为什么必需 | 缺失后果 |
|---|---|---|
| `--print` | non-interactive (从 stdin 接 prompt + stdout 出结果) | session 起 TUI 卡住 |
| `--output-format stream-json` | 流式 NDJSON 输出 (每 event 一行) | 不能结构化解析 |
| `--verbose` | Claude CLI 强制要求 stream-json + --print 必须配 | 启动即报 "stream-json requires --verbose" |
| `--permission-mode bypassPermissions` | 授 AI 全权 Write/Edit/Bash 工具 | Write/Edit/Bash 全被拒, session 无法做实际工作 |

**`bypassPermissions` 的合法性**: 跟 NC-4（worktree 隔离即安全边界）配套 — AI 工具任意操作仅限隔离 worktree 内, 主仓不受影响. **没了 NC-4 这条 NC, bypassPermissions 等于安全洞 — 两者不可拆**.

#### stream-json event 解析（PR #23 实证）

`stream-json` 输出多种 event 类型 (system / rate_limit_event / assistant / result), AI 的最终答复**不**在 top-level JSON, 而是封在 nested text content。Parser 优先级：

1. **`result` event 的 `.result` 字段** (subtype=success 时, 是 final assistant text 聚合) — **最常见**
2. **`assistant` event 的 `.message.content[].text`** (单 message 也可能含 final JSON)
3. **Top-level JSON** (legacy / mock 路径, 保兼容)

各级 text 内的 JSON 抽取规则：
- 整 text 是 JSON
- ```` ```json``` ```` 或 ```` ``` ``` ```` code block 内 (prompt template 推荐 AI 用这个)
- inline 散落 JSON (兜底)

**判定为 final JSON 的特征**: dict 含 `task_id` 且含 `verify_cmd_exit_code`。

### Unified CLI（PR #25 实证）

C2 的 CLI 入口**必须**通过 v4 顶层 unified dispatcher (`suiyin_flow.cli:main`) 而非直接挂 `c2_executor.cli`。

**为什么**: v4 一个 binary `suiyin-flow` 既需要 `verify`（C4）又需要 `task`（C2）。直接挂任一会让另一个不可达 (P0 spike 实例：PR #25 之前 `suiyin-flow task ...` 报 "invalid choice: 'task' (choose from verify)")。

**Dispatcher 设计**:

```python
# src/suiyin_flow/cli.py
def main(argv):
    cmd = argv[0]
    if cmd == "verify":
        return c4_verify.cli.main(argv)
    if cmd == "task":
        return c2_executor.cli.main(argv)
    # ... help / unknown handling
```

`pyproject.toml`:
```toml
[project.scripts]
suiyin-flow = "suiyin_flow.cli:main"
```

**未来扩展**: C3 / C5 / C8 等组件加入时, 各自加 subcommand 路由（`suiyin-flow arbiter` / `suiyin-flow review` / `suiyin-flow deploy`）。

### 跨平台兼容性（macOS / Linux / Windows）

**这是 constitution NC-5（跨平台支持）的具体实现**。v4 主跑 macOS + Linux，但 Python impl 必须兼容 Windows（业务项目可能跑 Windows dev box）。**约束**：

| 项 | 规则 | 反面例子 |
|---|---|---|
| 路径处理 | 全程 `pathlib.Path`，**绝不**手拼 `/` 或 `os.sep` | `worktree_path + "/.suiyin/..."` ❌ → `worktree_path / ".suiyin" / ...` ✅ |
| 进程 kill | 用 `psutil.Process(pid).kill()` —— 它跨平台映射到对的 signal/API | `os.kill(pid, signal.SIGKILL)` ❌（Windows 没 SIGKILL） |
| 进程树 kill | `psutil.Process(pid).children(recursive=True)` 拿子进程再批量 kill；**不要**用 `os.killpg`（POSIX only） | — |
| subprocess 调用 | `shell=False` + `list[str]` args | `shell=True` ❌（Windows cmd 语义不同，引号转义陷阱） |
| 子进程 Python I/O 编码 | spawn 子进程（claude session 等）时 env = **继承父环境** + 叠加 `PYTHONIOENCODING=utf-8` / `PYTHONUTF8=1`——父端 Popen 的 `encoding="utf-8"` 只管父侧管道编解码，不改变子进程自身的 locale 默认 | 只设父端 encoding ❌（Windows 非 UTF-8 locale 下子进程读含中文的 prompt 被 surrogateescape 静默损坏，直到重编码才炸 `UnicodeEncodeError`——issue #60 Windows CI 实证） |
| worktree 命名 | 只用 ASCII (`task_id`/`feature_id` pattern 均限 ASCII slug, v0.4.0 LOCAL_ID_PATTERN) | 非 ASCII 路径在 Windows NTFS / Git for Windows 下 quirks |
| 换行 | 文件读写 binary 模式或 explicit `encoding='utf-8', newline=''` | text 模式默认 newline 转换在 Windows 上会改写 CRLF |
| gh / git CLI | 用 `shutil.which('gh')` 探测，找不到降级 | hardcode `/usr/local/bin/gh` ❌ |

**测试要求**：CI matrix 跑 macOS + Linux + Windows（GitHub Actions 矩阵或本地 lefthook 至少手测 Windows 1 次）。**P0 阶段**：macOS + Linux 必跑通，Windows 在 spike 时手测一次确认无致命问题，正式 Windows CI 进 P1+。**已落地（2026-07-09，issue #60 / PR #62）**：`.github/workflows/ci.yml` 3-OS matrix（ubuntu×py3.11/3.14 + windows×py3.11 + macos×py3.14），branch protection required check = `ci-ok`。

### 模块拆分建议

```
suiyin_flow/
  c2_executor/
    __init__.py
    cli.py            # argparse 入口
    worktree.py       # git worktree 包装
    session.py        # Claude Code headless 调用 + timeout/kill
    prompt.py         # §4 模板填充
    retry.py          # 重试策略
    schema.py         # Pydantic 模型 (§2.1/2.2/2.3)
```

### 跟 C 模块协作

- **被 C7 Phase Coordinator 调度**（P2 落地后）—— 现阶段 P0 由人/CLI 直接调
- **调用 C4 Verify Contract**：通过 `verify_cmd` 间接调，C2 不直接 import C4
- **被 C3 Arbiter 委托**：high criticality 时 C3 起两个 C2 session 并行，C2 本身不感知是否被仲裁
- **输出供 C5 AI Reviewer**：PR 描述里的 `spec_ref / ac_list` 是 C5 的入口

### v4 自身 dogfood

- P0 MVP 完成后第一个 dogfood task：**让 C2 实现 C5 AI Reviewer 的 spec**（自举：C2 写 C5 spec → C2 自动跑 verify → human review spec → merge）
- 验证 C2 是否能 handle "写文档类 task"（不只是写代码）—— 若不能，spec 需修订

### 跟 constitution 的关系

- **NC-1**（零 SaaS）：gh CLI 可选；无 gh 降级本地分支 ✅
- **NC-3**（业务项目独立）：worktree 在业务项目 `<repo_root>/worktrees/` 下，不在 v4 仓 ✅
- **NC-4**（worktree 隔离即安全边界）：§3.1 I1/I2 + Session 调用模式节直接 enforce ✅
- **NC-5**（跨平台）：上方"跨平台兼容性"节 + Session 调用模式跨 macOS/Linux/Windows 验过 ✅
- **PC-1**（最简实现）：CLI 优先而非 SDK；retry 上限硬性 ≤ 3 ✅

---

**Version**: v0.5.0-draft
**Last Updated**: 2026-08-12
**Status**: draft — P0 spike 跑通 (PR #21+25 impl, PR #24 dogfood)；Q2-2/Q2-3 已 spike 验证；v0.2.x 接入 C7 调度（open_pr + base-branch 视角输入校验）；v0.3.0 R2 retry-with-feedback + worktree 活跃锁；v0.3.1 constitution_ref 默认值面向业务项目；v0.3.2 子进程 UTF-8 I/O 强制（Windows CI 实证）；v0.4.0 canonical identity（gen4-plan P0-1）；v0.5.0 安全闸（gen4-plan P0-5）

**Changelog**:
- v0.5.0 (2026-08-12): **MINOR — gen4-plan P0-5 安全闸三条**。用零模型、纯正则机械阻断：(1) 生产 MongoDB 端口 `27017`；(2) 生产库账号 `bzds` 与写操作同一行共现（只读放行）；(3) private key、AWS/OpenAI 风格密钥或非占位符明文凭证进入新增 git diff。两挂点分别位于 `validate_refs` 后、`ensure_worktree` 前，以及 `_finalize_success()` commit 采纳/push/开 PR 前；命中统一返回 `SAFETY_BLOCKED`，后者保留 worktree 供人工处置。
- v0.4.0 (2026-08-12): **MINOR — gen4-plan P0-1 canonical identity**。(1) §2.1 加 `feature_id`（可选，缺省从 base_branch 派生；约定 = spec-kit feature 目录名），canonical key = `feature_id + task_id`，单一权威实现 `suiyin_flow/identity.py`；(2) `task_id` pattern `^T-\d{3,}$` → LOCAL_ID_PATTERN（`^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$`）——002·T001 沙盒实验 `T-001B` 被 schema 拒收的案例转正，模板仍推荐 `T-NNN`；(3) **I1 修订**：worktree `worktrees/<feature_id>/<task_id>`、分支 `task/<feature_id>/<task_id>`——不同 feature 的同名 task 不再互撞；(4) batch manifest schema v0.2.0（顶层 `feature_id`；v0.1.0 兼容读 + 派生提示）；(5) precheck v2：`constitution_ref` 一并查 base 可见性 + tasks.yaml 自身与 base HEAD 一致性（C1 execution_plan 写回未 commit → fail-fast）+ base 不可解析从静默跳过改 stderr 警告。AC-7 更新 + tests/test_identity_p0_1.py（T-001B 回归靶 / 兼容读 / 漂移失败型）。
- v0.3.2 (2026-07-09): **PATCH** — §7 跨平台表加「子进程 Python I/O 编码」行：spawn 子进程时 env 继承父环境并叠加 `PYTHONIOENCODING=utf-8` + `PYTHONUTF8=1`。**issue #60 Windows CI 首跑实证**：父端 `Popen(encoding="utf-8")` 只管父侧管道，Windows 非 UTF-8 locale 的子进程读中文 prompt 会 surrogateescape 静默损坏、重编码时才炸（AC-10 retry 4 连崩现场）。C5 session / C1 semantic 同源同修（其 spec 跨平台节均为「继承 C2 §7 表」引用式，不另 bump）。§7 测试要求标注 Windows CI 已落地（3-OS matrix + `ci-ok` required check）。impl: PR #62
- v0.3.1 (2026-06-12): **PATCH** — §2.1 `constitution_ref` 默认值 `docs/sdd/constitution.md` → `.specify/memory/constitution.md`（业务项目 spec-kit 标准位置）。**r4 真闭环发现 #1**：旧默认是 v4 自身的 constitution 路径，业务项目（v5）跑 C2 时校验「constitution_ref 在 base HEAD 可见」(v0.2.1) → `SPEC_NOT_FOUND` 阻断整个 phase run。v4 自身 dogfood 是特例（显式传 `docs/sdd/constitution.md`）；全部单元测试显式传 `constitution.md` → 零影响。cascade：C5 spec 同步（c5_reviewer 同源默认）+ `tasks-template.md` / `sy-tasks SKILL` schema 默认。
- v0.3.0 (2026-06-10): **MINOR** — P1.3 R2 + C7 联动需求 2 双件落地。(1) **R2 retry-with-feedback**（C5 §7 Block Recovery R2 / Q5-5 的 C2 半边）：§2.1 加 `review_feedback`（C5 report 路径，文件系统校验语义），§4 加「上次 Review 发现的问题」渲染规则（severity 降序 + `feedback_disputes` 出口），§2.2 加 `review_feedback_applied` audit 字段，§2.3 加 `REVIEW_FEEDBACK_INVALID`；retry 编排留 caller（新 Q2-6 → Q7-2）。(2) **worktree 活跃 session 锁**（真闭环 dogfood 发现 #8 C2 半边）：§3.1 新 I8（`.suiyin/lock` pid 锁，同 C7 I9 pattern：O_EXCL 原子创建 + psutil 探活 + stale 接管），§2.3 加 `WORKTREE_LOCKED`。AC-10..AC-14。CLI 加 `--review-feedback`。
- v0.2.1 (2026-06-10): **PATCH** — `SPEC_NOT_FOUND` / `CONTEXT_SEEDS_MISSING` 校验语义钉死为「在 `base_branch` HEAD 可见」（`git cat-file -e`；base 解析不了 fallback 文件系统）。**C7 dogfood r3 发现 #9**：旧版按 repo_root 当前 checkout 的文件系统校验，repo 主树与 base_branch 分支不一致时双向出错——feature 分支独有文件被误报 missing（r3 实测 fail-fast 在 T-001），盘上未提交文件被误判可用（session worktree 实际看不到）。错误码不变，仅校验基准修正；error message 带 `checked_against` 提示。
- v0.2.0 (2026-06-10): **MINOR** — §2.1 加 `open_pr: bool`（default true 向后兼容）。C7 spec v0.1.0 §7 联动需求 1 落地（I6：C7 调度下 task→feature 本地 merge，不 push 不开 task PR，关 dogfood 发现 #7）。CLI 加 `--no-pr`。注：todo P1.3 的 R2 `--review-feedback` 留后续 MINOR；联动需求 2（worktree 活跃 session 锁，发现 #8 C2 半边）一并留待下一 bump。
- v0.1.2 (2026-05-24): **P1.1.2 反推** — §3.1 I2 加 NC-4 reference；§3.2 加 diff_stats fallback 说明；§7 加 "Session 调用模式" 节（4 个必需 flag + stream-json 解析优先级，PR #21+23+25 实证）；§7 加 "Unified CLI" 节（PR #25 实证）；§7 跨平台节加 NC-5 reference；§7 跟 constitution 关系加 NC-4 / NC-5
- v0.1.1 (2026-05-20): §1 Purpose 加"含闭环 verify"；§2.2 Output schema 强化（conditionality + path 绝对/相对标注 + failed fallback + 2 examples）；新增 `pr_created` 字段消歧；§7 加"跨平台兼容性"节
- v0.1.0 (2026-05-20): 初稿
