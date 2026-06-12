---
description: "v4 tasks.yaml template — Fork A: yaml is the truth source, not tasks.md"
output_filename: tasks.yaml
---

# v4 Task List Template (Fork A: tasks.yaml)

> **v4 IMPORTANT**: 这个文件是 spec-kit `/sy-tasks` 借用的 template，**但 v4 已 Fork A 拍板**：
> task 真相载体 = `tasks.yaml`（不是默认的 `tasks.md`）。
>
> 模型读完这份模板后，**必须**在 `FEATURE_DIR/tasks.yaml` 写出符合下述 schema 的 yaml 文件，
> 而不是 markdown checklist。C2 Task Executor 的 batch adapter (`suiyin-flow task batch`)
> 直接消费这个 yaml；md 仅在 P2+ 由 render 工具二次生成给人看。
>
> **🔴 任务边界规则（C1 落地后版，2026-06-11）**：执行器有两档，规则随档位走——
>
> - **C7 `suiyin-flow phase run`（默认推荐）**：逐 phase merge——phase N 全部 task
>   ff-merge 回 `base_branch` 后 phase N+1 才分叉，**依赖链成立**。按构建顺序拆 task +
>   标 `depends_on` + **每 task 声明 `modifies`（写足迹）**。**同 phase 并行组内
>   task 不可触碰同一文件**（并行 fork 靠 rebase 整合，同文件 = conflict = park）：每个
>   共享文件恰好一个 task 拥有，聚合类文件（barrel / index / 注册表）归最后的聚合 task
>   （r3 dogfood 实证 pattern）。**execution_plan 不手写**——跑 `suiyin-flow plan run`
>   由 C1 从 depends_on + modifies 确定性生成（漏声明 modifies → C1 退化用
>   context_seeds 重叠近似 → 过度串行，T-009 实证）。
> - **P1.2.5 `task batch`（仅独立 task）**：每 task 从 base HEAD 独立分叉、产物互不可见，
>   旧硬约束仍生效——task 必须 self-contained，顺序构建塌缩成 1 个 task，`depends_on`
>   只是顺序声明不传递代码，`modifies`/`execution_plan` 被忽略。

---

## 输出文件

- **路径**：`FEATURE_DIR/tasks.yaml`（FEATURE_DIR 来自 setup-tasks.sh 的 `FEATURE_DIR`）
- **格式**：YAML 1.2，UTF-8

---

## Schema (v0.1.0)

```yaml
schema_version: v0.1.0
feature_name: 001-feature-slug          # spec-kit feature 目录名 (string, optional)
tasks:                                  # list[BatchTaskEntry], 必须 ≥ 1
  - task_id: T-001                      # 全 repo 唯一; pattern ^T-\d{3,}$
    spec_ref: specs/001-feature/spec.md # spec.md 路径 (相对 repo_root)
    plan_ref: specs/001-feature/plan.md # plan.md 路径
    constitution_ref: .specify/memory/constitution.md  # optional; 默认即此值
    verify_cmd: "pytest tests/foo -q"   # C4 L1+L2 跑通的命令
    context_seeds:                      # list[str], 注入给 AI 的必读文件 (相对 repo_root)
      - src/foo/__init__.py
    modifies:                           # list[str], 本 task 的写足迹 (glob OK); C1 分组依据
      - src/foo/service.py
      - tests/foo/**
    ac_list:                            # list[str], 本 task 对应的 AC 编号
      - AC-1
      - AC-2
    criticality: medium                 # low | medium | high; high 会被 C2 拒绝 (走 C3)
    depends_on: []                      # list[task_id]; C7 下只能指向更早 phase 的 task
    max_retries: 3                      # optional, 0..3, 默认 3
    session_timeout_seconds: 7200       # optional, > 0, 默认 7200 (2h)
    base_branch: main                   # optional, 默认 "main"; C7 要求全部 task 一致
# execution_plan 不要手写: 跑 `suiyin-flow plan run --tasks-yaml <path> --repo-root <p>`
# 由 C1 从 depends_on + modifies 确定性生成 (marker 块追加到文件尾, 幂等可重跑)
```

### 字段语义

