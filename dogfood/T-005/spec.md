# Spec: C6 Gate Contract mini-dogfood — Mock pre-merge gate on PR #30 (P1.2 阶段 3.2)

## 1. Purpose

T-005 是 P1.2 阶段 3.2 的 mini-dogfood — **用 C6 (本 PR #34 实现的) 对已 merged 的 PR #30 (C5 impl) 做 mock pre-merge gate 评估**，验证 4 条规则评估正确 + I8 reason precedence + I9 R1 atomicity + safe_pr_ref 转义全部在真实场景下成立。

对比 T-003 (C5 自审 PR #29) / T-004 (C5 self-review C6 spec PR #33)，T-005 是首个 **跨阶段 dogfood** — 用 当前阶段产物 (C6 impl) 评估 上一阶段产物 (C5 impl PR)。

## 2. Public API

N/A — dogfood task 不是 imperative 代码，是验证脚本 + 落盘 fixture + commit evidence。

## 3. Behavior Contract

文档 / 验证脚本类，无 imperative logic。AC 全部基于 "fixture 已落盘 + C6 真跑 4 个场景 + gate_report 落点正确"。

## 5. Acceptance Criteria

> 用 AC-401..AC-410 避免跟 C2/C4/C5/C6/T-001..T-004 已有 AC-1..AC-310 冲突.

- **AC-401**: `dogfood/T-005/fixtures/verify_report.json` 存在 — 来源 = 重跑 C4 verify 对 PR #30 merged commit (9793d51) 的真实输出，含 `overall_verdict` 字段。

- **AC-402**: `dogfood/T-005/fixtures/review_report.json` 存在 — 来源 = 重跑 C5 review 对 PR #30 的真实输出，含 `verdict` + `findings`。

- **AC-403**: `dogfood/T-005/run.sh` (或 Python 等价) 跑 4 个场景按顺序：
  - 场景 1 (baseline): 4 条全 pass + dry_run → `gate_result=merged`, merged_sha absent
  - 场景 2 (verify 篡改): 拷贝 fixture 改 `overall_verdict=fail` → `held + reason=VERIFY_NOT_PASS`
  - 场景 3 (review 篡改): 拷贝 fixture 改 `verdict=block` → `held + reason=REVIEW_NOT_APPROVE`, dry_run 下 recovery_action.kind=r1_label_and_comment 但 label_added/comment_posted absent
  - 场景 4 (ff diverged): 把 pr_ref 指向 main HEAD 之前的 sha → `held + reason=NOT_FF_MERGEABLE`

- **AC-404**: 每场景跑完 `.suiyin/gates/<safe_pr_ref>-<ts>.json` 落盘成功 — 文件名扁平不含 `/` `:` 等 unsafe chars。

- **AC-405**: 场景 3 (review block) 的 recovery_action 在 dry_run 模式下 **label_added/comment_posted/comment_url 全 absent** (AC-8 实证) — payload omit-when-absent 正确。

- **AC-406**: I8 precedence 验证 — 额外跑场景 5: 同时 `overall_verdict=fail` + mock label `human:block` → `reason=HUMAN_BLOCKED` (不是 VERIFY_NOT_PASS)，rules 字段记录两个 false 实情。

- **AC-407**: safe_pr_ref 转义验证 — pr_ref 用 `https://github.com/chinaszzt/suiyin-v4/pull/30` 形式 → 落盘文件名含 `pull-30`、目录扁平。

- **AC-408**: dogfood evidence 落盘 — `dogfood/T-005/results/` 目录含 5 个场景的 gate_report.json + stdout/stderr 捕获，供后续 audit (跟 T-001/T-002 落 evidence 一致)。

- **AC-409**: dogfood **不污染 git history** — fixture 文件在 `dogfood/T-005/fixtures/`，run.sh 跑完不修改 src/ 或 docs/；如有副作用全限制在 .suiyin/ 内。

- **AC-410**: T-005 dogfood 完成后向 todo.md 标 P1.2 阶段 3.2 ✅ + Insight F 候选 (如有 C12 I6 触发) 进 sinks。

## 6. Open Questions

- **Q-T005-1**: PR #30 fixture 是用真实 C4/C5 重跑获取，还是手写 minimal fixture？前者更真实但需要 venv setup + 跑通；后者更快但脱离真实场景。当前倾向: 手写 minimal fixture（schema 符合 C4 §2.2 / C5 §2.2 即可）+ 注释指明 "完整真实数据可用 `suiyin-flow verify run --target PR #30 commit` 重生成"。
- **Q-T005-2**: dogfood run script 用 bash 还是 Python？bash 简单但缺类型；Python 跟 v4 仓栈一致 + 可复用 pytest mock pattern。倾向 Python script (放 `dogfood/T-005/run.py`)，可 invoke 也可 pytest 化。

## 7. Implementation Notes

- 复用 C6 `suiyin-flow gate run --dry-run` CLI 跑，不直接调 `execute_gate` Python API — 验证 entry point 完整。
- 场景 4 (NOT_FF_MERGEABLE) 需要本地 git state 有 diverged ref；用临时 worktree 或临时 branch 模拟。
- 场景 5 (I8 precedence) 在本地 mock 模式难做 (gh API 真查 label)，可降级为 unit test 已覆盖 (AC-5 in tests/c6_gate/test_acceptance_criteria.py)，dogfood 跳过或用 mock_gh fixture。
- evidence 落 `dogfood/T-005/results/<scenario>-gate_report.json` 一份 + `dogfood/T-005/results/README.md` 汇总。
