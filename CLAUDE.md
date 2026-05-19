# 碎银 v4 — Project Memory

> Auto-loaded by Claude Code on session start. Critical context for any new conversation.

---

## 项目定位（最重要）

**v4 是 SDD 工具链开发项目本身**，不是业务产品。

- **suiyin-v4** (`/Users/zhangtuo/Documents/suiyin-v4`) — SDD 工具链：methodology / toolchain / installer / `/sy-*` slash commands
- **suiyin-v5** (`/Users/zhangtuo/suiyin-v5`) — 真正业务产品（碎银 v5），用 v4 工具链开发

不要把 v4 当成业务项目跑 spec / feature。**v4 自身的"feature"是工具组件（C1-C11）**。

---

## 新 Context 入口

读这两份文档就有完整 mental model：

1. **`docs/sdd/todo.md`** — 当前所有 pending 工作 + 推荐下一步
2. **`docs/sdd/constitution.md`** — v4 项目独有约束（v0.2）

完整文档总览见 `docs/sdd/` 目录（speed reference 表在 todo.md 末尾）。

---

## v4 自身的工作模式

| 项 | 配置 |
|---|---|
| **AI 角色** | `autonomous` (D 档) — AI 主写、自动 merge、人按 deploy + 拍 spec/plan + 紧急 override |
| **配置文件** | `runtime/role-profile.yml` |
| **代码修改** | 必须 worktree（不在 main 上直接改） |
| **Constitution 修改** | 走 ADR + PR + 人审拍板（governance §7） |
| **业务 specs** | 不要写（v4 是工具链，不是业务） |

---

## 关键文档（详见 todo.md）

| 想做 | 读哪份 |
|---|---|
| 了解 SDD 方法论 | `docs/sdd/methodology.md` |
| 11 个组件定义 | `docs/sdd/toolchain.md` |
| 流程图（11 张 Mermaid） | `docs/sdd/diagrams.md` |
| 状态机 + Bug / Initiative | `docs/sdd/workflows.md` |
| 项目宪法（v0.2） | `docs/sdd/constitution.md` |
| C 模块 spec 模板 | `docs/sdd/component-spec-template.md` |
| AI 角色 4 档 | `docs/sdd/role-profiles.md` |
| **当前所有 TODO** | `docs/sdd/todo.md` |

---

## 工具链产物

- `bin/init.sh` — 给业务项目（v5+）一键装 v4 工具链
- `skills/sy-*` (14 个) — slash commands
- `runtime/` — v5 安装后的运行时（templates / scripts / extensions）
- `templates/` — v4 自定义的 constitution-template / README-v5

---

## 多 session 接力指引

- 改 constitution 是高杠杆操作（governance §7）：必须 ADR + PR + 人审
- 改 toolchain.md / workflows.md：worktree + PR 即可（D-autonomous 模式自动 merge）
- 写 C 模块 spec：用 `component-spec-template.md` 格式，放 `docs/sdd/components/c{N}-*.md`
- 不确定时：读 `docs/sdd/todo.md` 看 P0/P1 推荐

---

**Project state on session start**: 读 todo.md 末尾的 starter prompt → 接力。
