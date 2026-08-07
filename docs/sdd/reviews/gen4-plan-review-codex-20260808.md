# 外部审稿结论：BLOCK

[`gen4-plan.md`](/Users/zhangtuo/Documents/suiyin-v4/worktrees/gen4-plan/docs/sdd/gen4-plan.md:1) 的方向可继续，但当前不能直接作为实施 backlog。至少有六个开工阻断：

1. “plan 人审放弃”尚未修改根方法论和四档 role-profile，现行权威规则仍会停在 plan gate。
2. 两级 merge 的 feature→main 收口仍未实现，C5 又只接受单个 `task_id`，多 task feature 没有合法审查入口。
3. C4 L3 尚未实现，实际 C4 还不支持 Go；desk spec 也不符合 `AC-N`/AC 段格式。
4. 契约文档层退役后，内部接缝、资源写权、错误语义没有新的权威载体。
5. mutation、FOREIGN 分诊、R2 的实现顺序反了；按现计划，先污染环境或烧完 attempt，后分诊。
6. desk 宪法存在后加附则、临时豁免和 E4/E5 悬空引用，不能“逐条复制”迁移。

“v4 底盘不动”也不准确。应改成“v4 架构 invariant 不动，但 C2/C4/C5/C6/C7、methodology、role-profile、workflow 的契约都要修订”。

---

# 一、遗漏

## 1. 四档 role-profile 与 plan gate

计划取消 plan 人审（`docs/sdd/gen4-plan.md:59-61`），但：

- 四档都保留人工 `plan_pinning`：`docs/sdd/role-profiles.md:42-52`。
- D 档运行配置仍将它列为 human gate：`runtime/role-profile.yml:34-39`。
- 根方法论仍规定 spec/plan 是人的杠杆点：`docs/sdd/methodology.md:15,45-53,173-193,321-322`。
- 文档优先级是 methodology > constitution > toolchain > 其他：`docs/sdd/constitution.md:283-307`。

应在 `gen4-plan.md §〇` 补：

> Gen-4 主线 dogfood 默认采用 D-autonomous。“取消 plan 人审”仅指满足 plan lint、typed seam manifest、failure-mode 处置和后果题回流后，D 档可自动 pin 纯技术 plan；A/B/C/D 的 plan/review/merge/park 行为须逐档定义。在上述前置未完成前，旧 plan gate 继续有效。

并把修改清单明确列为：

`methodology.md`、`toolchain.md`、`workflows.md`、`diagrams.md`、`role-profiles.md`、`runtime/role-profile.yml`。

验收：同一 fixture 跑四档；四档均不能绕过 AC/NC 门，A/B 不自动 merge，D 不再卡在旧 `plan_pinning`。

## 2. 两级 merge 的最终收口

现行流程是 task→feature 本地 ff-merge，feature→main 才走 C5/C6：`docs/sdd/workflows.md:36-78`、`docs/sdd/diagrams.md:23-70`。但 C7 明确不 push、不调 C5/C6，Q7-3 仍未拍：`docs/sdd/components/c7-phase-coordinator.md:247-264,332-334`。

同时，C5 强制一个 `task_id`，并声称每个 PR 都来自单 task：`docs/sdd/components/c5-ai-reviewer.md:18-49`。这与五 task 聚合 feature 冲突。

应在 `gen4-plan.md §三 P0` 最前补：

> 权威 gate 固定在 feature→main：C7 `all_merged` 后，对 feature HEAD 跑全量 C4，再以 `subject={kind: feature, feature_id, task_ids[], manifest_ref}` 调 C5，最后调 C6。Q7-3 未关闭前可由确定性 harness 串接，但不得宣称端到端全自动。

验收：r4 五 task fixture 只产生一个 feature PR；C4/C5/C6 报告均绑定同一 feature HEAD，并能回链五个 task 和完整 AC 集。

## 3. C4 L3 原职责、Go 支持和 AC 格式迁移

P0 直接把 mutation 放进 C4 L3（`gen4-plan.md:84-86`），但当前：

- L3 的定义是 spec AC 集合↔测试名映射，不是 mutation：`docs/sdd/components/c4-verify-contract.md:136-149,193-200`。
- 显式请求 L3 必须返回 `LEVEL_NOT_IMPLEMENTED`：同文件 `:198,225-239`。
- `ac_list` 仍可为空：`runtime/templates/tasks-template.md:68-80`。
- `/sy-tasks` 下半段仍写 “Tests are OPTIONAL”：`skills/sy-tasks/SKILL.md:195-200`。
- 实际 C4 只探测 Python/Dart，没有 Go runner：`src/suiyin_flow/c4_verify/cli.py:71-109`、`runners/__init__.py:1-7`。
- parser 注释声称支持 `TestAC1_xxx`，正则实际不匹配：`src/suiyin_flow/c4_verify/parser.py:5-35`。
- desk 001–004 使用“用户故事/FR/成功指标”，不是 `AC-N` 和 `## 5. Acceptance Criteria`；C4 会 `SPEC_PARSE_FAILED`：`c4-verify-contract.md:181-182,214-215`。

应把 P0 条目改为：

