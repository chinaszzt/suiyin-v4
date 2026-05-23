# ADR-0002: v4 工具链技术栈 = Python 3.11+

---

## Status

`Accepted (2026-05-24)`

## Context

constitution v0.2 §6b Q-C-2 留下 open question: **v4 自身工具链 CLI 用什么语言**
（候选 Python / Shell / Bun / Go），标注"待 C2/C4 实现时定"。

P1.1 阶段 1 写 C2 Task Executor / C4 Verify Contract spec 时（2026-05-20 前后），
触发实际需求审视：

- C2 要包 git worktree / Claude Code headless `kill -9` 整树超时 / Pydantic schema
- C4 要解析 pytest-style 测试名 → AC 映射 / 跑 CLI / 结构化 JSON 报告
- 两者都要严格 type-safety、能跨平台跑（macOS dev + Linux CI）
- AI 主写代码（D-autonomous）→ 强类型 + 大社区文档是 hard requirement

P1.1 阶段 1 user 在 spec PR #11 拍板 = Python 3.11+。C2 §0 / C4 §7 已**事实记录**该决定，
但 constitution Q-C-2 行未关闭、也没正式 ADR 记 trace。

按 governance §8.1，关闭 constitution Open Question 属于 substantive 变更，必须补 ADR。
本 ADR 即追溯记录该决策。

## Decision

**v4 工具链 imperative 实现统一用 Python 3.11+**，配套技术栈：

- **Runtime**: Python 3.11+（match-case / 更快 startup / pathlib 增强）
- **Schema**: pydantic 2.x（C2/C4 input/output/error schema 全部 Pydantic model）
- **Testing**: pytest（AC↔test 命名 Fork G 跑在 pytest 上）
- **Linting**: ruff（替代 black + flake8 + isort）
- **Type checking**: mypy（strict 模式，AI 写的代码必须先过 mypy）
- **Process control**: psutil（C2 §3.2 整树 `kill -9`，跨平台 process tree 枚举）

## Rationale

| 方案 | 选 / 弃 | 理由 |
|---|:---:|---|
| **Shell (bash/zsh)** | ✗ | 没类型；JSON schema 校验靠 jq 拼；超过 200 行不可维护；AI 写起来易出 quoting bug |
| **Bun + TypeScript** | ✗ | 业务用户多数没 Bun runtime；TS 生态对 process tree 控制 / psutil 等价物薄；Bun 跨平台仍在演进 |
| **Go** | ✗ | 编译产物友好但开发循环慢；Pydantic 等价的 schema 体验不如 Python；AI 主写时 Go 反射 / generic 心智负担大 |
| **Python 3.11+ (chosen)** | ✓ | 生态最成熟（pydantic / pytest / mypy / psutil）；强类型可选；macOS / Linux 默认带 / brew install 易；AI 训练数据最厚 → 出错率低；PC-1 最简实现优先 |

关键决定因素：

1. **PC-1 最简实现优先**: pydantic schema 一行 `class TaskInput(BaseModel): ...` vs Go struct tag 或 TS Zod 配置
2. **AI 友好**: Python 在 AI 训练数据中占比最高，AI 写 Python 出错率最低
3. **跨平台 process control**: psutil 是 process tree 枚举 / kill 的事实标准（C2 §3.2 整树 kill 强需求）
4. **业务项目零摩擦**: Flutter dev box 通常已有 Python（Flutter doctor 自带 check）；最坏 `brew install python@3.11` 一行

## Consequences

### Positive

- **生态成熟**: pydantic 2.x / pytest / mypy / ruff 都是事实标准，文档 / Stack Overflow 答案多
- **强类型 + AI 友好**: mypy strict + pydantic runtime 校验 → AI 写的代码可机器验证，与 D-autonomous 自动 merge 模型契合
- **跨平台**: subprocess / pathlib / psutil 在 macOS + Linux 行为一致；Windows 通过 WSL（业务不优先）
- **单一语言**: C1-C11 imperative 组件不混语言，认知成本低；共享 utils 易抽取
- **测试基础设施**: pytest fixture / monkeypatch 让 C4 这种"跑测试 + 解析结果"的 meta-tooling 写起来很自然

### Negative / Trade-off

- **业务项目要装 Python**: Flutter dev box 通常已有 / 否则 `brew install python@3.11` 一行。可接受。
- **启动时长**: 比 Go 编译产物慢（~50-200ms vs <10ms），但 C2/C4 都是分钟级任务，启动开销不构成 bottleneck
- **打包分发**: 不像 Go 单二进制；要靠 venv + pip install。已用 `pyproject.toml` + 安装脚本 `bin/init.sh` 兜底
- **版本要求**: Python 3.11+（match-case / Self type / 更好 error message），低于 3.11 不支持。macOS 系统 Python 通常 3.9，要求用户 brew install

### Cascade（影响范围 — 哪些下层文档要 cascade 修改）

| 文件 / 模块 | 修改类型 | 状态 |
|---|---|---|
| `docs/sdd/constitution.md` §6b Q-C-2 | 关闭 open question，引用本 ADR | ✅ 本 PR 同步 |
| `docs/sdd/constitution.md` §9 + metadata | bump v0.2.0 → v0.2.1 (PATCH，关 Q 不改 NC) | ✅ 本 PR 同步 |
| `docs/sdd/components/c2-task-executor.md` §0 | 已记录 Python 决定，无需改 | ✅ 已落地 (v0.1.1) |
| `docs/sdd/components/c4-verify-contract.md` §7 | 已记录 Python 决定，无需改 | ✅ 已落地 (v0.1.1) |
| `pyproject.toml` / `src/suiyin_flow/` | 已经 Python 实现，无需改 | ✅ 已落地 (PR #20, #21, #22, #23) |
| 未来 C1 / C3 / C5-C11 imperative 实现 | 必须用 Python 3.11+，否则 block | ⏳ 待 P1.2+ 各组件实现时 enforce |

## Alternatives Considered

见 Rationale 表格（已穷举 4 个候选）。

## References

- Related ADRs: ADR-0001 (constitution v0.1 → v0.2，本 ADR 关闭它留的 Q-C-2)
- PRs / Commits:
  - `PR #11` (C2 spec — 首次记录 Python 决定)
  - `PR #20` (C4 impl — Python 落地)
  - `PR #21` (C2 impl — Python 落地)
  - `PR #22` (C4 venv fallback — Python 实践)
  - `PR #23` (C2 session.py — Python 实践)
- Relevant Specs / Docs:
  - `docs/sdd/constitution.md` §6b Q-C-2 (本 ADR 关闭的 open question)
  - `docs/sdd/components/c2-task-executor.md` §0 (事实记录)
  - `docs/sdd/components/c4-verify-contract.md` §7 (事实记录)
  - `docs/sdd/todo.md` §P0.3 (本 ADR 的 task 入口)
- Discussion: 2026-05-20 P1.1 阶段 1 spec PR review

## Author + Date

- **Author**: 张佗 + Claude
- **Decided**: 2026-05-20（C2/C4 spec PR 时事实拍板）
- **Recorded**: 2026-05-24（追溯文档：决策落地后补 ADR + 关 Q-C-2）
- **Last Updated**: 2026-05-24

---

## Version History

| Version | Date | Changes |
|---|---|---|
| v0.1.0 | 2026-05-24 | 初版（追溯 P1.1 阶段 1 Python 拍板 + 关闭 constitution §6b Q-C-2） |
