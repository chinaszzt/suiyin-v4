---
name: "sy-tasks"
description: "Generate an actionable, dependency-ordered tasks.yaml for the feature based on available design artifacts."
argument-hint: "Optional task generation constraints"
compatibility: "Requires spec-kit project structure with .specify/ directory"
metadata:
  author: "github-spec-kit (v4 forked)"
  source: "templates/commands/tasks.md"
user-invocable: true
disable-model-invocation: false
---

## v4 OVERRIDE — tasks.yaml, not tasks.md  (Fork A)

> **碎银 v4 已 Fork A 拍板：task 真相载体是 `tasks.yaml`，不是 spec-kit 默认的 `tasks.md`。**
> 正文 Outline / Task Generation Rules 已按此改写（2026-08-13，M3 PR 0 清理 spec-kit 残留）；本块是输出契约的权威。
>
> **输出契约**：
> 1. **文件名**：`FEATURE_DIR/tasks.yaml`（不是 `tasks.md`）
> 2. **顶层 schema**（v0.1.0）：
>    ```yaml
>    schema_version: v0.1.0
>    feature_name: <feature 目录名>          # optional metadata
>    tasks:                                   # list, ≥ 1, **按执行顺序排列**
>      - task_id: T-001                       # LOCAL_ID_PATTERN: 字母数字开头, 允许 ._- , ≤64 字符; feature 内唯一
>        spec_ref: specs/<feature>/spec.md    # 相对 repo_root
>        plan_ref: specs/<feature>/plan.md
>        constitution_ref: .specify/memory/constitution.md  # optional
>        verify_cmd: "pytest tests/foo -q"    # C4 L1+L2 跑通的命令
>        context_seeds: [src/foo/main.py]     # AI 必读文件清单
>        modifies: ['src/foo/main.py', 'tests/foo/**']  # 写足迹 (glob OK); C1 分组依据
>        ac_list: [AC-1]                      # spec.md 里的 AC 编号
>        criticality: medium                  # low | medium | high
>        depends_on: []                       # optional; C7 下指向更早 phase 的 task
>        max_retries: 3                       # optional
>        session_timeout_seconds: 7200        # optional
>        base_branch: main                    # optional; 全部 task 必须一致 (C7)
>    # execution_plan 不要手写 —— 跑 `suiyin-flow plan run` 由 C1 从
>    # depends_on + modifies 确定性生成 (marker 块追加, 见第 5/6 条)
>    ```
> 3. **schema 约束**（C2 batch 解析时强校验）：
>    - 全局身份 = `feature_id + task_id`（feature_id 由 spec_ref 推导）；不同 feature 的同名 task_id 不冲突，**不需要跨 feature 续号**
>    - `task_id` 在 `tasks[]` 内不可重复
>    - `depends_on` 中每个 ID **必须早于本 task 出现**（违反 → `BATCH_ORDER_VIOLATION`）
>    - `depends_on` 不可含自身
> 4. **任务粒度**：单 task ≈ AI 一次 session 能改完 + verify 能跑过（一般 1-3 个文件 + 测试）
> 5. **执行**：用户后续先跑 `suiyin-flow plan run --tasks-yaml <path> --repo-root <p>`
>    （C1 生成 execution_plan 并行分组），再 `suiyin-flow phase run --tasks <path>
>    --repo-root <p>`（C7，默认推荐）；或 `suiyin-flow task batch --tasks-yaml <path>
>    --repo-root <p>`（仅限完全独立 task，忽略 modifies/execution_plan）
> 6. **🔴 任务边界规则（C1 落地后版，2026-06-11）**：C7 Phase Coordinator
>    **逐 phase merge**——phase N 全部 task ff-merge 回 `base_branch` 后，phase N+1 的
>    worktree 才分叉，**依赖链成立**（"T-002 用 T-001 建的文件" 现在能跑）。因此：
>    - **依赖链 OK**：按构建顺序拆 task，标 `depends_on`
>    - **每 task 必须声明 `modifies`（写足迹，1:1 文件归属）**——这是 r3 scope note 的
>      结构化版：**每个共享文件恰好一个 task 拥有**；聚合类文件（barrel / index / 注册表）
>      归最后的聚合 task（r3 实证 pattern：src/index.ts 归 T-005，T-002/3/4 禁碰）。
>      context_seeds 的 scope note 仍建议给（钉 session 行为边界），modifies 钉调度边界
>    - **execution_plan 不手写**：C1 `suiyin-flow plan run` 从 depends_on + modifies
>      确定性生成（分界拍板见 c1 spec §7：AI 声明事实，算法做规划）。**漏声明 modifies
>      的代价**：C1 退化用 context_seeds 重叠近似 → 共读文件的 task 被过度串行
>      （T-009 场景 3 实证：3 phase 串成 5 phase，安全但慢）
>    - `depends_on` 边只能指向**更早 phase** 的 task（同 phase 内依赖 → C7 报 INVALID_PLAN）
>    - **仅用 batch（不用 C7）时旧硬约束仍生效**：task 必须完全独立（不共享新建文件、
>      verify 各自可跑），顺序构建塌缩成 1 个 self-contained task
>    - 来源：P1.2.5 真闭环 dogfood 头号发现（batch 跑不动依赖链）→ C7 spec v0.1.0 +
>      r3 dogfood (2026-06-10, 5-task 依赖链 all_merged 实证) + C1 v0.1.0 (T-009,
>      2026-06-11)。见 todo.md
>
> **不再生成的内容**：spec-kit 原 template 的 markdown checkbox 格式、`[P]` `[Story]` 标签、"Parallel Example" 节、"Implementation Strategy" 节 —— 这些信息**全部融入 yaml 字段语义**（顺序 = `tasks[]` 顺序；并行/phase 划分由 C1 Planning Engine 从 depends_on + modifies 算出，不再人写）。
>
> **完整模板**：见 `runtime/templates/tasks-template.md`（虽然文件名是 `.md` 但内容是 yaml schema 指引；resolver 暂时按 `.md` 后缀查）。
>
> **Step 5 Report** 也按这个改：输出 `tasks.yaml` 路径 + task 数量 + 依赖关系摘要（不再报"Format validation: checklist 格式"）。

