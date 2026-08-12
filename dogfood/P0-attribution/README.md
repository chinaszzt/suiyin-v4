# P0 整链验收 — 8 条 E4 blocker 归因表 (2026-08-13)

> gen4-plan §一 硬要求：「新管线回放时须对这 8 条逐条声明"哪个机制抓到"，不许只报总数。」
> 场地: `~/suiyin-desk-v4lab`，B 产物 = `dc70814`（分支 `v4lab/b-product`；注意 `v4lab/002-t001-replay-b` 只是起跑点+种子修正，**不含产物代码**）。

## 归因表

| # | E4 blocker (2026-08-08, gpt-5.6-sol tier=std) | gen4 承接机制 | P0 实测 |
|---|---|---|---|
| 1 | BSON tag 改名仍绿（schemas_roundtrip 护栏漏断） | mutation 探针 | ✅ **检出**（M-bson-tag-rename survived） |
| 2 | 接口方法改名仍绿（TestContractShapes 不冻结方法集） | mutation 探针 | ✅ **检出**（M-iface-method-rename，extra_edits 双点） |
| 3 | 审计断言缺 before/after 字段（registry_test） | mutation 探针 | ✅ **检出**（M-audit-field-drop survived） |
| 4 | 只追加扫描器 taint 条件重绑定逃逸 | mutation 探针 | ✅ **检出**（M-taint-escape survived） |
| 5 | ScratchState 浅拷贝可篡改 | mutation 探针 | ✅ **检出**（M-scratch-shallow-copy survived） |
| 6 | spec 行为违例：done→merged 当合法正例 | C5 residual（独立语义审查） | ❌ **未捕获 0/2**（见下"C5 对照实验"）——R3 场景绑定的实证加固 |
| 7 | 接缝缺失：`ExitReason` 枚举整个不存在 | seam manifest + lint（M3 门内） | ⚠️ **预期漏检**（机制未建，M3 前如实记录） |
| 8 | 会话日志 `.suiyin/sessions/*.log` 提交入 git | safety v0.5.1 规则 4（机械 hygiene 闸） | ✅ **检出 ×3**（`SAFETY_RUNTIME_ARTIFACT_IN_DIFF`，对 main...e4-cross diff） |

**结果：8 条中 6 检出 / 1 未捕获（C5 residual，有对照实验数据）/ 1 预期漏（M3 机制未建）。**
1-5 evidence: [../P0-3/](../P0-3/)；6/8 evidence: 本目录 `results/`。

## C5 对照实验（"审查质量是尺子的函数"的直接检验）

同一 C5（sonnet 默认、criticality=medium、同 diff `main...v4lab/b-product` 23 files +3219），只换权威输入：

| 跑 | spec_ref 输入 | verdict | findings |
|---|---|---|---|
| A | `spec.md` + `plan.md` | **approve** | 0 |
| B | **契约** `contracts/T001-topic-model.md`（+spec.md 作 plan 槽位） | **block** | 1 high spec_drift（`topic.EnsureIndexes` 未接入 server main——真实集成缺口，E4 亦有观测） |

- **尺子效应方向性实证**：换契约当权威输入，同一审查器从 0 finding 变 1 条真 finding
- **但 #6（done→merged）两跑均漏**：现役 C5 单审（无 typed inputs、无行为违例专项尺）对 spec 状态机违例不可靠。E4 抓到它靠"契约闭集判据 + 实跑 transition 正反例"。归因落点：M3 C5 typed inputs（拍板 7：契约进 `review_input_manifest` 权威序）+ R3 跨厂商审的场景绑定（拍板 10：block 争议/高危）——**均已在 gen4-plan 排期内，本表提供第 2/3 个实证**
- 附带正向发现：给错 ref（空 diff）那一跑，C5 没有幻觉出审查，verdict=block +「0 FR 被实现」——fail-safe 语义正确

## 校准附注（M4 回放清单）

P0-5 安全闸三条老规则对 desk 真实 diff（main...e4-cross）的命中：27017 ×33 / bzds 写 ×22 / 凭证 ×18——绝大多数是**守卫断言与测试夹具的合法出现**（desk 自己的判定是"测试命令指向 27017"级别的精准语义，文本级粗判必然过拦）。**M1 迁移时需处理误报面**（候选：范围限定 verify_cmd + 非测试文件 / 白名单标注），否则 desk 真实收口会被安全闸卡死。规则 4（.suiyin/）零误报。

## 复现

```bash
# 1-5: mutation (见 ../P0-3/)
# 8:
python -c "from suiyin_flow.c2_executor.safety import check_diff; ..."  # 见 results/safety-rule4-hits.txt
# 6:
suiyin-flow review run --pr-ref v4lab/b-product --spec specs/002-topic-triage/spec.md ... # 跑 A
suiyin-flow review run --pr-ref v4lab/b-product --spec specs/002-topic-triage/contracts/T001-topic-model.md ... # 跑 B
```
