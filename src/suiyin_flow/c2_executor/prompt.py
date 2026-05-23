"""C2 prompt template — §4 implementation.

注入 task context (spec/plan/constitution + ac_list + context_seeds) 给
Claude headless session. 同时含 ref 校验 (SPEC_NOT_FOUND / CONTEXT_SEEDS_MISSING).
"""

from __future__ import annotations

from pathlib import Path

from suiyin_flow.c2_executor.schema import TaskExecutorError, TaskInput

# §4 模板. 注意 .format() 占位符里的 `{` 用 `{{` 转义 (Output 那段 JSON example).
_TEMPLATE = """\
# Task Executor — Implementation Session

## Your Role

你是 C2 Task Executor 调度下的 implementer. 单 task 闭环实现, 从 spec 到通过 verify 的代码.

## Task Context

- **task_id**: {task_id}
- **spec**: 见 {spec_ref} (必读)
- **plan**: 见 {plan_ref} (必读)
- **constitution**: 见 {constitution_ref} (必读)
- **ac_list**: {ac_list} (产出的代码必须能让对应 `AC-N` 命名的测试通过)
- **context_seeds** (必读, 先扫一遍再动手):
{context_seeds_yaml}

## Steps

1. 读 spec / plan / constitution / 所有 context_seeds
2. 列出要改的文件清单 (先 plan, 后写)
3. 实现代码 + 写测试 (测试名必须 prefix `AC-N: ` 对应 ac_list)
4. 跑 `{verify_cmd}` 在 worktree 内 (cwd = `{worktree_path}`)
5. verify 绿后 `git add` + `git commit` (commit message 含 task_id + 主要变更)
6. 输出 §Output 部分的 JSON 摘要

## Constraints (C2 §3 Behavior Contract)

- 只在 worktree `{worktree_path}` 内改文件, 严禁 cd 到主仓 / 修改其他 worktree
- 测试命名约定: `test('AC-N: ...')` (JS/Dart) / `def test_AC_N_...` (Python) — 见 C4 spec §3.1
- 1 个 test 名只能 prefix 1 个 `AC-N`
- 失败时输出符合 C2 §2.3 error schema 的 JSON 而非自然语言
- 严禁修改 spec.md / plan.md / constitution.md (你是 implementer, 不是 spec 协商者)
- 严禁引入 NC-1 / NC-2 / NC-3 违反项 (见 constitution §6)

## Output (session 最后一行必须输出)

```json
{{
  "task_id": "...",
  "files_changed": [...],
  "verify_cmd_exit_code": 0,
  "commit_sha": "..."
}}
```

verify 没绿时不要 commit. 可以重复跑 verify_cmd 调试.
"""


def validate_refs(task_input: TaskInput) -> None:
    """SPEC_NOT_FOUND 校验: spec_ref / plan_ref / constitution_ref 文件存在."""
    repo_root = Path(task_input.repo_root)
    for label, ref in (
        ("spec_ref", task_input.spec_ref),
        ("plan_ref", task_input.plan_ref),
        ("constitution_ref", task_input.constitution_ref),
    ):
        path = repo_root / ref
        if not path.exists():
            raise TaskExecutorError(
                "SPEC_NOT_FOUND",
                f"{label} not found: {ref}",
                task_id=task_input.task_id,
                missing_ref=label,
                path=str(path),
            )


def validate_context_seeds(task_input: TaskInput) -> None:
    """CONTEXT_SEEDS_MISSING 校验: 所有 seed 文件/目录存在."""
    repo_root = Path(task_input.repo_root)
    for seed in task_input.context_seeds:
        seed_path = repo_root / seed
        if not seed_path.exists():
            raise TaskExecutorError(
                "CONTEXT_SEEDS_MISSING",
                f"context_seed not found: {seed}",
                task_id=task_input.task_id,
                missing_seed=seed,
                path=str(seed_path),
            )


def render_prompt(task_input: TaskInput, worktree_path: Path) -> str:
    """渲染 §4 prompt template (要求 refs / seeds 已校验过)."""
    seeds_yaml = (
        "\n".join(f"  - {s}" for s in task_input.context_seeds)
        if task_input.context_seeds
        else "  (无)"
    )
    ac_list_str = (
        ", ".join(task_input.ac_list) if task_input.ac_list else "(无)"
    )
    return _TEMPLATE.format(
        task_id=task_input.task_id,
        spec_ref=task_input.spec_ref,
        plan_ref=task_input.plan_ref,
        constitution_ref=task_input.constitution_ref,
        ac_list=ac_list_str,
        context_seeds_yaml=seeds_yaml,
        verify_cmd=task_input.verify_cmd,
        worktree_path=str(worktree_path),
    )