> C4 L3 完整落地顺序：稳定 AC ID 迁移 → Go L1/L2 runner 与 Go AC 命名协议 → AC 集合完全映射 → freeze check → mutation adequacy。代码型 task 的 `ac_list` 必填；非行为 task 使用显式 `kind: support` exemption。

## 4. 旧 roadmap 没有逐项去向

`gen4-plan.md:81-103` 新设 P0-P2，但 `docs/sdd/toolchain.md:309-323`、`docs/sdd/todo.md:376-421` 仍是旧优先级。`todo.md:559-562` 只说新计划“压过”旧计划，没有处置：

- C3
- C4 L4
- R3/C5 N=2
- C8
- C9
- C10/C11/C12
- Q7-2/Q7-3
- P1.6
- `/sy-role`
- domain glossary
- r4 auto-commit 缺口

应在 `gen4-plan.md §三` 开头增加“旧 roadmap 处置表”，每项必须是：

`保留 / 取消 / 被替代 / 前移 / 后移 / 临时替代物 / 开工条件`。

尤其：

- C3 不能静默取消；C2 对 high 硬拒绝：`c2-task-executor.md:247-252,358-360`。
- C4 L4 是否由 C5 吸收，必须拍板；E5 退役不等于 constitution compliance 取消。
- C8 不受本轮设计否定，至少应保留原 P4。
- R3 若被“mutation 唯一对抗残余”否决，应显式关闭 Q5/Q5-6，而非悬空。

## 5. C9 遗漏，C10/C11/C12 被错误合并

desk 001–005 整体迁移符合 v4 的 Initiative 定义；C9 正是生成 `affected.yaml` 和跨 spec 验证的组件：`docs/sdd/workflows.md:153-212`。计划却只写 C10/C11/C12：`gen4-plan.md:99-102`。

三者也不是同一种“知识层”：

- C10：spec 写完、clarify 前做 overlap。
- C11：plan lookup + post-merge registry 双引擎。
- C12：spec/debug/反思时的 capture ritual，且 C5 finding 半边已落地。

出处：`docs/sdd/diagrams.md:235-307,356-423`、`docs/sdd/discussion-notes.md:491-543`、`docs/sdd/todo.md:495-498`。

应在 `§三 P1` 补：

> desk 多 spec 迁移按 Initiative 管理；本轮至少生成一次性 `affected.yaml` 作为 C9 contract fixture。完整 C9 若延期，须明确该临时替代物。C10 的迁移期 overlap pass 前移到 P1；C11 与 C12 分项排期。

## 6. failure-modes 与“坑清单变组件 AC”冲突

failure-modes 是业务项目自有文件；v4 只提供 slot：`docs/sdd/failure-modes-contract.md:22-38`。它还明确区分 architecture/implementation 两段及消费者：同文件 `:40-58`。

而 `gen4-plan.md:113-114` 要求 desk 坑清单逐条变成“gen-4 组件 AC”，会把业务坑污染进通用工具链，违反 v4 项目独立性和 failure-modes 边界。

建议替换该句：

> desk 坑清单逐条建立迁移记录，但不一律写成 v4 组件 AC。业务产品复发模式进入 desk `.specify/memory/failure-modes.md`；Gen-4 工具链缺陷进入对应组件 regression AC；不可妥协的安全边界进入业务 constitution NC + 机械闸；可复用知识进入 ADR/glossary/C12。每条只有一个 primary owner，并有机械证明。

还要明确：

- plan lint 只读 architecture-level。
- C5 只读 implementation-level。
- 取消 plan 人审后，现有 soft warning 是升级为 hard、需 waiver，还是继续 advisory，必须逐条定；不能留下无人负责的 warning。
- C5 接 failure-modes 尚未实现：`docs/sdd/todo.md:140-146`。

## 7. R1.5 与现有 R2/C7 没接上

当前 R1/R2/R3 是 feature→main 的 C5 block recovery：`docs/sdd/workflows.md:96-106`。C7 park 位于更早的 task→feature 层。把 park 分诊叫 R1.5 会混合两条恢复阶梯。

此外：

- C2 已在内部消耗 `VERIFY_FAILED/SESSION_CRASHED/TIMEOUT` attempt：`c2-task-executor.md:269-287`。
- C7 收到的是耗尽后的 `TASK_FAILED/TASK_ERROR`：`c7-phase-coordinator.md:272-282`。
- 现有 R2 输入只能是非空 C5 findings，普通 verify 红票不能直接喂：`c2-task-executor.md:84-98`。
- Q7-2 仍未关闭：`c7-phase-coordinator.md:332`。

应将其改名为 `Execution Failure Triage`，并在 `§二 拍板 4` 补：

> 分类器只输出 `class/evidence/retryable/charge_owned_attempt`，不得输出下一节点；C7 仍是唯一路由权威。先完成 base/head 归因和 attempt accounting，再接 classifier。verify 类恢复必须新增 `repair_feedback.kind=review_findings|verify_failure|reverify_failure`，或另命名，不能冒充现有 R2。

## 8. task identity、claim 与跨组件 run ledger

v4 文档要求 `task_id` 全 repo 唯一，但实现只检查单 manifest 内唯一：`runtime/templates/tasks-template.md:44,72`、`src/suiyin_flow/c2_executor/batch.py:111-118`。C2 worktree、branch、lock 都只用裸 task id：`c2-task-executor.md:247-265`。

