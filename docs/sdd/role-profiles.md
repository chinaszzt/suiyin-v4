# 碎银 v4 SDD — Role Profile (AI 角色定义)

> **工具链元配置**：定义 AI 在项目中的自治程度。
>
> 不是 constitution 的内容（constitution 约束行为原则；role-profile 配置工作模式）。
> v5 项目装上 v4 后协商（未来通过 `/sy-role` slash command；当前阶段：直接编辑 `.specify/role-profile.yml`）。

---

## 为什么单独抽出 role-profile

4 个原因：

1. **影响多个组件行为**（C2 prompt / C5 review 规则 / C6 merge gate / C8 deploy gate）
2. **不同项目可能不同**（不能 hardcode 进 v4）
3. **可能随项目 phase 调整**（P0 严格 / P1+ 放松）
4. **避免污染 constitution**（constitution 应稳定，profile 可调）

---

## 4 档预设（assistant / junior / collaborator / autonomous）

### AI 能力矩阵

| 能力 | A (assistant) | B (junior) | C (collaborator) | D (autonomous) |
|---|:---:|:---:|:---:|:---:|
| `draft_spec` | ❌ | ✅ | ✅ | ✅ |
| `draft_plan` | ✅ | ✅ | ✅ | ✅ |
| `challenge_spec` | ❌ | ❌ | ✅ | ✅ |
| `ask_clarify_questions` | ✅ | ✅ | ✅ | ✅ |
| `modify_plan_in_execution` | ❌ | ❌ | ✅ | ✅ |
| `modify_spec_in_execution` | ❌ | ❌ | ❌ | ❌ |
| `auto_review_pr` | ❌ | ❌ | ✅ | ✅ |
| `auto_merge_pr` | ❌ | ❌ | ✅ | ✅ |
| `arbitrate_minor` | ❌ | ❌ | ❌ | ✅ |
| **典型用例** | 传统团队试 AI | 建立 trust 期 | 跨学科项目 | 业务专家 + AI 主写 |

`modify_spec_in_execution` 始终 ❌——任何档下 AI 发现 spec 不对都触发 `spec_drift_arbitration`（找人）。

### 人介入点

| 节点 | A | B | C | D |
|---|:---:|:---:|:---:|:---:|
| spec_writing | ✅ 人写 | (AI 起草 + 人审) | (AI 起草 + 人审) | (AI 起草 + 人审) |
| spec_pinning | ✅ | ✅ | ✅ | ✅ |
| clarify_answers | ✅ | ✅ | ✅ | ✅ |
| plan_pinning | ✅ | ✅ | ✅ | ✅ |
| **pr_review** | ✅ | ✅ | ❌ | ❌ |
| **merge** | ✅ | ✅ | ❌ | ❌ |
| spec_drift_arbitration | ✅ | ✅ | ✅ | ✅ |
| production_deploy | ✅ | ✅ | ✅ | ✅ |
| emergency_override (`human:block`) | ✅ | ✅ | ✅ | ✅ |

**C → D 飞跃**：AI 可在 **constitution 允许范围内**自治微调（complexity 阈值、retry 策略、phase 分组、task 顺序）。超出范围 → 仍然触发 spec_drift_arbitration。

### Git Automation 矩阵

| | A | B | C | D |
|---|:---:|:---:|:---:|:---:|
| `auto_commit_on_sy_command` | ❌ | ❌ | ✅ | ✅ |
| `auto_push` | ❌ | ❌ | ❌ | ❌ |

**所有档 `auto_push` 默认 false**——push 触发 CI / deploy，要人按。

---

## Bootstrap 特例：`/sy-constitution`

`/sy-constitution` **不在 role-profile 管辖范围**——它是项目立基阶段，meta-level。

**所有 4 档强制**：

- ✅ auto-commit（每轮协商完都 commit）
- ✅ auto-push（每轮协商完都 push 到 origin）

### 为什么 constitution 是特例

1. **Constitution 没立 → role-profile 没意义**（chicken-and-egg）—— role 是 constitution 之后的事
2. **Constitution 是团队立基产物** → push 让团队立刻可见
3. **协商可能多轮** → 每轮 commit + push 防丢失
4. **统一规则简单** → 不需要协商时还判断"用哪档"

### 实现

`runtime/extensions.yml` 的 `after_constitution` hook 配置 `optional: false`（mandatory）：

```yaml
hooks:
  after_constitution:
    - extension: git
      command: sy.git.commit
      optional: false   # 强制（所有 profile）
    - extension: git
      command: sy.git.push
      optional: false   # 强制（所有 profile）
```

其他 `after_*` hooks 仍是 `optional: true` —— 按 role-profile 的 `git_automation.auto_commit_on_sy_command` 字段决定。

### Bootstrap 特例集合

当前只有 `sy-constitution`。未来可能加入：

- `sy-domain-glossary`（业务概念词典，类似立基产物）
- `sy-architecture-decision`（重大架构决策记录）

加入 special case 的判定：**该产物是否团队立基级**？是 → push 让团队可见。

---

## v4 自身: D (autonomous)

v4 工具链项目本身用 D 档——前面 PR #1~#5 都是这模式跑出来的：

- AI 主写所有内容（methodology / toolchain / workflows / diagrams 等）
- 人审 spec/plan、按 deploy（即 merge PR）
- AI 自动 merge PR 之后的 commit / push（通过手动 trigger，未来自动化）

`runtime/role-profile.yml` 是 v4 仓的默认配置文件，**也是 v5 装上后的初始 default**（用户可改）。

---

## v5 项目: 协商时拍板

未来 `/sy-role` skill 引导协商（待实现）。

当前阶段（v4 P0 之前）：

```bash
# 编辑 .specify/role-profile.yml，把 preset 改成想要的档
vim /path/to/v5-project/.specify/role-profile.yml
```

切换 profile 的 effect：

- 改 yaml → 下次 `/sy-*` skill 跑时读取 → 行为变化
- 已生成的 constitution / specs / plans **不受影响**

---

## 跟 Constitution 的关系

| | constitution | role-profile |
|---|---|---|
| **性质** | 约束**行为**的原则 | 配置**工作模式** |
| **稳定性** | 一年不该改 | 可随项目 phase 调整 |
| **Enforce** | C4 L4 / C5 finding | SKILL.md 读取注入 prompt + extensions hook 决定 |
| **修改流程** | ADR + PR + 项目负责人审批 | 直接 commit（profile 不需要 ADR） |

Constitution **引用** role-profile（"v5 当前用 D 档，详见 `.specify/role-profile.yml`"），但**不内嵌内容**。

---

## Open Questions

- **Q-Role-1**: 未来支持自定义 profile（非 4 档之一）吗？还是强制选预设？
- **Q-Role-2**: 跨 feature 用不同 profile（敏感 feature 用 B，普通 feature 用 D）—— v0.2 考虑
- **Q-Role-3**: profile 切换历史是否纳入 ADR？（changes role 算 governance 决策吗）

---

**Version**: v0.1.0
**Last Updated**: 2026-05-19
**Status**: 初版，待 P0 spike 后视情况升 v1.0
