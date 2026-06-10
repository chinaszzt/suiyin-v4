# C7 Phase Coordinator — Component Spec

> 按 `execution_plan` 逐 phase 调度 C2 Task Executor，phase 内 task 完成后把 `task/<id>` 分支**本地 ff-merge 回 base_branch（feature 分支）**，让下一 phase 的 worktree 从含前序产物的 base HEAD 分叉。关掉 P1.2.5 真闭环 dogfood 的头号能力错配：「`/sy-tasks` 拆得出依赖链，batch 跑不动依赖链」。
>
> 路由核心是**确定性状态机**（纯 Python transition table，routing path 零 AI）——性质上跟 C6 的"纯 boolean 规则评估"同源，只是 C7 是 imperative 组件（要管进程、git、状态落盘）。

## 0. Type

- [x] 自建组件（imperative logic — 需要写代码）
- [ ] 行为契约（declarative contract — 配置 + 编排）

**实现栈**：Python（Q-C-2 已拍）。CLI 入口拟为 `suiyin-flow phase run`（经 unified dispatcher，见 §7）。

**注意**：虽是 imperative 组件，§3.1 I1 强制其路由核心具备契约性质（确定性 + 可枚举 transition table）。AI 只存在于被调度的 C2 session **内部**，不在 C7 自身任何路径上。

## 1. Purpose

读 `tasks.yaml`（含可选 `execution_plan`），按 phase 顺序调度 C2：phase 内 task 各自 worktree 实现，成功后**逐个 ff-merge 回 base_branch**；全 phase merge 完才进下一 phase——依赖链的代码可见性靠 **base 前进**传递，而非 worktree 互看。任一 task 卡住 → 隔离（park）+ 停止推进 + surface to human，**绝不回滚已 merge 的 task**。

跟 P1.2.5 `task batch` 的本质区别：

```
batch (P1.2.5):  task 全部从同一 base HEAD 分叉 → 互相看不见 → 只能跑独立 task
C7    (P1.3):    phase N 全部 merge 进 base → phase N+1 从新 HEAD 分叉 → 依赖链成立
```

## 2. Public API

### 2.1 Input Schema

```yaml
type: object
required: [tasks_yaml_path, repo_root]
properties:
  tasks_yaml_path:
    type: string
    description: tasks.yaml 路径。schema 向后兼容 batch manifest v0.1.0（BatchManifest），外加可选 execution_plan（见下）
  repo_root:
    type: string
    description: 业务项目根目录绝对路径
  max_parallel:
    type: integer
    minimum: 1
    default: 1
    description: phase 内同时在跑的 C2 session 上限。v0.1.0 MVP = 1（串行）；契约写成并行安全（I5/I7/I10 保证串行是并行的合法实现），真并行开闸条件见 Q7-1
  max_requeue:
    type: integer
    minimum: 0
    default: 3
    description: 单 task 整合阶段 rebase-requeue 重试上限（§3.3），超限 park
  dry_run:
    type: boolean
    default: false
    description: 解析 + 校验 + 输出 phase 计划；不取锁、不建 worktree、不 merge（边界见 §3.2）
  resume:
    type: boolean
    default: true
    description: latest state file 存在且 run 未终态时按 §3.1 I3 的 resume 语义续跑；false = 忽略旧 state 全新开跑（旧 versioned state 保留为 audit）
  retry_parked:
    type: array
    items: { type: string }
    description: resume 时显式重试的 parked task_id 列表（或字面量 "all"）。缺省 = parked 保持 parked（人修完显式点名重试，避免静默烧 token 重 dispatch）
  claude_cmd:
    type: array
    items: { type: string }
    description: 测试注入 mock claude；透传给 C2（同 batch 同名参数）
```

#### tasks.yaml 扩展：`execution_plan`（C1 Planning Engine 输出；可缺省）

```yaml
execution_plan:
  type: array
  items:
    type: object
    required: [phase, parallel]
    properties:
      phase:
        type: integer
        description: 从 1 起连续递增
      parallel:
        type: array
        items: { type: string }   # task_id
        minItems: 1
        description: 本 phase 内可并行的 task 集合（C1 判定互相独立）
```

