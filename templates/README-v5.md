# {{PROJECT_NAME}}

用 [suiyin-flow](https://github.com/chinaszzt/suiyin-v4) (AI native SDD 工具链) 开发的业务项目。

---

## 当前状态

✓ 已安装 suiyin-flow 工具链
⏳ **下一步：协商 constitution**

---

## 下一步：协商 Constitution

在 **Claude Code** 中打开本仓库，运行 slash command：

```
/sy-constitution
```

AI 会引导你回答 5-10 个问题：

- 项目身份是什么？
- AI 在这个项目里的角色？
- 5 条核心原则（可从 [suiyin-flow methodology §10](https://github.com/chinaszzt/suiyin-v4/blob/main/docs/sdd/methodology.md) 5 条铁律起步）
- 量化指标（推荐起点：函数 ≤ 80 行 / 文件 ≤ 600 / 嵌套 ≤ 5 / 圈复杂度 ≤ 18）
- Governance 规则

完成后输出 `.specify/memory/constitution.md`。Commit + push 即可。

---

## 完整工作流（v4 工具链规约）

```
[人 + AI 协商]                  [AI 主写 + 自动化 Gate]              [人按按钮]

Layer 1  业务协商              Layer 2-5  执行引擎                  Layer 6  发布
- constitution      ◄── 你在这  - 规划 (C1)                          - Deploy
- specify ⇌ clarify             - 执行 (C2, C3)                      - 灰度 / 全量
- plan ⇌ reuse-scan             - 验证 (C4 + C5)                     - 触发 CD
- tasks                         - Gate (C6)
                                - 调度 (C7)

[suiyin-flow 已装 ✓]              [待 v4 P0 实现]                       [既有 CD]
```

详细流程图见 [suiyin-v4/diagrams.md](https://github.com/chinaszzt/suiyin-v4/blob/main/docs/sdd/diagrams.md)（11 张 Mermaid 图）。

---

## 已安装内容

| 路径 | 来源 | 用途 |
|---|---|---|
| `.specify/` | suiyin-flow | 工作目录（constitution / specs / templates） |
| `.specify/templates/constitution-template.md` | **suiyin-flow customized** | v4 流派的 constitution 模板 |
| `.specify/role-profile.yml` | **suiyin-flow customized** | AI 角色配置（4 档预设，default = autonomous） |
| `.claude/skills/sy-*` | suiyin-flow | Claude Code slash commands |
| `.claude/settings.json` | **suiyin-flow customized** | git 命令 allowlist（auto-commit/push） |
| `CLAUDE.md` | suiyin-flow | Claude Code 项目级配置 |

---

## AI 角色 + Git 自动化

本项目默认 AI 角色 = **autonomous**（D 档）—— AI 主写、自动 merge、人按 deploy + 拍 spec/plan + 紧急 override。

修改：编辑 `.specify/role-profile.yml`，把 `preset` 改成 `assistant` / `junior` / `collaborator` / `autonomous`。完整定义见 [role-profiles.md](https://github.com/chinaszzt/suiyin-v4/blob/main/docs/sdd/role-profiles.md)。

### Git 自动化行为

| 触发 | 行为 |
|---|---|
| **`/sy-constitution` 完成**（bootstrap 特例） | ✅ 自动 commit + ✅ 自动 push（**所有档**） |
| **其他 `/sy-*` 完成**（autonomous / collaborator 档） | ✅ 自动 commit；❌ 不 push |
| **其他 `/sy-*` 完成**（assistant / junior 档） | ❌ 不自动 commit；❌ 不 push |

> Constitution 是项目立基产物，团队可见性关键 → 所有档强制 push 到 remote。
> 其他产物（spec / plan / task）push 仍要人按。

---

## Slash Commands（suiyin-flow 提供）

| 命令 | 用途 | 何时用 |
|---|---|---|
| `/sy-constitution` | 协商项目宪法 | **现在用这个** |
| `/sy-specify` | 写 feature spec | constitution 完成后 |
| `/sy-clarify` | AI 反问澄清 spec | specify 后 |
| `/sy-plan` | 技术方案 | clarify 完成后 |
| `/sy-analyze` | 跨产物一致性检查 | plan 完成后 |
| `/sy-tasks` | 拆 task | analyze 后 |
| `/sy-implement` | 实施（暂用 suiyin-flow 默认，待 v4 P0 替换为 C2 Task Executor） | tasks 完成后 |

> **分支创建（v4 默认行为）**：v4 默认**关闭** spec-kit 的 `before_specify` hook —— `/sy-specify`
> **不会**自动创建新分支。v4 是 worktree-centric 工作流：**先**自己 `git worktree add` 建好分支再
> 跑 `/sy-specify`。若想恢复 spec-kit "每次 specify 自动切新分支" 的行为，把 `.specify/extensions.yml`
> 里 `before_specify` 的 `enabled` 改成 `true`（详见 ADR-0004）。

---

## 参考文档（suiyin-v4 仓）

- [方法论 methodology.md](https://github.com/chinaszzt/suiyin-v4/blob/main/docs/sdd/methodology.md) — SDD 怎么用，给团队读
- [工具链规约 toolchain.md](https://github.com/chinaszzt/suiyin-v4/blob/main/docs/sdd/toolchain.md) — 11 个组件 / 契约
- [工作流 workflows.md](https://github.com/chinaszzt/suiyin-v4/blob/main/docs/sdd/workflows.md) — 状态机 / Bug / Initiative 流程
- [流程图 diagrams.md](https://github.com/chinaszzt/suiyin-v4/blob/main/docs/sdd/diagrams.md) — 11 张图
- [Component spec template](https://github.com/chinaszzt/suiyin-v4/blob/main/docs/sdd/component-spec-template.md) — 给 v4 内部组件用

---

## 工具链阶段

| Layer | 工具 | 状态 |
|---|---|---|
| **1. 协商** | suiyin-flow (`/sy-*`) | ✅ 已装可用 |
| **2-5. 执行/验证/Gate** | suiyin-flow (C1-C11) | ⏳ 待 v4 P0 实现后接入 |
| **6. 发布** | 待选 CD | ⏳ 待定 |

P0 之前，所有阶段都用 suiyin-flow 默认（含 `/sy-implement`）跑。P0 上线后切换 Layer 2-5 到 suiyin-flow 组件。

---

**Powered by**: [suiyin-flow](https://github.com/chinaszzt/suiyin-v4)

> Slash commands forked & customized from [github/spec-kit](https://github.com/github/spec-kit) (MIT-licensed). Thanks to the spec-kit team.
