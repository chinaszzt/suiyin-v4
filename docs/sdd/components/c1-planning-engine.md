# C1 Planning Engine — Component Spec

> 把扁平 `tasks.yaml` 升级成「phase + 并行组」执行计划：静态依赖分层 + 文件冲突检测，输出 `execution_plan` 字段供 C7 Phase Coordinator 消费。核心定位是 **wall-clock 优化器，不是安全门**——并行正确性的安全网在 C7 整合子流程（rebase-requeue + I10 重 verify），C1 的冲突检测只决定「省多少时间」，不承担「保证不撞」。

## 0. Type

- [x] 自建组件（imperative logic — 需要写代码）
- [ ] 行为契约（declarative contract — 配置 + 编排）

**实现栈**：Python（Q-C-2 已拍）。CLI 入口拟为 `suiyin-flow plan run`（经 unified dispatcher，见 §7）。

**注意**：MVP 的核心是**确定性算法**（DAG 分层 + 集合重叠检测，零 AI）。toolchain.md C1 节列的「语义冲突分析（AI）」是可选增强 pass（`--semantic-pass`，默认关）——Q1 的 false positive 精度风险被「默认关 + 只能收紧」双重圈住。

## 1. Purpose

读 `tasks.yaml`（batch manifest v0.1.0 兼容），按 `depends_on` 拓扑分层 + 写入足迹冲突拆分，生成 `execution_plan: [{phase, parallel: [task_ids]}]` 写回 manifest，让 C7 能在 phase 内并行调度互不冲突的 task（Q7-1 开闸的前置之一）。

跟 degenerate plan（C7 缺省：每 task 一个 phase 串行）的本质区别：

```
degenerate:  N task → N phases 全串行 → 正确但 wall-clock = Σ(task)
C1:          N task → ≤N phases, 独立 task 同 phase → wall-clock ≈ Σ(max per phase)
```

正确性两者等价（都由 C7 I10 reverify 兜底）；C1 提供的纯粹是并行加速。

## 2. Public API

### 2.1 Input Schema

```yaml
type: object
required: [tasks_yaml_path, repo_root]
properties:
  tasks_yaml_path:
    type: string
    description: tasks.yaml 路径（batch manifest schema v0.1.0；tasks[] 含 task_id / depends_on / context_seeds / 可选 modifies，见「联动需求」）
  repo_root:
    type: string
    description: 业务项目根目录绝对路径（语义 pass 读 spec/plan 时解析相对路径用）
  dry_run:
    type: boolean
    default: false
    description: 只输出 plan 到 stdout，不写回 tasks.yaml
  semantic_pass:
    type: boolean
    default: false
    description: |
      可选 AI 语义冲突分析（toolchain C1 第三能力）。开启后起一个只读
      claude session 读 task 描述 + spec/plan，判断静态检测漏掉的
      「会动同一资源」对，输出只能**收紧**计划（拆并行），不能放宽（I4）。
      默认关 —— Q1 的 false positive 会过度串行化，先让确定性部分跑起来，
      实测精度后再决定开闸（同 Q7-1 的渐进哲学）。
  output_path:
    type: string
    description: 可选；写到别处而非原地写回（默认原地，I5 注释保留语义见 §3.1）
```

### 2.2 Output Schema

> 主产物是**写回后的 tasks.yaml**（新增 `execution_plan` 顶层字段，schema 与 [C7 spec §2.1](c7-phase-coordinator.md) 的消费定义**逐字一致**）。stdout 同时输出本 JSON 摘要。

```yaml
type: object
required: [schema_version, status, phases_count, tasks_count, execution_plan, written_to]
properties:
  schema_version:
    type: string
    description: "always；C1 output schema 版本，当前 'v0.1.0'"
  status:
    enum: [written, dry_run]
    description: always
  phases_count:
    type: integer
    description: always
  tasks_count:
    type: integer
    description: always
  execution_plan:
    type: array
    description: 'always；与写回 yaml 的内容一致'
    items:
      type: object
      required: [phase, parallel]
      properties:
        phase:
          type: integer
          description: 从 1 起连续递增
        parallel:
          type: array
          items: { type: string }
          minItems: 1
          description: 本 phase 内可并行的 task_id（按 manifest 原序）
  conflict_splits:
    type: array
    description: 'always（可空数组）；被冲突检测拆开的 task 对 + 依据，audit trail'
    items:
      type: object
      required: [task_a, task_b, reason, evidence]
      properties:
        task_a: { type: string }
        task_b: { type: string }
        reason:
          enum: [modifies_overlap, context_seeds_overlap, semantic_conflict]
        evidence:
          type: string
          description: 重叠的路径 / glob，或语义 pass 给的一句话理由
  semantic_pass:
    type: object
    description: 'conditional（when input.semantic_pass=true）；透明记录 AI pass 结果'
    properties:
      completed: { type: boolean }
      adjustments: { type: integer, description: '收紧的 task 对数' }
      fallback_reason:
        type: string
        description: 'session 失败时为什么 fallback 到纯静态结果（Q1-2）'
  written_to:
    type: string
    description: 'always；绝对路径；dry_run 时为 null'
```

