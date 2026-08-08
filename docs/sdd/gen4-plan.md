# Gen-4 计划 — 三代合流（v4 底盘 + desk 尺子 + goal-control 遗产）

> **来源**：2026-08-07/08 与用户的三代复盘对话 + 002·T001 A/B 回放实验（§一）+
> codex gpt-5.6-sol ultra 外部审稿（BLOCK，全文存档 `reviews/gen4-plan-review-codex-20260808.md`，
> 本版已消化其修正；未采纳处见 §三"P0 规模裁定"）。
> §二每条都是用户拍板过的，不是提案。**读者**：接手 v4 下一阶段的 session，读完本文 + todo.md 即可开工。

## 〇、定位与总结论

三个全自动开发项目的时间线与遗产（真实顺序，勿按"代际"直觉）：

| 项目 | 时间 | 遗产 | 死因/现状 |
|---|---|---|---|
| **suiyin-v4** | 2026-05~07 | 骨架：编排=确定性进程、LLM 只在叶子、状态可 kill -9 | 没死——被遗忘（无场景验证，v5 没空继续） |
| **goal-control** | 2026-07 末 | 信息对称原则（接缝两侧不该靠人传话） | 控制面计费实体=模型，一天烧 codex 周额度 50% |
| **suiyin-desk 流程** | 2026-08 | 尺子：闭集判据、mutation 探针、机械闸、归因纪律 | 现役；其收敛方向（脚本主干控制器）即 v4 起点 |

**总结论（用户 8-08 拍板）**：gen-4 = v4 底盘 + desk 尺子移植 + goal-control 遗产以"合并会话"
而非"通道"形式继承。实验品 = **suiyin-desk 产品（非流程）**，v5 不整了。价值排序：
**文档 > 测试 > 代码**——迁移即"spec 与 AC 层进，代码可重生成"。

**"底盘不动"的准确含义**（codex 修正）：不动的是**架构 invariant**（C7 唯一路由权威、routing 零 AI、
task→feature 本地 ff / feature→main 才 C5/C6、worktree 隔离、C4/C5 报告结构化且绑定当前 tree、
C6 fail-closed、C1 只排序不改 task）；C2/C4/C5/C6/C7 的组件契约与 methodology/role-profiles/
workflows 的相应条款**都要修订**——修订清单见 §三。

**两条定理**：控制面的计费实体决定生死；审查质量是尺子的函数，不是审查器的函数。

## 一、实验证据（002·T001 沙盒回放 + 交叉审查）

沙盒 `~/suiyin-desk-v4lab`（desk clone，origin 指本地裸仓），基线=T001 首次 claim 前（228fb1e）。
对照组=desk 真实战绩（v5 尺 12 轮 + v6 尺 2 轮，41 文件 +7011 行）。

| | 条件 A（spec/plan/tasks.md） | 条件 B（+契约 v6+README 两个 seed） |
|---|---|---|
| attempts / 耗时 | 2 / 47min | 3 / 83min |
| 产出 | 13 文件 +1588，make test 绿 | 23 文件 +3219，make test 绿 |
| 契约接缝 | 4 处关键缺失 | 全闭合，契约 §五 被译成测试 |
| C5 verdict | approve，0 findings | block：1 high + 1 low |

**交叉审查**（desk E4 审 B 产物）：BLOCKED，8 blocker（std 档拦 3 放 5）。
**证据→机制归因表**（codex 修正：8 条增量分属四种机制，不许再说"mutation 唯一残余"）：

| E4 独有发现 | 条数 | 责任机制（gen-4 承接者） |
|---|---|---|
| 自写测试空心（tag 改名仍绿/方法改名仍绿/审计断言缺字段/扫描器 taint 逃逸/浅拷贝可篡改） | 5 | **mutation 探针**（P0） |
| spec 行为违例（done→merged 当合法正例） | 1 | **独立语义审查**（C5 residual，不可裁撤） |
| 接缝缺失（ExitReason 枚举整个不存在） | 1 | **seam 完备性检查**（seam manifest + lint） |
| 会话日志被提交入 git（系实验者 `git add -A` 误伤） | 1 | **机械 hygiene 闸**（静态检查） |

其余实证：A 条件"凡 seeds 写明的全对、凡契约独有的按比例缺失"；desk 的"他人包 flaky 烧轮次"
在 v4 原样复发（B attempt-1 被基线代码 TestCallTimeout 烧掉）；53min 单发 headless 会话稳定完成
（"单次大响应必断线"是交互形态特有）；E4 新鲜度门在陌生环境 fail-closed 正确（宁退 3 不出脏票）。
**新管线回放时须对这 8 条逐条声明"哪个机制抓到"，不许只报总数。**

## 二、拍板集（用户 2026-08-07/08，v0.4 含 codex 修正后定稿）