| 字段 | 必填 | 说明 |
|---|---|---|
| `schema_version` | ✅ | 当前固定 `v0.1.0`；C2 解析时会校验；bump 见 [batch.py](../../src/suiyin_flow/c2_executor/batch.py) BATCH_SCHEMA_VERSION |
| `feature_name` | ❌ | metadata 用；不影响 C2 行为 |
| `task_id` | ✅ | 唯一；写 yaml 时按执行顺序排列（depends_on 关系必须在前） |
| `spec_ref` / `plan_ref` | ✅ | C2 验证「在 `base_branch` HEAD 可见」（C2 v0.2.1；不可见 → SPEC_NOT_FOUND，**未提交的文件不算存在**） |
| `verify_cmd` | ✅ | 单 task 完成判定；C4 §1+§2 范畴。C7 下 rebase 后还会用它重 verify（I10） |
| `context_seeds` | ✅ | AI 必读文件清单（同样要求在 base_branch 上已提交）；空数组合法。**建议含本 task 的 scope note**（钉 session 行为边界） |
| `modifies` | 🔶 强烈建议 | 本 task 的**写足迹**（文件路径 / glob，例 `src/auth/**`）。**C1 `plan run` 的并行分组依据**（r3 scope note 的结构化版）：同 phase 候选里 modifies 重叠的 task 对会被拆开。**漏声明的代价**：C1 退化用 context_seeds 重叠近似 → 共读文件的 task 被过度串行（T-009 场景 3 实证 3 phase → 5 phase，安全但慢）。**1:1 归属原则**：每个共享文件恰好一个 task 拥有；聚合文件（barrel / index / 注册表）归聚合 task。batch / C2 / C7 不读此字段 |
| `ac_list` | ❌ | 默认空；Fork D 自然语言 AC 编号 |
| `criticality` | ❌ | 默认 `medium`；`high` 必须由 C3 Arbiter 调度（C2 拒接） |
| `depends_on` | ❌ | 默认空数组。batch：只校验顺序、**不传递代码可见性**。C7：依赖通过逐 phase merge 真实可见，但边只能指向**更早 phase**（同 phase 内依赖 → `INVALID_PLAN`） |
| `execution_plan` | ❌（**勿手写**） | C7 phase 分组（batch 忽略此字段）。**由 C1 `suiyin-flow plan run` 从 depends_on + modifies 确定性生成**（marker 块追加文件尾，幂等可重跑；分界拍板见 c1 spec §7：AI 声明事实，算法做规划）。校验三规则：恰好覆盖 `tasks[]` 全集 / 依赖只指向更早 phase / 全部 task `base_branch` 一致。缺省 → C7 退化为每 task 一 phase 串行（依赖链照跑） |

### Schema-level 校验（C2 batch adapter 落地）

- `task_id` 在 `tasks[]` 内**不可重复**
- `depends_on` 中每个 ID 必须**早于**本 task 出现，否则报 `BATCH_ORDER_VIOLATION`
- `depends_on` 不可包含**自身**

---

## 执行顺序

`suiyin-flow task batch --tasks-yaml <path>` 按 `tasks[]` 的**列表顺序**串行跑：

1. 顺序遍历 → 调 C2 `execute_task`
2. 中间 task fail → 立即停 + 剩余 task 标 `skipped`（无 phase 回滚，P1.3 C7 加）
3. `--dry-run` → 仅解析 + 列 task，不真起 session

> **不做拓扑排序 / 并行 / phase 调度**：P1.2.5 故意收窄 scope，把"依赖图驱动调度"留给 P1.3 C1 Planning Engine。yaml 里允许写 `depends_on` 是为了未来 C1 接 manifest 时不用迁移格式。

---

## Task 生成原则（给 sy-tasks model 的指引）

