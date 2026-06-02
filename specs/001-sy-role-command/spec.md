# Feature Specification: /sy-role — 协商 role-profile.yml 的交互式 slash command

**Feature Branch**: `claude/sy-role-dogfood-p125` (spec dir: `specs/001-sy-role-command`)

> v4 disables the `before_specify` hook, so the working branch is the pre-created worktree
> branch — NOT a hook-cut `NNN-<slug>` branch. The spec directory keeps the `NNN-` prefix
> only for ordering; it does not imply a matching git branch exists.

**Created**: 2026-05-28

**Status**: Draft

**Input**: User description: "/sy-role interactive slash command for negotiating role-profile.yml (4 tier presets: assistant / junior / collaborator / autonomous). 4 档定义见 docs/sdd/role-profiles.md, 目标产物是 runtime/role-profile.yml（在业务项目内即 .specify/role-profile.yml）。"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 业务项目首次协商 role-profile (Priority: P1)

业务项目（v5 等）刚装完 v4 工具链（跑过 `bin/init.sh`），开发者打开 Claude Code session，跑 `/sy-role`。AI 提示 4 档预设的关键差异（draft_spec / auto_merge_pr / arbitrate_minor 三个最影响日常工作的能力），开发者回答想要的档位，AI 显示对应 yaml 草稿（含人介入点 + git automation 矩阵）让开发者确认，确认后写到 `.specify/role-profile.yml` 并 git commit。

**Why this priority**: 这是 /sy-role skill 存在的根本理由——目前用户必须手编辑 yaml（role-profiles.md L130-132），门槛偏高且容易写错 schema。MVP 必须覆盖这条路径。

**Independent Test**: 在一个干净的业务项目（刚跑完 `bin/init.sh`）内跑 `/sy-role`，回答提问，验证最终 `.specify/role-profile.yml` 的 `preset` 字段是用户选择的档，且 ai_capabilities / git_automation / human_gates 三块跟 docs/sdd/role-profiles.md 矩阵一致。

**Acceptance Scenarios**:

1. **Given** 业务项目已装 v4 工具链，`.specify/role-profile.yml` 是 v4 default (autonomous)，**When** 用户跑 `/sy-role` 选 collaborator，**Then** 文件被更新为 `preset: collaborator` 且 ai_capabilities 全部对齐 role-profiles.md C 档矩阵
2. **Given** 用户选 assistant 档，**When** 协商完成，**Then** yaml 中 `draft_spec: false` / `auto_review_pr: false` / `auto_merge_pr: false`（A 档严格人审）
3. **Given** 协商过程中用户回答模糊（"我也不知道选哪个"），**When** /sy-role 检测到，**Then** AI 提供"按 3 个关键能力问"的简化路径并给推荐档

---

### User Story 2 - 已有 profile 的局部修订 (Priority: P2)

项目已有 role-profile.yml（前次协商或手编辑产生）。开发者跑 `/sy-role`，AI 先读现有 yaml + 展示当前档位摘要，然后问开发者要不要换档 / 改某个具体能力（例如把 `auto_merge_pr` 从 true 改 false）。修订完成显示 diff，用户确认后写回 + commit。

**Why this priority**: 项目阶段会变（P0 严格 / P1+ 放松，role-profiles.md L13），需要支持 in-place 调整。但首次协商解决后再修订是低频操作，所以 P2 而非 P1。

**Independent Test**: 已有 `.specify/role-profile.yml` (preset: autonomous)，跑 `/sy-role` 选"修改单项"+"把 auto_push 改 true"，验证最终 yaml 只动了那一项，preset / 其他能力不变。

**Acceptance Scenarios**:

1. **Given** 现有 yaml `preset: autonomous, git_automation.auto_push: false`，**When** 用户跑 `/sy-role` 选"只改 auto_push 为 true"，**Then** yaml 中 `auto_push: true`，其他字段不变
2. **Given** 用户在 /sy-role 提问中途反悔（输入 abort / 退出），**When** 命令终止，**Then** yaml 文件**不被修改**（保持运行前状态）

---

