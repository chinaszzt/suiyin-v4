# ADR-0004: 默认关闭 spec-kit `before_specify` hook —— v4 worktree-centric vs hook-driven 分支创建

> P1.2.5 真闭环 dogfood（PR #40，用 /sy-role 当 driver 跑 `/sy-specify → … → batch`）启动时，
> 撞到 spec-kit 上游"每次 specify 强制创新分支"的 hook 跟 v4"开发者预先建 worktree"工作流分歧。
> 本 ADR 把"默认关闭 `before_specify` hook"这个决策固化，并记录连带的工具链修正。

---

## Status

`Accepted (2026-05-29)`

## Context

spec-kit 上游设计：`/sy-specify` 跑之前由 `before_specify` hook（`sy.git.feature`）强制创建一条新
feature 分支（`git checkout -b NNN-<short-name>`）。这条 hook 在 `runtime/extensions.yml` 里配置为
`enabled: true / optional: false`（mandatory），即"每个 spec = 一条新分支"。

v4 的实际工作流跟这个设计冲突：

1. **多 Claude session 并行 = 预先建 worktree**：v4（及业务项目）开发者在进 Claude Code session
   **之前**就用 `git worktree add` 建好 worktree + 分支，每个 session 绑一个 worktree。分支在
   `/sy-specify` 跑之前**已经存在**。
2. **强切分支造成 worktree 目录名 vs 分支名错位**：hook 在 worktree 内 `git checkout -b 001-foo`
   会让 `.claude/worktrees/<name>` 目录上跑着 `001-foo` 分支，C2/C6/batch 识别 worktree 不直观。
   （P1.2.5 dogfood 实测：hook 在 worktree 内 `checkout -b` 能成功，但目录/分支名确实错位。）
3. **v4 dogfood 自身时命名约定不符**：hook 会创不合 v4 `claude/*` 命名约定的 `001-*` 分支。

**发现路径**：2026-05-29，用 /sy-role 当 driver feature 跑 P1.2.5 全链 dogfood，开 worktree
`claude/sy-role-dogfood-p125` 后准备跑 `/sy-specify`，发现 mandatory hook 会跟预建 worktree 打架。
用户拍板：在源头 `runtime/extensions.yml` 关掉 hook，让决策随 `bin/init.sh` 带到业务项目。

随后 PR #40 的 code-review（9-angle finder + verify）暴露出"只关 hook 不够"——还有一串连带契约
需要同步修正（见 Decision）。

## Decision

### D1: 默认关闭 `before_specify` hook

`runtime/extensions.yml` 的 `before_specify` 改为 `enabled: false`（`optional` 保持上游的 `false`）。
`/sy-specify` 直接在当前分支写 spec，不创建新分支。

- **opt-in 恢复上游行为**：业务项目把 `.specify/extensions.yml` 里 `before_specify` 的
  `enabled` 改回 `true` 即可——`optional` 保持 `false`，hook 自动运行，**完全等价上游**（只翻
  `enabled` 一个字段，不需要动别的）。
- 同步在 per-extension manifest `runtime/extensions/git/extension.yml` 标 `enabled: false`，避免
  "聚合配置关了、子 manifest 还写 mandatory"的漂移。

### D2: 连带契约修正（关 hook 后必须配套）

