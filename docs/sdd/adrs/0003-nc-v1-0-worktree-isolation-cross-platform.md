# ADR-0003: NC v1.0 — 新增 NC-4 (worktree 隔离安全边界) + NC-5 (跨平台支持)

> P1.1 P0 MVP 跑通后的 constitution 回顾, 把 v4 设计期就隐含但未明文的 2 个不可妥协前提
> 正式 promote 到 NC, 关闭 Q-C-1 v1.0 集合.

---

## Status

`Accepted (2026-05-24)`

## Context

P1.1 (P0 MVP) 跑完整闭环后 (PR #11 spec → PR #20-25 impl + hotfix → PR #24 真 dogfood),
回头审 constitution v0.2.1 (NC-1/2/3 + PC-1/2/3), 发现 2 个 P1.1 经验里反复体现、
但 constitution 没明文写的不可妥协前提:

1. **Worktree 隔离作为 C2 自动化安全边界**: C2 用 `--permission-mode bypassPermissions` 给
   AI 全权 Write/Edit/Bash 工具. 这个授权模型**只有在 AI 被隔离在 worktree 内才安全**.
   一旦 AI 能动主仓 working tree, 整个安全模型崩塌.
   - 当前隐含: C2 spec §3.1 I1/I2 强制 worktree 路径命名 + AI session 必须在 worktree 内.
   - 但未来 C3 Multi-Implementation Arbiter / C5 AI Reviewer / 其他 imperative 组件都要遵守
     同一约束, 拉到 constitution 层 = 不再依赖每个 component spec 重复声明.

2. **跨平台支持作为 v4 市场定位的隐性 NC**: P1.1 各 spec §7 都写了"跨平台兼容性"节
   (pathlib / psutil / shell=False / utf-8 explicit / shutil.which fallback), 实质上是
   "v4 必须跑 macOS + Linux + Windows" 的 NC 级承诺.
   - 但 constitution v0.2.1 没明文.
   - PR #22 venv PATH fix + PR #25 unified CLI 都是为跨平台铺路.
   - 不明文 = 未来 PR 引入 POSIX-only 调用 (`os.kill SIGKILL` / `/bin/sh`) 没拦截机制.

按 governance §8.1 三问法 (v4 独有? 项目原则? 行为约束?) 两条都过, 应升 NC.

Q-C-1 ("完整 NON-NEGOTIABLE 集合 — P0 spike 后定 v1.0") 是 P0 spike 的退出条件之一.
P1.1 即 P0 spike, 跑通后正是关闭 Q-C-1 的时机.

## Decision

### 加 NC-4: 隔离 worktree 是自动化执行的安全边界

所有 v4 自动化执行类组件 (C2 / C3 / C5 / 未来 imperative 组件) **必须**在隔离 git worktree 内运行,
**严禁**直接对主仓 working tree 写入.

### 加 NC-5: 跨平台支持 (macOS / Linux / Windows)

v4 工具链 (CLI / runner / installer / etc) **必须**在三个 platform 都能跑.
任何 POSIX-only 调用必须有 Windows fallback.

### 关闭 Q-C-1: NC v1.0 集合 = NC-1..NC-5 + PC-1..PC-3

P0 spike (P1.1) 跑过, NC v1.0 集合宣告完整: 5 NC + 3 PC. 未来新增 NC/PC 走 governance §8.1
独立 ADR (本 ADR 之后).

### bump constitution v0.2.1 → v0.2.2

MINOR (新增 2 个 NC, 关闭 1 个 open question).

## Rationale

### NC-4 worktree 隔离 vs PC

| 方案 | 选 / 弃 | 理由 |
|---|:---:|---|
| **NC-4 (chosen)** | ✓ | 没了 worktree 隔离, `bypassPermissions` 等于授 AI 写主仓 git history / branches / settings, **整个安全模型崩**. 这条不允许"PR-by-PR override". |
| PC-4 (弃) | ✗ | PC 允许 ADR override; 但 worktree 隔离不允许 override (override = 安全洞). 应是 NC. |
| 留隐式 (弃) | ✗ | 隐式在 C2 §I1/I2; 但 C3/C5/etc 未来要重复声明. 拉 constitution 层 = single source of truth. |

### NC-5 跨平台 vs PC

| 方案 | 选 / 弃 | 理由 |
|---|:---:|---|
| **NC-5 (chosen)** | ✓ | 业务项目 dev box 可能 Windows / Linux / macOS. v4 工具如果绑死 POSIX 等于丢 Windows 市场. 跨平台代码成本低 (pathlib / psutil / shell=False / utf-8 explicit), 设计期付小成本 vs 长期重构代价 — user 拍 NC. |
| PC-5 (弃) | ✗ | PC 允许 PR 用"先做 macOS 后做 Windows"做借口; 不强制设计期就跨平台 → 长期累积 POSIX 假设. NC 更稳. |
| 限 macOS+Linux (弃) | ✗ | 失 Windows 业务 dev box (含 WSL 用户). 不符合 v4 市场定位. |

### Q-C-1 v1.0 vs 继续 open

| 方案 | 选 / 弃 | 理由 |
|---|:---:|---|
| **v1.0 关闭 (chosen)** | ✓ | P0 spike (P1.1) 跑过, 用户 reflection 拍板 NC-4/5. 5 NC + 3 PC 是"最小够用 + 各有明确 rationale"集合. 继续 open 等不到更好 trigger. |
| 继续 open 到 P1.2 (弃) | ✗ | P1.2 (C5+C6) 跑通不会暴露新 NC 候选 (C5 是 imperative 组件, 受 NC-4 约束; C6 是契约, 受 NC-1 约束). 没必要 hold. |

## Consequences

### Positive

- **NC-4**: C3/C5/etc 未来组件不用各自重复声明 worktree 约束, 直接 reference NC-4
- **NC-4**: C5 AI Reviewer (P1.2) 实现时多一条 finding 类: `non_negotiable_violation` for 任何"主仓 working tree 写入"代码
- **NC-5**: 跨平台不再是"软约束", 任何 POSIX-only PR 会被 C5 block (一旦 reviewer 实现)
- **NC-5**: 设计期就提示 Windows fallback, 避免 P1+ 大返工
- **Q-C-1 关闭**: 减少 1 个 pending fork; constitution v0.2.2 进入"稳态" (后续变化是新 ADR 增量, 不是"还在 finalize")
- **整体**: NC 数量从 3 → 5, 仍满足 I6 invariant ("一年内 NC 数量变化 ≤ 2 条" — 本次正好 +2)

### Negative / Trade-off

- **NC-4**: 限制了某些场景灵活性 — 如果未来想做"hotfix 类组件直接动 main", 需要走 NC override (走新 ADR + MAJOR bump 改 NC-4 性质). 但 hotfix 本来就该走标准 git workflow, 不该是自动化范畴.
- **NC-5**: Windows runtime 实际测试成本高 (CI matrix + dev box). P0 阶段已 punt 到 P1+ CI. 这条 NC 在 P1+ CI 落地前是"design-level enforcement" (C5 reviewer 看代码, 不实测 Windows). 一旦 Windows CI matrix 落地 (P1+ Tooling), 升级到"runtime enforcement".
- **NC 集合 v1.0 关闭**: 未来增 NC 要走 ADR + 人审 — 标准 governance §8.1, 不算新代价.

### Cascade（影响范围 — 哪些下层文档要 cascade 修改）

| 文件 / 模块 | 修改类型 | 状态 |
|---|---|---|
| `docs/sdd/constitution.md` §6 | 加 NC-4 + NC-5 文段 | ✅ 本 PR 同步 |
| `docs/sdd/constitution.md` §6b Q-C-1 | 状态改 "已拍 v1.0: 见 ADR-0003" | ✅ 本 PR 同步 |
| `docs/sdd/constitution.md` §9 + metadata | bump v0.2.1 → v0.2.2 | ✅ 本 PR 同步 |
| `docs/sdd/components/c2-task-executor.md` | NC-4 已隐含在 §3.1 I1/I2, 无需改 | ✅ 已 cover |
| `docs/sdd/components/c4-verify-contract.md` | NC-5 已隐含在 §7 跨平台节, 无需改 | ✅ 已 cover |
| 未来 C5 AI Reviewer spec (P1.2) | 必须含 NC-4/NC-5 检查 finding | ⏳ P1.2 设计时落地 |
| 未来 C3 Arbiter spec (P3) | 必须延续 NC-4 worktree 约束 | ⏳ P3 设计时落地 |
| `docs/sdd/todo.md` Pending Forks | Q-C-1 移除 | ⏳ 下个 todo cleanup PR |

## Alternatives Considered

### 不加 NC-4 (worktree 隔离), 让 component spec 各自重复

- **弃用理由**: 重复声明易漂 (C2 写了 C3 忘了); 跨多 spec 的 invariant 应 promote 到 constitution layer
- **user 反馈**: "成本不高，免去很多麻烦"

### 把 cross-platform 升 NC-5 vs 留 PC-4

- 我初步推荐 PC-4 (Windows 只是 ≥smoke)
- **user 拍 NC-5**: "成本不高，免去很多麻烦" — 长期省返工
- **接受 user 判断**: NC 增加设计期 discipline, 短期略繁但长期收益高. v4 用户画像 (业务专家 + 不审 PR) 也要求"工具一开始就靠谱", 不能"先做能用再补 Windows"

### 把 NC-4 / NC-5 拆成两个独立 ADR

- 弃: 两条都是同一次 P1.1 review insights 触发, 应同 PR / 同 ADR 落地, 减少 governance ceremony

### 留 Q-C-1 open 到 P1.2 后再宣告 v1.0

- 弃: P1.2 (C5 + C6) 不太可能再暴露新 NC 候选 (C5 受 NC-4 约束, C6 受 NC-1 约束). 没必要 hold, 现在就关.

## References

- **Related ADRs**:
  - ADR-0001 (constitution v0.1 → v0.2 layering fix)
  - ADR-0002 (Python 技术栈; 关 Q-C-2)
- **PRs / Commits (P1.1 经验来源)**:
  - PR #11 (C2/C4 spec v0.1.1)
  - PR #20 (C4 impl) / PR #21 (C2 impl)
  - PR #22 (C4 venv PATH fallback — NC-5 跨平台经验)
  - PR #23 (C2 stream-json parse)
  - PR #24 (真 dogfood — NC-4 worktree 隔离实证 work)
  - PR #25 (P0 spike triage 4 bugs — NC-5 跨平台 + 工具健壮性)
- **Relevant Specs**:
  - `docs/sdd/constitution.md` §6 (NC/PC 集合)
  - `docs/sdd/components/c2-task-executor.md` §3.1 I1/I2 (worktree 隔离已隐含)
  - `docs/sdd/components/c4-verify-contract.md` §7 (跨平台节已隐含)
- **Discussion**: P1.1.1 constitution review 2026-05-24 session

## Author + Date

- **Author**: 张佗 (拍板 NC-4/NC-5/v1.0) + Claude (review + ADR 草稿)
- **Decided**: 2026-05-24
- **Last Updated**: 2026-05-24

---

## Version History

| Version | Date | Changes |
|---|---|---|
| v0.1.0 | 2026-05-24 | 初版: 加 NC-4 (worktree 隔离) + NC-5 (跨平台) + Q-C-1 关 v1.0 |