### 2.3 Error Schema

```yaml
type: object
required: [code, message]
properties:
  code:
    enum:
      - MANIFEST_NOT_FOUND      # 透传 batch loader（tasks.yaml 不存在 / 不可读）
      - INVALID_MANIFEST        # 透传 batch loader（yaml / schema 校验失败）
      - CYCLE_DETECTED          # depends_on 成环（batch 顺序断言只挡前向引用，环要 C1 全图检测）
      - PLAN_SELF_CHECK_FAILED  # 产出未过 C7 三规则自检（I1；理论不可达，防御性）
      - WRITE_FAILED            # 写回 tasks.yaml 失败（权限 / 并发改动）
  message: { type: string }
  details: { type: object }
  retryable: { type: boolean }
```

注：语义 pass 的 session 失败**不是** Error——fallback 到纯静态结果 + `semantic_pass.fallback_reason` 记录（§3.3）。

## 3. Behavior Contract

### 3.1 Invariants

- **I1（自检后落盘）**: 写回前 execution_plan 必须通过 [C7 spec §2.1](c7-phase-coordinator.md) 的三条校验规则（task_id 集合恰好等于 tasks[]、depends_on 只指向更早 phase、base_branch 统一）。**自产自销必自检**——C1 的输出坏了应该死在 C1，不该让 C7 报 `INVALID_PLAN`。
- **I2（确定性）**: 静态 pass 同输入必同输出（byte-identical）。分层算法、冲突拆分顺序、phase 内排序全部确定（无随机、无时间戳、无 dict 序依赖）。语义 pass 的 AI 不确定性被 I4 圈住：它只能在确定性结果上做单调收紧。
- **I3（优化器不是安全门）**: 冲突检测**宁可 false positive（过度串行，只浪费 wall-clock）**，但不承诺 false negative = 0。漏检的并行写冲突由 C7 整合子流程兜底（rebase conflict → park `REBASE_CONFLICT`；rebase 干净但语义冲突 → I10 重 verify → park `REVERIFY_FAILED`）。**此 invariant 是 Q1 精度问题的定位锚**：精度影响的是加速比，不是正确性。
- **I4（语义 pass 只收紧）**: AI 输出只能把同 phase 的 task 对拆开，**不能**合并静态判定为冲突的对、不能改 depends_on、不能动 task 内容。AI 不在任何放宽路径上（同 C7 I1「AI 不在 routing path」的哲学）。
- **I5（manifest 最小侵入）**: 只新增 / 替换顶层 `execution_plan` 字段；`tasks[]` 内容、顺序、yaml 注释（含 sy-tasks 生成的顶部推理注释，r2 dogfood 实证其价值）原样保留。实现上用 marker 块追加而非整文件重序列化（§7）。
- **I6（phase 结构）**: phase 编号从 1 连续递增；每 task 的 phase = 1 + max(其 depends_on 的 phase)（最长路径分层，依赖跨多层时取最深）；冲突拆分只把 task 推向**更晚** phase；phase 内 `parallel` 按 manifest 原序。

### 3.2 Side Effects

- 写回 `tasks.yaml`（原地或 `output_path`；dry_run 时无任何写）
- `--semantic-pass` 时起一个**只读** claude session（同 C2 §7 Session 调用模式 4 flag；在临时 dir 跑，不在业务 worktree 内——session 只读分析输出 JSON，同 C5 I7 隔离哲学）
- 无 git 操作、无网络（语义 pass 的 claude API 除外）、不碰 worktree

### 3.3 Failure Modes

| 失败类型 | 触发条件 | 处理动作 |
|---|---|---|
| `MANIFEST_NOT_FOUND` / `INVALID_MANIFEST` | batch loader 失败 | 立即报错，零副作用 |
| `CYCLE_DETECTED` | depends_on 全图有环 | 立即报错，details 带环路径（例 `T-001 → T-003 → T-001`），零副作用 |
| `PLAN_SELF_CHECK_FAILED` | I1 自检失败 | 立即报错不落盘（防御性；出现 = C1 算法 bug） |
| `WRITE_FAILED` | 写回失败 | 报错；原文件不得半写（先写 temp 再原子 rename） |
| 语义 pass session 失败 | claude crash / timeout / 输出不可解析 | **非 Error**：fallback 纯静态结果 + `semantic_pass.fallback_reason`；语义 pass 是可选优化，失败不该阻塞 plan 产出（Q1-2 记录待实测复核） |