desk 每个 feature 都复用 T001 等本地编号；迁移后会串 worktree、成本、review 和状态。

应在 desk 迁移前补：

> canonical task key 固定为 `feature_id + local_task_id`；worktree、branch、C7 state、review、cost、claim 全部使用同一 key。每个 feature run 分配 `run_id`，`.suiyin/runs/<run_id>.json` 只存工件指针、hash、终态和下一确定性动作，不复制派生态正文。

多 clone/多机是否在威胁模型内：待验证。若在，pid lock 不足，需 git CAS/origin claim；若不在，必须明确“单机单 clone”。

## 9. “能不拆就不拆”没有落实到 `/sy-tasks`

C1 只排列既有 task，不负责合并 task；其语义 pass 只能收紧并行：`docs/sdd/components/c1-planning-engine.md:144-151`。真正决定粒度的是 `/sy-tasks`，而当前仍建议“一般 1–3 文件+测试”：`skills/sy-tasks/SKILL.md:45`、`runtime/templates/tasks-template.md:102-110`。

应在 `§二 拍板 5` 补：

> task 粒度由 `/sy-tasks` 在 C1 前决定。先判断单 C2 session 是否能在 2h timeout、criticality、单次 verify 和资源边界内完成；满足则单 task。拆分时中心 seam task 先行，两侧依赖中心；30% 胶水必须是预声明 integration task 或后续 repair task。C1 只排序，不替代该决策。

并让 `task batch` 对非空 `depends_on` fail-fast；依赖 task 必须走 `phase run`。

## 10. 成本记账缺模型身份、失败记录和并发语义

`gen4-plan.md:73,87` 只列 tokens/时长/角色。至少还缺：

`invocation_id/run_id/feature/task/role/model/model_version/attempt/start/end/status/input_tokens/cache_tokens/output_tokens/cost/source/error`。

需要统一覆盖 C1 semantic pass、C2、C5、未知 park 翻译会话，并定义 slash command 是否纳入。失败、timeout、kill -9 也必须有记录，不能只记成功。

“强模型假设”又依赖真实模型身份，但 Q-Model-1 仍未关闭：`docs/sdd/todo.md:524`。

应在 `§二 拍板 6/8` 补：

> 每次调用记录实际模型及配置；模型或 prompt profile 变化触发固定 corpus 回放。成本账只观测不参与 routing。token 解析失败不得阻断开发，但必须留下显式 `cost_log_error`，不得静默漏记。

## 11. local-bare dogfood 缺 C6 adapter

dogfood 明定 local bare origin：`gen4-plan.md:26,112`。但 C6 的 C5-block 恢复依赖 GitHub label/comment，失败可升级为 Error：`docs/sdd/components/c6-gate-contract.md:127-139,180-185`。

应在 `§三 P0 两级收口` 补：

> `human:block` 是本地 versioned semantic state；GitHub label/comment 只是可选 adapter。local-bare 环境下 C5 block 必须形成可 resume 的 stopped/parked 状态，不能因无 `gh` 变成工具故障。

---

# 二、内部矛盾与隐含风险

## 1. 实验证据不支持“mutation 是唯一对抗残余”

E4 相对 C5 的八条增量是：

- 5 条 mutation 空心测试；
- 1 条 spec 行为违例；
- 1 条 seam 缺失；
- 1 条 floor 日志误提交。

见 `gen4-plan.md:39-48`。

其中只有五条属于 mutation。行为违例需要独立 spec↔oracle 审查，seam 缺失需要 typed seam completeness，日志误提交需要静态 hygiene gate。因此 `:52-54` 的“mutation 唯一对抗残余”与同文实验直接矛盾。

应改为：

> mutation 是 AC 测试证伪力的专用证据；独立语义审查、seam completeness 和机械 floor gate 分别承接其余风险，不得由 mutation 代替。

并要求新管线回放时对八条逐条声明“哪个机制抓到”，不能只报总数。

## 2. AC 测试不能成为第二份“唯一真相”

方法论规定 spec 是唯一真相，测试是可执行投影：`docs/sdd/methodology.md:19-47`。`gen4-plan.md:52` 把 AC 测试称为“行为契约本体”，容易使 spec 与测试成为双权威。

正确关系应是：

`spec AC（权威） → AC test（可执行投影） → mutation attestation（投影证伪力证据）`

测试与 spec 冲突时，spec 必须胜出。还要补第三条修改通道：

- Type B：spec 漏行为，补 spec+AC+测试，不强制 ADR。
- Type C：产品意图改变，改 spec+ADR+测试。
- `projection_fix`：spec 未变、AC 测试翻译错，允许修测试并给出旧/新 oracle 证据，不应伪造一次 spec 变更。

现行方法论只要求 Type C ADR：`methodology.md:209-243`；计划把 B/C 都写成“带 ADR”是冲突。

## 3. “测试三层”分类本身不闭合

当前文字实际包含两个测试类别和一个测试验证操作：

1. AC 行为测试；
2. 实现测试；
3. mutation 探针。

mutation 不是与测试并列的权威层，而是作用于测试的 adequacy operator。更关键的是，desk 的 seam/NC guard tests 无处归类：

