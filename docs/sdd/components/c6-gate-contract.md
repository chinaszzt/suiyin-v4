# C6 Gate Contract — Component Spec

> 自动化 merge gate。接收 PR + C4 `verify_report.json` + C5 `review_report.json`，按 4 条规则纯逻辑评估 → `merged` / `held`。**v4 P1.2 自闭环 merge 的最后一公里**：C5 出 verdict 后由 C6 决定是否 ff-merge to main，不让人按 merge 按钮。

## 0. Type

- [ ] 自建组件 (imperative logic — 需要写代码)
- [x] 行为契约（declarative contract — 配置 + 编排）

**契约性质**：规则评估纯逻辑（4 条 boolean AND），无 AI、无策略推断、无可调参数。所有"实现"都是把规则评估挂到某种执行容器上（hook / CI / merge queue）。

**实现谱系优先级**：(d) 混合 — 默认 (a) 本地 git pre-push hook 兜底，(c) GitHub Branch Protection 在 SaaS 用户场景兜底。v4 P1.2 阶段仅落地 (a) + 一个 Python CLI（`suiyin-flow gate run`）做规则评估宿主。

**实现栈**: Python 3.11+（同 C2/C4/C5，见 ADR-0002）。CLI 入口 `suiyin-flow gate run <pr_ref>`，复用顶层 unified dispatcher（见 C2 §7 "Unified CLI"）。

## 1. Purpose

接收一个 PR + 关联 verify_report.json + review_report.json，按 **4 条 gate 规则全 AND** 判定 → 满足则 `ff-merge to main` + 删 branch；任何一条 false → `hold` + 触发对应 recovery（Block Recovery R1 / rebase 子流程 / 等人解锁）。**核心特性**: 纯规则评估、可重复、零 AI 不确定性、main 历史保 fast-forward 线性。

## 2. Public API

### 2.1 Input Schema

```yaml
type: object
required: [pr_ref, verify_report_path, review_report_path, repo_root]
properties:
  pr_ref:
    type: string
    description: PR URL（gh 可达时）或本地分支名（无 remote 时降级）
  verify_report_path:
    type: string
    description: C4 verify_report.json 路径（相对 repo_root 或绝对）
  review_report_path:
    type: string
    description: C5 review_report.json 路径（相对 repo_root 或绝对）
  repo_root:
    type: string
    description: 业务项目根目录（绝对路径）
  dry_run:
    type: boolean
    default: false
    description: true 时仅评估规则、输出 gate_report，不执行 merge / label / comment 副作用
```

### 2.2 Output Schema

```yaml
type: object
required: [gate_result, rules, timestamp]
properties:
  gate_result:
    enum: [merged, held]
    description: 终判
  rules:
    type: object
    description: 4 条规则的 pass/fail breakdown（debug 必备）
    required: [verify_all_pass, review_approved, ff_mergeable, not_human_blocked]
    properties:
      verify_all_pass:    { type: boolean }
      review_approved:    { type: boolean }
      ff_mergeable:       { type: boolean }
      not_human_blocked:  { type: boolean }
  reason:
    type: string
    description: held 时必填，标 fail 的第一条规则；merged 时省略
    enum: [VERIFY_NOT_PASS, REVIEW_NOT_APPROVE, NOT_FF_MERGEABLE, HUMAN_BLOCKED, null]
  recovery_action:
    type: object
    description: held 时触发的 side effect 记录
    properties:
      kind:
        enum: [r1_label_and_comment, rebase_required, no_op, null]
      label_added:    { type: boolean }
      comment_posted: { type: boolean }
      comment_url:    { type: string }
  merged_sha:
    type: string
    description: merged 时 main 的新 HEAD sha；held 时省略
  timestamp:
    type: string
    description: ISO8601 UTC
```

### 2.3 Error Schema