1. **测试分类：三类测试 + 一个验证维度**（原"测试三层"修正——spec 是唯一真相，测试永远是投影）：
   - ①**行为测试**（spec AC 衍生，**冻结**）：`spec AC（权威）→ AC 测试（可执行投影）→ mutation
     attestation（投影证伪力证据）`；冲突时 spec 胜。修改通道三条：Type B（spec 漏行为：补 spec+AC，
     不强制 ADR）、Type C（意图变更：改 spec+ADR）、**projection_fix**（spec 未变、测试翻译错：
     修测试并留新旧 oracle 证据，不伪造修宪）。
   - ②**seam/guard 测试**（plan/宪法衍生，**同受冻结保护**）：内部接缝形状、写权守卫、27017 禁令类
     ——不是外部行为，也绝不是"后任可随意改"的实现测试。
   - ③**实现测试**：脚手架，后任自由改。
   - **mutation = 对①②的 adequacy 验证**。触发键（用户 8-08 批）：AC/守卫测试变更 ∪ mutant 目录
     变更 ∪ **被测包导出面变更**（廉价近似）；完整 reachable-slice 键待验证。零适用 mutant/目标缺失/
     解析失败一律 fail-closed。
2. **E5 退役是目标不是事实**。退役门 = 历史 E5 blocker 语料经"typed authorization + 静态守卫 +
   C5 residual"回放，seam/floor 逃逸为零。在此之前 E5 义务由迁移矩阵逐条指定临时承接者。
   安全边界三条（测试禁 27017 / bzds 只读 / 凭证禁入库）**不等迁移**，P0 就上机械闸
   ——注意它们现居 desk CLAUDE.md 而非宪法（codex 发现）。
3. **plan 人审退役有前置链**。前置齐之前旧 plan gate 有效：methodology/role-profiles/runtime 配置
   逐档改定（四档各自的 plan/review/merge/park 行为）+ plan 机检就位（seam manifest、
   authorization manifest、lint）。"取消人审"的准确表述：前置满足后 D 档可自动 pin 纯技术 plan。
4. **Execution Failure Triage**（原"park 分诊器"更名并钉边界）：分类器只输出
   `class/evidence/retryable/charge_owned_attempt`，**不得输出下一节点——C7 是唯一路由权威**。
   UNKNOWN → park → 生成后果化拍板题工件，用户答案作为 typed event 回灌 C7。
   feature 级 C5 block → 新建 feature-repair task/worktree（task worktree 已在整合后删除，不复用）。
5. **接缝三则**：①能不拆就不拆——1M 上下文吃得下就单会话跨栈干完（接缝是人类上下文限制的产物）；
   但"装得下"非充分条件，还须过：2h timeout 内可完成、verify 单次可执行、资源可隔离、变更有原子
   审查边界——**粒度决策落在 /sy-tasks，C1 只排序**；②拆则规划钉形状 + 接缝中心先行 + 两侧并行，
   预算内接受 70% 可用 + 30% 胶水——**胶水必须是预声明的 integration task 或 C5 block 后生成的
   repair task**（产生新 manifest hash/run），不许执行会话临场越界；接缝特重→合并成一个 task
   或做成持续演进；③会话互聊出局（群聊回错回漏实证；单聊能解决的恰证明该合并成单会话）。
6. **成本记账**：每次模型调用一行——`invocation_id/run_id/feature/task/role/model/attempt/
   start/end/status/input_tokens/cache_tokens/output_tokens/error`；失败、timeout、kill -9 也必须
   有记录；解析失败留显式 `cost_log_error` 不静默；只观测不参与 routing。
7. **C5 输入面契约化**：`review_input_manifest[]`（kind/path/authority/required/content_sha256），
   权威序 `NC > spec/AC > plan/seam > failure-modes > advisory`；required 缺失/hash 漂移 fail-closed；
   **任何 NC 命中一律输出 nc_violation**（专用类别只作 subtype——修 C5 现役 cross_platform 归
   approve 类与 NC-5 的冲突）。legacy 契约只能作迁移期输入，不得成为第二套永久契约。
8. **模型能力假设哪都不写**（用户 8-08）：实际执行就是 sonnet 5 / opus 5 / GPT 5.6；
   重估触发条件 = 代码反复过不了验收。不建 benchmark 基建，不进宪法。
9. **P1.6 重写**：`plan/constitution → typed authorization manifest → 机械 path/command/network/DB
   闸 → 极少语义残余`。机械可判路径的模型调用数为零；manifest 缺失/失效 fail-closed。
10. **独立性开支阶梯**：**独立测试作者**（便宜，常开；候选实现=测试先行顺序双会话，执行闸复用
    AC 冻结机制）→ **R3 跨厂商审**（block 争议/高危；8-08 交叉审查实证 codex 8 vs claude 2）→
    **C3 双实现**（最后手段；成本曲线：尺子=高固定/零边际/跨 task 复利，双实现=零固定/每次 2x/
    不复利；仅"一次性高危且正确性难枚举成 AC"的 task 轮到它）。人类对照物：TDD + pair programming。