| 修正 | 文件 | 为什么 |
|---|---|---|
| `check_feature_branch` 前加 `feature_json_matches_feature_dir` guard | `runtime/scripts/bash/check-prerequisites.sh` | 关 hook 后当前分支不再匹配 `^[0-9]{3,}-`，否则 `/sy-implement` 等消费 check-prerequisites 的命令会在 v4 worktree 分支上硬失败（setup-plan.sh / setup-tasks.sh 已有此 guard，check-prerequisites 漏了） |
| spec 的 `Feature Branch` 字段填真实当前分支 | `skills/sy-specify/SKILL.md` step 2/6 | 无 hook 时 BRANCH_NAME 不存在，模型会用 spec 目录名瞎填，跟实际 git 分支漂移 |
| `bin/init.sh` reinstall 保留 `.specify/extensions.yml` | `bin/init.sh` | extensions.yml 现在是 user-tunable（hook 开关）；reinstall 不能像以前那样 `rm -f` + 覆盖，否则业务项目的 opt-in 会被静默冲掉。改为 preserve + 落 `.suiyin-suggested` 变体（同 role-profile.yml 待遇） |
| 安装文档同步声明 hook 默认关闭 | `templates/README-v5.md` / `runtime/extensions/git/README.md` / `bin/init.sh` 的 CLAUDE.md heredoc | 不让业务项目按 spec-kit 惯例假设"specify 会自动建分支" |

### D3: `bin/init.sh` repo-root 校验收紧 + self-install 警告（同 PR 顺带）

- worktree 的 `.git` 是 file，原 `[ -d .git ]` 误判；改 `rev-parse --is-inside-work-tree` **且** 要求
  `TARGET_DIR == git rev-parse --show-toplevel`（防止装进子目录 / `.git` 目录 / bare repo）。
- `TARGET_DIR == V4_DIR`（v4 装自己）时打印显式 self-install 警告——把"静默产出 gitignored 副本"
  变成"loud"。

## Rationale

### 关 hook vs 其他方案

| 方案 | 选 / 弃 | 理由 |
|---|:---:|---|
| **默认关 hook（chosen, D1）** | ✓ | v4 是 worktree-centric，"每 spec 一新分支"在 v4 是负担不是收益。关掉成本最低，opt-in 一行恢复。 |
| 在 `/sy-specify` skill 里加"已在 worktree 就跳过 hook"判断 | ✗（暂） | 更"智能"但更脆——需要可靠判定"是否已在专用 worktree"，且 hook 框架的 `condition` 字段语义还没实现（SKILL.md 把 condition 评估 punt 给未落地的 HookExecutor）。等 condition 机制成熟可重审。 |
| 保留上游 mandatory、v4 自己 override | ✗ | override 要么散在每个项目（治理负担），要么改 source——改 source 就是本 ADR。 |

### `optional` 保持 `false`（不跟着翻 true）

code-review 发现：若把 `optional` 一起翻 `true` 当"双重保险"，opt-in 文档说"设 enabled=true 恢复上游"
就会**骗人**——SKILL.md 里 `optional: true` 渲染成"Optional Pre-Hook"（提示式），`optional: false` 才是
"Automatic Pre-Hook"（自动执行）。且 `enabled: false` 先被过滤，`optional` 在关闭态根本不被读取，所谓
"双重保险"是 dead bytes。故 `optional` 保持上游 `false`，opt-in 真正一行可逆。

## Consequences

### Positive

- v4 / 业务项目的 worktree-centric 工作流不再被 hook 打架；`/sy-specify` 在预建分支上直接写 spec。
- 连带 guard（check-prerequisites）让 `/sy-implement` 等命令在 `claude/*` 分支上正常跑。
- extensions.yml 进入 user-tunable preserve 集合，业务项目 opt-in 不会被 reinstall 冲掉。
- opt-in 路径（`enabled: true`）真正等价上游，一行可逆，文档不骗人。

### Negative / Trade-off

- **spec 目录 `NNN-` 命名仍镜像上游设计**：`create-new-feature.sh` / `find_feature_dir_by_prefix`
  仍按 `^[0-9]{3,}-` 给 spec 目录编号，但分支已不再对应。即"关 hook"只解决了分支创建，**没解决
  spec 目录命名跟分支解耦**的另一半抽象泄漏。读到 `001-foo` 目录的人可能仍误以为有对应分支。
  → 列为 **已知限制**，待 C1/C7 落地或有 trigger 时再统一（todo.md Insight）。