**校验规则**（违反 → Error `INVALID_PLAN`，零副作用）：

1. `execution_plan` 的 task_id 集合**恰好等于** `tasks[]` 集合（无缺、无多、无重复）
2. 任一 task 的 `depends_on` 只允许指向**更早 phase** 的 task（指向同 phase / 更晚 phase = C1 输出坏了，C7 不收）
3. 全部 task 的 `base_branch` **必须一致**（逐 phase merge 的目标只能有一个；混用即计划不自洽）

**缺省 execution_plan → degenerate plan**：每个 task 自成一个 phase，按 manifest 顺序。此时规则 2 由 batch 既有的 `_check_dependency_order`（被依赖者必须在前）自动满足。**degenerate plan 已足以跑依赖链**（每 task 后 merge → 下一 task 看得见）——C7 不依赖 C1 先落地，C1 提供的是并行加速，不是正确性。

### 2.2 Output Schema

> 填写约定同 C2：`always` / `conditional`；path 字段一律绝对路径。

```yaml
type: object
required: [schema_version, status, base_branch, phases, state_file_path]
properties:
  schema_version:
    type: string
    description: "always；C7 output schema 版本，当前 'v0.1.0'（与 C2 / batch schema 解耦）"
  status:
    enum: [all_merged, stopped, dry_run]
    description: 'always；run 终态。stopped = 出现 parked task，fail-stop 于 phase 边界'
  base_branch:
    type: string
    description: 'always；整合目标分支（= manifest 统一 base_branch）'
  phases:
    type: array
    description: 'always；按 phase 顺序'
    items:
      type: object
      required: [phase, status, tasks]
      properties:
        phase: { type: integer }
        status:
          enum: [merged, parked, skipped, dry_run]
        tasks:
          type: array
          items:
            type: object
            required: [task_id, state]
            properties:
              task_id: { type: string }
              state:
                enum: [merged, parked, skipped, dry_run]
                description: 'task 终态（中间态只活在 state file 里，不出现在 Output）'
              c2_output:
                type: object
                description: 'conditional（task 被 dispatch 过）；C2 §2.2 TaskOutput 原样嵌入'
              park_reason:
                enum: [TASK_FAILED, TASK_ERROR, REBASE_CONFLICT, REVERIFY_FAILED, MERGE_NOT_FF]
                description: 'conditional（state=parked 时必填）；语义见 §3.3'
              merged_sha:
                type: string
                description: 'conditional（state=merged 时必填）；merge 后 base_branch HEAD'
              rebased:
                type: boolean
                description: 'conditional（进过整合子流程时填）；true = 走了 rebase-requeue'
              reverify_pass:
                type: boolean
                description: 'conditional（rebased=true 时必填）；rebase 后重跑 verify_cmd 的结果'
  stopped_at_phase:
    type: integer
    description: 'conditional（status=stopped 时必填）；首个 parked phase 编号'
  state_file_path:
    type: string
    description: 'always；本 run 的 versioned state file 绝对路径（dry_run 时也填，见 §3.2 dry_run 边界）'
```

#### Phase-state file schema（落盘产物，公开 artifact — resume 与 dogfood 都读它）

路径（同 C5/C6 versioned + latest 落盘 pattern；`safe_base_branch` 转义规则复用 C6 §3.2，`/` `:` `?` → `-`）：

- versioned：`<repo_root>/.suiyin/phase-state/<safe_base_branch>-<run_ts>.json`（run 内每次状态转移后**原子覆写**：temp + rename）
- latest 镜像：`<repo_root>/.suiyin/phase-state/latest-<safe_base_branch>.json`

> 锚点适配说明：todo.md P1.3 锚点写的是 `<safe_pr_ref>`。C7 v0.1.0 的调度单位是 feature batch（task→feature 层没有 PR，见 I6），故 key 取 `base_branch`——与锚点同义（都是"这次整合流的唯一标识"），措辞随架构落地修正。