- 内部接口/schema/error 不是外部行为 AC；
- 生产库/网络/写权 guard 也不能当可随意修改的实现测试。

建议改为三类测试、一个验证维度：

1. spec-derived behavior tests；
2. plan/constitution-derived seam/guard tests；
3. implementation tests；
4. mutation 对 1/2 做 adequacy 验证。

## 4. mutation 只按测试变更触发是错误缓存键

证伪力不是测试文件的静态属性，而取决于：

`spec + test + reachable production slice + mutant catalog/toolchain`。

生产实现、seam 形状、mutation operator 变化，都可能让未改测试失去作用。desk 的五类 mutant 本身就修改生产接口/schema/条件/复制语义，而非测试。

应把 `gen4-plan.md:85-86` 改成：

> attestation cache key = `spec_hash + AC_test_hash + reachable_target_hash + mutant_catalog_version + test_command/toolchain_hash`。任一变化即重跑；零适用 mutant、目标缺失、解析失败一律 fail-closed。

具体 reachable-slice 算法和成本：待验证。

## 5. C4 “只读” invariant 与 mutation 相撞

C4 明定不修改源码：`c4-verify-contract.md:201-206`。mutation 必然改生产代码或测试环境。desk 的正确形态是 throwaway worktree：`suiyin-desk/docs/process-evolution.md:54-58`。

因此 P0 mutation 必须先有：

- throwaway worktree；
- 独立 DB/cache/port/tmp；
- crash cleanup；
- 原 worktree byte-identical 证明。

把“一 lane 一容器”放到 P1（`gen4-plan.md:95-96`）而 mutation 放 P0，顺序错误。

## 6. 契约层退役后，内部 seam 没有权威载体

v4 spec 禁止接口、数据库结构等实现细节：`methodology.md:62-80`。desk E2/P9/E11 的核心却是接口、错误语义、schema、依赖边界、集合写权。

所以：

- 不能把它们塞进 spec AC；
- 不能仅靠行为测试完整表达；
- 不能用 `modifies` 替代授权；`modifies` 只是 C1 调度足迹，C2/C7 不把它当 permission：`runtime/templates/tasks-template.md:75-80`。

应把 `gen4-plan.md:60` 的“契约⊆spec”改成：

> 仅行为义务必须可追溯到 spec；内部 seam 可追溯到 plan，资源授权可追溯到 plan+constitution。契约文档退役前，typed seam manifest、authorization manifest、对应 lint 和 guard test 必须全部就位。

## 7. E5 的退役理由不成立

“后任可以改前任”解决的是代码所有权，不解决：

- 未授权数据库写；
- 绕过发送出口；
- 隐藏副作用；
- 未声明依赖；
- 当前 task 破坏下游 seam。

desk E5 的对象见 `suiyin-desk/docs/constitution.md:97-100`，P9 又将 seam 偏离列为任何档都不可放行：同文件 `:61-72`。

正确退役标准应是：

> 历史 E5 blocker corpus 经 typed authorization、static guard、runtime capability gate 和 C5 residual review 回放，seam/floor 逃逸为零，才退役 LLM 席。

在 parity 回放前，“E5 已溶解”应标为目标，不应标为完成事实。

## 8. plan lint 与“不迁契约文档层”互相矛盾

`gen4-plan.md:60,97` 要做“契约⊆spec 矩阵”，`gen4-plan.md:104-105` 又删除契约文档层。矩阵左侧不存在。

应重新定义为：

- plan seam/error/dependency/side-effect 声明；
- authorization manifest；
- AC/seam/guard test manifest；
- architecture failure-mode acknowledgements。

未完成这些结构化对象前，不得先拆 plan 人审。

## 9. “能不拆就不拆”与既有执行约束没有边界

“1M 上下文装得下”不是充分条件。还必须满足：

- C2 2h timeout；
- 一次 verify 可执行；
- worktree/resource 权限可隔离；
- criticality 不为 high；
- 变更具有一个可回滚/可审查原子边界。

否则一个巨型 task 会绕过 C1/C7 并行设计，又把 failure localization 变差。应把这些条件写入 `/sy-tasks`，不能只看上下文长度。

## 10. R1.5 的 LLM 会撞 C7 零 AI 路由

C7 I1/I2 要求 routing path 零 AI且唯一路由权威：`c7-phase-coordinator.md:236-246`。

未知类的廉价模型只能生成给人的 consequence question artifact；无论生成成功还是失败，状态转移都固定为：

`UNKNOWN → park_unknown → human_decision_required`

用户答案再作为 typed event 输入 C7。模型不得输出 `next_action_owner` 或决定 retry/merge。

## 11. feature 级 C5 block 无法复用原 worktree

现有 R2 假设复用被 block 的 task worktree：`c2-task-executor.md:91-96`。但 C7 在 task merge 后删除 worktree/branch：`c7-phase-coordinator.md:253`；C5 又发生在 feature 聚合完成之后。

建议：

- task/整合阶段 OWN failure：复用 parked worktree；
- feature C5 block：新建 `feature-repair` task/worktree；
- repair 后重跑 feature 全量 C4→C5。

不要为复用旧语义而保留所有 task worktree。

## 12. C5 输入显式化不是“seeds 进调用”这么小