- **业务项目 reinstall 升级 hook 默认值不再自动生效**：preserve 语义的代价——已装项目 reinstall
  不会自动拿到新的 hook 默认，要看 `.suiyin-suggested` 手动 merge。这是"不静默毁用户配置"的正确取舍。

### Cascade（影响范围）

| 文件 / 模块 | 修改类型 | 状态 |
|---|---|---|
| `runtime/extensions.yml` `before_specify` | enabled true→false，注释指向本 ADR | ✅ 本 PR |
| `runtime/extensions/git/extension.yml` | 同步 enabled: false | ✅ 本 PR |
| `runtime/extensions/git/README.md` | hook 表格行标注 DISABLED | ✅ 本 PR |
| `runtime/scripts/bash/check-prerequisites.sh` | 加 feature.json guard | ✅ 本 PR |
| `bin/init.sh` | repo-root 收紧 + self-install 警告 + extensions.yml preserve + CLAUDE.md heredoc | ✅ 本 PR |
| `skills/sy-specify/SKILL.md` | 无-hook 时 Feature Branch 填真实分支 | ✅ 本 PR |
| `templates/README-v5.md` | 声明 hook 默认关闭 + opt-in | ✅ 本 PR |
| **"v4 自身 vs 业务项目"语义错位升 constitution** | FR-010/D-2 目前在 per-feature spec 里 carve-out | ⏳ follow-up（需人审，见下） |

## Alternatives Considered

### 把 "v4-self-install 不在 /sy-* 服务范围" 升到 constitution（CR-7）

code-review altitude 角度指出：spec.md FR-010 + Decision Log D-2 在**单个 feature spec** 里 carve-out
"v4 用自己时只动 `.specify/role-profile.yml`、不碰 `runtime/` template"。若每个 `/sy-*` skill spec 都要
重复这条 carve-out，就是 wrong altitude——应是一条 constitution 级规则（或一个 `bin/init.sh` 守卫）让所有
skill 继承。

- **本 ADR 不直接做**：改 constitution 是高杠杆操作（governance §7：ADR + PR + 人审拍板）。本 ADR 先用
  `bin/init.sh` 的 self-install 显式警告把"静默 OK"变 loud，作为过渡；constitution 级规则留作 follow-up
  ADR，由人拍板。

### 同时解决 spec 目录 `NNN-` 命名解耦

- 弃：那是 spec-kit `create-new-feature.sh` 的目录编号逻辑，改动面大且跟 C1（execution_plan）/ C7
  调度耦合。本 ADR 聚焦"分支创建"这一刀，目录命名解耦留作已知限制。

## References

- **Related ADRs**: ADR-0003（NC-4 worktree 隔离 —— 本 ADR 是 NC-4 worktree-centric 工作流在
  toolchain 配置层的具体落地）
- **PR / 来源**: PR #40（/sy-role spec + worktree-friendly fixes）+ 其 `/code-review`（9-angle
  finder → verify → sweep，暴露 check-prerequisites guard / optional 误翻 / reinstall 冲配置 等连带项）
- **Relevant files**: `runtime/extensions.yml`、`runtime/scripts/bash/{check-prerequisites,setup-plan,setup-tasks}.sh`、`runtime/scripts/bash/common.sh`（`feature_json_matches_feature_dir` / `check_feature_branch`）、`skills/sy-specify/SKILL.md`
- **Discussion**: 2026-05-29 P1.2.5 dogfood session

## Author + Date

- **Author**: 张佗（拍板 disable hook + worktree-centric 取向）+ Claude（ADR 草稿 + 连带修正）
- **Decided**: 2026-05-29
- **Last Updated**: 2026-05-29

---

## Version History

| Version | Date | Changes |
|---|---|---|
| v0.1.0 | 2026-05-29 | 初版：默认关 `before_specify` hook + 连带契约修正（check-prerequisites guard / extensions.yml preserve / spec Feature Branch / 安装文档）+ init.sh repo-root 收紧 |