```yaml
type: object
required: [schema_version, run_id, manifest_path, manifest_sha256, base_branch, status, phases, merge_queue, updated_at]
properties:
  schema_version: { type: string }
  run_id: { type: string, description: '<run_ts> 派生，全 run 不变' }
  manifest_path: { type: string }
  manifest_sha256: { type: string, description: 'resume 时校验 manifest 没被改过；不符 → STATE_CORRUPTED' }
  base_branch: { type: string }
  status: { enum: [in_progress, all_merged, stopped] }
  dry_run: { type: boolean }
  phases:
    type: array
    items:
      type: object
      properties:
        phase: { type: integer }
        status: { enum: [pending, executing, integrating, merged, parked, skipped] }
        tasks:
          type: array
          items:
            type: object
            properties:
              task_id: { type: string }
              state: { enum: [pending, executing, awaiting_merge, integrating, merged, parked, skipped] }
              park_reason: { type: string }
              merged_sha: { type: string }
              requeue_count: { type: integer, description: 'rebase-requeue 已重试次数（todo 锚点 retry_count 的落地）' }
              worktree_path: { type: string }
  merge_queue:
    type: array
    items: { type: string }
    description: '待整合 task_id 队列快照（完成序 = 整合优先级；todo 锚点"队列优先级"的落地）'
  updated_at: { type: string }
```

### 2.3 Error Schema

Error 形态与 Output 形态**互斥**（同 C6 顶层 shape 约定）。

```yaml
type: object
required: [code, message]
properties:
  code:
    enum:
      - MANIFEST_NOT_FOUND      # 透传 batch loader（tasks.yaml 不存在 / 不可读）
      - INVALID_MANIFEST        # 透传 batch loader（yaml/schema 校验失败；含 precheck_refs_on_base 失败）
      - INVALID_PLAN            # execution_plan 校验失败（§2.1 规则 1/2/3 任一）
      - COORDINATOR_LOCKED      # 同 repo_root + base_branch 已有活跃 coordinator（I9，发现 #8）
      - STATE_CORRUPTED         # resume 时 state file 解析失败 / manifest_sha256 不符 / state 与 git 事实矛盾（声称 merged 但 sha 非 base 祖先）
      - REPO_ROOT_NOT_FOUND     # --repo-root 不是目录
      - GIT_ERROR               # git binary / 仓库异常（区别于整合失败 — 那是 park，不是 Error）
  message: { type: string }
  details: { type: object }
  retryable:
    type: boolean
    description: '仅 GIT_ERROR 为 true，其余 false'
```

**分层原则**（同 C6 reason/code 分离）：**task/phase 级失败是 park（出现在 Output `park_reason`），run 级失败才是 Error**。C2 跑挂不是 C7 的 Error——C7 正常完成了它的工作（调度 + 判定 + 落盘 + 停车）。

## 3. Behavior Contract

### 3.1 Invariants

前四条直接落地 todo.md P1.3 的 spec 预设锚点（2026-05-28 讨论沉淀）：

- **I1（确定性状态机）**：状态转移 = 纯函数 transition table，输入只有(a) 下游组件输出的语义字段、(b) git 可观察事实（ff 可达性 / rebase 退出码 / verify 退出码）、(c) 本 spec 枚举的配置。**routing path 上零 AI 调用**。同 input + 同组件结果 → 逐 bit 相同的决策序列（AC-9）。
- **I2（路由集中）**：C7 是工具链**唯一路由权威**。只消费下游输出的语义字段（C2 `status`；未来 C6 `reason` / `recovery_action.kind`），下游 schema **禁止**出现 `next_action_owner` 等拓扑字段，C7 输出同样不含指挥第三方的拓扑字段——拓扑只活在 C7 transition table 里。理由：拓扑随阶段切换（P1.2 = 人 / P1.3+ = C7 / SaaS = merge queue），写进组件 schema 会引爆 churn。
- **I3（状态落盘）**：每次状态转移后**先落盘再执行下一动作**（原子覆写 versioned + latest，schema 见 §2.2）。crash（含 kill -9）后 state file 必反映最后一次完成的转移；`resume=true` 时按以下确定性规则续跑：
  | state file 中的 task state | resume 动作 |
  |---|---|
  | `merged` | 跳过；先校验 git 事实（merged_sha 是 base HEAD 祖先），不符 → `STATE_CORRUPTED` |
  | `executing`（crash 时 session 在跑） | 重 dispatch C2（C2 I4 续命同 worktree；幂等重验已实证，todo 发现 #8 附带验证） |
  | `awaiting_merge` / `integrating` | 重入整合子流程（§3.3） |
  | `parked` | 保持 parked；仅 `retry_parked` 点名时重试（整合类 park → 重入整合；task 类 park → 重 dispatch） |
  | `pending` / `skipped` | 照常调度 |