### 4. AI Prompt Template

**仅 `--semantic-pass` 使用**（静态 pass 零 AI）。

````markdown
# C1 Planning Engine — Semantic Conflict Pass

## Your Role
你是 C1 的语义冲突分析 pass。**只读分析**，判断候选并行 task 对会不会动同一资源。

## Input
- 候选并行对（静态检测后同 phase 的 task 对）:
{candidate_pairs_yaml}
- 每个 task 的描述 / spec_ref / plan_ref / context_seeds / modifies: 见 {tasks_yaml_path}
- spec / plan 全文可读（repo_root = {repo_root}）

## Steps
1. 逐对读两个 task 的语义（描述 + spec 相关 section）
2. 判断「并行实现是否会写同一文件 / 改同一接口 / 依赖对方未完成的产物」
3. 只输出**有冲突**的对；拿不准 = 不输出（false positive 的代价是过度串行，
   安全网在 C7，宁可漏报不误报 —— 注意这跟常规 reviewer 心智相反）

## Output（session 最后一行）
```json
{"conflicts": [{"task_a": "T-002", "task_b": "T-003", "reason": "一句话"}]}
```

## Constraints (来自 §3 contract)
- 只能收紧（输出冲突对），不能建议合并 / 改 depends_on / 改 task 内容（I4）
- 不写任何文件、不跑任何命令（只读分析）
- 输出不可解析时整个 pass 作废（C1 fallback 静态结果），不要输出散文
````

## 5. Acceptance Criteria

- **AC-1**: r3 形态的 5-task 依赖链（T-001 骨架 ← T-002/3/4 ← T-005 聚合，无 modifies 重叠）→ 输出 3 phases `[[T-001], [T-002,T-003,T-004], [T-005]]`
- **AC-2**: depends_on 成环（含跨多 task 环）→ `CYCLE_DETECTED` + details 带环路径，不落盘
- **AC-3**: 同 phase 候选对 `modifies` 重叠（含 glob 命中，例 `src/auth/**` vs `src/auth/login.ts`）→ 拆到不同 phase，`conflict_splits` 记 `modifies_overlap` + 重叠证据
- **AC-4**: 一方 `modifies` 缺省时 fallback 用 `context_seeds` 重叠判定（保守近似）→ 同样拆分，reason = `context_seeds_overlap`
- **AC-5**: 任意合法输入的产出**直接喂给 C7 的 plan 校验函数**全过（I1；用 c7_coordinator 的校验实现做 oracle，不另写一份规则）
- **AC-6**: 写回后 yaml 顶部注释 + tasks[] 内容 byte 级原样（I5），且整文件可被 batch loader + C7 重新解析
- **AC-7**: `dry_run=true` → 文件零修改，stdout 摘要含完整 execution_plan
- **AC-8**: 已有 execution_plan 的 manifest 重跑 → marker 块原位替换，幂等（连跑两次 byte-identical）
- **AC-9**: 无依赖无冲突的 N task → 1 个 phase 全并行
- **AC-10**: 同输入连跑两次输出 byte-identical（I2 确定性；静态 pass）
- **AC-11**: 语义 pass session 失败（mock crash）→ 静态结果正常落盘 + `semantic_pass.fallback_reason` 非空，exit 0

## 6. Open Questions

- **Q1**（从 toolchain.md 继承）: 语义冲突分析精度——false positive 过度串行化。**本 spec 的处置**：默认关 + I4 只收紧 + I3 把精度问题定位成加速比问题而非正确性问题。开闸条件：真 dogfood 实测（拿 v5 真 feature 的 tasks.yaml 对比开/关的 plan 差异 + C7 实跑 park 率）
- **Q1-2**: 语义 pass 失败 fallback（§3.3）vs strict 模式（用户显式要了 AI pass，失败要不要硬报错）？v0.1.0 = fallback + 透明记录；等真实使用反馈再决定要不要 `--semantic-pass-strict`
- **Q1-3**: `modifies` 字段谁来填？候选：(a) `/sy-tasks` 生成时让 AI 顺手声明（上游 skill 改造，cascade 到 `skills/sy-tasks` + `tasks-template.md`）；(b) 人补。倾向 (a)——AI 拆 task 时本来就知道每个 task 动哪些文件（r3 的 scope note 实践就是手工版 modifies）。**impl 后 cascade 项，不阻塞本 spec**
- **Q1-4**: phase 内并行度上限要不要进 execution_plan？**不**——那是 C7 的 runtime 资源参数（`max_parallel`），C1 只管静态结构。分层：C1 = 结构（谁能并行），C7 = 运行时（实际开几个）