C5 I1 当前白名单只有 spec/plan/constitution/diff/verify，并禁止 implementer log：`c5-ai-reviewer.md:167-183`。增加 README/failure-modes 会修改 public schema、权威顺序、finding taxonomy 和审计报告。

至少需要：

```text
review_input_manifest[]:
  kind
  path
  authority
  required
  content_sha256
  source_commit
```

权威顺序固定为：

`constitution/NC > spec/AC > plan/seam > failure-modes > README/advisory`

legacy contract 只能作为迁移期输入，不能借 `seeds` 复活第二套永久契约。

另有现存风险：C5 把 `cross_platform` 归入 approve 类，但 NC-5 是 NON-NEGOTIABLE：`c5-ai-reviewer.md:171-175` 对比 `docs/sdd/constitution.md:197-211`。应规定任何 NC 命中统一输出 `nc_violation`，专用类别只能作 subtype。

## 13. P9/E11 与 C5/C6 的 verdict 架构冲突

desk 的原则是“reviewer 全量判定，gate 按 tier 过滤处置”：`suiyin-desk/docs/constitution.md:230-255`。v4 却由 C5 自己把 finding 压成 approve/block，C6 只消费 verdict：`c5-ai-reviewer.md:171-180`、`c6-gate-contract.md:121-132`。

同时：

- desk rough 允许 accept/quality fix-forward；
- Gen-4 冻结 AC 失败则 C4 全局 fail；
- criticality/tier 又被延后未决：`gen4-plan.md:121`。

必须二选一：

1. 不迁 desk tier 放行，只迁 taxonomy 和 fix-forward 账；或
2. C5 输出原始 findings，新增确定性 disposition policy，C6 消费 policy 结果。

`criticality` 与 desk `rough/std/core` 也不是同一维度：前者决定实现拓扑/C3，后者决定 finding disposition，禁止合并成一个字段。

## 14. 强模型假设放错层

NC 要求长期稳定：`docs/sdd/constitution.md:103-110`；模型/profile 是可变运行配置：`docs/sdd/role-profiles.md:10-17,141-150`。而当前模型仍由环境隐式决定。

建议 constitution 只写：

> 自动执行只使用通过固定 capability benchmark 的 model profile。

具体模型、阈值和降级策略放 role/model profile。实验已经显示强模型仍有 5/8 空心测试，不能把“强模型能产出可靠测试”直接写成事实。

---

# 三、P0–P2 移植清单重排与验收

## Gen4-P0：闭环与证据底座

### P0-0 治理与 roadmap 对账

完成 role-profile 四档矩阵、根方法论修订、旧 roadmap 逐项处置、desk source commit 固定。

验收：三份优先级文档只有一个 active priority；doc-lint 能发现重复优先级和未同步 invariant。

### P0-1 canonical identity、commit 基线与薄 run ledger

实现 `feature_id/local_task_id/run_id`；关闭 r4 auto-commit 缺口。未提交 spec/plan/tasks 不得进入执行，参见 `docs/sdd/todo.md:340-346` 和 `runtime/templates/tasks-template.md:73-75`。

验收：两个 feature 同时存在 T001 时，worktree、state、review、cost 完全隔离；kill -9 后不重复调用或 merge。

### P0-2 Q7-3 feature 收口和 local adapter

实现 feature PR builder、feature scope C5、feature 全量 C4→C5→C6，以及 local `human:block` 状态。

验收：五 task fixture 只开一个 feature PR；无 GitHub 环境也能 block、resume；全量 gate 未过不能进 main。

### P0-3 Go C4 + AC migration + 原始 L3

先建立 desk FR/GWT/成功指标→稳定 `AC-N` 的映射，再实现 Go runner/parser和集合完全匹配。

验收：

- 每个 desk FR/GWT/成功指标都有 source→AC；
- Go `build/vet/test` 进入结构化报告；
- missing/duplicate/multi-AC 必须 fail；
- 代码型 task 空 `ac_list` 被拒绝。

### P0-4 AC freeze

增加 AC manifest：

`ac_id/spec_hash/test_files/test_hash/oracle_status/baseline_ref`。

验收：

- 删除、skip、改名、弱化被冻结测试且 spec 未变时阻断；
- Type B 不强制 ADR，Type C 强制 ADR；
- `projection_fix` 可在 spec 不变时修错误测试；
- baseline 无法解析时 fail-closed；
- merge/记账 commit 不误触发。

“弱化”的一般语义无法仅靠 diff 完全机械判定，能机械判的闭集与 UNKNOWN 行为必须写清。

### P0-5 最小资源隔离 + mutation

先建 throwaway worktree 和 lane 资源隔离，再实现五类 desk mutant。

验收：

- B 产物五类空心测试全部被杀；
- baseline 必须先绿，任一 surviving mutant 阻断；
- 原 worktree 前后 byte-identical、git status 不变；
- crash 不留下 mutant 或假 attestation；
- 零适用 mutant 不能算 pass。

### P0-6 报告新鲜度

C4/C5/mutation 报告必须带：

`target_tree_sha/spec_hash/input_manifest_hash/toolchain_hash`。

C6 先校验所有票据与当前 feature HEAD 一致，再评估四布尔 gate。现有缺口见 `c6-gate-contract.md:187-189`。

