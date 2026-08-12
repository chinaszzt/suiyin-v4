# AC Freeze Gate — Component Spec

> 行为/守卫测试的冻结闸（gen4-plan P0-2，拍板 1 测试分类的执行面）。**纯机械 diff 拦截，零模型**。
> 8-08 交叉审查实证的头号缺陷类：自写测试空心（tag 改名仍绿 / 断言缺字段）——mutation 探针（P0-3）验存量空心，本闸拦**增量弱化**。

## 0. Type

- [x] 自建组件（imperative logic）
- 无 C 编号（挂 C4 verify 域工位；P0-4 收口 harness 串接）

## 1. Purpose

spec 是唯一真相，测试是投影（拍板 1）。三类测试中①行为测试（spec AC 衍生）与②seam/guard 测试（plan/宪法衍生）**冻结**：spec 未变时对它们的删除 / 改名 / skip / 弱化一律阻断；③实现测试是脚手架，不进 manifest，闸不管。

## 2. Public API

### 2.1 AC manifest（盘上工件，`.specify/specs/<feature>/ac-manifest.yaml`）

```yaml
schema_version: v0.1.0
feature_id: <LOCAL_ID>          # canonical key 上半 (P0-1)
entries:
  - ac_id: AC-1 | GUARD-1       # ^(AC|GUARD)-[A-Za-z0-9._-]+$
    kind: behavior | guard
    spec_ref: <权威来源文件>     # behavior→spec.md, guard→plan/宪法
    spec_hash: <sha256>          # 冻结时基准 (CRLF→LF 归一化后取 hash, NC-5)
    test_ref: <测试文件路径>
    test_hash: <sha256>
    test_names: [test_AC_1_x]    # 可选; 空 = 整文件粒度
    baseline_ref: <commit/branch>
```

entries 骨架由人/AI 写，`acgate freeze` 钉 hash——冻结动作走 PR 受 C5/人审。

### 2.2 CLI

- `suiyin-flow acgate run --manifest <p> --repo-root <p> --base <ref> --head <ref>` → GateReport JSON；exit 0 pass / 1 block / 2 error
- `suiyin-flow acgate freeze --manifest <p> --repo-root <p> --ref <ref>` → 按 ref 刷新 spec_hash/test_hash/baseline_ref 写回

### 2.3 GateReport

`{schema_version, feature_id, verdict: pass|block, base_ref, head_ref, findings[]}`；
finding = `{kind, file, ac_ids[], detail, channel, blocking}`。

## 3. 判定语义（invariants）

- **I1（机械闭集）**：冻结测试文件的四类变更可机械归类——`TEST_FILE_DELETED`（删/整文件改名，git R 状态旧路径按删除）/ `TEST_DELETED`（def test 行删除且无同名新增 = 删除或改名）/ `TEST_SKIPPED`（新增 `@pytest.mark.skip` / `pytest.skip(` / `@unittest.skip`）/ 其余含删除行的变更 → `TEST_WEAKENED_UNKNOWN`。
- **I2（fail-closed）**：UNKNOWN **同样不放行**——机械闭集之外的"弱化"不猜语义，宁可误拦交人。纯新增（无删除行）= 加强，放行。
- **I3（三条合法通道，机械特征识别）**：
  - `spec_changed`：该 AC 的权威来源（spec_ref）同 diff 变更 → 放行（Type B 补 spec+AC / Type C 改 spec+ADR；B/C 区分与 ADR 是否齐由 C5/人管，闸只认"权威动了"）
  - `projection_fix`：spec 未变，diff 新增/修改 `**/projection-fixes/<ac_id>*` 证据文件（新旧 oracle 记录）→ 放行
  - 通道放行的 finding 保留在 report（blocking=false）作 audit trail
- **I4（manifest 基准一致性）**：manifest 记录的 hash 必须与 base 侧实际文件一致（归一化后比），不符 → `MANIFEST_STALE` **恒 blocking**（spec_changed 不豁免——基准坏了先重新 freeze，否则全部判定不可信）。
- **I5（hash 规约）**：sha256 over CRLF→LF 归一化字节（PR #64 Windows autocrlf 教训）。
- **I6（零模型）**：整条判定路径无模型调用。

## 5. Acceptance Criteria

tests/acgate/test_acceptance_criteria.py（真 git fixture，13 AC）：
AC-1 冻结完好 pass / AC-2 删文件 block / AC-3 改名 def block / AC-4 skip block / AC-5 删断言 → UNKNOWN block（失败型核心）/ AC-6 纯新增 pass / AC-7 spec_changed 通道放行 / AC-8 projection_fix 通道放行 / AC-9 stale manifest 恒 block / AC-10(+10b) freeze 刷新 + 失败型 / AC-11 CLI exit code 契约 / AC-12 git rename 拦。

## 6. Open Questions

- **QA-1**：manifest 缺失时挂点行为——P0-4 harness 串接时定（M3 门内强制 vs 迁移期跳过 + 警告）
- **QA-2**："弱化"机械闭集的扩展（断言参数改动的 AST 级判定）——等 M4 回放误报/漏报数据
- **QA-3**：test_names 粒度下同文件非冻结函数的删除行是否豁免 UNKNOWN——初版从严（整文件），等误拦实例

## 7. 关系

- 上游：`/sy-tasks` 后由人/AI 建 manifest 骨架 + freeze（M2 迁移时 desk FR/GWT → AC-N 批量建）
- 挂点：P0-4 feature 收口 harness（feature HEAD 全量判定）；task 级挂 C4 工位留 QA-1
- 配对：P0-3 mutation 探针验"测试杀不杀得动 mutant"（存量空心），本闸拦"测试被动过"（增量弱化）；触发键共享（AC/守卫测试变更）

---

**Version**: v0.1.0-draft
**Last Updated**: 2026-08-12
**Changelog**:
- v0.1.0 (2026-08-12): 初稿 + impl + 13 AC。来源 gen4-plan §二拍板 1（三类测试 + 三通道）+ §三 P0-2。
