"""C2 prompt template — §4 implementation.

注入 task context (spec/plan/constitution + ac_list + context_seeds) 给
Claude headless session. 同时含 ref 校验 (SPEC_NOT_FOUND / CONTEXT_SEEDS_MISSING)
与 R2 review feedback 解析 (REVIEW_FEEDBACK_INVALID, v0.3.0).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

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
{review_feedback_section}
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


def _git_ok(repo_root: Path, *args: str) -> bool:
    """git -C repo_root <args>; 只看 returncode==0; 任何异常视为 False."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            shell=False,
            check=False,
        )
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return False
    return result.returncode == 0


def _ref_visible(task_input: TaskInput, ref: str) -> tuple[bool, str]:
    """ref 在 task 视角的树里是否可见.

    v0.2.1 (真闭环 r3 发现 #9): session 读的是 worktree (从 base_branch HEAD
    分叉), 不是 repo_root 当前 checkout 的分支。旧版按 repo_root 文件系统校验,
    两边分支不一致时双向出错: feature 分支独有文件被误报 missing (r3 实测),
    盘上未提交文件被误判可用 (session 实际看不到)。

    校验顺序:
    1. base_branch 可解析 → `git cat-file -e <base>:<ref>` (文件/目录皆可)
    2. base_branch 解析不了 (非 git repo / unborn) → fallback 文件系统存在性

    Returns:
        (visible, checked_against)
    """
    repo_root = Path(task_input.repo_root)
    base = task_input.base_branch
    if _git_ok(repo_root, "rev-parse", "--verify", "--quiet", base):
        return (
            _git_ok(repo_root, "cat-file", "-e", f"{base}:{ref}"),
            f"branch {base!r}",
        )
    return (repo_root / ref).exists(), "filesystem (base_branch unresolvable)"


def validate_refs(task_input: TaskInput) -> None:
    """SPEC_NOT_FOUND 校验: spec_ref / plan_ref / constitution_ref 对 task 可见.

    "可见" = 在 base_branch HEAD 上 (worktree 从这里分叉), 见 _ref_visible.
    """
    for label, ref in (
        ("spec_ref", task_input.spec_ref),
        ("plan_ref", task_input.plan_ref),
        ("constitution_ref", task_input.constitution_ref),
    ):
        visible, against = _ref_visible(task_input, ref)
        if not visible:
            raise TaskExecutorError(
                "SPEC_NOT_FOUND",
                f"{label} not found: {ref} (checked against {against}; the "
                "task worktree forks from base_branch HEAD — commit the file "
                "to base_branch first)",
                task_id=task_input.task_id,
                missing_ref=label,
                ref=ref,
                checked_against=against,
            )


def validate_context_seeds(task_input: TaskInput) -> None:
    """CONTEXT_SEEDS_MISSING 校验: 所有 seed 对 task 可见 (同 validate_refs 语义)."""
    for seed in task_input.context_seeds:
        visible, against = _ref_visible(task_input, seed)
        if not visible:
            raise TaskExecutorError(
                "CONTEXT_SEEDS_MISSING",
                f"context_seed not found: {seed} (checked against {against}; "
                "the task worktree forks from base_branch HEAD — commit the "
                "file to base_branch first)",
                task_id=task_input.task_id,
                missing_seed=seed,
                checked_against=against,
            )


# R2 feedback section 模板 (spec §4 渲染规则, v0.3.0)
_FEEDBACK_SECTION_HEADER = """
## 上次 Review 发现的问题 (R2 retry-with-feedback — 必须优先处理)

上一轮实现被独立 AI Reviewer (C5) block. 当前 worktree 里已有上一轮的实现,
**不要从头重写** — 逐条修复以下 findings (或在最终输出的 JSON 里加
`feedback_disputes` 字段说明为什么某条不需要改), 然后再走常规 Steps:
"""

_SEVERITY_RANK = {"high": 0, "medium": 1, "low": 2}


def load_review_findings(task_input: TaskInput) -> list[dict[str, Any]] | None:
    """读 + 校验 review_feedback (R2). None = input 未提供.

    校验语义是文件系统存在性 (spec §2.1 语义要点 3): review report 是
    运行时 artifact (.suiyin/reviews/..., gitignored), 跟 spec_ref 那套
    base_branch 可见性校验 (#9 修正) 适用范围不同.

    Raises:
        TaskExecutorError(REVIEW_FEEDBACK_INVALID) — 路径不存在 / JSON 非法 /
        findings 缺失或为空 (block report 必有 ≥1 finding, 空反馈属 caller
        调用错误, fail-fast 不静默跑普通模式).
    """
    if task_input.review_feedback is None:
        return None
    path = Path(task_input.review_feedback)
    if not path.is_absolute():
        path = Path(task_input.repo_root) / path
    if not path.is_file():
        raise TaskExecutorError(
            "REVIEW_FEEDBACK_INVALID",
            f"review_feedback file not found: {path}",
            task_id=task_input.task_id,
            review_feedback=str(path),
        )
    try:
        data: Any = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise TaskExecutorError(
            "REVIEW_FEEDBACK_INVALID",
            f"review_feedback is not valid JSON: {path} ({exc})",
            task_id=task_input.task_id,
            review_feedback=str(path),
        ) from exc
    findings = data.get("findings") if isinstance(data, dict) else None
    if not isinstance(findings, list) or not findings:
        raise TaskExecutorError(
            "REVIEW_FEEDBACK_INVALID",
            f"review_feedback has no findings: {path} (a C5 block report "
            "always carries >=1 finding; empty feedback is a caller error)",
            task_id=task_input.task_id,
            review_feedback=str(path),
        )
    return [f for f in findings if isinstance(f, dict)]


def _render_feedback_section(findings: list[dict[str, Any]] | None) -> str:
    """渲染「上次 Review 发现的问题」节; findings=None → 空串 (退化 v0.2.x 形态).

    排序: severity high → medium → low (未知 severity 排最后), 同级保持原序.
    """
    if findings is None:
        return ""
    ordered = sorted(
        findings,
        key=lambda f: _SEVERITY_RANK.get(str(f.get("severity", "")), 99),
    )
    lines = []
    for i, f in enumerate(ordered, start=1):
        severity = f.get("severity", "?")
        category = f.get("category", "?")
        location = f.get("location", "(no location)")
        fix = f.get("suggested_fix", "(no suggested_fix)")
        lines.append(f"{i}. [{severity}/{category}] {location}")
        lines.append(f"   fix: {fix}")
    return _FEEDBACK_SECTION_HEADER + "\n" + "\n".join(lines) + "\n"


def render_prompt(
    task_input: TaskInput,
    worktree_path: Path,
    review_findings: list[dict[str, Any]] | None = None,
) -> str:
    """渲染 §4 prompt template (要求 refs / seeds / feedback 已校验过)."""
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
        review_feedback_section=_render_feedback_section(review_findings),
    )
