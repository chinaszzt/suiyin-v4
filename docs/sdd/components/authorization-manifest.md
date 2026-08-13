# Authorization Manifest + 机械闸 — Component Spec

> gen4-plan 拍板 9（P1.6 重写）：`plan/constitution → typed authorization manifest →
> 机械 path/command/network/DB 闸 → 极少语义残余`。承接 desk `WF-LEDGER-ROLEGATE`
> （role-gate hook + CONTRACT_GRANTED 例外表）与 E5 义务 OBL-1（未授权 DB 写）/
> OBL-2（绕统一发送出口）。
> **验收判据**（migration-matrix WF-LEDGER-ROLEGATE 行）：机械可判路径模型调用数为零；
> manifest 缺失/失效/解析失败 fail-closed；**不存在需要持续扩张的通配例外表**
> （CONTRACT_GRANTED 野蛮生长教训，process-evolution §十一之补）。

## 0. Type

- [x] 自建组件 (imperative logic)
- [ ] 行为契约

**实现栈**: Python 3.11+。CLI `suiyin-flow authz check`，unified dispatcher。

## 1. Purpose

feature 的**写权声明**显式化为 typed manifest（plan 阶段人批 plan 时一并批写权），
机械闸在收口/执行侧对照 diff 判越权。四个维度：**path（写文件面）/ command（可跑命令）/
db（可写 db.collection）/ network（可及出口）**。

## 2. Manifest Schema (v0.1.0) — `specs/<feature>/authorization.yaml`

```yaml
schema_version: v0.1.0
feature_id: 002-topic-triage        # LOCAL_ID_PATTERN
denies:                             # feature 级禁区 (优先级最高, 覆盖一切 grant)
  paths: [".specify/memory/**", "docs/legacy/**"]   # glob; 命中即 block
grants:                             # per-task; task 无 grant 条目 → 默认最小权 (见 I2)
  - task_id: T001                   # LOCAL_ID_PATTERN; 文件内唯一
    write_paths: []                 # 追加于 tasks.yaml modifies 之外的 path 写权 (glob);
                                    # 通常留空 —— modifies 是 path 写权的主声明 (单一真相),
                                    # 这里只放 modifies 表达不了的例外 (如生成物目录)
    run_commands:                   # 精确字符串白名单 (不是前缀/正则 —— 通配禁令);
      - "go test ./internal/topic/..."   # task 的 verify_cmd 自动授予, 不必列
    db_writes: ["suiyin_desk.topics"]    # "db.collection" 字面量; 禁 "*" / 前缀;
                                         # 空 = 禁一切 DB 写 (deny by default)
    network: []                     # 出口 host 字面量; 空 = 禁出口 (E5-OBL-2: 发送必须走统一出口
                                    # → 出口封装层的 host 才会出现在这里)
```

**设计裁定**：
- **path 写权的单一真相是 tasks.yaml `modifies`**——authz 不重复声明，只放例外追加
  （双声明 = 漂移温床）。机械闸的有效 path 面 = `modifies ∪ write_paths − denies`
- **通配禁令（schema 级强制）**：`db_writes` / `network` / `run_commands` 里出现 `*` 或空串
  → schema 校验失败（fail-closed）。例外表只能逐条加、每条可审计——这就是对
  CONTRACT_GRANTED 教训的结构性回答：不是"管住例外表"，是**让通配在 schema 上不可表达**
- **deny 优先**：denies.paths 命中即 block，不看任何 grant
- task 无 grant 条目 = 合法且最小权（modifies + verify_cmd + 禁 DB + 禁网）——
  防止"每加一个 task 就要动 authz"的摩擦推动通配化

## 3. 机械闸 Behavior Contract

### 3.1 CLI

```
suiyin-flow authz check --manifest <authorization.yaml> --tasks-yaml <tasks.yaml> \
  --diff <pr_diff.patch> --task-id <id> [--report <out.json>]
```

`--task-id` 定位 grant；diff = 该 task（或 feature 收口时整 feature）的产出。

### 3.2 检查维度（M3 落地面 vs 声明面）

| 维度 | M3 机械闸 | 判法 |
|---|---|---|
| **path** | ✅ 落地 | diff 触碰的文件路径（`+++ b/<path>` 全集）逐一判：命中 denies → `AUTHZ_PATH_DENIED`；不在 `modifies ∪ write_paths` → `AUTHZ_PATH_UNGRANTED`。git diff 路径是精确 ground truth，零误报面 |
| **command** | ✅ 落地（收口侧） | close harness / C2 将要执行的 verify_cmd 若非 task.verify_cmd 且不在 run_commands → `AUTHZ_COMMAND_UNGRANTED` |
| **db** | 声明 + C5 | db_writes 声明进 C5 typed inputs（授权声明随 seam/contract 进输入面）；**文本级 diff 判 DB 写的机械化并入件 8 安全闸误报校准**（73 FP 教训：文本粗判先不上闸，防止假信号） |
| **network** | 声明 + C5 | 同上；出口越界（E5-OBL-2）M3 阶段由 C5 按声明审，机械化随件 8 |