- **I4（harness 边界）**：C7 调下游组件时，组件 Error / 非预期输出 → **确定性 park / stop + surface**，绝不把错误丢给 LLM session "想办法"。C7 自身 exit code：**0 = all_merged / 1 = stopped / 2 = Error**；caller（sy-* harness / dogfood orchestrator）对非 0 必须 stop + surface to human。此规则先于 C7 存在（P1.2 约定），本 spec 把它从约定升格为契约。
- **I5（逐 phase merge）**：phase N+1 的任何 worktree 创建，必须发生在 phase N **全部** task ff-merge 进 base_branch 之后。依赖链的可见性只靠 base 前进传递（头号发现的 closure）。
- **I6（task→feature 本地 merge 语义，关发现 #7）**：C7 整合 task 用**本地 ff-merge** `task/<id>` → base_branch；**不 push 任何分支、不开 task PR**。PR 只存在于 feature→main 层（C6 域）；base_branch 是否上 remote 是用户的事，C7 不越权。
- **I7（ff-only）**：base_branch 历史只接受 ff 前进。非 ff 时走 rebase-requeue 子流程（§3.3）；绝不产 merge commit、绝不 force、绝不 squash。
- **I8（隔离不回滚，关 Q7）**：已 merge 进 base_branch 的 task **永不回滚**——它们是 verify 过的 ff 增量，回滚 = 改写 feature 历史（违 I7）+ 销毁已验证工作。卡住的 task **隔离**：park + worktree 完整保留现场。phase 内任一 task park → phase 标 parked，后续 phase 全 skipped（fail-stop 于 phase 边界——后续 phase 可能依赖被 park 的 task，半推进没有意义）。
- **I9（单实例锁，关发现 #8 的 coordinator 半边）**：同一 `repo_root` + `base_branch` 同时至多一个 coordinator 实例。pid file lock `<repo_root>/.suiyin/locks/coordinator-<safe_base_branch>.lock`（`O_CREAT|O_EXCL` 原子创建，内容 = pid + run_id + start_ts）：锁存在且 pid 活 → `COORDINATOR_LOCKED` 拒跑，**绝不静默复用 worktree**；pid 死（stale）→ 确定性接管（覆写）。正常 / Error 退出都释放锁（finally 语义）。
- **I10（rebase 后必重 verify）**：rebase 必然改变 task tree（commits 落到新 base 上，吸收了并行 task 的变更）→ merge 前必须在 task worktree 重跑该 task 的 `verify_cmd`，绿才 merge。比 C6 "rebase 干净则报告仍 valid" 更严——C6 场景是纯 base 推进，C7 场景是并行 task 合流，**语义冲突只有跑了才知道**。
- **I11（worktree 生命周期归 C7）**：C7 调度下，merged task 的 worktree + 本地 `task/<id>` 分支由 C7 清理；parked task 双双保留。C2 standalone 直跑时沿用 C2 既有约定（保留，人清理）。

### 3.2 Side Effects

