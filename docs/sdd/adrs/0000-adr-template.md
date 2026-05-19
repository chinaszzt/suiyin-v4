# ADR-NNNN: {Title}

> Architecture Decision Record. 记录单个**项目独有**的架构 / 流程决策。
>
> 用本模板：复制此文件为 `NNNN-{kebab-slug}.md`，按 8 章节填写。
> 缺章节 → 显式 `N/A` + 理由。

---

## Status

`Proposed` | `Accepted (YYYY-MM-DD)` | `Deprecated by ADR-XXXX (YYYY-MM-DD)` | `Superseded by ADR-XXXX (YYYY-MM-DD)`

## Context

触发本次决策的情况：

- 之前的状态 / 假设
- 什么事件 / 需求 / dogfood 反馈触发审视
- 为什么需要正式记录（不只是聊天里说说）

## Decision

做了什么决定（**一句话能说清**最好，详细在 Rationale）：

- ...
- ...

## Rationale

为什么做这个决定，**vs 其他候选方案**：

| 方案 | 选 / 弃 | 理由 |
|---|:---:|---|
| Option A | ✗ | ... |
| Option B (chosen) | ✓ | ... |
| Option C | ✗ | ... |

## Consequences

### Positive

- 正面影响 1
- 正面影响 2

### Negative / Trade-off

- 负面影响 / 代价
- 已知风险

### Cascade（影响范围 — 哪些下层文档要 cascade 修改）

| 文件 / 模块 | 修改类型 | 状态 |
|---|---|---|
| `path/to/file.md` | ... | ✅ 已改 / ⏳ 待 P0.X / ❌ 不改 |

## Alternatives Considered

如果 Rationale 里没穷举，这里展开：

- **Option X**: ... — 弃用理由
- **Option Y**: ... — 弃用理由

或写 `N/A`（如果只有一个明显方案）。

## References

- Related ADRs: ADR-XXXX (depends on), ADR-YYYY (related)
- PRs / Commits: `PR #N`, `commit abcd1234`
- Relevant Specs / Docs: `docs/sdd/...`
- Discussion: chat session / issue link

## Author + Date

- **Author**: {name / role}
- **Decided**: YYYY-MM-DD
- **Last Updated**: YYYY-MM-DD

---

## 编号约定

- ADR 编号 4 位数 0001-9999，单调递增，不复用
- 文件名: `NNNN-{kebab-slug}.md`（slug 用短语，不要超过 5-6 词）
- 编号与时间序无关（按提交顺序，不按决定生效顺序）

## Status 流转

```
Proposed ──> Accepted ──┬──> Deprecated by ADR-XXXX
                         └──> Superseded by ADR-XXXX
```

- **Proposed**: 在 PR 里讨论中
- **Accepted**: 已 merged，生效
- **Deprecated**: 不再适用但保留为历史（无后继）
- **Superseded**: 被新 ADR 替代（必标新 ADR 编号）

Deprecated / Superseded 的 ADR **不能删除**——保留历史 trace。
