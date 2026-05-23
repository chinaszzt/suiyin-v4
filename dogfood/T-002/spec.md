# Spec: C5 AI Reviewer 组件 Spec (P1.2 起步)

## 1. Purpose

写 `docs/sdd/components/c5-ai-reviewer.md` — 即 C5 AI Reviewer 组件的完整 spec
v0.1.0。这是 v4 工具链 **P1.2 阶段 (自闭环 merge) 的第一份 spec**, 同时是
dogfood 进阶 T-002 (验证 spec v0.1.2 反推后 C2 跑代码/spec 类 task 是否 work).

C5 角色简述: 独立 AI session, 读 spec + plan + constitution + PR diff (**不**读
implementer 工作过程), 给 verdict (`approve` / `request_changes` / `block`) +
structured findings 列表。最终输出供 C6 Gate Contract 判断是否 merge.

## 2. Public API

N/A — 这是文档/spec 类 task, 不是 imperative 代码.

## 3. Behavior Contract

文档类, 无 imperative logic. AC 全部基于"文件存在 + 内容含特定结构 + 引用正确"。

## 5. Acceptance Criteria

> 用 AC-201..AC-208 避免跟 C2/C4/T-001 已有 AC-1..AC-102 冲突 (C4 parser
> 全局扫 AC-\d+).

- **AC-201**: `docs/sdd/components/c5-ai-reviewer.md` 文件存在, 含 8 章节
  Markdown headings (严格按 `component-spec-template.md` 顺序):
  ```
  ## 0. Type
  ## 1. Purpose
  ## 2. Public API
  ## 3. Behavior Contract
  ## 4. AI Prompt Template
  ## 5. Acceptance Criteria
  ## 6. Open Questions
  ## 7. Implementation Notes
  ```

- **AC-202**: §0 Type 标 "自建组件 (imperative logic — 需要写代码)" (C5 是
  imperative, 不是 contract).

- **AC-203**: §2 Public API 含至少 3 个 ```yaml``` schema block (Input / Output /
  Error). Output schema 必须含 `verdict` 字段 + `findings` 数组.

- **AC-204**: §3.1 Invariants 至少 5 条 (I1..I5+). 必须含一条声明 "独立 session,
  不继承 implementer context" 类的隔离 invariant.

- **AC-205**: §4 AI Prompt Template 不是 "N/A" — C5 是 imperative 组件必有完整
  prompt (含 Your Role / Input / Steps / Output / Constraints).

- **AC-206**: §5 Acceptance Criteria 至少 6 条 AC (C5 自己的 AC, 不是 T-002 这份).

- **AC-207**: §5 / §3 / §7 任一处含 finding category 列表, **必须包含**这 2 类:
  - `complexity` (跨文件查重 / 过度设计 / 重复实现 — Fork L 通过 C11 query 协作)
  - `reusable_knowledge_not_captured` (C12 Knowledge Capture 触发, 见
    `discussion-notes.md` §十 + `diagrams.md` 图 11 C12 placeholder)

- **AC-208**: §6 Open Questions 至少含 Q5 (来自 `toolchain.md` §六附录 B):
  "C5 reviewer 单次 review 还是 N=2 分歧仲裁 (按 task.criticality 路由)？"

## 6. Open Questions

无 (T-002 自身).

## 7. Implementation Notes

### C5 内容设计要点 (AI 写 spec 时参考)

#### 性质
- C5 = 独立 AI session reviewer, 平行于 C2 implementer.
- 关键隔离: C5 **不读** C2 的 session log / implementer 工作过程, 只读最终产物
  (spec / plan / constitution / PR diff / verify_report.json).
- 避免被 implementer 视角污染 → independent审查能发现 implementer 没注意的 issue.

#### Public API 草稿

```yaml
Input:
  pr_ref: str  # PR URL 或本地 branch 名
  spec_ref: str  # spec.md 路径
  plan_ref: str  # plan.md 路径
  constitution_ref: str  # constitution.md 路径
  verify_report_path: str | null  # C4 输出, optional
  task_id: str | null  # 关联回 task
  criticality: enum [low, medium, high]  # 决定是否走 N=2 仲裁
```

```yaml
Output:
  verdict: enum [approve, request_changes, block]
  findings: array of:
    severity: enum [low, medium, high, critical]
    category: enum [
      complexity,  # 过度设计 / 重复实现 / 函数超长
      spec_drift,  # PR diff 跟 spec 不对齐
      ac_uncovered,  # 缺 AC 对应 test
      nc_violation,  # 违反 constitution NC-1..NC-5
      pc_violation,  # 违反 PC-1..PC-3
      cross_platform,  # NC-5 跨平台违规
      security,  # 安全问题
      reusable_knowledge_not_captured,  # C12: spike 发现没沉淀到 spec/constitution
      ...
    ]
    location: str  # file:line 或 spec section
    suggested_fix: str  # 具体建议
  reviewed_at: datetime
  session_id: str
```