## 三、移植与建设清单（v0.4 按 codex 顺序修正重排）

**P0 规模裁定**（用户 8-08："先最小化，跑起来"）：codex 的 P0-0..P0-9 十件套按"审稿完备性"排列，
照单全收=先建笼子再干活（goal-control 死法，违 desk"暴露驱动"与 v4 PC-1）。**P0 取最小可信链，
其余挂 M3 工具就绪门**（desk 代码重生成前机械拦，见 §四）——门会拦住，不需要预建。

**P0 · 最小可信链**（顺序即依赖序）
1. **身份与基线**：canonical key = `feature_id + local_task_id`（worktree/branch/state/review/cost
   同键；实验中 T-001B 被 schema 拒收即此坑预演）；r4 auto-commit 缺口收口（产物不在 base HEAD
   即 fail-fast）。
2. **AC 迁移与冻结**：desk FR/GWT/成功指标 → 稳定 AC-N 映射（002 先行）；Go verify 接线走
   verify_cmd（结构化 Go runner 后补）；**AC/守卫测试冻结闸**（diff 拦截：删除/skip/改名/弱化且
   spec 未变 → 阻断；配 AC manifest：ac_id/spec_hash/test_hash/baseline_ref；机械可判闭集之外
   的"弱化"标 UNKNOWN 不放行）。
3. **最小隔离 + mutation**：throwaway worktree + lane mongo（C4"只读"invariant 与 mutation 相撞的
   解法，desk E4 现成模式）；五类 desk mutant；验收=B 产物五处空心全杀、原 worktree 前后
   byte-identical、零适用 mutant 不算 pass。
4. **feature 收口 harness**：确定性脚本串"feature HEAD 全量 C4 → C5（subject=feature，含
   task_ids[]）→ C6"；`human:block` 做成本地 versioned 状态（GitHub label 只是可选 adapter）；
   Q7-3 完整实现前由 harness 串接，**不宣称端到端全自动**。
5. **安全闸三条**：任何测试命令指向 27017、bzds 写操作、凭证入 git——模型调用前机械阻断。
6. **成本记账最小版**（拍板 6 字段集）。

**M3 门内（desk 代码重生成前必须齐，P0 不预建）**：C5 typed inputs（拍板 7）、C4/C5 报告新鲜度
绑定（target_tree_sha/spec_hash，C6 先验票再评门）、完整 lane 隔离（DB/cache/port/tmp；全仓构建
有限 semaphore——desk 实证仅 Mongo 隔离仍会 CPU 互踩团灭）、seam manifest + authorization
manifest + plan lint、plan gate 分档修订（拍板 3 前置链）。

**P1**
- **Execution Failure Triage + 归因**（顺序：统一 failure envelope → base/head 对照 → C2 attempt
  accounting 重构 → 分类器 → Q7-2 → 通用 repair_feedback.kind=review_findings|verify_failure|
  reverify_failure）。判定：base 红=FOREIGN / base 绿 head 红=OWN / 同 commit 重跑翻转=INFRA /
  无法归因=UNKNOWN park；FOREIGN/INFRA 不扣 owned attempt 但有独立有限预算。
- **独立测试作者**（拍板 10 候选实现；与 mutation 配对：探针验存量，独立作者管增量）。
- **desk 迁移 M0-M2**（见 §四）+ **C9 fixture**（迁移即 Initiative，至少产一次 `affected.yaml`）+
  **C10 迁移期 overlap 一跑** + **C11 v0 评估**（candidate：包壳 codebase-memory-mcp——函数定义/
  调用链/语义检索现成，自建仅剩 overlap% + plan 接线 + post-merge 增量）。

**P2**：巡检席（只读、零模型、只告警不 merge/unpark，先拿 desk watchlist 历史回放测误报）、
C12 收尾（C5 finding 半边已有，补 capture protocol）、领域词典 + /sy-role 恢复 backlog、
spec-kit fork 反向指令清理（tasks.md/tests-optional/T001 编号残留——AC 冻结与身份键的隐患）、
verify 证据分型（test/static/mutation/metric/runtime_guard/manual；manual 不满足自动 merge 硬门）。

**旧 roadmap 处置表**（逐项，不许悬空）：