- 经 C2 产生其全部副作用（worktree 创建 / session / commits）——属 C2 §3.2 域，C7 透传 `claude_cmd` 等注入
- **base_branch ref 本地前进**（每 task merge 一次）：refs-direct ff（实现建议见 §7，学 C6 v0.1.3 零 checkout 教训）
- task worktree 内执行 `git rebase <base_branch>`（requeue 路径）；conflict 时 `git rebase --abort` 还原现场再 park
- task worktree 内重跑 `verify_cmd`（I10）
- merged task：`git worktree remove` + `git branch -d task/<id>`（I11）
- phase-state 落盘（versioned + latest，§2.2）
- lock file 创建 / 释放（I9）
- **不做**：push 任何分支 / 开任何 PR / 动 main / 调 C5、C6（v0.1.0，见 Q7-3）/ 修改 spec.md、plan.md、tasks.yaml

#### dry_run 边界

- **跳过**：取锁、建 worktree、dispatch C2、一切 git 写操作、**latest 镜像更新**
- **仍执行**：manifest + execution_plan 全量校验、phase 计划输出（Output 形态，全 task `state=dry_run`）、versioned state file 落盘（带 `dry_run: true` 标）
- **跟 C6 v0.1.2 "落盘永远执行" 的偏离及理由**：C6 的 gate report 是只增 audit 记录；C7 的 **latest 镜像是 resume 入口（可变操作状态）**，dry_run 污染它会让下次真跑误 resume。versioned 文件保留 audit 语义（不丢），latest 保护 resume 语义——两个 pattern 各取其义。

### 3.3 Failure Modes

**(a) Park cases**（task/phase 级，出现在 Output `park_reason`，run 以 `status=stopped` 正常结束）：

| `park_reason` | 触发条件 | 处理动作 |
|---|---|---|
| `TASK_FAILED` | C2 返回 `status=failed`（重试是 C2 内政，到 C7 手里已 RETRY_EXHAUSTED） | park task；worktree 保留；phase parked → 后续 phase skipped → run stopped |
| `TASK_ERROR` | C2 抛 Error（TIMEOUT / SESSION_CRASHED / SPEC_NOT_FOUND …） | 同上；C2 Error 原样进 state file `details` |
| `REBASE_CONFLICT` | requeue rebase 出 conflict | `git rebase --abort` 还原 worktree → park；人解完 conflict 后 `--retry-parked` 重入整合 |
| `REVERIFY_FAILED` | rebase 干净但重跑 verify_cmd 非绿（并行 task 语义冲突实锤） | park，不 merge；v0.2 候选接 R2 retry-with-feedback（Q7-2） |
| `MERGE_NOT_FF` | requeue 重试超 `max_requeue` 仍非 ff（防御性；串行整合队列下理论不可达） | park；git 事实写入 state `details` |

**(b) Error cases**（run 级，§2.3）：发生即 abort（exit 2）；除 `COORDINATOR_LOCKED` / `STATE_CORRUPTED` 外都发生在取锁前的校验段，零副作用。

#### 整合子流程（merge queue，I7/I10 的执行体；Q6-2 (b) "重排队列" 在 task→feature 层的确定性定义）

task 达到 `awaiting_merge` 后进入**串行**整合队列（完成序）：

```
dequeue task
  ├─ task/<id> HEAD 是 base HEAD 的 ff 可达后代？
  │    ├─ 是 → ff-merge（refs-direct）→ merged；清理 worktree + 分支（I11）
  │    └─ 否（base 被同 phase 先完成者推进）→ requeue:
  │         rebase task/<id> onto base HEAD（worktree 内）
  │           ├─ conflict → abort rebase → park REBASE_CONFLICT
  │           └─ clean → 重跑 verify_cmd（I10）
  │                ├─ 非绿 → park REVERIFY_FAILED
  │                └─ 绿 → 回队列头重试 ff（requeue_count += 1；> max_requeue → park MERGE_NOT_FF）
```

phase barrier：本 phase 全部 task `merged` → phase `merged` → 进下一 phase；任一 park → 等 in-flight task 跑完（不中断已在跑的 session，其结果照常整合）→ phase `parked` → run stopped。

## 4. AI Prompt Template

**N/A — 路由 path 零 AI（I1）。** AI 只活在被调度的 C2 session 内部，其 prompt 属 C2 spec §4。C7 自身全部逻辑（计划校验 / 状态机 / 整合 / 落盘 / 锁）是纯 Python。