### User Story 3 - bootstrap_special_cases 不可改 (Priority: P3)

`bootstrap_special_cases` 字段（当前是 `[sy-constitution]`）是 role-profiles.md 明确"所有档强制 auto-commit + auto-push"的特例。/sy-role 不应该让用户在交互中修改这一项——AI 在显示草稿时说明这一字段是工具链内置规则、不参与协商。

**Why this priority**: 这是"避免用户误操作破坏 bootstrap 契约"的护栏，但发生概率低（多数用户不会主动改这个字段），所以 P3。

**Independent Test**: 跑 `/sy-role`，主动问"我能改 bootstrap_special_cases 吗"，验证 AI 回复说明这是工具链内置不可改 + 最终 yaml 中该字段保持 `[sy-constitution]`。

**Acceptance Scenarios**:

1. **Given** 用户在协商中要求"把 bootstrap_special_cases 设为空数组"，**When** /sy-role 检测到，**Then** AI 拒绝并解释"该字段由工具链管理，不参与 profile 协商"
2. **Given** 协商完成，**When** 比对最终 yaml 跟运行前的 bootstrap_special_cases，**Then** 该字段完全一致

---

### Edge Cases

- 用户跑 /sy-role 时 `.specify/role-profile.yml` 不存在（init.sh 应该装了，但如果被删）：AI 用 v4 default (autonomous) 作为起点协商
- 用户跑 /sy-role 时项目还没装 v4（没有 .specify/ 目录）：skill 应该报错"请先跑 bin/init.sh 安装工具链"
- 用户手工编辑过 yaml 加了未知字段（v4 后续版本可能加新字段）：保留未知字段、只协商已知字段
- 协商过程中 git working tree 不干净：AI 提示"建议先 commit 当前改动再协商"（沿用 sy-constitution 的协调模式）

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: `/sy-role` MUST 读取 `docs/sdd/role-profiles.md`（在业务项目内可能不存在；如不存在则读 `.specify/role-profile.yml` 的注释或内置默认）作为 4 档定义的权威来源
- **FR-002**: `/sy-role` MUST 在交互开始时检测 `.specify/role-profile.yml` 是否存在；若存在则读出当前 preset + 关键差异字段后再协商（修订模式），若不存在则进入首次协商模式
- **FR-003**: `/sy-role` MUST 把"切换档位"和"修改单项能力"作为两条独立分支（用户选其一），避免一次问太多
- **FR-004**: `/sy-role` MUST 显示草稿 yaml 给用户确认，确认前不写入文件系统
- **FR-005**: 写入的 yaml MUST 符合 v4 default `runtime/role-profile.yml` 的结构（顶部注释 + preset + ai_capabilities + git_automation + bootstrap_special_cases + human_gates）
- **FR-006**: `/sy-role` MUST 拒绝修改 `bootstrap_special_cases` 字段（工具链内置，不参与协商）
- **FR-007**: `/sy-role` MUST 在写文件后按 role-profile.yml 自身的 `auto_commit_on_sy_command` 字段决定是否 git commit（不应硬编码 commit；profile 的修订必须遵守 profile 自己的规则——这是 dogfooding 的自洽性要求）。Resolution: 选项 A（D-1，见 [Decision Log](#decision-log)）
- **FR-008**: `/sy-role` MUST 在协商中途被用户终止时**不修改** `.specify/role-profile.yml`
- **FR-009**: `/sy-role` MUST 保留 yaml 中的未知字段（向前兼容 v4 后续版本添加的字段）
- **FR-010**: `/sy-role` MUST 只读写 `.specify/role-profile.yml`，**不**尝试感知"当前是 v4 自身仓还是业务项目"。v4 仓的 `runtime/role-profile.yml` 是给业务项目的 default template，跟 `.specify/role-profile.yml`（dogfood / 业务项目实际使用的那份）语义不同，更新 default template 不在 /sy-role 的服务范围（需走 ADR + 手动 PR）。Resolution: 选项 D（D-2，见 [Decision Log](#decision-log)）

### Key Entities

- **RoleProfile**: yaml 文档对象，包含 preset (4 档之一) / ai_capabilities (9 个 bool 字段) / git_automation (2 个 bool) / bootstrap_special_cases (list) / human_gates (list)，schema 在 `runtime/role-profile.yml` 头部
- **Preset**: 4 档枚举 (assistant / junior / collaborator / autonomous)，每档对应一组完整的 ai_capabilities + git_automation 默认值，定义在 docs/sdd/role-profiles.md

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 新装 v4 的开发者跑 `/sy-role` 一次能在 5 分钟内得到符合需求的 role-profile.yml（首次协商场景）
- **SC-002**: 协商产出的 yaml 100% 符合 `runtime/role-profile.yml` 的 schema（preset 是 4 档之一 / ai_capabilities 9 个字段齐全 / git_automation 2 个字段齐全）
- **SC-003**: 至少 90% 的用户在协商中**不需要**回到 docs/sdd/role-profiles.md 查表（即 /sy-role 提问已经把关键差异说清楚了）
- **SC-004**: 用户用 /sy-role 改 profile 后，下一次跑 `/sy-plan` / `/sy-implement` 等 skill 的行为符合新 profile（如把 `auto_merge_pr` 从 true 改 false 后，C6 gate 不再自动 merge）
- **SC-005**: /sy-role 命令终止 / abort 时，`.specify/role-profile.yml` 的字节级 hash 跟运行前一致（不破坏现有配置）

## Assumptions

- 用户在 Claude Code session 内运行 /sy-role；交互方式是文字 Q&A（不需要 GUI）
- 业务项目已跑过 `bin/init.sh`，因此 `.specify/role-profile.yml` 至少存在 v4 default 那份
- v4 default `runtime/role-profile.yml` 永远保持 `preset: autonomous`（不会随 v4 版本变动）
- role-profiles.md 文档稳定（4 档定义在 v4 内不会大改；如果改动会通过 ADR 推进，这时 /sy-role 才需要同步更新）
- 用户能够区分"切档"（整套预设）和"改单项"（覆盖某个 capability）这两种操作模式
- `auto_push: false` 在所有档都是默认（push 必然要人按）；/sy-role 不需要为 push 单独提问

## Decision Log

记录本 spec 中已解决的关键澄清问题（替代 [NEEDS CLARIFICATION] markers 的去向，便于回溯）。

### D-1: /sy-role 是否进 bootstrap special case (FR-007)

- **Question**: /sy-role 写完 role-profile.yml 后该不该强制 auto-commit（像 /sy-constitution 一样）？
- **Options considered**: (A) 按 profile 自身的 `auto_commit_on_sy_command` 决定；(B) 强制 auto-commit + auto-push（纳入 bootstrap）；(C) 强制 auto-commit、不 auto-push
- **Decision**: A —— SDD 自洽性优先于便利。profile 自己定的规则就该约束自己；A 档（assistant）用户跑 /sy-role 不自动 commit 是设计预期（A 档定义本就是"每步要人审"）
- **Implication**: bootstrap_special_cases 集合保持只含 `sy-constitution`；后续若加 `sy-domain-glossary` 要重新审视

### D-2: v4 自身仓 vs 业务项目目标分歧 (FR-010)

- **Question**: 在 v4 自身仓内跑 /sy-role 改的是 `.specify/role-profile.yml`（dogfood 配置）还是 `runtime/role-profile.yml`（v4 给业务项目的 default template）？
- **Options considered**: (A) 统一只改 `.specify/`；(B) v4 仓内两份同步；(C) 用 heuristic 检测当前是不是 v4 仓；(D) 不解决，明确写"v4 自身不在 /sy-role 服务范围"
- **Decision**: D —— v4 是工具链开发项目，"v4 用自己" 跟"业务项目用 v4" 语义就是不同。把语义错位变成显式约定（在 FR-010 中说明），比硬塞 heuristic 干净
- **Implication**: 改 `runtime/role-profile.yml` template 走 ADR + 手动 PR；v4 自己当 dogfood 跑 /sy-role 时只动 `.specify/role-profile.yml`