```yaml
type: object
required: [code, message]
properties:
  code:
    enum: [MISSING_INPUT, INVALID_REPORT, GIT_ERROR, GH_ERROR, PERMISSION_DENIED]
  message: { type: string }
  details:
    type: object
    description: 错误上下文（哪个文件 / 哪个命令 / stderr）
  retryable: { type: boolean }
```

**Error 与 held 的区别**：`held` 是契约的正常结果（规则评估成功但未全 pass）；`Error` 是契约自身无法评估（缺 input / git 失效）。`held` 不算异常，`Error` 才算。

## 3. Behavior Contract

### 3.1 Invariants

跨调用必须成立的事实：

- **I1 Gate Rule（核心）**: gate_result == `merged` ⟺ `verify_report.overall == pass && review_report.verdict == approve && ff_mergeable(pr_branch, main) && !pr.has_label("human:block")`。**4 条全 AND，缺一不可**。
- **I2 Hold Default**: 任何一条规则 false → 必 `held`，**绝不 force-merge / 绕过任何一条**。
- **I3 Reasoned Hold**: `held` 时 output 必含 `reason`（标 fail 的第一条规则）+ `rules` 4 字段完整 breakdown，便于 debug。
- **I4 Hold ≠ Permanent Block**: `held` 是当时状态评估，不持久化；条件改善后（rebase / 解锁 / 重 verify / 重 review）下次 gate run 可重新评估。
- **I5 ff-only Main History**: merge 操作 = `git merge --ff-only`。**main 永远线性**，禁止 merge-commit / squash 在此契约外触发（squash if any 由上游 PR review 时完成，不归 C6 管）。
- **I6 Determinism**: 同样 input（同 pr_ref + 同 verify_report + 同 review_report + 同 main HEAD）→ 同样 output。无 AI 不确定性、无随机参数。
- **I7 Block Recovery R1（D-autonomous 硬约束）**: 当 `reason == REVIEW_NOT_APPROVE` 时，必触发 R1 副作用（加 `human:block` 标签 + comment review findings）；**不允许静默 hold**。这是 v4 D-autonomous profile "执行阶段 AI 自闭环、异常时人才出来" 的兜底（详见 `workflows.md` Block Recovery 节）。

### 3.2 Side Effects

- `gh pr merge <ref> --merge --ff-only`（或 `git push origin <branch>:main` ff-only）当 gate_result == merged
- `gh pr edit <ref> --add-label "human:block"` 当 reason == REVIEW_NOT_APPROVE
- `gh pr comment <ref> --body "<formatted findings>"` 当 reason == REVIEW_NOT_APPROVE（inline C5 findings）
- 落盘 `<repo_root>/.suiyin/gates/<pr_ref>-<ts>.json`（gate_report 持久化，供 audit）
- **dry_run=true 时一切副作用跳过**，仅输出 gate_report

不触碰的：
- 不调 C4 重 verify
- 不调 C5 重 review
- 不调 C2 重写代码
- 不修改 spec / plan / constitution
- 不动 PR 描述（只加 label + 加 comment）

### 3.3 Failure Modes

| Code / 触发 | 来源 | 处理动作 |
|---|---|---|
| `VERIFY_NOT_PASS`（held） | `verify_report.overall != pass` | hold + 不重跑 C4；caller（C7 / 人）决定是 fix code 还是 fix verify_report；不加 human:block 标签（不是 reviewer 的判断） |
| `REVIEW_NOT_APPROVE`（held） | `review_report.verdict == block` | hold + **Block Recovery R1**：加 `human:block` 标签 + comment C5 findings inline；不自动 retry C2（R2 在 P1.3 加） |
| `NOT_FF_MERGEABLE`（held） | base (main) 已 advance，PR branch 不是 ff 可达 | hold + 不重跑 C2/C4/C5（产物未变）；触发 rebase 子流程（P1.2 阶段 = 让人 rebase；C7 落地后 = 重排队列，见 §6 Q6-2） |
| `HUMAN_BLOCKED`（held） | PR 已有 `human:block` label | hold + no-op；不重复加 label / 不再 comment；等人移标签后下次 gate run 重新评估 |
| `MISSING_INPUT`（Error） | verify_report_path / review_report_path 不存在 / 不可读 | abort，输出 Error；不触碰 PR |
| `INVALID_REPORT`（Error） | report JSON parse 失败 / schema 不符 | abort，输出 Error |
| `GIT_ERROR`（Error） | `git merge --ff-only` 失败（非 NOT_FF_MERGEABLE，是 git binary 错误）/ push 失败 | abort，retryable=true（外层可重试） |
| `GH_ERROR`（Error） | `gh` CLI 失败（auth 失效 / network） | abort，retryable=true |
| `PERMISSION_DENIED`（Error） | merge to main 被远程拒（branch protection 不允 ff push） | abort，retryable=false；提示用户检查 GitHub branch protection 配置 |

