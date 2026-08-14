# Review 收敛协议研究综合（2026-08-14）

> 触发案：M5 shadow T003 归入引擎四轮 C5 循环不收敛（实现侧零翻案全修复、审查侧每轮采样新
> findings、第 4 轮靠类别通胀触发 block、人裁退化为盖章）。用户裁定：停止开发，研究软件工程
> 成熟方法论。三个独立研究方向（正式审查方法论 / 统计质量控制 / 现代工业实践 + LLM 审查），
> 各自先做通用研究、再对同一份流程卷宗做映射。本文是三方综合。
> 三份原始报告全文见本文档同目录归档（agent 产出，含全部文献出处）；
> Fagan 1976 / IEEE 1028-2008 / Capers Jones DRE 原文留存本地 tool-results。

## 一、三方一致的结构诊断（3/3 独立到达）

**病灶不是"审查者太严"，而是把三个在一切成熟体系里必须分离的权力焊死在 C5 一个采样器手里：
发现权（提 finding）、定性权（归 category）、裁决权（category 机械翻转 verdict）。**

- 正式审查系：Gilb 的 issue（登记者报的）与 defect（裁决后的）是两个身份；checker 只有登记权
- 统计系：等于把 AQL 判定表的裁定权交给抽样员本人；"审到没新意见"在无限检查面上是发散条件
- 现代系：GitLab reviewer 提意见 / maintainer 终裁合并，两个权限层；Google "事实压倒意见"

配套的三条定理级论证：
1. **单轮 recall 25-88% 是四十年实证常数**（Fagan 67%/Gilb 25-75%/Jones 表），重复同手段加轮
   收益递减且交 3.5-7% bad-fix 税——"C5 多跑几轮逼近全覆盖"与实证相悖
2. **nit 序列不衰减这一事实本身证明它属于噪音过程**（不满足缺陷总量有限假设），必须排除出
   判停信号；逐轮修 nit = Deming 漏斗实验的 tampering（调整制造新检查面、放大方差）
3. **inspection（开放采样）与 verification（闭集核销）是正统上严格分离的两个阶段**
   （Fagan follow-up / IEEE 6.5.7），我们把它们焊成了同一个循环

## 二、T003 四轮的正统判读（三方交叉）

| 轮 | 正统定性 | 应走的通道 |
|---|---|---|
| 1（232 行骨架 block）| **增量拒收案**（Cleanroom：过拟合尺子=增量整体不合格）| 打回重做，不进 findings 循环、不烧预算——实际被记作反馈第 1 轮是记账错误 |
| 2（+3523 行 block）| **正当的首次完整 inspection**（受审物换了；Fagan 5% 规则下旧清单作废开新轮）| 闭集台账应从这轮封版 |
| 2 漏检轮 3 才发现的契约违例 | **审查过程的逃逸缺陷**（单轮 recall<100% 常数 + 3700 行超 Fagan 单场速率 25 倍，漏检是必然不是 bug）| 修掉 + 记逃逸台账校准审查；不作为延长循环依据 |
| 3-4 的"全新 findings" | **对稳定过程的重采样 = tampering 开始** | 分流：interdiff 内 regression 可阻断；其余立票 |
| 4 的"断言精度→nc_violation" | **类别通胀翻转 verdict**（抽样员自改 AQL 表）| 锚点准入校验下活不过登记环节 |

按新协议回放：四轮压到两轮，与上一代人工流程"判据闭集+元规则"12→2 轮的历史实证同构。

## 三、Review 收敛协议 v1（拟）——落到组件的改造清单

### P0（结构件，治不收敛本身）