| 旧项 | 处置 |
|---|---|
| C3 双实现 | 保留为最后手段（拍板 10）；C2 对 criticality=high 的硬拒**不动**——首个 high task 前实现 C3 或提供 fail-closed 人工替代，不得静默降 medium |
| C4 L4 宪法合规 | 待拍：C5 吸收 vs 独立实现（E5 退役门评审时一起定） |
| R3 codex 双审 | 保留，场景绑定（block 争议/高危）；Q5/Q5-6 并入该场景 |
| C8 发布门 | 保留原 P4；C8 未建前 dogfood 终点=main，不触生产 |
| C9 / C10 / C11 / C12 | 见 P1/P2（C9 fixture 先行、C10 迁移期一跑、C11 评估包壳、C12 收尾） |
| P1.6 语义闸 | 已重写（拍板 9） |
| Q7-2 / Q7-3 | Q7-2 并入 P1 Triage；Q7-3 = P0 harness → 完整实现 |
| /sy-role、词典、r4 #5 输出语言 | backlog；r4 #4 auto-commit 并入 P0-1 |

## 四、Dogfood 与迁移计划

- **唯一实验品 = suiyin-desk 产品**（v5 不整了）：desk spec + constitution 整体带进 gen-4 当主线。
- **迁移按 codex M0-M5 执行**（全文见审稿存档 §四，此处为纲）：
  **M0** 冻结 desk 源 commit（迁移开工时的 main SHA）+ 生成 effective-constitution（把 8-06 附则、
  005 临时豁免等叠层归一为单一现行语义，每条带稳定 source ID）+ exception-registry；
  **M1** 原子迁移矩阵（每条：source_id/语义/scope/disposition/primary_target/enforcer/evidence；
  验收 orphan=0、multiple_primary=0、对已退役 E4/E5/契约的活引用=0；"溶解"必须指向替代机制及其
  验收）——codex 报告里的 P1-P9/E1-E11 逐条归宿表即矩阵初稿；desk 条款进 desk 项目的
  `.specify/memory/constitution.md`，**不进 v4 宪法**（工具/业务分界）；
  **M2** spec/契约资产拆分（US/FR→AC-N；接口/schema/error→seam manifest；写权→authorization
  manifest；契约验收判据→behavior/seam/guard 测试+mutant ID；真实坑→desk failure-modes——
  **业务坑进 desk failure-modes，gen-4 工具链缺陷进组件 regression AC，每条一个 primary owner**）；
  **M3** 工具就绪门（见 §三；任一缺失，迁移停在文档 dry-run）；
  **M4** 历史双轨回放（回放集：本次 8 条 E4 blocker、历史 E5 越界票、desk 坑清单、002·T001、
  业务型 T003；验收：seam/floor 逃逸零、指定 mutant 全杀、FOREIGN 不耗 owned attempt）；
  **M5** shadow 一轮 + T003 主线通过才 cut over；任一历史 seam/floor 病例漏检自动恢复旧 gate；
  旧契约/review 历史只读归档不删除。**desk 现役流程的退役节奏 = 切换前置（M5 管），不再是
  "不阻塞"项。**
- **沙盒先行**：`~/suiyin-desk-v4lab` 模式继续用（clone + 本地裸仓 origin + 基线分支）。
- **首个校验点**：T003（归入引擎，业务逻辑型）A/B 再跑一轮——T001 是 schema 型最吃契约红利，
  样本有偏。

## 五、未决（不阻塞 P0）

- **tier vs criticality fork**（用户延迟）：P9/E11 迁移二选一——只迁 taxonomy+fix-forward 账，
  或 C5 输出 raw findings + 确定性 disposition policy + C6 消费 policy 结果。两者不是同一维度
  （criticality 定实现拓扑/C3，tier 定 finding 处置），禁止合并成一个字段。
- criticality 由非技术用户定档——遇到再说（用户 8-08）。
- mutation reachable-slice 全键的算法与成本；"弱化"的机械可判闭集边界。
- multi-clone/多机是否在威胁模型内（在→pid 锁不够需 git CAS claim；不在→明写"单机单 clone"）。
- 8-06 那批 desk 修宪（P7/P9/E10/E11）是否有正式修宪记录；bzds 账号只读是否数据库层强制——
  M0 时逐条核实（待验证）。
- 每个 backlog 项统一 DoD：组件 spec bump + schema + 至少一条失败型 AC + workflows/diagrams
  cascade + todo 处置 + 真 dogfood 工件 + kill-9/resume 或明确"不适用"。

---

**Version**: v0.4（2026-08-08）
**Changelog**: v0.4 消化 codex ultra 审稿——证据→机制归因表（撤"mutation 唯一残余"）、测试分类
三类+一维、E5 退役改目标+parity 门、plan 退役前置链、Triage 更名与路由边界、身份键、P0 重排为
最小可信链+M3 门（用户裁定）、模型假设不落文档（用户裁定）、mutation 触发键折中（用户裁定）、
旧 roadmap 处置表、M0-M5 迁移纲要。v0.3 拍板 10 独立性阶梯。v0.2 用户四拍板。v0.1 初稿。