**关键设计点**：`NOT_FF_MERGEABLE` 不触发重跑 C2/C4/C5 — rebase 后**代码产物 = 同一个 tree**（只是父 commit 换了），所以已有的 verify_report / review_report 仍 valid。这是降低 P1.2 闭环成本的关键决策。

## 4. AI Prompt Template

**N/A — 此模块是契约，规则评估纯 boolean 逻辑（4 条 AND），不跑 AI prompt。**

副作用执行（gh CLI / git CLI / 落盘）也不涉及 AI。任何"自然语言生成"的部分（如 PR comment 里 finding 渲染）都是模板化字符串拼接，不调 Claude session。

## 5. Acceptance Criteria

可证伪的 AC（每条对应一个 test）：

- **AC-1 4 条全 pass → merged**：给定 `verify.overall=pass, review.verdict=approve, ff_mergeable=true, !has_label("human:block")` → `gate_result=merged`，main HEAD 前进，merged_sha 输出。
- **AC-2 verify 失败 → held**：`verify.overall=fail` 其他全 pass → `gate_result=held, reason=VERIFY_NOT_PASS, recovery_action.kind=no_op`（不加 label / 不 comment）；main 不动。
- **AC-3 review block → held + R1**：`review.verdict=block` 其他全 pass → `gate_result=held, reason=REVIEW_NOT_APPROVE, recovery_action.kind=r1_label_and_comment, label_added=true, comment_posted=true`；comment body 含所有 findings 的 category + severity + summary + location + suggested_fix 字段渲染。
- **AC-4 非 ff → held + 不重跑**：`ff_mergeable=false` 其他全 pass → `gate_result=held, reason=NOT_FF_MERGEABLE`；不调 C4 / 不调 C5；main 不动。
- **AC-5 已 human:block → no-op**：PR 已有 `human:block` 标签 + 其他规则随意 → `gate_result=held, reason=HUMAN_BLOCKED, recovery_action.kind=no_op`；不重复加 label / 不重复 comment。
- **AC-6 MISSING_INPUT → Error**：verify_report_path 不存在 → `Error.code=MISSING_INPUT`；不动 PR / 不动 main。
- **AC-7 Determinism**：同一 input 跑 N 次（N ≥ 3）→ N 次 output `gate_result` + `reason` + `rules` 完全一致（dry_run 模式下验证）。
- **AC-8 dry_run 不触发副作用**：dry_run=true 时 review_approved=false → 输出仍含 reason=REVIEW_NOT_APPROVE，但 `recovery_action.label_added=false, comment_posted=false, comment_url=null`。
- **AC-9 ff-only enforce**：merge 路径必使用 `--ff-only` 等价语义；若 ff 失败（race condition：评估时 ff_mergeable=true 但 merge 时 base 移动）→ 输出 Error `GIT_ERROR, retryable=true`，不 fallback 到 merge-commit。
- **AC-10 Gate report 落盘**：每次调用必落盘 `<repo_root>/.suiyin/gates/<pr_ref>-<ts>.json`，含完整 output（含 dry_run 标志）。

## 6. Open Questions

