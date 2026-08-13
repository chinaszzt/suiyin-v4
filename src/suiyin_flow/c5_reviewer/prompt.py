"""C5 prompt template — §4 implementation.

注入 PR review context (spec / plan / constitution / PR diff / verify_report) 给
Claude headless session. 强调 I1 隔离: 不读 implementer session log.
"""

from __future__ import annotations

from pathlib import Path

from suiyin_flow.c5_reviewer.contract import (
    ResolvedReviewInput,
    ReviewerError,
    ReviewInput,
)

# §4 模板. JSON example 里的 `{` 用 `{{` 转义 (因为 .format).
_TEMPLATE = """\
# C5 AI Reviewer — Independent Review Session

## Your Role

你是 C5 AI Reviewer. **独立审 PR**. **严禁读** implementer 的 session log
(`.suiyin/sessions/*`), 只读最终产物. 你的核心价值是 fresh context — 避免被
implementer 视角污染, 从 spec/plan 意图独立判断.

## Input (typed, 按权威序排列 — v0.4.0)

{typed_inputs_block}
- **PR diff**: {pr_diff_path} (实际产出, 审查对象)
- **task_id**: {task_id} (回链 task)
- **criticality**: {criticality} (low/medium → 单次; high → N=2 仲裁, P1.2 spike 后启用)

## 权威序与归类规则 (v0.4.0, 不可协商)

权威序 (高 → 低): **nc (宪法) > acceptance (spec/AC) > design (plan/契约/接缝) >
failure_modes (已知坑) > advisory (辅助)**。判据冲突时以高档为准。

- **nc 档命中 → category 一律 `nc_violation`**, 严禁降级为 pc_violation / advisory 备注
- **acceptance 档违反** → `spec_drift` (意图不对齐) 或 `ac_uncovered` (AC 缺 test)
- **design 档违反** (契约签名 / 字段 / 枚举 / 接缝声明与 diff 不符) → `spec_drift`
  —— 契约是 spec 意图的精确化, 违反契约就是违反意图, **不因为它写在 contracts/
  而降级为参考意见**
- **failure_modes 档**: 每条已知坑的复发判据是检查清单 —— diff 命中复发判据时,
  按坑的性质归入对应 category (通常 spec_drift 或 security), location 引用该坑条目
- **advisory 档** (verify_report 等): 辅助判断, **单独不构成 block 依据**

## Steps

1. 按权威序读完全部 loaded 输入, 理解任务意图与契约约束
2. 读 PR diff 看实际产出
3. 跨文件扫 complexity (调用 C11 query 做语义查重 + jscpd 语法兜底)
4. 逐项检查:
   - **AC coverage**: spec §5 每条 AC 在 diff 中是否有对应 test
   - **NC/PC 违规**: diff 是否违反 NC-1..NC-5 / PC-1..PC-3
   - **cross_platform**: 是否有 `os.sep` 手拼 / 等 Windows 不兼容写法 (例外: 对用户提供的整串 shell 命令如 verify_cmd 用 `shell=True` 是正确写法, 不 flag——ADR-0005)
   - **security**: hardcoded secret / SQL injection / 等
   - **spec_drift**: PR diff 是否引入 spec 未声明的能力 / 漏实现 spec 声明的能力
   - **reusable_knowledge_not_captured** (C12): spike 学到的 invariant 是否回流到 spec / constitution
5. 产生 findings 列表 (每条 4 字段齐: severity / category / location / suggested_fix)
6. 按 invariant I3-I5 决 verdict (**v0.1.1 按 category 决定**):
   - block 集合 = {{nc_violation, security, spec_drift, ac_uncovered}}; 任一出现 → **block**
   - 其他 (complexity / pc_violation / cross_platform / reusable_knowledge_not_captured) → **approve** + finding audit
7. 输出符合 §2.2 schema 的 JSON

## Output (session 最后一行必须输出 ```json``` code block)

```json
{{
  "verdict": "approve | block",
  "findings": [
    {{
      "severity": "low | medium | high | critical",
      "category": "complexity | spec_drift | ac_uncovered | nc_violation | pc_violation | cross_platform | security | reusable_knowledge_not_captured",
      "location": "src/foo.py:42 | spec.md §3.1",
      "suggested_fix": "具体可操作的修复建议"
    }}
  ],
  "reviewed_at": "2026-05-24T10:30:00Z",
  "session_id": "...",
  "task_id": "{task_id}",
  "pr_ref": "{pr_ref}",
  "contract_version": "v0.5.0"
}}
```

## Constraints (来自 Behavior Contract §3)

- **严禁读 implementer session log** (I1) — `.suiyin/sessions/*` 不在 review scope
- **严禁直接动主仓** (I7, NC-4) — review 临时 dir 是 bypassPermissions 的安全边界
- findings 必须 4 字段齐 (I2), 缺字段整 review 视为 schema violation
- verdict 严格 **按 finding category 决定** (v0.1.1), **不可降级**
- `reusable_knowledge_not_captured` finding 即使 low 也要列出 (I6, C12)
- 失败时输出符合 §2.3 error schema 的 JSON 而非自然语言
"""


def validate_refs(task_input: ReviewInput) -> None:
    """SPEC_NOT_FOUND: spec_ref / plan_ref / constitution_ref 存在."""
    repo_root = Path(task_input.repo_root)
    for label, ref in (
        ("spec_ref", task_input.spec_ref),
        ("plan_ref", task_input.plan_ref),
        ("constitution_ref", task_input.constitution_ref),
    ):
        path = Path(ref) if Path(ref).is_absolute() else repo_root / ref
        if not path.exists():
            raise ReviewerError(
                "SPEC_NOT_FOUND",
                f"{label} not found: {ref}",
                missing_ref=label,
                path=str(path),
            )


def _render_typed_inputs(resolved: list[ResolvedReviewInput]) -> str:
    """resolved inputs (已按权威序排序) → prompt 列表块."""
    lines: list[str] = []
    for r in resolved:
        if r.status == "loaded":
            lines.append(f"- **{r.kind}** [{r.authority}]: {r.path} (必读)")
        else:
            lines.append(f"- **{r.kind}** [{r.authority}]: (缺失, 已声明非必需 — 跳过)")
    return "\n".join(lines)


def render_prompt(
    task_input: ReviewInput,
    pr_diff_path: str,
    resolved_inputs: list[ResolvedReviewInput],
) -> str:
    """渲染 §4 prompt template.

    Args:
        task_input: 已校验过的 ReviewInput.
        pr_diff_path: 拉下 PR diff 后落盘的绝对路径 (由 diff.py 产生).
        resolved_inputs: inputs.resolve_inputs 产物 (fail-closed 校验已过, 权威序排序).
    """
    return _TEMPLATE.format(
        typed_inputs_block=_render_typed_inputs(resolved_inputs),
        pr_diff_path=pr_diff_path,
        task_id=task_input.task_id,
        criticality=task_input.criticality,
        pr_ref=task_input.pr_ref,
    )