## 5. Acceptance Criteria

- **AC-1 依赖链闭环（degenerate plan，头号发现 closure）**：manifest 无 execution_plan，T-002 `depends_on` T-001（T-001 产出 T-002 要用的文件）→ 两 task 各自成 phase 串行；**T-002 worktree 创建时 base HEAD 已含 T-001 产物**（worktree 内可见该文件）；终态 `all_merged`，base_branch 含两个 task 的 commit 且全程 ff。
- **AC-2 execution_plan 调度（I5）**：`[{phase:1, parallel:[A,B]}, {phase:2, parallel:[C]}]` → C 的 worktree 创建时刻晚于 A、B 双双 merge；输出 phases 顺序与计划一致。
- **AC-3 fail-stop + 不回滚（I8，Q7）**：3 phase 计划，phase 2 的 task C2 failed → task `parked(TASK_FAILED)`，phase 2 `parked`，phase 3 全 task `skipped`，`status=stopped`、`stopped_at_phase=2`；**phase 1 已 merge 的 commit 仍在 base_branch（HEAD 不回退）**，parked worktree 保留。
- **AC-4 rebase-requeue（I7/I10，Q6-2 (b)）**：phase 内 A、B 并行（mock 双成功），A 先整合 → B 非 ff → B 被 rebase（干净）+ 重跑 verify（绿）→ merge；输出 B 项 `rebased=true, reverify_pass=true`，base_branch 全程无 merge commit。
- **AC-5 REBASE_CONFLICT**：同 AC-4 但 A、B 改同一文件同一行 → B rebase conflict → worktree 被还原到 rebase 前状态（无 conflict marker 残留）→ `parked(REBASE_CONFLICT)`，base_branch 只含 A。
- **AC-6 REVERIFY_FAILED**：B rebase 干净但重 verify 非绿 → 不 merge，`parked(REVERIFY_FAILED)`，base_branch 只含 A。
- **AC-7 coordinator 锁（I9，发现 #8）**：实例 1 持锁存活期间，实例 2 同 repo_root + base_branch 启动 → 即刻 Error `COORDINATOR_LOCKED`（exit 2），不创建 / 不触碰任何 worktree、不写 state。
- **AC-7b stale lock 接管**：lock file 存在但 pid 已死 → 新实例确定性接管（覆写锁）并正常开跑。
- **AC-8 crash resume（I3）**：任意时点 kill -9 coordinator → state file 反映最后一次完成的转移；`resume=true` 重跑 → `merged` task **不重 dispatch C2**（mock 调用计数为证），未完成 task 从 state 续跑，终态与不 crash 的 run 一致。
- **AC-8b retry_parked**：AC-5 之后人解掉 conflict，`--retry-parked B` 重跑 → B 不重 dispatch C2，直接重入整合并 merge。
- **AC-9 determinism（I1）**：mock 固定全部组件结果，同 input 跑 N ≥ 3 次 → 状态转移序列 + Output（剔除 timestamp / 路径时变量）完全一致。
- **AC-10 路由集中（I2）**：给 mock C2 output 注入 `next_action_owner: "human"` 等拓扑字段 → C7 决策与无该字段时逐项一致（忽略而非消费）；全 run 中 claude CLI 仅出现在 C2 dispatch 路径，C7 自身调用 0 次。
- **AC-11 exit code + dry_run 边界（I4，§3.2）**：`all_merged`→0 / `stopped`→1 / Error→2；dry_run：不取锁、不建 worktree、base_branch ref 不动、latest 镜像不动，versioned state（`dry_run:true`）+ 完整 phase 计划照常产出，exit 0。
- **AC-12 INVALID_PLAN（§2.1 校验）**：(a) execution_plan 漏列 task；(b) 同 phase 内出现 depends_on 边；(c) task 间 base_branch 不一致——三者各自 → Error `INVALID_PLAN`，零副作用。
- **AC-13 生命周期（I11）**：merged task → worktree 已删 + `task/<id>` 分支已删；parked task → 双双保留。

## 6. Open Questions