- **Q6**（从 `toolchain.md` C6 节继承）: Gate 失败升级通知渠道（取决于实现选项）。**当前 P1.2 决议**: 仅落地 PR comment + `human:block` 标签作为通知通道；邮件 / IM webhook 留 P3+。Q6 在 P1.2 阶段降级为"通知通道 = PR comment"，不再开。
- **Q6-2**: `NOT_FF_MERGEABLE` 时 rebase 由谁触发？候选：
  - (a) C6 自动 rebase 后重新评估（contract 内嵌）— 复杂度高、有 merge conflict 风险
  - (b) hold + 等 C7 Phase Coordinator 重排队列（P1.3 加 C7 后）
  - (c) hold + 让人 rebase（P1.2 阶段最简兜底）
  - **当前倾向**: P1.2 = (c)；C7 落地后转 (b)。
- **Q6-3**: `human:block` 标签被人移除后，是否自动 re-run gate？候选：
  - (a) GitHub webhook 触发（重型）
  - (b) 下一次 push 触发（依赖 push event 钩子）
  - (c) 手动 CLI `suiyin-flow gate run <pr>` 重跑（最简）
  - **当前倾向**: P1.2 = (c)；自动触发留 P3+ 决定。
- **Q6-4**: 多次 hold（同一 PR 不同 reason 反复）时 PR comment 策略？候选：
  - (a) thread to single root comment + reply 累加
  - (b) 每次 hold 新 comment（时间序列，简单不丢历史）
  - **当前倾向**: (b) 简单且 audit trail 清晰。
- **Q6-5**: gate 评估时机？候选：
  - (a) C5 review 完成后由 caller（C7 / 人）显式调
  - (b) git pre-push hook 自动调
  - (c) GitHub Actions on PR review event 自动调
  - **当前倾向**: P1.2 = (a) 显式调（先把闭环跑通），(b)/(c) 等 P1.3 C7 / Actions 集成后加。

## 7. Implementation Notes

### 实现谱系（toolchain.md C6 节复述 + v4 P1.2 选项）

| 选项 | 性质 | v4 阶段 |
|---|---|---|
| (a) git pre-push hook + Python CLI | 本地零 SaaS | **P1.2 默认** |
| (b) 通用 CI（GitLab/CircleCI/Jenkins）| 集中评估 | 留 |
| (c) GitHub Branch Protection + Merge Queue | SaaS 集成 | 留 |
| (d) 混合（本地 hook 反馈 + CI 权威） | 双层兜底 | 长期目标 |

**P1.2 落地形态**：

```bash
# .git/hooks/pre-push 或 lefthook
suiyin-flow gate run \
  --pr <ref> \
  --verify-report .suiyin/verify/<pr>.json \
  --review-report .suiyin/reviews/<pr>.json
```

CLI 内部跑规则评估 + 副作用执行，输出 gate_report.json + exit code（0 = merged，1 = held，2 = Error）。

### CLI 入口 / Unified CLI

C6 通过顶层 unified dispatcher（同 C2/C4/C5，见 C2 §7 "Unified CLI"）注册 `gate` subcommand：

```python
# src/suiyin_flow/cli.py
def main(argv):
    cmd = argv[0]
    if cmd == "verify": return c4_verify.cli.main(argv)
    if cmd == "task":   return c2_executor.cli.main(argv)
    if cmd == "review": return c5_reviewer.cli.main(argv)
    if cmd == "gate":   return c6_gate.cli.main(argv)   # C6 入口
    ...
```

### 模块拆分建议

```
suiyin_flow/
  c6_gate/
    __init__.py
    cli.py            # `suiyin-flow gate run`
    contract.py       # §2 schema (Pydantic)
    rules.py          # §3.1 4 条 invariant 评估（纯函数）
    ff_check.py       # ff_mergeable 检测（git CLI 包装）
    actions.py        # merge / label / comment 副作用执行
    report.py         # gate_report.json 落盘
```

### 跨平台兼容性（NC-5）