```yaml
Error:
  code: enum [
    SESSION_CRASHED,  # claude CLI 错
    TIMEOUT,  # review 超 30 min
    SPEC_NOT_FOUND,  # input ref 不存在
    PR_DIFF_FETCH_FAILED,  # 获取 PR diff 失败
    ...
  ]
  message: str
  details: dict
```

#### Invariants 草稿

- **I1**: C5 session 独立, fresh context, **不**继承 C2 implementer 的任何 log/state.
- **I2**: findings 必须四字段齐 (severity / category / location / suggested_fix).
- **I3**: severity=high/critical → verdict=block (C5 自己不可降级).
- **I4**: severity=medium → verdict=request_changes.
- **I5**: severity=low only → verdict=approve.
- **I6**: `reusable_knowledge_not_captured` finding 即使 severity=low 也必须出现在
  output (C12 持续触发, 不阻断 merge 但提示沉淀).
- **I7**: C5 跑在隔离 worktree 或临时 dir, **不**直接动主仓 working tree (NC-4).

#### Failure Modes 草稿

| 失败 | 触发 | 处理 |
|---|---|---|
| `SESSION_CRASHED` | claude CLI 非 0 退出 | retry ≤ 2 |
| `TIMEOUT` | review > 1800s (30 min) | retry 1 次 |
| `SPEC_NOT_FOUND` | input path 不存在 | 立即 error |
| `PR_DIFF_FETCH_FAILED` | gh / git 获取 diff 失败 | retry ≤ 2 |

#### AI Prompt Template 草稿

```
# C5 AI Reviewer — Independent Review Session

## Your Role
你是 C5 AI Reviewer. 独立审 PR. **不读** implementer session log.

## Input
- spec: {spec_ref}
- plan: {plan_ref}
- constitution: {constitution_ref}
- PR diff: <attached>
- verify report: {verify_report_path} (optional)

## Steps
1. 读 spec / plan / constitution 理解意图
2. 读 PR diff 看实际产出
3. 跨文件扫 complexity (调 C11 query for 语义查重)
4. 检查 AC coverage / NC/PC 违规 / cross-platform / etc
5. 产生 findings 列表
6. 按 invariant I3-I5 决 verdict
7. 输出符合 §2.2 schema 的 JSON

## Constraints
- 不读 implementer log
- 不直接动主仓 (NC-4)
- findings 必须 4 字段齐
- ...
```

#### Q5 (Open Question)

"C5 单次 review 还是 N=2 分歧仲裁?" — 按 task.criticality 路由:
- low/medium: 单次 review
- high: N=2 + 分歧时第 3 个 AI 仲裁 (类似 C3 模式)

留 open 待 P1.2 spike 验证.

#### 跟其他 C 协作

- 被 **C6 Gate Contract** 读 `verdict` 判 merge / hold
- 调 **C11 query** (Fork L) 做 complexity 跨文件查重
- **C12** 联动: `reusable_knowledge_not_captured` finding 是 C12 的设计触发点

#### 跟 constitution

- NC-1 (零 SaaS): C5 用本地 claude CLI, 不依赖 SaaS API ✅
- NC-4 (worktree 隔离): C5 跑在临时 dir 或 worktree, 不动主仓 ✅
- NC-5 (跨平台): 同 C2/C4 跨平台约束 ✅
- PC-1 (最简实现): 默认单次 review, N=2 仲裁仅 high criticality ✅

#### 实现栈

Python (同 C2/C4) + claude CLI headless (同 C2 §7 Session 调用模式: 4 个必需 flag).

#### 模块拆分

```
src/suiyin_flow/c5_reviewer/
  __init__.py
  cli.py
  contract.py  # Pydantic schema
  prompt.py
  session.py
  findings.py  # category enum + validation
```

### 测试 (AI 必须写)

写 `tests/dogfood/test_c5_spec.py` 含 8 个 `test_AC_2XX_...`:

```python
from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parents[2]
SPEC_PATH = REPO_ROOT / "docs" / "sdd" / "components" / "c5-ai-reviewer.md"

def test_AC_201_c5_spec_exists_with_8_sections() -> None:
    content = SPEC_PATH.read_text(encoding="utf-8")
    for heading in ["## 0. Type", "## 1. Purpose", "## 2. Public API",
                    "## 3. Behavior Contract", "## 4. AI Prompt Template",
                    "## 5. Acceptance Criteria", "## 6. Open Questions",
                    "## 7. Implementation Notes"]:
        assert heading in content, f"missing section: {heading}"

def test_AC_202_type_is_imperative() -> None:
    content = SPEC_PATH.read_text(encoding="utf-8")
    assert "自建组件" in content and "imperative" in content

# ... etc, AC-203..208
```

---

**Version**: v0.1.0 (T-002 input)
**Last Updated**: 2026-05-24
**Status**: dogfood task input
