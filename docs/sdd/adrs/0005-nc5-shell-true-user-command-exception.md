# ADR-0005: NC-5 subprocess 条目加"用户命令字符串 shell=True"例外

> r4 真闭环发现 #2 的 constitution cascade：宪法 Test 启发式与正确实现冲突，修文字不修约束本体。

---

## Status

`Accepted (2026-07-09)`

## Context

- NC-5（跨平台支持，ADR-0003 引入）的 Test 清单写死一条执法启发式：`subprocess：shell=False + list[str] args（避免 Windows shell 语义差异）`。
- r4 真闭环（2026-06-12，v5 login-core-r4）发现 #2：C7 reverify 旧版按这条启发式用 `shlex.split + shell=False` 跑用户 verify_cmd，`&&` 被当**字面参数**（实测 `echo a && echo b` → `a && echo b`）→ 复合 verify_cmd（`npm install && npm run typecheck && npx vitest`）必失败 → REVERIFY_FAILED 误 park 健康代码。
- 修复（C7 v0.1.1，PR #57）把 `run_verify` 改 `shell=True`：verify_cmd 是用户定义的整串 shell 命令，本就该 shell 解释（POSIX→`/bin/sh`、Windows→`cmd`，`&&` 两边语义都成立）。**这是正确的跨平台行为，但与宪法 Test 文字直接冲突**。
- 同一启发式被 C5 spec §2.2 category 注释 + §4 review checklist（以及 `src/suiyin_flow/c5_reviewer/prompt.py`）复述为「`shell=True` = cross_platform 违规」——C5 下次 review C7 类代码会按宪法误报，且 cross_platform 虽非 block 集合、但 NC 违规（nc_violation）是，误判升级路径存在。
- 正式记录原因：constitution 修改必须走 governance §8.1（ADR + PR + 人审）；且这是「执法启发式 vs 约束本体」的第一次显式区分，值得留 trace。

## Decision

1. NC-5 Test 的 subprocess 条目改为：**默认 `shell=False` + `list[str]` args；例外：执行用户提供的整串 shell 命令（如 verify_cmd）必须 `shell=True`（POSIX→`/bin/sh`、Windows→`cmd`），禁止 `shlex.split` 后 `shell=False` 跑**。
2. constitution v0.2.2 → **v0.2.3（PATCH）**。
3. Cascade 同 PR 完成：C5 spec v0.1.2 → v0.1.3（§2.2 注释 + §4 checklist 同句例外）+ `c5_reviewer/prompt.py` 同步。

## Rationale

| 方案 | 选 / 弃 | 理由 |
|---|:---:|---|
| 保持 blanket `shell=False`，要求 C7 回退 | ✗ | r4 #2 实证该写法在含 `&&` 的用户命令上**恰恰破坏 NC-5 本体意图**（三平台正确跑）。启发式压倒本体 = 本末倒置。 |
| **PATCH 加例外（chosen）** | ✓ | NC-5 约束本体（macOS/Linux/Windows 三平台可跑）**未变**；Test 清单是执法启发式，例外让启发式回归本体意图。 |
| 升 MINOR | ✗ | 没有新增/移除/重定义 NC。`INVALID_VERSION_BUMP` 的判据是"constraint 语义"变化——此处语义（跨平台可跑）不变，变的是启发式清单的精度。 |
| 把 Test 清单整体挪出 constitution（到 methodology / C2 §7） | ✗ | 动静大、cascade 面广；启发式与 NC 同处便于 C4 L4 / C5 直接引用。若后续例外反复累积再议。 |

## Consequences

### Positive

- 宪法文字与正确实现一致，消除 C5 误报 C7 的定时炸弹。
- 显式确立「约束本体 vs 执法启发式」的区分：启发式可 PATCH 修，本体动才升 MINOR/MAJOR。

### Negative / Trade-off

- `shell=True` 意味着 verify_cmd 是**受信输入**。与 v4 威胁模型一致（verify_cmd 由用户在自己项目的 tasks.yaml 里定义，不存在对抗自己仓库的攻击者），但若未来出现"第三方提供 tasks.yaml"场景需重估。
- **附带发现（本 ADR 走 §8.1 流程时暴露）**：governance §8.1 step 3 要求 C5 review 宪法 PR，但 C5 §2.1 required `spec_ref/plan_ref/task_id` 使宪法类 PR 无法构造合法输入——C5 审宪法 PR 的输入形态是 open gap，下次动 C5 时定（已记 todo）。

### Cascade（影响范围）

| 文件 / 模块 | 修改类型 | 状态 |
|---|---|---|
| `docs/sdd/constitution.md` | NC-5 Test subprocess 条目 + v0.2.3 | ✅ 本 PR |
| `docs/sdd/components/c5-ai-reviewer.md` | §2.2 注释 + §4 checklist 例外，v0.1.3 | ✅ 本 PR |
| `src/suiyin_flow/c5_reviewer/prompt.py` | checklist 同句例外（CONTRACT_VERSION 不变，report schema 未动） | ✅ 本 PR |
| `docs/sdd/components/c7-phase-coordinator.md` | 例外的合法使用方 | ❌ 不改（v0.1.1 已自带 rationale） |
| `docs/sdd/components/c2-task-executor.md` §7 表 | `shell=True ❌` | ❌ 不改（C2 自身不直跑用户命令串——verify_cmd 经 prompt 由 AI session 的 bash 执行；表述对 C2 自身子进程仍准确） |
| `docs/sdd/components/c4-verify-contract.md` §7 | runner 调用 `shell=False` | ❌ 不改（L1/L2 runner 命令是配置化 list 形态，非用户整串命令） |

## Alternatives Considered

N/A（Rationale 表已穷举）。

## References

- Related ADRs: ADR-0003（NC-5 引入）
- PRs / Commits: PR #57（C7 v0.1.1 修复）；本 PR（issue #60 任务 3）
- Relevant Specs / Docs: `docs/sdd/todo.md` r4 发现 #2、`components/c7-phase-coordinator.md` §3.2/§3.3、`components/c5-ai-reviewer.md` §4
- Discussion: GitHub issue #60（Phase 0 关门）

## Author + Date

- **Author**: Claude（Fable 5 session，2026-07-09 流程评估）+ user 拍板
- **Decided**: 2026-07-09
- **Last Updated**: 2026-07-09