规则同 C5/C2 跨平台节（`pathlib.Path` / `subprocess.run(shell=False)` / `gh` + `git` CLI 走 `shutil.which` 检测 / `encoding='utf-8'` 等）。不重复。

### 跟其他 C 模块协作

- **消费 C4 `verify_report.json`**：读 `overall` 字段判 verify_all_pass。
- **消费 C5 `review_report.json`**：读 `verdict` 字段判 review_approved；当 verdict=block 时读 `findings` 数组渲染 PR comment（R1）。
- **被 C7 Phase Coordinator 调用（P1.3+）**：C7 在 phase 内每个 task 的 C5 完成后调 C6；C6 输出 `held + reason=NOT_FF_MERGEABLE` 时 C7 决定 rebase / 重排 / 升级。
- **跟 C8 Deploy Contract 间接关联**：C6 merge 后 main 进入"可发布状态"，C8 在 main 上挑 release 点。
- **不调用 C11**：C6 不查重；查重在 C5 内嵌。

### 跟 constitution NC-1..NC-5 对照

- **NC-1**（零 SaaS）：C6 本身用本地 git CLI + 本地 gh CLI（gh CLI 是 SaaS 客户端，但远端可换 GitLab / Gitea，CLI 抽象在 actions.py 后）✅
- **NC-2**（spec-kit Layer 1 backbone）：C6 不写 spec/plan，只消费 C5 review_report ✅
- **NC-3**（业务项目独立性）：gate_report 落盘 `<repo_root>/.suiyin/gates/`，不在 v4 仓 ✅
- **NC-4**（worktree 隔离即安全边界）：C6 不 spawn worktree，但 merge 操作只 ff-only，不会污染未提交 worktree ✅
- **NC-5**（跨平台支持）：见跨平台节 ✅
- **PC-1**（最简实现优先）：P1.2 仅 (a) hook + Python CLI，不引入 GitHub Actions / Merge Queue ✅
- **PC-2**（组件 vs 契约明确分离）：C6 明确标"行为契约"，无 imperative 推断逻辑（4 条 AND boolean） ✅

### Block Recovery R1 协作约定

C5 spec §7 已经定义了 Block Recovery 三阶段（R1/R2/R3）。C6 在 P1.2 阶段**只实现 R1**：

| C5 verdict | C6 触发 |
|---|---|
| `approve` | 评估其他 3 条规则；全 pass → merge |
| `block` | held + `human:block` 标签 + PR comment 渲染 findings |

R2（C2 retry-with-feedback）和 R3（Codex 仲裁）在 P1.3 / P3+ 阶段才会让 C6 加分支处理。当前 spec 不写 R2/R3 钩子，避免过度设计。

### v4 自身 dogfood

- **T-004（本 spec PR）**: C5 self-review C6 spec — 自举验证 spec 结构与 v0.1.1 contract 一致。
- **P1.2 mini-dogfood T-005（impl PR 阶段）**: 用 C6 对已 merged PR #30（C5 impl）做 mock pre-merge gate 评估 — 重跑 verify + review 落盘 fixture，再喂给 C6 验证 4 条规则评估正确。验证点：
  - 4 条全 pass 时 gate_result=merged（dry_run）
  - 人为篡改 verify_report 让 overall=fail → gate_result=held, reason=VERIFY_NOT_PASS
  - 人为篡改 review_report 让 verdict=block → gate_result=held, reason=REVIEW_NOT_APPROVE, comment 渲染正确
  - 模拟 base 前进 → ff_mergeable=false → reason=NOT_FF_MERGEABLE
- **后续 dogfood**: P1.2.5 tasks.yaml → C2 adapter 跑通后，跑一次"真闭环" — `/sy-tasks` → 生成 tasks.yaml → batch 跑 → C2 → C4 → C5 → C6 全自动到 merge。

---

**Version**: v0.1.0-draft
**Last Updated**: 2026-05-24
**Status**: draft（待 C5 self-review + user 审）