> 分期理由：path/command 判定有精确 ground truth（git diff 路径 / 命令字符串等值），
> 可直接 fail-closed 上闸；db/network 是文本级推断，直接上闸会复刻 27017 规则 73 处误报
> ——先做声明面（让 C5 有尺子），精判随件 8 校准落地。**本表即 M1 校准债的处置声明载体之一。**

### 3.3 Invariants

- **I1 fail-closed**：manifest 缺失（调用方要求时）/ 不可解析 / schema 校验失败 / feature_id
  与 tasks.yaml 不一致 → 终态 error（exit 2），不降级放行
- **I2 默认最小权**：task 无 grant 条目 → 有效权 = modifies + verify_cmd + 禁 DB + 禁网
- **I3 deny 优先**：denies 命中即 block，任何 grant 不可覆盖
- **I4 零模型调用**：check 全程纯静态（glob 匹配 + 字符串等值），不起 session、不联网
- **I5 通配不可表达**：schema 拒收 `*` / 空串 / 前缀式条目（db/network/command 三维；
  path 维 glob 合法但 denies 优先兜底）
- **I6 全量汇总**：findings 逐条带维度 + 定位，不 fail-fast
- **I7 只读**：不改任何文件（--report 除外）

### 3.4 接入点

1. **close harness**：`authz` 步序插在 `acgate` 之后 `mutation` 之前；
   `specs/<feature>/authorization.yaml` 缺失 → 步 fail（feature 收口必须有写权声明；
   与 seam lint 的步序问题一并在 M3 门自检定，QS-2 同源）
2. **C5 typed inputs**：kind 新增 `authorization`（authority=design 档）——授权声明进输入面，
   C5 审 db/network 越界有据可查
3. **C2 per-task**（后续）：manifest 存在时 `_finalize_success` 前跑 path 维（与 safety 闸同点）

## 4. Acceptance Criteria

- **AC-1**: diff 只触碰 modifies 内路径 + 无 denies 命中 → exit 0
- **AC-2**: diff 触碰 denies 路径 → `AUTHZ_PATH_DENIED`, exit 1（即使该路径同时在 modifies）
- **AC-3**: diff 触碰 modifies ∪ write_paths 之外路径 → `AUTHZ_PATH_UNGRANTED`, exit 1
- **AC-4**: 待执行命令 ≠ verify_cmd 且 ∉ run_commands → `AUTHZ_COMMAND_UNGRANTED`
- **AC-5**: db_writes 含 `*` / 空串 / `db.` 前缀式 → schema 校验失败, exit 2（I5 通配禁令）
- **AC-6**: manifest 不可解析 / feature_id 错配 → exit 2 fail-closed（I1）
- **AC-7**: task 无 grant 条目 → 按 I2 最小权判（modifies 内 pass / DB 声明面为空）
- **AC-8**: 同 diff 多类违规 → 一次全量报出（I6）
- **AC-9**: write_paths 例外追加生效（modifies 外但 write_paths 内 → pass）
- **AC-10**: report JSON 含 per-维度 counts + findings[]，schema 稳定

## 5. Open Questions

- **QA-1**: C2 per-task 接入（3.4 第 3 点）是 M3 内做还是 M4 回放后按需——倾向 M4 后
  （close harness 已兜住收口面，per-task 上闸多一次进程调用，先看回放证据）
- **QA-2**: db/network 精判机械化的判法（AST/静态分析 vs 文本规则 vs verify_cmd 指向法
  ——desk 旧机制是"测试命令指向"级精准判定）→ 件 8 校准时定

## 6. Implementation Notes

- 模块 `src/suiyin_flow/authz/{__init__,schema,gate,cli}.py`；风格同 acgate/seamlint
- diff 路径提取：复用/对齐 `c2_executor/safety.py` 的 `+++ b/` 解析（勿重造第二套 diff 解析器
  ——若 safety 里的解析不便复用，抽公共 helper）
- glob 匹配：`fnmatch` / `pathlib.PurePosixPath.match`；diff 路径统一 POSIX 分隔符（NC-5）
- tasks.yaml 读取复用 `c2_executor.batch.load_tasks_yaml`
- C5 InputKind 加 `authorization`（authority=design）——随本件实现一并 cascade C5 spec PATCH

---

**Version**: v0.1.0-draft
**Last Updated**: 2026-08-13
**Status**: draft — M3 件 3（gen4-plan 拍板 9）；schema 拍板 + 闸待实现（codex 外包）

**Changelog**:
- v0.1.0 (2026-08-13): 初稿。四维写权（path 精判上闸 / command 等值上闸 / db+network 声明面先行、精判并入件 8）；通配 schema 级不可表达（CONTRACT_GRANTED 教训的结构性回答）；path 单一真相 = tasks.yaml modifies，authz 只放例外追加；默认最小权。