- **Q7**（从 `toolchain.md` C7 节继承）：phase 内某 task 卡住、其他已 merge——回滚还是隔离？**已拍，本 spec 关闭：隔离（I8）**。理由：已 merge 的 task 是 verify 过的 ff 增量，回滚 = 改写 feature 历史 + 销毁已验证工作 + 违 I7；park + 现场保留给人的信息量远大于回滚。**cascade：toolchain.md C7 节 + 附录 Q-table、workflows.md Q-table 本 PR 同步**（ADR-0001 governance）。
- **Q7-1**：phase 内真并行（`max_parallel > 1`）何时开闸？契约已并行安全（I5/I7/I10 下串行是并行的合法实现，差异仅 wall-clock），开闸前置：C1 execution_plan 实际质量（Q1 语义冲突精度）+ 多 claude session 资源占用实测。v0.1.0 默认 1。
- **Q7-2**：parked 的自动恢复——`REVERIFY_FAILED` / `TASK_FAILED` 是否接 R2 retry-with-feedback（把 verify 失败上下文注入 C2 重 dispatch）？v0.1.0 = 一律 park 等人（D 档哲学：异常即人出场）；R2 联动留 C7 v0.2 + C2 v0.2（todo P1.3 R2 项）。
- **Q7-3**：feature→main 收口——所有 phase merge 完后，C7 是否继续负责 push base_branch + 开 feature→main PR + 调 C4/C5/C6（全链无人）？v0.1.0 终点 = base_branch 聚合完成，收口留人 / 后续编排。此决策牵动 C6 caller 拓扑与 Q6-5（gate 触发时机），留 P1.3 末拍。
- **Q7-4**：state key 取 `base_branch`——同一 feature 先后跑**不同** manifest 会共享 latest 镜像（manifest_sha256 不符 → 现行为 STATE_CORRUPTED，需 `--no-resume` 显式绕过）。要不要 key 里加 manifest hash？倾向不加（PC-1：同 feature 多 manifest 本身就是该被喊停的状态）。

## 7. Implementation Notes

### 技术栈与工程约定

- Python 3.11+（同 C2/C6）；跨平台约定**全文继承 C2 §7 表**（pathlib / shell=False / `O_CREAT|O_EXCL` 锁跨平台、pid 探活用 `psutil.pid_exists`）
- C7 自身不管进程树生死（那是 C2 的 I7），只管 git + 状态 + 锁

### CLI（经 unified dispatcher 加 `phase` 子命令）

```bash
suiyin-flow phase run \
  --tasks .specify/specs/00X-feat/tasks.yaml \
  --repo-root /abs/path/to/v5 \
  [--dry-run] [--no-resume] [--retry-parked T-002,T-003 | all] \
  [--max-parallel 1] [--max-requeue 3]
```

exit code：0 = all_merged / 1 = stopped / 2 = Error（I4；caller 非 0 必须 stop + surface）。

### 模块拆分建议

```
suiyin_flow/
  c7_coordinator/
    __init__.py
    cli.py            # argparse 入口
    plan.py           # execution_plan 校验 + degenerate plan 推导
    statemachine.py   # I1 transition table（纯函数，独立可测）
    integrate.py      # ff-merge / rebase-requeue / reverify（§3.3 子流程）
    lock.py           # I9 pid file 锁
    state.py          # I3 落盘 + resume 规则
    schema.py         # Pydantic 模型（§2.1/2.2/2.3 + state file）
```

复用 batch 既有件：`load_tasks_yaml`（manifest 解析）、`precheck_refs_on_base`（spec_ref/plan_ref 在 base HEAD 可见性 fail-fast）、`BatchTaskEntry.to_task_input`。

### ff-merge 实现（学 C6 v0.1.3 教训：零 checkout）

base_branch 几乎必然被某个 worktree checkout（dogfood r2 实证：就是用户当前 worktree）→ **禁用一切 checkout 路径**。推荐 refs-direct：

```
git -C <repo_root> merge-base --is-ancestor <base> <task_head>   # ff 可达性判定
git -C <repo_root> update-ref refs/heads/<base_branch> <task_head_sha> <expected_old_sha>
```