验收：C4/C5 后改任意源码、spec、AC test 或 review seed，旧票必被 `INVALID_REPORT` 拒绝。

### P0-7 C5 typed inputs + failure-modes

实现 `review_input_manifest[]`、输入权威顺序、failure-mode finding category、必需 C4 report。

验收：

- 重放 A/B：缺 seam seed 与声明 seed 的差异稳定可复现；
- required 输入缺失/hash 漂移时 fail-closed；
- C5 不读未声明 README、契约或 session log；
- report 可证明 verdict 基于哪组输入；
- NC finding 不会落入 approve subtype。

### P0-8 invocation/cost ledger 与 model capability

统一记录成功、失败、timeout、kill。模型变化跑固定回放 corpus。

验收：三路并发无丢行/重复 header；kill -9 后未完成调用标 `aborted/unknown`；配置成本账不会改变 routing。

### P0-9 desk 最小安全闸

27017 禁止测试、bzds 只读、凭证禁入库不能等到 P1 迁移后再做。它们实际来源于 `suiyin-desk/CLAUDE.md:25-34`，并不都在 desk constitution。

验收：任何测试命令指向 27017、bzds 写操作、凭证入 git 均在模型调用前机械阻断。bzds 数据库账号是否真实只读：待验证。

## Gen4-P1：归因、迁移与 plan 自动化

### P1-1 完整 lane isolation 与 failure envelope

隔离 DB、cache、port、tmp、build cache；不可隔离的全仓构建用有限全局 semaphore。desk 已证明仅 Mongo 隔离仍会因 CPU 争抢团灭：`suiyin-desk/docs/process-evolution.md:254-259`。

验收：三 lane 历史 flaky fixture 不交叉污染；资源销毁无残留；base/head 归因使用同一环境参数。

### P1-2 base/head 归因、attempt accounting、Execution Failure Triage

顺序必须是：

1. 统一 failure envelope；
2. base/head 对照；
3. 重构 C2 attempt accounting；
4. classifier；
5. C7 Q7-2；
6. 通用 repair feedback。

判定：

- base 红/head 红：FOREIGN；
- base 绿/head 红：OWN；
- 同 commit 重跑翻转：INFRA；
- 无法归因：UNKNOWN park。

验收：FOREIGN/INFRA 不扣 owned attempt，但有独立有限预算；UNKNOWN 不自动放行；kill 后各预算不重置。

### P1-3 desk migration mapping + C9 fixture

按下节 M0–M5 执行；至少生成 `affected.yaml`。

验收：P1–P9、E1–E11、001–005 FR、旧契约接口/schema/error/ownership 均有唯一归宿；orphan=0，multiple-primary=0。

### P1-4 typed seam/authorization manifest + plan lint

lint 左侧改为 seam、authorization、AC/guard tests 和 failure-mode acknowledgement。

验收：

- 每个 seam/error/side-effect 可追到 plan；
- 每个行为义务可追到 spec AC；
- 下位自设更严预算被项目规则拦截；
- 未处置 architecture failure mode 必须 block 或有显式 waiver；
- lint 完成前旧 plan gate 不退役。

### P1-5 C3/high 与 tier policy

首个 high task 前实现 C3，或提供 fail-closed 人工替代；不得静默降 medium。

另外单独拍板是否迁 P9/E11 tier。若迁，增加 deterministic disposition policy；若不迁，明确只保留 taxonomy/fix-forward。

### P1-6 重写旧 P1.6

废弃 `docs/sdd/todo.md:394-409` 的 per-tool 小模型主方案。新顺序：

`plan/constitution → typed authorization manifest → mechanical path/command/network/DB gate → 极少语义残余`

验收：机械可判路径模型调用数为零；manifest 缺失/失效/解析失败时 fail-closed；不存在需要持续扩张的通配例外表。

## Gen4-P2：按机制拆开

- **巡检**：只读、零模型、只能告警，不能 merge/unpark；先用历史 watchlist 回放测误报。
- **C10**：单独做 spec overlap；迁移期先跑一次。
- **C11**：依赖 feature→main hook；先 bootstrap registry，再验证 add/modify/delete 增量一致。延期期间 C5 complexity 只有 jscpd 降级。
- **C12**：标明“C5 finding 已完成、非 post-merge capture protocol 未完成”。
- **C8**：保留原 roadmap；没有 C8 时 dogfood 终点只能是 main，不能触生产。
- **domain glossary、`/sy-role`**：恢复为显式 backlog 项。
- **C4 L4/R3**：明确保留、由 C5 吸收或取消，不能悬空。

---

# 四、desk spec + constitution 迁移方法论风险

desk 源应固定在 commit `91377962c6d3fd50c3a36afcb624fa1cfa04345e`。其 constitution 头仍写“v1.3、最近修订 2026-07-30”，但 P7/P9/E10/E11 含 2026-08-06 修订；这些是否完成正式修宪记录：待验证。

## 1. P1–P9 逐条处置

源文件：`suiyin-desk/docs/constitution.md:9-73`。

