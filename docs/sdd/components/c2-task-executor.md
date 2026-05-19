# C2 Task Executor — Component Spec

> 单个 task 从 spec 到 PR 的全自动实现。worktree 隔离、Claude Code headless session、prompt 模板注入、失败重试与超时保护。**v4 工具链 P0 MVP 的核心组件之一**（另一个是 C4 Verify Contract）。

## 0. Type

- [x] 自建组件（imperative logic — 需要写代码）
- [ ] 行为契约（declarative contract — 配置 + 编排）

**实现栈**：Python（见 `constitution.md` Q-C-2 已拍）。CLI 入口拟为 `suiyin-flow task run <task_id>`。

## 1. Purpose

接收单个 task 描述，在隔离 worktree 内跑 Claude Code headless session 完成代码实现，产出一个可被 C4/C5/C6 流转的 PR。

## 2. Public API

### 2.1 Input Schema

```yaml
type: object
required: [task_id, spec_ref, plan_ref, context_seeds, verify_cmd, criticality, repo_root]
properties:
  task_id:
    type: string
    pattern: '^T-\d{3,}$'
    description: 全 repo 唯一，例 'T-042'
  spec_ref:
    type: string
    description: spec.md 路径（相对 repo_root），例 '.specify/specs/003-login/spec.md'
  plan_ref:
    type: string
    description: plan.md 路径
  constitution_ref:
    type: string
    description: constitution.md 路径，默认 'docs/sdd/constitution.md'
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
```

### 2.2 Output Schema