## 7. Implementation Notes

### 技术栈与算法

- Python 3.11+（同 C2-C7）；跨平台约定继承 C2 §7 表
- **分层**：Kahn 拓扑排序变体——`phase(t) = 1 + max(phase(d) for d in t.depends_on)`（无依赖 = 1）。环检测在分层前跑（DFS 三色或 Kahn 残留法，记录环路径供 details）
- **冲突拆分**：同 phase 内逐对（按 manifest 序）检测足迹重叠；重叠 → 后者推到下一 phase（再与该 phase 检测，级联推进）。足迹 = `modifies`（支持 glob，`pathlib.PurePosixPath.full_match` / `fnmatch`）；一方缺省 → 双方 `context_seeds`（路径前缀重叠即冲突，目录 seed 视为其下全部）
- **写回**：marker 块 `# --- execution_plan (C1 generated, do not hand-edit) ---` 到 EOF；已存在 marker → 从 marker 起替换。先写 `tasks.yaml.tmp` 再 `os.replace`（WRITE_FAILED 不半写）。**不用 ruamel.yaml 整文件重序列化**——PC-1 最简 + I5 注释保留靠「不碰 marker 之前的内容」实现
- 语义 pass session：复用 C2 §7 Session 调用模式 + C5 的只读隔离（临时 dir cwd）

### CLI（经 unified dispatcher 加 `plan` 子命令）

```bash
suiyin-flow plan run \
  --tasks-yaml .specify/specs/00X-feat/tasks.yaml \
  --repo-root /abs/path/to/project \
  [--dry-run] [--semantic-pass] [--output <path>]
```

### 联动需求（C1 是需求方）

1. **batch manifest 加可选 `modifies` 字段**（`BatchTaskEntry`）：`list[str]`，glob 支持，缺省 = 未声明（fallback context_seeds）。纯新增可选字段，batch schema v0.1.0 内向后兼容（pydantic 容忍缺省；schema_version 不 bump——加载行为零变化，只有 C1 读它）
2. **`/sy-tasks` cascade**（impl 后，Q1-3）：生成 yaml 时为每 task 声明 `modifies`（r3 scope note 的结构化版），并可直接内联生成 execution_plan 的建议初稿？**不**——生成职责归 C1（确定性算法），sy-tasks 只声明事实（depends_on / modifies），保持「AI 声明事实、算法做规划」分界

### 跟其他 C 模块协作

- **C7 Phase Coordinator**：唯一消费方。C1 产 execution_plan → C7 校验 + 执行。C7 **不反向依赖** C1（degenerate plan 兜底，C7 spec §2.1 已定）；C1 也不调 C7
- **`task batch`（P1.2.5）**：不受影响——batch 不读 execution_plan（独立 task 场景仍最轻路径）
- **C2**：无直接交互（C1 不起 task session）

### v4 自身 dogfood

天然验收件（同 C7 的做法）：r3 那份 **5-task login-core manifest**（手写 execution_plan 3 phases 的那份）——删掉手写 plan 让 C1 重新生成，对比是否一致（AC-1 的真实版）；再开 `--semantic-pass` 看 AI 会不会对 scope note 已钉死边界的 task 误报冲突（Q1 first data point）。

### 跟 constitution 的关系

- **NC-1**（零 SaaS）：纯本地文件操作；语义 pass 的 claude CLI 与 C2/C5 同等地位 ✅
- **NC-3**（业务项目独立）：产物（tasks.yaml）在业务项目内 ✅
- **NC-4**（worktree 隔离）：语义 pass session 只读 + 临时 dir，不碰任何 working tree ✅
- **NC-5**（跨平台）：继承 C2 §7 约定表；glob 匹配用 posix 语义统一 ✅
- **PC-1**（最简实现）：静态算法 MVP，AI pass 默认关；marker 追加不引 ruamel ✅

---

**Version**: v0.1.0-draft
**Last Updated**: 2026-06-10
**Status**: draft — 待人审拍板（spec 先行，同 C7 PR #47 先例）；impl 等 spec 过审

**Changelog**:
- v0.1.0 (2026-06-10): 初稿。关键拍板：(1) 定位 = wall-clock 优化器非安全门（I3，把 Q1 精度降级为加速比问题，安全网 = C7 I10 reverify，r3 dogfood 已实证该兜底路径）；(2) 语义 pass 默认关 + 只收紧（I4）；(3) manifest 最小侵入 marker 写回（I5，保 sy-tasks 注释）；(4) 自检后落盘（I1，C7 校验函数当 oracle）。联动需求：batch `modifies` 可选字段 + sy-tasks cascade（Q1-3）。