`update-ref` 带 old-value 形式（CAS 语义）防 race。**已知 caveat**：base_branch 被 checkout 的那个 worktree，在 ref 前进后 working tree 落后于 ref（同 C6 推 main 的既有情形）——C7 在 run 结束输出里提示「base ref advanced，相应 worktree 需自行 sync」，不代替用户动他的 working tree。

### 跟其他 C 模块协作

- **调度 C2**：构造 TaskInput 同 batch；`claude_cmd` 透传。**C2 v0.2 联动需求（本 spec 是需求方，C2 spec bump 时落地）**：
  1. `open_pr: bool` input（default true 向后兼容；**C7 传 false**——I6，关发现 #7：task→feature 本地 merge，不 push 不开 PR）
  2. worktree 活跃 session 检测（worktree 内 `.suiyin/lock` pid 文件）——发现 #8 的 **C2 半边**：C7 的 I9 锁挡"同 manifest 双 coordinator"，C2 锁挡"coordinator 在跑 + 人又直跑单 task"的交叉竞态
  3. `--review-feedback`（R2，已有预案）——Q7-2 联动
- **C1 Planning Engine**：execution_plan 生产者；C7 只消费 + 校验，**不反向依赖**（degenerate plan 兜底）
- **C6 Gate Contract**：v0.1.0 无运行时交互（feature→main 收口留 Q7-3）。架构关系：**Q6-2 翻 (b) 后**，"NOT_FF_MERGEABLE → 重排队列"的队列语义就是本 spec §3.3 整合子流程在 task→feature 层的定义；feature→main 层在 C7 接管收口前维持人工 rebase 兜底
- **`task batch`（P1.2.5）**：保留不动（向后兼容，独立 task 场景仍最轻）。C7 **impl** 落地后 cascade：`skills/sy-tasks/SKILL.md` + `tasks-template.md` 的「任务独立性硬约束」解除 → 改为「依赖链 OK，标 depends_on；可选 execution_plan」；workflows.md / diagrams.md 主流程图按两级 merge（task→feature→main）重绘。**这些 cascade 属 impl PR，不在本 spec PR**（spec 先行，约束在工具能跑之前不能松）

### v4 自身 dogfood

天然验收件：v5 第一轮真闭环跑不动的那份 **5-task 依赖链 manifest**（login-credential-core，T-002/3/4 依赖 T-001 骨架、T-005 聚合）。C7 impl 后用它重跑——AC-1/AC-2/AC-3 的真实版。

### 跟 constitution 的关系

- **NC-1**（零 SaaS）：纯本地 git 操作，无 gh 依赖（连降级都不需要——根本不碰 remote，I6）✅
- **NC-3**（业务项目独立）：worktree / state / lock 全在业务项目 `<repo_root>` 下 ✅
- **NC-4**（worktree 隔离安全边界）：C7 不削弱 C2 的边界；自身只动 refs 与 `.suiyin/`，不动任何 working tree 内容（rebase 在 task 自己的 worktree 内）✅
- **NC-5**（跨平台）：继承 C2 §7 约定表 ✅
- **PC-1**（最简实现）：MVP 串行（max_parallel=1）、degenerate plan 不等 C1、v0.1.0 不接 C5/C6 ✅
- **PC-2**（组件 vs 契约分离）：imperative 组件，但路由核心按契约性质约束（I1）✅

---

**Version**: v0.1.0-draft
**Last Updated**: 2026-06-10
**Status**: draft — 待人审拍板（spec_pinning human gate）；落地 todo.md P1.3 四条 invariant 锚点（I1-I4），吸收真闭环 dogfood 发现 #头号（I5）/ #7（I6）/ #8（I9），关 Q7（I8）+ cascade 关 Q6-2 翻 (b)

**Changelog**:
- v0.1.0 (2026-06-10): 初稿。来源：2026-05-28 session 讨论沉淀（4 invariant 锚点）+ 2026-06-08~10 两轮真闭环 dogfood 实测（todo.md【真闭环 dogfood 实测发现】+【第二轮真闭环】）
