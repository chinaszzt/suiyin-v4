# Seam Manifest + Lint — Component Spec

> 接缝（seam）= 跨 task 的接口/数据形状/错误/依赖契约。**漏声明的依赖是唯一不以物理冲突显形的一类缺陷**
> （todo §P2.0.5 expense-tracker 双变体实验：变体 B 静默 all_merged + CI 全绿 + 端到端 KeyError；
> desk E4 病例 SEAM-EXIT-REASON：首版实现整个枚举缺失，下游编译探针全部 undefined）。
> seam manifest 把接缝显式化为机械可查的清单；seam lint 做完备性机械检查。
> 原料实证：gen4 clone `specs/002-topic-triage/seam-manifest.draft.yaml`（M2 产物，31 条）。

## 0. Type

- [x] 自建组件 (imperative logic — lint 需要写代码)
- [ ] 行为契约

**实现栈**: Python 3.11+（ADR-0002）。CLI 入口 `suiyin-flow seamlint run`，复用顶层 unified dispatcher。

## 1. Purpose

1. **schema**：`specs/<feature>/seam-manifest.yaml` 的正式格式（M2 draft 转正）
2. **lint**：机械检查接缝完备性——身份存在性（provider/consumer 是真 task）、依赖闭合
   （consumer 必须能沿 depends_on 传递闭包到达 provider——变体 B 那类"漏声明依赖"在 plan 阶段就拦）、
   test 挂钩状态
3. **下游消费**：C5 typed inputs `kind=seam_manifest`（v0.4.0 已接，close harness 自动收，
   正式版优先 draft 兜底）；sy-tasks/sy-plan 生成 tasks.yaml 时的接缝硬约束参照（todo §P2.0.5 #B）

## 2. Manifest Schema (v0.1.0)

```yaml
schema_version: v0.1.0          # 必填; lint 只认 v0.1.0 (draft-v0.1 明确拒收, 指引转正)
feature_id: 002-topic-triage    # 必填; LOCAL_ID_PATTERN
source_basis: "contracts/README.md v13"   # optional; 抽取来源说明
entries:                        # ≥1
  - seam_id: SEAM-EXIT-REASON   # ^SEAM-[A-Z0-9][A-Z0-9-]{0,62}$, 文件内唯一, 冻结后不重排
    kind: schema                # 闭集: interface | schema | error | dependency
    declaration: |              # 必填非空; 签名/字段/枚举**原文摘录** (不是转述)
      type ExitReason string
      const (...)
    provider_task: T001         # 恰好一个 owner (LOCAL_ID_PATTERN) —— 同 modifies 1:1 所有权;
                                # draft 里 "T001（...）+ T002（...）" 这类注记语义拆去 note
    consumer_tasks: [T004, T008]  # ≥1, LOCAL_ID_PATTERN, 不得含 provider_task
    source: "contracts/README.md:125-144"   # 必填; 文件[:行区间/章节]
    test_ref: "tests/contract/exit_test.go::TestExitReasonClosedSet"
                                # optional; 接缝的机械 integration test (todo §P2.0.5 #B);
                                # 显式待测试作者用哨兵值 "PENDING-TEST-AUTHOR"
    note: >-                    # optional; 判例引用 / 特殊约定 ("不得改签名" 等)
      E4 病例: reviews/T001-acceptance-20260806-0527.md
```

**设计裁定**：
- `provider_task` 单值（不是列表）——接缝声明与聚合文件同理，**恰好一个 owner**；
  "T002 实现但不得改签名"属于 consumer 侧约束，写 note
- `consumer_tasks` 复数命名（draft 的 `consumer_task` 是列表值单数名，转正时统一）
- `test_ref` 不进 required：red-first 未机械化（M1 缺口 1 → 独立测试作者 P1），
  但 lint 必须**点名统计** PENDING/缺失面，不许静默
- draft (`schema_version: draft-v0.1`) 一律拒收：draft 是 M2 原料，转正必须人过一遍
  provider 注记语义（防止机器猜错所有权）

## 3. Lint Behavior Contract

### 3.1 CLI

```
suiyin-flow seamlint run --manifest <seam-manifest.yaml> --tasks-yaml <tasks.yaml> [--report <out.json>]
```

`--tasks-yaml` 必填——身份与依赖检查是 lint 的主要价值，没有 tasks.yaml 的"纯格式检查"
不单独提供（防止"过了 lint"的假信号）。

### 3.2 检查层（全部跑完再汇总，不 fail-fast 到第一条）