1. **从 spec.md 抽 AC**：把 AC 按依赖关系分组，每组对应一个 task
2. **任务粒度**：单 task ≈ "AI 一次 session 能改完 + verify 能跑过" 的范围（一般 1-3 个文件 + 测试）
3. **顺序**：spec setup / foundational / 各 user story / polish；同 story 内 model 先于 service 先于 endpoint
4. **`context_seeds` 必填**：每个 task 至少列 1 个文件（spec.md 之外的真相源）
5. **`verify_cmd`**：尽量精确到本 task 受影响的测试目录或 marker，避免每次跑全量
6. **`criticality`**：默认 `medium`；只有触碰 NON-NEGOTIABLE 原则（认证 / 支付 / 数据迁移 / 跨 module 重构）才打 `high`，那种 task 会被 C2 拒接转去 C3 Arbiter
7. **`modifies` 每 task 都给**：拆 task 时你本来就决定了每个 task 动哪些文件——把它写下来（1:1 归属，聚合文件归聚合 task）。这直接决定 C1 能并行多少：声明全 → 互不重叠的 task 同 phase 并行；漏声明 → 退 context_seeds 近似被过度串行。**不要用宽 glob 偷懒**（`src/**` 等于告诉 C1 "我可能动一切" → 跟谁都冲突 → 全串行）

---

## 完整示例（小型 feature, 3 个 task 串行）

```yaml
schema_version: v0.1.0
feature_name: 002-add-no-color-flag

tasks:
  - task_id: T-101
    spec_ref: specs/002-add-no-color-flag/spec.md
    plan_ref: specs/002-add-no-color-flag/plan.md
    verify_cmd: "pytest tests/c4_verify/test_report.py -q"
    context_seeds:
      - src/suiyin_flow/c4_verify/report.py
    modifies:
      - src/suiyin_flow/c4_verify/report.py
      - tests/c4_verify/test_report.py
    ac_list: [AC-1]
    criticality: medium

  - task_id: T-102
    spec_ref: specs/002-add-no-color-flag/spec.md
    plan_ref: specs/002-add-no-color-flag/plan.md
    verify_cmd: "pytest tests/c4_verify/test_report.py -q"
    context_seeds:
      - src/suiyin_flow/c4_verify/cli.py
      - src/suiyin_flow/c4_verify/report.py
    modifies:
      - src/suiyin_flow/c4_verify/cli.py
    ac_list: [AC-2]
    criticality: medium
    depends_on: [T-101]

  - task_id: T-103
    spec_ref: specs/002-add-no-color-flag/spec.md
    plan_ref: specs/002-add-no-color-flag/plan.md
    verify_cmd: "pytest tests/c4_verify -q"
    context_seeds:
      - src/suiyin_flow/c4_verify/cli.py
    modifies:
      - docs/c4-usage.md
      - tests/c4_verify/test_cli_no_color.py
    ac_list: [AC-3]
    criticality: medium
    depends_on: [T-102]
```

---

## 跑这份 yaml

```bash
# 1. C1 生成 execution_plan (依赖分层 + modifies 冲突拆分; --dry-run 先看不写)
suiyin-flow plan run \
  --tasks-yaml specs/002-add-no-color-flag/tasks.yaml \
  --repo-root "$(pwd)"

# 2. C7 按 phase 调度 (默认推荐; 依赖链 + 逐 phase merge)
suiyin-flow phase run \
  --tasks specs/002-add-no-color-flag/tasks.yaml \
  --repo-root "$(pwd)"

# 备选: 完全独立 task 时可直接 batch (忽略 modifies/execution_plan)
suiyin-flow task batch \
  --tasks-yaml specs/002-add-no-color-flag/tasks.yaml \
  --repo-root "$(pwd)" \
  --dry-run
```

`plan run` 输出 `PlanOutput` JSON（含 execution_plan + conflict_splits audit）；
`phase run` 输出 `PhaseRunOutput`；`task batch` 输出 `BatchOutput`。

---

## 跟 P1.3+ 的演进关系

- **C1 Planning Engine ✅ (2026-06-11)**：`suiyin-flow plan run` 在 yaml 上**追加**
  `execution_plan` 字段（marker 块，幂等），C7 按 phase 调度。schema 不变。
- **R2 C2 retry-with-feedback ✅ (C2 v0.3.0)**：`--review-feedback` 把 C5 findings 注入
  retry context（自动重投编排留 Q7-2）。
- **P1.4** C3 双 AI 实现 + 仲裁：`criticality: high` task 会被 C3 接走。

所以**今天写的 tasks.yaml 一直是 task 真相载体**，不用迁移。
