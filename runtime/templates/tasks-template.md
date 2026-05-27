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
    constitution_ref: docs/sdd/constitution.md  # optional; 默认即此值
    verify_cmd: "pytest tests/foo -q"   # C4 L1+L2 跑通的命令
    context_seeds:                      # list[str], 注入给 AI 的必读文件 (相对 repo_root)
      - src/foo/__init__.py
    ac_list:                            # list[str], 本 task 对应的 AC 编号
      - AC-1
      - AC-2
    criticality: medium                 # low | medium | high; high 会被 C2 拒绝 (走 C3)
    depends_on: []                      # list[task_id], P1.2.5 只做"被依赖必须在前"顺序断言
    max_retries: 3                      # optional, 0..3, 默认 3
    session_timeout_seconds: 7200       # optional, > 0, 默认 7200 (2h)
    base_branch: main                   # optional, 默认 "main"
```

### 字段语义

| 字段 | 必填 | 说明 |
|---|---|---|
| `schema_version` | ✅ | 当前固定 `v0.1.0`；C2 解析时会校验；bump 见 [batch.py](../../src/suiyin_flow/c2_executor/batch.py) BATCH_SCHEMA_VERSION |
| `feature_name` | ❌ | metadata 用；不影响 C2 行为 |
| `task_id` | ✅ | 唯一；写 yaml 时按执行顺序排列（depends_on 关系必须在前） |
| `spec_ref` / `plan_ref` | ✅ | C2 验证存在性（不存在 → SPEC_NOT_FOUND） |
| `verify_cmd` | ✅ | 单 task 完成判定；C4 §1+§2 范畴 |
| `context_seeds` | ✅ | AI 必读文件清单；空数组合法 |
| `ac_list` | ❌ | 默认空；Fork D 自然语言 AC 编号 |
| `criticality` | ❌ | 默认 `medium`；`high` 必须由 C3 Arbiter 调度（C2 拒接） |
| `depends_on` | ❌ | 默认空数组；P1.2.5 只校验顺序，不做拓扑/并行（留 P1.3 C1） |

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
    ac_list: [AC-1]
    criticality: medium

  - task_id: T-102
    spec_ref: specs/002-add-no-color-flag/spec.md
    plan_ref: specs/002-add-no-color-flag/plan.md
    verify_cmd: "pytest tests/c4_verify/test_report.py -q"
    context_seeds:
      - src/suiyin_flow/c4_verify/cli.py
      - src/suiyin_flow/c4_verify/report.py
    ac_list: [AC-2]
    criticality: medium
    depends_on: [T-101]

  - task_id: T-103
    spec_ref: specs/002-add-no-color-flag/spec.md
    plan_ref: specs/002-add-no-color-flag/plan.md
    verify_cmd: "pytest tests/c4_verify -q"
    context_seeds:
      - src/suiyin_flow/c4_verify/cli.py
    ac_list: [AC-3]
    criticality: medium
    depends_on: [T-102]
```

---

## 跑这份 yaml

```bash
# Dry-run: 解析 + 列 task, 不真起 session
suiyin-flow task batch \
  --tasks-yaml specs/002-add-no-color-flag/tasks.yaml \
  --repo-root "$(pwd)" \
  --dry-run

# 真跑
suiyin-flow task batch \
  --tasks-yaml specs/002-add-no-color-flag/tasks.yaml \
  --repo-root "$(pwd)"
```

输出 `BatchOutput` JSON（含 per-task 结果 + 整体 status）。

---

## 跟 P1.3+ 的演进关系

- **P1.3 C1 Planning Engine** 会在 yaml 上**增加** `execution_plan: [{phase, parallel: [task_ids]}]` 字段，
  然后 C7 Phase Coordinator 按 phase 调度。**schema 不变，只是新增字段**。
- **R2** C2 retry-with-feedback：每 task 自动加 review feedback 作 context 重试。
- **P1.4** C3 双 AI 实现 + 仲裁：`criticality: high` task 会被 C3 接走。

所以**今天写的 tasks.yaml 一直是 task 真相载体**，不用迁移。
