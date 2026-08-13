# Independent Test Author — Component Spec

> gen4-plan 拍板 10 独立性开支阶梯第一级：**独立测试作者（便宜，常开）**。
> 候选实现已拍板：**测试先行顺序双会话，执行闸复用 AC 冻结机制**。
> 与 mutation 探针配对：**探针验存量（已写的测试是否空心），独立作者管增量（新测试由谁写）**。
> M4 回放三路证据背书其优先级：E4#6 残差（状态机正反例）、E5#1 残差（接口面闭集测试）、
> 002 的 28 条 seam 护栏全 PENDING（seamlint L4 点名）。人类对照物：TDD + pair programming。

## 0. Type

- [x] 自建组件 (imperative logic)

**实现栈**: Python 3.11+。CLI `suiyin-flow testauthor run`，unified dispatcher。

## 1. Purpose

在 implementer session 之前，用**独立 fresh session** 从契约资产（spec/AC/seam/contract）写测试：

1. **独立性**：测试作者不知道实现会怎么写，只看声明——防"照实现写测试"的自证循环
   （E4 五条空心测试的结构性根因）
2. **红先行**：作者写完的测试在 base 上必须**非绿**（红/编译失败都算——Go 里引用未实现符号
   编译即失败，这就是 Go 的 red）；base 上就绿的"新测试"是空心嫌疑，fail-closed
3. **冻结交接**：作者产物经 acgate freeze 钉 test_hash → implementer 双会话开工；
   implementer 改/删/skip 冻结测试 → AC 冻结闸既有机制拦截（delete/rename/skip fail-closed，
   P0-2 已建，**本组件零新增执行闸**）

## 2. Public API

### 2.1 Input（CLI 参数即 schema）

```
suiyin-flow testauthor run
  --tasks-yaml <p>            # 必填; task 定位与 modifies 语境
  --task-id <id>              # 必填; 为哪个 task 写测试
  --repo-root <p>             # 必填
  --targets <p>               # 必填; 测试靶单 yaml (见 §2.2) —— 写什么测试的唯一指令源
  --test-paths <glob> [...]   # 必填 ≥1; 作者只许写这些路径 (机械圈地, authz 式 path 判定)
  --inputs-manifest <p>       # 可选; C5 v0.4.0 同款 typed inputs (contract/seam/ac_map 进输入面)
  --base-ref <ref>            # 默认 tasks.yaml base_branch; 红检基准
  --red-cmd <cmd>             # 可选; 红检命令, 缺省用 task.verify_cmd
  [--timeout <s>] [--report <out.json>]
```

### 2.2 测试靶单（targets yaml）

```yaml
schema_version: v0.1.0
task_id: T001
targets:                          # ≥1; 每条 = 一个要写的测试
  - target_id: GUARD-CLOCKX-FACE  # 唯一; 建议沿用 ac-map 的 AC-N/GUARD-N 或 seam_id
    kind: ac | guard | seam       # ac=spec AC; guard=契约判据; seam=接缝护栏
    source: "seam-manifest.yaml SEAM-CLOCKX"   # 声明出处
    directive: >-                 # 给作者 session 的判真伪指令 (可执行/可观测, 不许"测得好")
      Clock 接口面闭集 {Clock, System(), NewFake(t), Advance}: 反射/编译断言 FakeClock
      不暴露闭集外导出方法 (E5#1 Fake.Set 病例)
    suggested_test_ref: "internal/clockx/face_test.go::TestClockFaceClosedSet"  # 可选建议名
```

### 2.3 Output — testauthor_report.json

```yaml
schema_version: v0.1.0
task_id / session_id / target_tree_sha    # 身份 + 新鲜度 (treesha, M3 件 4 同款)
targets: [{target_id, status: authored|skipped, test_refs: [...], note}]
path_check: {touched: [...], violations: []}   # 圈地判定 (violations 非空 = fail)
red_check: {cmd, exit_code, red: bool}         # base 上跑 red-cmd 的结果
frozen: {manifest_path, entries: N}            # acgate freeze 产物
verdict: pass | fail
```

## 3. Behavior Contract

### 3.1 确定性步序

```
resolve targets → author session (fresh, typed inputs) → path 圈地检查 →
red 检 (base worktree 跑 red-cmd) → acgate freeze (targets → ac-manifest entries) → report
```

### 3.2 Invariants

- **I1 独立性**：author session fresh context；输入面 = typed inputs（contract/seam/ac_map 等
  声明类）+ 靶单 directive；**禁止读实现代码之外还禁止读 implementer 任何工件**
  （`.suiyin/sessions/*` 同 C5 I1）。作者可以读 base 上已有代码（写得出能编译的测试需要
  import 面），但 directive 必须来自声明不来自实现行为
- **I2 圈地 fail-closed**：session 产物 diff 触碰 `--test-paths` 之外任何路径 → verdict=fail
  （复用 authz 的 diff 路径判定形态；测试作者没有实现写权——它写实现 = 自证循环回归）
- **I3 红先行 fail-closed**：红检在 **base（不含作者产物之外的实现）** 上跑 red-cmd：
  exit 0（全绿）→ verdict=fail（base 就绿 = 测的是已有行为，不是增量判据）；
  非 0（测试红/编译失败）→ red=true 通过。红检跑在 throwaway worktree（mutation 同款，
  原树 byte-identical）
