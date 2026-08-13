# M4 病例回放 — E4 8 条 + E5 越界票 归因表（2026-08-13）

> 场地：`~/suiyin-desk-v4lab` 分支 `v4lab/m4-replay`（= `v4lab/e4-cross` + 002 契约资产转正：
> seam-manifest.yaml 28 条正式化 / authorization.yaml / tasks-desk-002.yaml 脚手架）。
> B 产物 diff = `main...v4lab/b-product`（23 files +3219）；A 产物 = `task/T-001`。
> 工具链 = v4 main @ M3 全收后（PR #73-#82）。lane mongo 38027（容器 suiyin-testmongo-p03）。

## E4 8 条 blocker

| # | 病例 | M4 闸 | 结果 | evidence |
|---|---|---|---|---|
| 1-5 | 空心测试 ×5（tag_rename / method_rename / assert_field_drop / taint_escape / shallow_copy） | mutation 探针复跑 | ✅ **5/5 survived 复现**（baseline 绿 + 全部放跑 = 空心实锤） | `results/mutation-rerun-b-artifact.json` |
| 6 | done→merged 行为违例 | C5 typed inputs | ❌ **仍漏**（预测内）：4 findings 无一命中状态机行为违例。残差承接 = R3 跨厂商审（拍板 10，P1）+ 独立测试作者的状态机正反例测试（GUARD 类） | `results/c5-typed-b-artifact.json` |
| 7 | SEAM-EXIT-REASON 枚举整组缺失 | C5 + seam_manifest 输入 | ✅ **[critical] 点名检出**——P0 时 expected-miss，seam 进输入面后转为机械链捕获（"审查质量是尺子的函数"第 3 次实证） | 同上，finding #1 |
| 8 | hygiene（.suiyin 工件入库） | safety 规则 4 | ✅ 复确认（件 8 校准后重跑：3 处真问题保留，73 FP 归零） | `dogfood/P0-attribution/` + c2 spec v0.5.2 |

附加交叉确认：C5 finding #2（ScratchState 浅拷贝 [high]）与 mutation `M-scratch-shallow-copy` survived **双闸独立命中同一缺陷**。

## E5 越界票（审计票 T001-audit-20260806-1842，3 blocker + 1 major）

| E5 条目 | M4 闸 | 结果 |
|---|---|---|
| #2 Makefile `test-mongo-force` 未声明副作用 | authz path 闸 | ✅ 探针机械检出（`AUTHZ_PATH_UNGRANTED: Makefile`） |
| #3 跨模块越界（cmd/opctl + api/guard/… 8 模块） | authz path 闸 | ✅ 探针 3/3 机械检出；A 产物合法面过闸零误报（1 处 glob 校准后） |
| #1 `Fake.Set` 接口面扩大 | C5 + seam 输入（SEAM-CLOCKX 闭集） | ⚠️ **机制实证、实例未点名**：A 轮 block/6 全为签名级 closed-face 违反（同类机制），但 Set 本身未被单独 flag。贡献因素：契约版本歪斜（A 产物 v3 vs 尺子 v13）+ reviewer 聚焦缺失/错配类未扫"多出的方法"。残差承接 = R3 + SEAM-CLOCKX test_ref（现 PENDING） |
| major `ErrMissingOpID` 未声明错误语义 | C5 + contract 输入 | 归入 A 轮同类签名/语义 drift 检出面（未单独点名，同上残差） |

E5 探针方法论：desk 真仓禁区（现役对照组零接触），审计票原文的违规形态合成 probe diff（`results/e5-probe.diff`）——与 mutation 探针同一方法论（重建缺陷形态验证闸门咬合）。

## 结构性 findings（回放的额外产出）

1. **seam schema v0.1.0 缺口**：跨 feature 消费方无法表达（SEAM-CORRECTIONS-ERRORS → 003 工作台），强塞 feature 内消费者制造假 L3（`results/seamlint-002.json` 保留该 finding 不消音）→ seam schema v0.2 加 `external_consumers`
2. **28/28 接缝测试全 PENDING**（seamlint L4 点名）→ 独立测试作者从 P1 候选升为 **M5 前硬需**（M4 复核实证：#6 与 E5#1 的残差承接都指向它）
3. **C5 meta-findings 反咬回放资产**：CardMu（v13 字段，B 产物成文早于 v13——版本歪斜被审出）+ authorization.yaml T001 `db_writes:[]` 与契约 §三 矛盾（裁定错误，待修正）——尺子对校准债同样有效
4. **契约版本歪斜是回放的系统性噪音源**：A/B 产物按 v3/v6 契约生成，尺子是 v13——M5 shadow 时新产物与尺子同代，此噪音消失

## 零逃逸门判定

**8 条 E4：7 检出（含 #7 转正）/ 1 已知漏（#6，残差承接已排期且有第 3 次实证背书）。**
**E5 4 条：2 机械检出 / 2 机制实证但实例未点名（残差承接同 #6）。**

门语义（gen4-plan §四 M4"零逃逸"）：**逃逸 = 未被检出且未被归因承接**。本轮零逃逸成立——
每条病例要么机械检出、要么有明确残差承接（R3 + 独立测试作者，均已排期）。
**M5 开工前置由此确定：独立测试作者（28 条 seam 护栏 + 状态机正反例）优先级最高。**

## 复现命令

```
# mutation（v4 仓 dogfood/P0-3 目录下）
suiyin-flow mutation run --catalog desk-mutants.yaml --repo-root ~/suiyin-desk-v4lab \
  --ref v4lab/e4-cross --env MONGO_TEST_URI=mongodb://127.0.0.1:38027/?directConnection=true
# C5 typed（v4lab 下，inputs manifest 含 contract×2 + seam_manifest + authorization）
suiyin-flow review run --pr-ref v4lab/b-product --spec specs/002-topic-triage/spec.md \
  --plan specs/002-topic-triage/plan.md --constitution docs/constitution.md \
  --task-id T-002 --feature-id 002-topic-triage --inputs-manifest .suiyin/m4-c5-inputs.yaml \
  --criticality medium --repo-root ~/suiyin-desk-v4lab
# authz E5 探针
suiyin-flow authz check --manifest specs/002-topic-triage/authorization.yaml \
  --tasks-yaml specs/002-topic-triage/tasks-desk-002.yaml --diff results/e5-probe.diff --task-id T001
```