| # | 件 | 规格 | 三方依据 |
|---|---|---|---|
| CV-1 | **verdict 权移出 C5** | C5 输出纯 findings（category 仅为提案）；门层新增 **admission validator**（确定性代码）：锚点校验通过的 blocking finding 才计入；`verdict = f(validated findings, 台账状态)` 查表计算 | GitLab 分权 / AQL 查表 / Gilb 两权分离 |
| CV-2 | **block 类锚点 schema** | `nc_violation`: {条款号, 条款文本 hash, diff 证据行}；`spec_drift`: {spec/契约锚点, 要求行为引文, 观察行为} 三元组；`security`: {CWE 或宪法安全条款, source/sink 路径}；校验不过 → 自动降级 advisory + 审计日志 | 候选 2 泛化（三方一致）；Fagan defect 客观化定义 |
| CV-3 | **ac_uncovered 迁出 C5** | AC↔测试 traceability matrix 机械检查器（acgate 扩展）；C5 block 类缩为三个 | 可判定命题不给采样器（三方一致） |
| CV-4 | **findings 台账 + 双模式复审** | 首轮（实质完整实现轮）findings 封版为带 ID 台账，每条附**验收谓词**（测试 id/断言/可 grep 事实）；复审 = verification pass：C5 输入裁剪为 (台账, rework interdiff)，逐条核销谓词 + 仅扫 interdiff；**5% 型分流器**：rework 面超阈值 → 判为新受审物开新 inspection（新台账，不占验收预算） | Fagan follow-up + 5% 规则 / IEEE 6.5.7 / Gerrit interdiff |
| CV-5 | **新发现分流 + 断路器** | interdiff 内 regression 或过锚点校验的 security（任何轮 Ac=0 豁免）→ 入台账；既存漏检/nit → 自动开票（P0 优先级、合并时通知人）不阻断；`contract_gap` 新类 → 路由 spec 变更流程不进 verdict；**validated blocking 数不严格递减 → 立即跳出进人裁**（不耗完预算）；同指纹 finding 两轮重现 → 单条进仲裁 | Google file-a-bug / 元规则成文 / Contrast 严格递减律 |
| CV-6 | **disposition 三选一，裁决前移** | inspection 收口即裁决：`approve / approve_after_verification / reinspect`——rework 之前锁死后续路径；二值 verdict 表达不了"接受待验证"这个收敛最快的出口 | IEEE 6.5.6.5（独有关键件） |
| CV-7 | **增量拒收规则** | 首轮 validated block 含"契约子系统/主流程缺位"类 → 增量整体打回重做，不进反馈循环不烧预算 | Cleanroom（治轮 1 型记账错误） |

### P1（检出率与人裁质量）

| # | 件 | 规格 |
|---|---|---|
| CV-8 | **首轮 panel 采样** | inspection pass 并行 n=3（可含 codex 一票——候选 3 的正确归宿）；按 (文件,行区,category) 指纹去重合并；blocking 入台账需 ≥2 复现，孤证降 advisory；双审重叠率白送 capture-recapture 残留估计（重叠低→值得加审） |
| CV-9 | **人裁封闭问题化** | 每条上交 finding 一张对抗卡：finding 原文+锚点校验结果+被引条款原文+**实现 session 自动征集的答辩**+复现率+机械层状态；人做 uphold/downgrade/defer 三选一+一句 rationale 落库；编排 AI 推荐**后置展示** |
| CV-10 | **受审面尺寸闸** | diff 超阈值（起点 ~800 行警告，按 plan 切片分块提审；工业中位变更 25-78 行）；轮 2 的 3523 行单面是采样不尽的一半原因 |

### P2（长期校准）

| # | 件 | 规格 |
|---|---|---|
| CV-11 | **逃逸台账 + nit 沉淀管道** | 复审在未改动代码上的真缺陷入逃逸台账（校准审查强度）；审计队列重复 ≥2 次的 category 自动开 process-improvement 票（lint/模板/C5 checklist），owner = v4 仓 ADR/PR 通道 |
| CV-12 | **跨任务控制图 + 切换规则** | 每任务记：首轮 validated block 数/逃逸数/降级率/翻案率；≥8 任务建 XmR 基线；record 好降审查强度（单审/抽审），逃逸 security 加严——ISO 2859 切换规则 |
| CV-13 | **量化出闸替身** | mutation kill rate 阈值进 exit criteria（Gilb 残留密度的可测替身——mutation 是确定性植入缺陷测量，比"C5 没再报"好得多的残留指标）；零 finding 合法化写进 C5 rubric（工业实证 87% review 零缺陷记录，防"交作业"压力） |

### 候选方案三条的终审

1. 闭集清单+复审只验收 → **采纳**，正统名 Fagan follow-up；补四洞（security 豁免/验收谓词/封版点在实质完整轮/5% 分流器）
2. nc_violation 强制条款引用 → **采纳并泛化**到全部 block 类 + verdict 权整体移交（只堵一类，通胀会迁移到下一个最模糊类别）
3. 第二厂商上诉审 → **否决**（开放问题上双采样器无共识可言，Contrast 三 reviewer 措辞分歧实验实证）；组件改嵌 CV-8 panel 一票 + CV-9 人裁包异议报告

## 四、待用户拍板

1. 协议 v1 的 P0 七件（CV-1..7）是否照单开工（v4 仓，C5 v0.5.0 + close harness v0.3.0 + acgate 扩展）
2. T003 处置：挂着当**新协议的第一个验收用例**（协议落地后用新门重判——r4 那条 nc_violation 会在锚点校验处自动降级）vs 现在人工 override 合并
3. P1/P2 的排期（建议 P1 随 P0 同批，P2 攒任务样本后）