| 条款 | 建议归宿 | 悬空/冲突 |
|---|---|---|
| P1 永不自动发言 | desk 业务 NC + outbound capability deny + spec AC | “V0.5 零发言”需绑定 milestone；否则阶段约束会被误迁为永久规则 |
| P2 话题基本单位 | 业务 spec/domain glossary + AC | 005 存在临时例外和到期条件；必须一并迁移，见 `specs/005.../spec.md:128-130` |
| P3 状态裁定闭环 | 状态机 spec + 持久化/非法迁移/逾期可见性 AC | 不能只测 UI 展示 |
| P4 发送风控 | 业务 NC + 唯一发送出口、限频、网络 capability gate | E5 删除后，绕出口必须由机械 gate 接手 |
| P5 简单优先 | `≤1000/天、单体、单库` 可保留为项目约束；“默认打回”转 PC+plan lint | C5 complexity 当前只 approve+finding，不能执行“默认打回” |
| P6 AI 可纠 | spec + decision-type↔correction-path 矩阵 + 校准落库 AC | 不能靠 reviewer 从散文自行穷举 |
| P7 及时性 | effective 数值进入 spec/constitution；证据类型允许线上 metric | 8-06 附则已收窄 10 分钟补齐/5 秒同步，不能把旧、新两套同时冻结 |
| P8 轻且响 | 产品 spec + OS/E2E evidence | “具体手段 plan 定”若改变用户可感知后果，仍须回 clarify；跨平台自动验收方式待验证 |
| P9 分档 | 先保留“爆炸半径成比例、判定/处置分离”原则；tier 激活待架构拍板 | 原文依赖 E11/E5/契约，与 C4 全绿和 C5 自判 verdict 冲突 |

这些条款必须进入 desk 项目的 `.specify/memory/constitution.md`，不能粘进 v4 的 `docs/sdd/constitution.md`。后者明确是工具项目而非业务产品：`docs/sdd/constitution.md:132-184`。

## 2. E1–E11 逐条处置

| 条款 | 建议归宿 | 悬空/冲突 |
|---|---|---|
| E1 两道人审门（`:81-84`） | 修改 `methodology.md` + role-profile；spec/后果题人 pin，技术 plan 有条件 auto-pin | 属治理 MAJOR 变化，不能靠迁移 agent自行改写 |
| E2 task 契约（`:85-87`） | 接口/schema/error→seam manifest；文件/表/网络写权→authorization manifest；行为→AC | 所有替代物未就绪前，旧契约不能退役 |
| E3 TDD（`:89-91`） | 要么增加 red-proof artifact，要么降为指导原则 | 当前 C2 只要求“实现+写测试”，无法证明 red-first：`c2-task-executor.md:307-313` |
| E4 独立对抗审查（`:93-95`） | fresh review→C5；沙箱/mutation→C4；记录→content-bound report | 不能把“mutation 唯一残余”解释成取消 C5 |
| E5 越界审计（`:97-100`） | LLM 席退役；义务迁 static/runtime authorization + C5 residual | 历史 E5 corpus parity 未完成前不得退役 |
| E6 机器验收（`:101-124`） | 通用 oracle/命令执行规则→methodology+C4；desk 字段/分类/UI 细节→AC/failure-modes/mutant catalog | seam/NC guard test 不能被归为“后任可随意改”的实现测试 |
| E7 外部依赖（`:126-128`） | 业务 NC + failure-mode + 检测/告警 AC | 与 E9 验证期“保留检测、砍恢复”存在覆盖，需生成唯一 effective rule |
| E8 AI 回放（`:226-228`） | 业务 NC + 固定 input/prompt/model/config snapshot + 指标 | 回放不等于输出 bit-identical，需定义比较指标 |
| E9 故障模型（`:130-215`） | 保证边界留 constitution；历史病例进 failure-modes；流程理由进 ADR/history | 前半与 8-06 附则有 supersession；所有 E4/E5 引用需改写 |
| E10 lane 隔离（`:217-224`） | 上移为 Gen-4 C4/C7/environment invariant；desk 只留 Mongo 参数 | 必须早于 mutation；v4 NC-4 目前只隔离 worktree |
| E11 taxonomy/tier（`:230-255`） | taxonomy 可映射到 C5 raw findings；tier 需 deterministic policy gate | `E5 恒全量`、契约头、tiers.conf 都会悬空；原样迁移不可行 |

## 3. 正确的迁移任务设计

### M0：冻结源并生成 effective constitution

产物：

- `source-snapshot.yaml`
- `effective-constitution.md`
- `exception-registry.yaml`

验收：

- 绑定 desk commit SHA；
- P/E 每个 bullet、附则、豁免均有稳定 source ID；
- P7/E7/E9 覆盖关系归一为一个现行语义；
- 005 临时豁免包含 scope、批准人、到期、撤销触发；
- 8-06 修宪状态未确认处标“待验证”。

### M1：原子迁移矩阵

每行至少：

```text
source_id
source_ref
exact_semantics
scope(product/toolchain/process/history)
disposition
primary_target
enforcer
evidence
exceptions
semantic_change
approval_required
status
```

验收：

- `orphan=0`
- `multiple_primary=0`
- `active_ref_to_retired_E4/E5/contracts=0`
- 语义变化必须生成 consequence question 或 amendment
- “溶解”必须指向替代机制及其 AC