```yaml
type: object
required: [task_id, status, worktree_path, pr_url_or_branch, attempts, verify_report_path]
properties:
  task_id: { type: string }
  status:
    enum: [success, failed]
  worktree_path:
    type: string
    description: 'worktrees/<task_id>' 完整路径
  pr_url_or_branch:
    type: string
    description: success 时返回 PR URL 或本地分支名（取决于 remote 是否配置）
  attempts:
    type: integer
    description: 实际跑的 session 轮数（含成功那轮，≤ max_retries+1）
  verify_report_path:
    type: string
    description: C4 verify_report.json 路径
  session_logs:
    type: array
    items:
      type: object
      properties:
        attempt: { type: integer }
        log_path: { type: string }
        duration_seconds: { type: number }
        verify_pass: { type: boolean }
  diff_stats:
    type: object
    properties:
      files_changed: { type: integer }
      insertions: { type: integer }
      deletions: { type: integer }
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

- **I1**: 每个 task 对应**唯一** worktree `worktrees/<task_id>`。同 task_id 复跑必须先清理或复用旧 worktree（按 `--clean` flag）。
- **I2**: AI session 在 worktree 内启动，**严禁在主仓库工作树跑**。
- **I3**: `verify_cmd` 在 worktree 内绿才 push；非绿不 push、不开 PR。
- **I4**: 每次 attempt 都跑独立 session（fresh context），不继承上一轮 stdout/stderr，但**继承代码变更**（同 worktree）—— 让 AI 在已有半成品上继续。
- **I5**: `criticality=high` 直接报 `HIGH_CRITICALITY_REJECT`，调度责任在 C3，不在 C2。
- **I6**: PR 描述里必须包含 `spec_ref` + `ac_list` + `attempts`，便于 C5 Reviewer 关联回 spec。
- **I7**: 单 session 超 `session_timeout_seconds` 强制 `kill -9`，**不允许优雅退出超时**（避免假活）。

### 3.2 Side Effects

- 创建 `worktrees/<task_id>/`（git worktree add）
- worktree 内产生 commits（每 attempt 至少 1 个 commit，便于 review）
- push 到 remote `origin/task/<task_id>`（remote 配置时），否则停在本地分支
- 调用 `gh pr create`（gh CLI 可用时），否则只输出分支名
- 跑 `verify_cmd` 期间可能调用业务项目 toolchain（dart / pnpm / pytest / ...）
- 写 `verify_report.json`（C4 输出，C2 透传路径，不解析内容）
- 写 session log 到 `worktrees/<task_id>/.suiyin/sessions/attempt-{N}.log`
- task 完成后 worktree **保留**（C6 merge 后由 cleanup 阶段或人工删，C2 不删）

### 3.3 Failure Modes

| 失败类型 | 触发条件 | 处理动作 |
|---|---|---|
| `TIMEOUT` | 单 session 跑超 `session_timeout_seconds` | `kill -9` 整棵进程树，本 attempt 计失败，进入重试（如有额度） |
| `SESSION_CRASHED` | Claude Code CLI 非 0 退出（含 OOM / SIGSEGV / API 429） | 记录 stderr tail，重试 |
| `VERIFY_FAILED` | session 结束但 `verify_cmd` 非 0 | 透传 verify_report.json，重试（attempt 内重启 session 让 AI 自己 fix） |
| `RETRY_EXHAUSTED` | `attempts > max_retries` 仍未 pass | 终态 failed，**worktree 保留**等人介入 |
| `WORKTREE_CONFLICT` | `worktrees/<task_id>` 已存在且分支不是 `task/<task_id>` | 立即报错，不覆盖 |
| `SPEC_NOT_FOUND` / `CONTEXT_SEEDS_MISSING` | 输入路径不存在 | 立即报错，不启动 session |
| `HIGH_CRITICALITY_REJECT` | `criticality=high` | 立即报错，提示调用 C3 |
| `INVALID_TASK_ID` | 不符合 `T-\d{3,}` | 立即报错 |

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

## 5. Acceptance Criteria

- **AC-1**: 给定 valid input（spec/plan/seeds 都存在 + verify_cmd 可跑通），返回 `status=success` 且 `pr_url_or_branch` 非空
- **AC-2**: 给定 `criticality=high`，立即返回 `HIGH_CRITICALITY_REJECT`，不启动 worktree
- **AC-3**: 给定不存在的 `spec_ref`，返回 `SPEC_NOT_FOUND`，不启动 worktree
- **AC-4**: AI session 跑超 `session_timeout_seconds`，返回 `TIMEOUT` 且进程被 `kill -9`
- **AC-5**: verify_cmd 连续 `max_retries+1` 次非 0，返回 `RETRY_EXHAUSTED` 且 worktree 保留
- **AC-6**: 同 `task_id` 复跑且 `worktrees/<task_id>/` 已存在异源分支，返回 `WORKTREE_CONFLICT`，不覆盖
- **AC-7**: `worktree_path` 命名严格为 `worktrees/<task_id>`，跨 100 次调用 100% 满足
- **AC-8**: 成功时 PR / 分支描述含 `task_id` + `ac_list` + `attempts` 三个字段
- **AC-9**: 每个 attempt 在 `.suiyin/sessions/attempt-{N}.log` 留下完整 stdout/stderr

## 6. Open Questions

- **Q2-1（已拍）**: 单 session 上限 = 2h 强制 kill ✅
- **Q2-2**: Claude Code CLI 是 `claude` headless 还是 SDK API 直调？默认 CLI（最轻），但需验证 headless 模式参数稳定性。P0 spike 时确认
- **Q2-3**: 重试是同 worktree 续命，还是清 worktree 从头？当前默认续命（I4），但有 corner case：AI 把代码搞乱后 worktree 状态不可恢复 → 后续考虑 `--reset-on-retry` flag
- **Q2-4**: remote push 失败（无 gh / 网络断）时的降级 —— 当前是停在本地分支返回 success（带 branch name），但 caller 可能误以为有 PR。考虑加 `pr_created: bool` 字段
- **Q2-5**: session 跑过程中产生的 `node_modules` / `.dart_tool` 等大目录是否纳入 worktree git ignore —— 跟业务项目自身 `.gitignore` 关系？暂定信任业务项目 `.gitignore`

## 7. Implementation Notes

### 技术栈

- **Python 3.11+**（Q-C-2 已拍）
- 子进程管理：`subprocess` + `psutil`（kill 整棵进程树）
- worktree 操作：直接 `git worktree add / remove` shell 命令
- session 调用：`claude` CLI headless 模式（待 P0 spike 验证）
- PR 创建：`gh pr create`（gh CLI 已有 → NC-1 零 SaaS 兼容：无 gh 时降级本地分支）

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
- **PC-1**（最简实现）：CLI 优先而非 SDK；retry 上限硬性 ≤ 3 ✅

---

**Version**: v0.1.0-draft
**Last Updated**: 2026-05-20
**Status**: draft — 待 P0 spike 验证 Q2-2 / Q2-3 后升 v0.2
