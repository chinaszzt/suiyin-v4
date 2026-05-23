# Plan: C5 AI Reviewer Spec 实施 (T-002)

## Steps

1. **读 context** (按顺序):
   - `docs/sdd/component-spec-template.md` — **严格按这 8 章节顺序**
   - `docs/sdd/toolchain.md` §C5 节 + Fork L (复用 C11 query for complexity)
   - `docs/sdd/components/c2-task-executor.md` — imperative 组件 spec **范例**
   - `docs/sdd/components/c4-verify-contract.md` — declarative 契约 spec **范例**
   - `docs/sdd/constitution.md` v0.2.2 — 引用 NC-1..NC-5 + PC-1..PC-3
   - `docs/sdd/discussion-notes.md` §十 — C12 Knowledge Capture (finding category 触发)
   - `dogfood/T-002/spec.md` §7 Implementation Notes — 内容设计要点参考

2. **写 `docs/sdd/components/c5-ai-reviewer.md`** v0.1.0-draft, 严格 8 章节:
   - §0 Type: 自建组件 (imperative)
   - §1 Purpose: 一句话核心职责
   - §2 Public API: yaml schema for Input / Output / Error (verdict + findings)
   - §3 Behavior Contract: Invariants (>=5) + Side Effects + Failure Modes
   - §4 AI Prompt Template: Your Role / Input / Steps / Output / Constraints
   - §5 Acceptance Criteria: >=6 AC (C5 自己的 AC, 例如 "正确识别 NC violation")
   - §6 Open Questions: 至少 Q5 + 其他 unknowns
   - §7 Implementation Notes: 技术栈 / 跨平台 / 跟 C 协作 / 跟 constitution

   **关键内容点 (从 T-002 spec.md §7 抄):**
   - finding category 必须含 `complexity` + `reusable_knowledge_not_captured`
   - I1 必须声明独立 session 不继承 implementer context
   - verdict enum 必须含 approve / request_changes / block
   - Public API 至少 3 个 yaml block (Input / Output / Error)

3. **写 `tests/dogfood/test_c5_spec.py`** 含 8 个 test:
   - `test_AC_201_c5_spec_exists_with_8_sections`
   - `test_AC_202_type_is_imperative`
   - `test_AC_203_public_api_has_3_yaml_blocks`
   - `test_AC_204_invariants_count_at_least_5`
   - `test_AC_205_prompt_template_not_na`
   - `test_AC_206_at_least_6_ac_in_spec`
   - `test_AC_207_finding_categories_include_complexity_and_reusable_knowledge`
   - `test_AC_208_q5_listed_in_open_questions`

4. **跑 verify_cmd**:

   ```bash
   /Users/zhangtuo/Documents/suiyin-v4/.claude/worktrees/dogfood-c5-spec/.venv/bin/suiyin-flow verify run \
     --target worktree --worktree-path . \
     --spec dogfood/T-002/spec.md \
     --ac AC-201 --ac AC-202 --ac AC-203 --ac AC-204 \
     --ac AC-205 --ac AC-206 --ac AC-207 --ac AC-208 \
     --repo-root .
   ```

5. **全绿 (overall=pass + ac_summary.covered = all 8 AC) 才 commit**.

## Constraints

- 严禁修改 `dogfood/T-002/` 内文件 (task input)
- 严禁修改 `docs/sdd/components/c2-task-executor.md` / `c4-verify-contract.md` (跟本 task 无关)
- 严禁修改 `src/suiyin_flow/` 内代码 (本 task 写 spec 文档, 不写 impl)
- 严禁修改 `docs/sdd/constitution.md` (引用即可, 不动)
- 不能违反 NC-4 (在 worktree 内跑) / NC-5 (跨平台用语)
- 测试名严格按 `test_AC_2XX_<descriptive>` 命名 (Fork G + C4 parser 识别)

## 期望产出 (review checkpoint)

- 1 个新文件 `docs/sdd/components/c5-ai-reviewer.md` (预计 250-400 行)
- 1 个新文件 `tests/dogfood/test_c5_spec.py` (8 个 test, ~50-80 行)
- AI 提交 1+ 个 commits, 走通 verify_cmd
- 自动开 PR task/T-002 → main, PR body 含 task_id / ac_list / attempts