- **I4 冻结交接**：red 通过后逐 target 生成 ac-manifest entries（ac_id=target_id /
  test_ref / test_hash / spec_hash=声明源 hash / baseline_ref）并 `acgate freeze`；
  freeze 失败 → verdict=fail
- **I5 逐靶记账**：每个 target 状态显式（authored/skipped+原因）；skipped 不静默——
  report 点名（红检通不过的 target 不得标 authored）
- **I6 零实现耦合**：本组件不调 C2、不管 implementer 双会话的第二段——顺序双会话的
  编排归 C7/close 流程（先跑 testauthor 后跑 task 是调用方纪律，M5 shadow 实证后再定
  是否机械强制）

### 3.3 Error Schema

`TESTAUTHOR_TARGETS_INVALID`（靶单不可解析/空）/ `TESTAUTHOR_SESSION_CRASHED` /
`TESTAUTHOR_TIMEOUT` / `TESTAUTHOR_TASK_UNKNOWN` / `TESTAUTHOR_BASE_UNAVAILABLE`
（base-ref 解析不了/worktree 建不出）。风格同 C5 ReviewerError。

## 4. Author Session Prompt 要点

- 角色：独立测试作者。**只看声明写判真伪测试；严禁按现有实现的行为反推断言**
- 输入：typed inputs（权威序同 C5 v0.4.0）+ 靶单（每条 directive 是唯一写测指令）
- 约束：只写 `--test-paths` 内文件；每 target ≥1 个具名测试函数；测试必须**在实现缺位时非绿**
  （编译失败合法）；输出最后一行 JSON：`{target_id: [test_refs]}` 映射
- 禁止：改实现文件、改契约资产、写 skip/短路

## 5. Acceptance Criteria

- **AC-1**: 合法靶单 + mock session 产出测试文件 → path 圈地过 + 红检红 + freeze 成功 → verdict=pass，report 逐 target authored
- **AC-2**: session 产物触碰 test-paths 外文件 → verdict=fail（I2），report.path_check.violations 点名
- **AC-3**: 红检在 base 上全绿 → verdict=fail（I3 空心嫌疑）
- **AC-4**: 红检非 0（编译失败形态）→ red=true 正常通过
- **AC-5**: freeze 后 ac-manifest 含全部 authored targets 的 entries（test_hash 已钉）；
  后续对冻结测试删/改名/skip → 既有 acgate run 检出（回归引用 P0-2 AC，不重测）
- **AC-6**: 靶单空/不可解析 → TESTAUTHOR_TARGETS_INVALID，session 不启动
- **AC-7**: 部分 target 未产出 → 该 target=skipped + 原因，verdict 仍可 pass（authored ≥1 且
  无 I2/I3 违反），report 点名 skipped 数（不静默）
- **AC-8**: report 带 target_tree_sha（base 的 tree sha）
- **AC-9**: 红检跑在 throwaway worktree，原树 byte-identical（mutation AC-3 同款断言）
- **AC-10**: typed inputs required 缺失/hash 漂移 → fail-closed 不启动（复用 C5 inputs 语义）

## 6. Open Questions

- **QT-1**: 顺序双会话的机械强制（task 开工前必须存在该 task 的 pass 报告？）——M5 shadow
  实证一轮再定（先当调用方纪律，避免又造前置门摩擦推动绕行）
- **QT-2**: 靶单生成的自动化（从 ac-map「待独立测试作者」行 + seamlint L4 PENDING 自动生成
  targets yaml）——机械可做，M5 用量起来后加 `testauthor targets-from` 子命令
- **QT-3**: 红检对"改既有行为"类 target 的语义（base 上旧行为绿、新判据红需要测试能表达差异）
  ——首轮只覆盖增量型（M4 证据的三类都是增量型），修改型留 feature-repair 场景一起设计

## 7. Implementation Notes

- 模块 `src/suiyin_flow/testauthor/{__init__,schema,runner,cli}.py`
- session 调用复用 C2 §7 模式（同 C5 session.py 的包装形态，costlog 同款接线）；
  typed inputs 复用 `c5_reviewer.inputs`（synthesize 不含 verify_report；核心件只 constitution
  ——spec/plan 由靶单 source 与 inputs-manifest 显式给，测试作者不默认读 plan：plan 是实现
  策略，读它会向实现视角倾斜。**裁定：默认输入 = constitution + inputs-manifest；spec 想进
  输入面就在 manifest 里声明 kind=spec**）
- throwaway worktree 复用 `mutation.runner` 的建树/清理 helper（勿重造）；diff 路径判定
  复用 `authz.gate.diff_touched_paths`
- freeze 复用 `acgate.freeze_manifest` API；tree sha 复用 `treesha.resolve_tree_sha`
- 跨平台 NC-5 全套

---

**Version**: v0.1.0-draft
**Last Updated**: 2026-08-13
**Status**: draft — M5 前置 1（拍板 10 第一级）；实现 codex 外包

**Changelog**:
- v0.1.0 (2026-08-13): 初稿。测试先行顺序双会话的作者半边：typed inputs + 靶单 directive → fresh session 写测 → 圈地（authz 式）→ 红检（throwaway worktree, base 非绿才过）→ acgate freeze 交接。执行闸零新增（复用 P0-2 冻结闸）。M4 三路证据（E4#6/E5#1 残差 + 28 seam PENDING）驱动。