---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).

## Pre-Execution Checks

**Check for extension hooks (before tasks generation)**:
- Check if `.specify/extensions.yml` exists in the project root.
- If it exists, read it and look for entries under the `hooks.before_tasks` key
- If the YAML cannot be parsed or is invalid, skip hook checking silently and continue normally
- Filter out hooks where `enabled` is explicitly `false`. Treat hooks without an `enabled` field as enabled by default.
- For each remaining hook, do **not** attempt to interpret or evaluate hook `condition` expressions:
  - If the hook has no `condition` field, or it is null/empty, treat the hook as executable
  - If the hook defines a non-empty `condition`, skip the hook and leave condition evaluation to the HookExecutor implementation
- When constructing slash commands from hook command names, replace dots (`.`) with hyphens (`-`). For example, `sy.git.commit` → `/sy-git-commit`.
- For each executable hook, output the following based on its `optional` flag:
  - **Optional hook** (`optional: true`):
    ```
    ## Extension Hooks

    **Optional Pre-Hook**: {extension}
    Command: `/{command}`
    Description: {description}

    Prompt: {prompt}
    To execute: `/{command}`
    ```
  - **Mandatory hook** (`optional: false`):
    ```
    ## Extension Hooks

    **Automatic Pre-Hook**: {extension}
    Executing: `/{command}`
    EXECUTE_COMMAND: {command}
    
    Wait for the result of the hook command before proceeding to the Outline.
    ```
- If no hooks are registered or `.specify/extensions.yml` does not exist, skip silently

## Outline

1. **Setup**: Run `.specify/scripts/bash/setup-tasks.sh --json` from repo root and parse FEATURE_DIR, TASKS_TEMPLATE, and AVAILABLE_DOCS list. `FEATURE_DIR` and `TASKS_TEMPLATE` must be absolute paths when provided. `AVAILABLE_DOCS` is a list of document names/relative paths available under `FEATURE_DIR` (for example `research.md` or `contracts/`). For single quotes in args like "I'm Groot", use escape syntax: e.g 'I'\''m Groot' (or double-quote if possible: "I'm Groot").

2. **Load design documents**: Read from FEATURE_DIR:
   - **Required**: plan.md (tech stack, libraries, structure), spec.md (user stories with priorities)
   - **Optional**: data-model.md (entities), contracts/ (interface contracts), research.md (decisions), quickstart.md (test scenarios)
   - Note: Not all projects have all documents. Generate tasks based on what's available.

3. **Execute task generation workflow**:
   - Load plan.md and extract tech stack, libraries, project structure
   - Load spec.md and extract user stories with their priorities (P1, P2, P3, etc.)
   - If data-model.md exists: Extract entities and map to user stories
   - If contracts/ exists: Map interface contracts to user stories
   - If research.md exists: Extract decisions for setup tasks
   - Generate tasks organized by user story (see Task Generation Rules below)
   - Generate dependency graph showing user story completion order (`depends_on` edges)
   - Validate task completeness (each user story has all needed tasks, independently testable, every task has a runnable `verify_cmd`)

4. **Generate tasks.yaml**: Read the tasks template from TASKS_TEMPLATE (from the JSON output above; if empty, fall back to `.specify/templates/tasks-template.md`) as schema guidance, and write `FEATURE_DIR/tasks.yaml` per the v4 OVERRIDE schema at the top of this file:
   - Correct feature name from plan.md
   - `tasks[]` in execution order: setup → foundational → user stories (priority order from spec.md) → polish
   - Every task carries: `task_id` / `spec_ref` / `plan_ref` / `verify_cmd` / `context_seeds` / `modifies` / `ac_list` / `criticality`; `depends_on` only points to earlier tasks
   - `modifies` declares the write footprint with exact file paths (1:1 ownership — see 任务边界规则 in the OVERRIDE block)
   - Do NOT hand-write `execution_plan` — that is generated by `suiyin-flow plan run` (C1)

