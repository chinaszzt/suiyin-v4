# Plan: T-005 C6 Mini-Dogfood (mock pre-merge gate on PR #30)

## 1. 输入

- C6 impl (本 PR #34 / worktree `claude/c6-gate-impl`)
- C5 spec / C4 spec (作为 fixture 字段名权威依据)
- PR #30 = C5 impl (target 评估对象)

## 2. 步骤

### 步骤 1 — 写 minimal fixture (Q-T005-1 选 minimal hand-written)

- `.suiyin/fixtures/T-005/verify_report.json` — 按 C4 §2.2 schema, `overall_verdict=pass`, 含 minimal levels[] + ac_summary
- `.suiyin/fixtures/T-005/review_report.json` — 按 C5 §2.2 schema, `verdict=approve`, findings=[] (PR #30 真实 self-review verdict 见 reviews 历史 — 也是 approve)

注释说明: 完整真实数据可用 `suiyin-flow verify run --target <PR #30 commit>` + `suiyin-flow review run --pr-ref 30 ...` 重生成。

### 步骤 2 — 写 `dogfood/T-005/run.py` (Q-T005-2 选 Python)

5 个场景顺序跑 + 每场景拷贝 fixture → 篡改 → 用 worktree 临时分支模拟 (or 本地分支) → 调 `suiyin-flow gate run --dry-run`：

| 场景 | 输入篡改 | 预期 gate_result + reason |
|---|---|---|
| 1 baseline | 原 fixture (4 全 pass) | merged, no reason |
| 2 verify fail | `overall_verdict=fail` | held, VERIFY_NOT_PASS |
| 3 review block | `verdict=block` + 加 findings | held, REVIEW_NOT_APPROVE |
| 4 NOT_FF | pr_ref 指向 main 之前的 sha | held, NOT_FF_MERGEABLE |
| 5 (skip if hard) | human:block label + verify=fail | held, HUMAN_BLOCKED |

每场景检查 stdout `gate_result:` 行 + 落盘 gate_report.json 内容。

### 步骤 3 — 落 evidence 到 `dogfood/T-005/results/`

- `<scenario>-gate_report.json` × 5
- `README.md` 汇总 (每场景的 input + expected + actual + pass/fail)

### 步骤 4 — 跑 + 检查

跑 `python dogfood/T-005/run.py`. 全 5 (或 4，跳 5) 场景 pass → T-005 ✅.

### 步骤 5 — todo.md 标 P1.2 阶段 3.2 ✅ + commit T-005 evidence 进 PR #34

## 3. 风险 + 兜底

- **场景 5 (I8 precedence) gh 依赖**: 本地 git 跑没有真 PR → has_human_block_label 返 false → 测不到 HUMAN_BLOCKED reason 选择。**兜底**: dogfood 跳过场景 5，引用 unit test `test_AC_5_i8_precedence_human_block_wins_over_verify_fail` 作为 I8 evidence (test 用 mock gh CLI 实证)。AC-406 也明确允许这个降级。

- **场景 4 (NOT_FF_MERGEABLE) git state**: 本地 worktree 内 main + 临时分支可制造 diverge — 临时 branch 增 commit → main update-ref → push 到本地 origin bare repo (跟 tests/c6_gate/conftest.py fixture_repo_diverged 同模式) — 实施时用临时目录避免污染 worktree。

- **dogfood pollute worktree 风险**: run.py 全在 tmpfile / `.suiyin/fixtures/T-005/` / `dogfood/T-005/results/` 操作，绝不 `git commit` 内部 state。

## 4. AC ↔ 步骤映射

- AC-401, 402 → 步骤 1
- AC-403, 404, 405 → 步骤 2 + 3
- AC-406 → 步骤 2 (场景 5, 兜底 跳)
- AC-407 → 步骤 2 (pr_ref URL 形式)
- AC-408 → 步骤 3
- AC-409 → 步骤 1+2+3 全程
- AC-410 → 步骤 5

## 5. 时间预估

- 步骤 1: 15 min (写 minimal fixture)
- 步骤 2: 30-45 min (run.py 5 场景)
- 步骤 3: 15 min (evidence 落盘 + README)
- 步骤 4-5: 15 min (跑 + todo + commit)

合计 1.5-2h。
