# Mutation Probe — Component Spec

> 冻结测试证伪力验证（gen4-plan P0-3，拍板 1「mutation = 对①②的 adequacy 验证」）。
> 8-08 交叉审查 8 条 E4 blocker 中 5 条归此机制（自写测试空心：tag 改名仍绿 / 方法改名仍绿 / 审计断言缺字段 / taint 逃逸 / 浅拷贝可篡改）。**catalog 驱动的确定性文本变异，零模型，语言无关**。

## 0. Type

- [x] 自建组件（imperative logic）
- 无 C 编号（C4 L3 工位；与 AC 冻结闸配对——闸拦增量弱化，探针验存量空心）

## 1. Purpose

`spec AC（权威）→ AC 测试（可执行投影）→ mutation attestation（投影证伪力证据）`——第三链。对被测代码注入已知缺陷（mutant），冻结的行为/守卫测试**必须变红**（killed）；仍绿（survived）= 测试是空心的。

## 2. Public API

### 2.1 Mutant catalog（`.specify/specs/<feature>/mutants.yaml`）

```yaml
schema_version: v0.1.0
feature_id: <LOCAL_ID>
default_test_cmd: <杀手测试 shell 命令>
mutants:
  - mutant_id: M-<slug>
    mutant_class: tag_rename | method_rename | assert_field_drop | taint_escape | shallow_copy | <自定义>
    target_file: <相对 repo_root>
    match: <字面串>            # 非正则; 必须恰好命中
    replacement: <字面串>      # != match
    occurrence: 1              # 第 N 处 (确定性)
    test_cmd: <可选覆盖>
    description: <模拟什么缺陷>
```

### 2.2 CLI

`suiyin-flow mutation run --catalog <p> --repo-root <p> --ref <ref> [--env KEY=VAL ...]`
→ ProbeReport JSON；exit 0 pass / 1 fail / 2 error。

### 2.3 ProbeReport（mutation attestation）

`{schema_version, feature_id, ref, verdict, results[], survived_count, killed_count}`；
result = `{mutant_id, mutant_class, target_file, outcome: killed|survived|apply_failed|error, test_exit_code, output_tail}`。

## 3. Invariants

- **I1（隔离）**：每个 mutant 在独立 **throwaway git worktree**（detached from ref，`.suiyin/mutation-wt/<rand>`）内注入，跑完 `worktree remove --force`；原 worktree/主树全程零接触（AC-3 byte-identical）。C4"只读"invariant 与 mutation 改代码的冲突解法（desk E4 现成模式）。
- **I2（fail-closed 三条，拍板 1）**：零适用 mutant（schema 拦空 catalog）/ match 失配（catalog stale → apply_failed）/ 目标缺失 / 命令起不来（error）——**一律 fail，不算 pass**。verdict=pass 当且仅当 ≥1 mutant 且全部 killed。
- **I3（确定性）**：字面替换 + occurrence 定位，无正则无随机；同 catalog + 同 ref → 同结果。
- **I4（运行时隔离靠注入）**：探针不管服务生命周期；lane 隔离（DB/端口）由 `--env` 注入杀手测试环境（例 lane mongo 的 `MONGO_URI`）。完整 lane 管理是 M3 门内条目。
- **I5（触发键，拍板 1 用户批）**：AC/守卫测试变更 ∪ mutant 目录变更 ∪ 被测包导出面变更——挂 P0-4 harness / C4 工位时接线；探针自身只管跑。
- **I6（零模型）**：全路径无模型调用。test_cmd 是用户 shell 命令 → shell=True（ADR-0005 例外，同 C7 reverify）。

## 5. Acceptance Criteria

tests/mutation/test_acceptance_criteria.py（真 git fixture，实心/空心双测试对照）：
AC-1 实心测试全杀 → pass / AC-2 空心测试放跑 → fail + 逐个点名（核心捕获目标）/ AC-3 原树 byte-identical + throwaway 清零 / AC-4(+4b) catalog stale·目标缺失 → apply_failed（失败型）/ AC-5 无效 catalog 三态拒收（失败型）/ AC-6 occurrence 第 N 处确定性 / AC-7 per-mutant cmd 覆盖 + env 注入 + 复合 `&&` / AC-8 CLI exit code 契约。

**gen4-plan 拍板验收（merge 后 dogfood）**：v4lab B 产物五处空心全部检出（五类 desk mutant catalog → 5 survived → 探针 fail 点名）。

## 6. Open Questions

- **QM-1**：reachable-slice 完整触发键的算法与成本（gen4-plan §五遗留，等真实数据）
- **QM-2**：mutant catalog 谁生成——M2 迁移时人工写 desk 五类；长期候选 = spec/AC 驱动半自动生成（等 M4 回放经验）
- **QM-3**：并行跑多 mutant（throwaway 互独立天然可并行）——等成本数据，先串行保简单

## 7. 关系

- 配对 [ac-freeze-gate.md](ac-freeze-gate.md)：闸拦"测试被动过"（增量），探针验"测试杀不杀得动"（存量）；触发键共享
- 挂点：P0-4 feature 收口 harness；attestation 作为 verify 证据链一环（P2 verify 证据分型时归 mutation 类）

---

**Version**: v0.1.1-draft
**Last Updated**: 2026-08-12
**Changelog**:
- v0.1.1 (2026-08-12): **MINOR — B 产物验收 dogfood 前逼出的两升级**。(1) `extra_edits` 协同多点替换：method_rename 类需接口声明+stub 同改保持编译通过，才能暴露"测试不冻结方法集"（E4 实测手法；单点改名只会编译红，信号错误）；任一点失配 → apply_failed。(2) **baseline 健全性跑（I2 补强）**：每个杀手命令先在未变异基线 throwaway 跑一次，红 → `baseline_ok=false` + verdict=fail + 不跑 mutant——否则坏环境（如 lane mongo 连不上）会把所有 mutant 误报 killed → 假 pass（E4 报告里 Mongo 拒连导致大量"无法判定"正是此病）。AC-9/AC-10。
- v0.1.0 (2026-08-12): 初稿 + impl + 10 AC。来源 gen4-plan §二拍板 1 + §三 P0-3；五类 mutant class 来源 8-08 E4 交叉审查。