5. **Report**: Output the path to the generated tasks.yaml and a summary:
   - Total task count and task count per user story
   - Dependency-chain summary (`depends_on` edges; which tasks are independent)
   - `modifies` ownership check: every shared file has exactly one owning task
   - `verify_cmd` coverage: every task has one; every AC in `ac_list` maps to a test (or is flagged 待独立测试作者)
   - Suggested MVP scope (typically just User Story 1)

6. **Check for extension hooks**: After tasks.yaml is generated, check if `.specify/extensions.yml` exists in the project root.
   - If it exists, read it and look for entries under the `hooks.after_tasks` key
   - If the YAML cannot be parsed or is invalid, skip hook checking silently and continue normally
   - Filter out hooks where `enabled` is explicitly `false`. Treat hooks without an `enabled` field as enabled by default.
   - For each remaining hook, do **not** attempt to interpret or evaluate hook `condition` expressions:
     - If the hook has no `condition` field, or it is null/empty, treat the hook as executable
     - If the hook defines a non-empty `condition`, skip the hook and leave condition evaluation to the HookExecutor implementation
   - When constructing slash commands from hook command names, replace dots (`.`) with hyphens (`-`). For example, `sy.git.commit` → `/sy-git-commit`.
   - For each executable hook, output the following based on its `optional` flag:
     - **Optional hook** (`optional: true`):
       ```
       ## Extension Hooks

       **Optional Hook**: {extension}
       Command: `/{command}`
       Description: {description}

       Prompt: {prompt}
       To execute: `/{command}`
       ```
     - **Mandatory hook** (`optional: false`):
       ```
       ## Extension Hooks

       **Automatic Hook**: {extension}
       Executing: `/{command}`
       EXECUTE_COMMAND: {command}
       ```
   - If no hooks are registered or `.specify/extensions.yml` does not exist, skip silently

Context for task generation: $ARGUMENTS

The tasks.yaml should be immediately executable - each task must be specific enough that an LLM can complete it without additional context.

## Task Generation Rules

**CRITICAL**: Tasks MUST be organized by user story to enable independent implementation and testing.

**测试不是可选项（gen-4 铁律，覆盖 spec-kit 上游默认）**：每个 task 必须带可执行的 `verify_cmd`；spec 的每条 AC 必须有测试对应——没有的在报告里标「待独立测试作者」，不许静默跳过。AC 冻结闸（acgate）以测试为准绳：无测试对应的 AC 无法冻结、无法过收口。spec-kit 上游的 "Tests are OPTIONAL" 指令在 v4 一律无效。

### Task ID 规则（canonical identity）

- `task_id` 满足 LOCAL_ID_PATTERN（字母数字开头，允许 `. _ -`，≤64 字符），**feature 内唯一即可**——全局身份 = `feature_id + task_id`（feature_id 由 spec_ref 推导），不同 feature 的同名 task_id 不冲突，不需要跨 feature 续号
- 编号建议从 T-001 起按执行顺序递增；修补/插入任务用后缀（如 T-001B），**不重排已冻结的编号**（AC manifest / review / cost ledger 都按身份键定位，重排会断链）
- 不再使用 spec-kit 的 markdown checkbox / `[P]` / `[Story]` 标签格式——并行性由 C1 从 `depends_on` + `modifies` 算出，story 归属放 yaml 注释或 `feature_name` 语境即可

### Task Organization

1. **From User Stories (spec.md)** - PRIMARY ORGANIZATION:
   - Each user story (P1, P2, P3...) gets its own phase
   - Map all related components to their story:
     - Models needed for that story
     - Services needed for that story
     - Interfaces/UI needed for that story
     - Tests specific to that story (mandatory — see 测试不是可选项 above)
   - Mark story dependencies (most stories should be independent)

2. **From Contracts**:
   - Map each interface contract → to the user story it serves
   - Each interface contract → contract test before implementation in that story's phase

3. **From Data Model**:
   - Map each entity to the user story(ies) that need it
   - If entity serves multiple stories: Put in earliest story or Setup phase
   - Relationships → service layer tasks in appropriate story phase

4. **From Setup/Infrastructure**:
   - Shared infrastructure → Setup phase (Phase 1)
   - Foundational/blocking tasks → Foundational phase (Phase 2)
   - Story-specific setup → within that story's phase

### Phase Structure

- **Phase 1**: Setup (project initialization)
- **Phase 2**: Foundational (blocking prerequisites - MUST complete before user stories)
- **Phase 3+**: User Stories in priority order (P1, P2, P3...)
  - Within each story: Tests → Models → Services → Endpoints → Integration
  - Each phase should be a complete, independently testable increment
- **Final Phase**: Polish & Cross-Cutting Concerns