| 层 | 检查 | 违反 → finding code |
|---|---|---|
| **L1 schema** | yaml 可解析 / schema_version=v0.1.0 / 必填字段齐 / kind 闭集 / seam_id pattern+唯一 / declaration 非空 / provider 单值合法 id / consumer_tasks ≥1 且不含 provider | `SEAM_SCHEMA_INVALID`（manifest 级，直接终态） / `SEAM_ENTRY_INVALID`（条目级） |
| **L2 identity** | feature_id == tasks.yaml feature（有则比）; provider_task / consumer_tasks 每个 id ∈ tasks[].task_id | `SEAM_TASK_UNKNOWN` |
| **L3 dependency** | 每个 consumer task 沿 `depends_on` 传递闭包**可达** provider_task（同 task 自足除外——L1 已禁）。不可达 = 漏声明依赖 | `SEAM_DEPENDENCY_MISSING` |
| **L4 test hook** | test_ref 缺失或 =PENDING-TEST-AUTHOR → 计数点名（**warning，不 fail**） | `SEAM_TEST_PENDING` |

### 3.3 Invariants

- **I1 fail-closed**：L1-L3 任一 finding → exit code 1；manifest 不可解析/版本不对 → exit code 2；
  只有 L4 warnings → exit 0。**零 entries 的 manifest 一律 fail**（空清单 ≠ 无接缝，是没做抽取）
- **I2 全量汇总**：一次跑完所有层所有条目，findings 逐条带 seam_id + 定位；不第一条就停
- **I3 确定性**：同输入同输出；不读网络/不起 session（纯静态检查）
- **I4 report**：`--report` 时落 JSON（schema_version / manifest_path / counts / findings[]）；
  stdout 人读摘要
- **I5**: lint 不改任何文件（只读）

### 3.4 Error Schema（进程级）

`SEAMLINT_MANIFEST_UNREADABLE` / `SEAMLINT_TASKS_UNREADABLE`（路径不存在/不可解析）→ exit 2 + stderr 单行 `ERROR <code>: <msg>`。

## 4. Acceptance Criteria

- **AC-1**: 合法 manifest + 全部依赖闭合 → exit 0，report counts 全 0（L4 除外）
- **AC-2**: `schema_version: draft-v0.1` → exit 2，报错信息含"draft 需转正"指引
- **AC-3**: seam_id 重复 / kind 越出闭集 / declaration 空 → `SEAM_ENTRY_INVALID` 逐条点名，exit 1
- **AC-4**: provider_task 不在 tasks.yaml → `SEAM_TASK_UNKNOWN`，exit 1
- **AC-5**: consumer 沿 depends_on 不可达 provider → `SEAM_DEPENDENCY_MISSING`（expense-tracker 变体 B 回归靶：两个并行 task 无 depends_on 边 + 一条 seam → 必检出）
- **AC-6**: 传递可达（A→B→C，seam provider=C consumer=A）→ 不误报
- **AC-7**: consumer_tasks 含 provider_task → `SEAM_ENTRY_INVALID`
- **AC-8**: test_ref=PENDING-TEST-AUTHOR ×N → exit 0 但 stdout/report 点名 N 条 `SEAM_TEST_PENDING`
- **AC-9**: entries 为空 → fail（I1）
- **AC-10**: findings 汇总不 fail-fast：一个 manifest 同时含 AC-3/4/5 三类问题 → 一次跑出全部三类

## 5. Open Questions

- **QS-1**: 反向完备性（contracts/*.md 里有接缝但 manifest 没收）无法纯机械判——候选：C5 review
  checklist 承接（typed inputs 已把 contract 和 seam_manifest 都送进输入面，reviewer 可对照）；
  或 M4 回放时用 E4 病例集验证覆盖率。暂记 C5 承接，不做机械化
- **QS-2**: seam lint 挂进 close harness 作为独立步序（acgate 之后）还是留 plan 阶段手跑？
  倾向 M3 门自检时定（等 authorization manifest 件 3 一起看步序）

## 6. Implementation Notes

- 模块 `src/suiyin_flow/seamlint/{__init__,schema,lint,cli}.py`；pydantic schema 同 acgate 风格
- 身份校验复用 `suiyin_flow.identity.LOCAL_ID_PATTERN`；tasks.yaml 解析复用
  `c2_executor.batch` 的 manifest loader（勿重造）
- depends_on 传递闭包：tasks.yaml 已强校验 depends_on 指向更早 task（无环），直接 DFS/BFS 即可
- 跨平台 NC-5：pathlib / encoding='utf-8'；CI 3-OS
- unified CLI：`cli.py` 加 `seamlint` 路由

---

**Version**: v0.1.0-draft
**Last Updated**: 2026-08-13
**Status**: draft — M3 件 2（gen4-plan §四 M3 门）；schema 拍板 + lint 待实现（codex 外包）

**Changelog**:
- v0.1.0 (2026-08-13): 初稿。schema = M2 draft 转正（provider 单 owner / consumer_tasks 复数 / test_ref+PENDING 哨兵 / draft 拒收）；lint 四层（schema/identity/dependency/test-hook），L3 依赖闭合 = expense-tracker 变体 B + E4 SEAM-EXIT-REASON 两案的机械化承接。