### M2：拆分 spec/contract 资产

- US/GWT/FR/成功指标 → stable `AC-N`
- 接口/schema/error/依赖方向 → seam manifest
- 文件/包/集合/网络/数据库写权 → authorization manifest
- 契约验收判据 → behavior/seam/guard test + mutant ID
- 计划机制和内部预算 → plan
- 真实坑 → failure-modes
- 裁定/豁免 → ADR/exception registry

验收：001–005 每个 FR/GWT/指标都有映射；旧契约接口/schema/error/ownership row 零遗漏；内部 Go shape 不进入行为 spec。

### M3：Gen-4 tool-ready gate

在 desk 代码重生成前必须完成：

- Go C4 runner/parser；
- Mongo lane isolation；
- 27017/bzds gate；
- content-bound reports；
- C5 typed inputs；
- seam/authorization lint；
- plan auto-pin 前置链。

任何一项缺失，迁移只能停在文档 dry-run。

### M4：历史双轨回放

回放集至少包括：

- 本次八个 E4 blocker；
- 历史 E5 越界票；
- `process-evolution.md:131-153` 坑清单；
- 002·T001；
- 业务型 T003。

验收：

- seam/floor 历史逃逸为零；
- 选定 policy 下应阻断的 accept/quality 全命中；
- mutation catalog 指定 mutant 全杀；
- FOREIGN 不消耗 owned attempt；
- fail-closed 路径有票、有 state、可 resume。

### M5：修宪、shadow 和切换

- 旧契约/review 历史只读归档，不删除。
- 新旧 gate 至少 shadow 一轮。
- T003 主线通过后才 cut over。
- 任一历史 seam/floor 病例漏检，自动恢复旧 gate。
- `gen4-plan.md:122` 的 desk 旧流程共存节奏不能继续列为“不阻塞”；进入主线迁移时它是切换前置。

---

# 五、补充建议

## 1. 在 `gen4-plan.md §一` 增加“证据→机制”归因表

不要再从“E4 多抓八条”直接跳到“mutation 唯一残余”。八条分别标：

`finding / 责任机制 / 是否阻断 / fixture / regression AC`。

这样下一轮回放才能知道是哪个机制退化。

## 2. 在 `§二` 增加“不可破坏 invariant 表”

至少覆盖：

- C7 唯一路由权威、routing 零 AI；
- task→feature 本地 ff、feature→main 才 C5/C6；
- C2/C5 worktree 隔离；
- C1 只排序不改 task；
- C4/C5 报告结构化且绑定当前 tree；
- C6 fail-closed；
- profile 只能改变 actuation/escalation，不能关闭 AC/NC 门。

## 3. 给 verify evidence 增加类型

不是所有约束都应强塞成单元测试。建议 C4 evidence schema 支持：

`test / static / mutation / metric / runtime_guard / manual_attestation`

其中 manual 不能满足自动 merge 的硬门，除非 profile 明确要求人工。

落点：`docs/sdd/components/c4-verify-contract.md`。

## 4. 明确“30% 胶水”的 owner

接缝中心完成后，两侧并行产生的 glue 不能靠执行会话临场越界。应预声明 integration task；若未知，则 feature C5 block 后生成 repair task。动态新增 task 必须产生新 manifest hash/run，而不是原 C7 state 内偷偷改清单。

落点：`gen4-plan.md §二-5`、`skills/sy-tasks/SKILL.md`、C7 schema。

## 5. 清理 spec-kit fork 内的相反指令

`skills/sy-tasks/SKILL.md` 同时包含 v4 YAML override 和旧 spec-kit 的：

- `tasks.md`
- tests optional
- contracts optional
- `T001` 编号

这些会直接破坏 AC freeze 与 canonical identity。应删除或机械屏蔽被 override 的旧段，而非只在文件顶部声明“以下按新规则解释”。

## 6. 把“强模型”做成 benchmark，不做品牌声明

固定 corpus 至少包含：

- 五类 mutant kill；
- 已知 seam/floor fixture；
- spec 行为反例；
- task success/retry 成本；
- C5 precision/recall。

模型、prompt、tool permission 或上下文策略变化即重跑。落点：model/role profile + `gen4-plan.md §二-8`。

## 7. 每个 Gen-4 backlog 项统一 DoD

每项完成必须同时具备：

- 组件 spec/version bump；
- schema；
- 至少一条失败型 AC；
- `workflows.md`/`diagrams.md` cascade；
- `todo.md` 旧项处置；
- 真 dogfood artifact；
- kill-9/resume 或明确“不适用”。

否则会再次出现实现、状态机、roadmap 三套事实。

## 8. 明确标注待验证

以下事项不能以默认值带过：

- 2026-08-06 的 P7/P9/E10/E11 是否完成正式修宪；
- desk 现有测试中哪些是真行为 AC、哪些耦合 Go 内部实现；
- bzds 账号只读是否由数据库权限真实强制；
- multi-clone/multi-machine 是否在威胁模型内；
- tier 是否迁移及与 criticality 的关系；
- mutation reachable slice、operator catalog 与成本；
- P8 跨平台自动验收方式；
- 实际 C2/C5 model identity 和降级阈值；
- E5 历史 blocker 是否已被确定性 replacement 全量覆盖。