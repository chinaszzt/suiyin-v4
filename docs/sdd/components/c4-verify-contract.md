# C4 Verify Contract — Component Spec

> 行为契约。定义 PR / working state 必须通过的 5 层 check。**本文档只定 contract，不规定实现**。落地走实现谱系（本地 lefthook / 通用 CI / SaaS）选其一。P0 MVP 只覆盖 **L1 (Static) + L2 (Tests)**，L3/L4/L5 在 P3。

## 0. Type

- [ ] 自建组件
- [x] 行为契约（declarative contract — 配置 + 编排）

**实现谱系优先级**（见 toolchain.md §0.5）：

| 选项 | v4 立场 | 备注 |
|---|---|---|
| (a) **本地 lefthook**（git hook 触发 lint + tests） | ✅ **v4 唯一首选** | NC-1 零 SaaS 兼容；最轻；P0/P1/P2 都用这个 |
| (b) 通用 CI（GitLab / CircleCI / Jenkins） | 业务项目自决 | v4 不提供配置；业务项目自带 CI 可叠加 |
| (c) GitHub Actions | 业务项目自决（且违反 NC-1 默认走 (a)） | v4 不提供配置 |
| (d) 混合（本地 + CI） | 业务项目自决 | (a) 之外的部分由业务项目自己加 |

**实际落地**：v4 工具链锁 (a) —— 本地 lefthook + 各语言 toolchain（pytest / flutter test / eslint / dart analyze）。verify_report.json schema 跨谱系保持一致（I5），业务项目若自加 CI 也产出同 schema 即可。

## 1. Purpose

为任意 PR / working state 产出一份**结构化 verify_report**，作为 C5 AI Reviewer 和 C6 Gate Contract 的可消费输入。

## 2. Public API

### 2.1 Input Schema

```yaml
type: object
required: [target, spec_ref, ac_list, levels, repo_root]
properties:
  target:
    type: object
    oneOf:
      - description: 跑在 worktree 内的 working state
        required: [kind, worktree_path]
        properties:
          kind: { const: worktree }
          worktree_path: { type: string, description: '绝对路径' }
      - description: 跑在 PR diff 上
        required: [kind, pr_ref]
        properties:
          kind: { const: pr }
          pr_ref: { type: string, description: 'PR URL 或本地分支名' }
  task_id:
    type: string
    pattern: '^T-\d{3,}$'
    description: |
      optional —— C2 闭环调用时透传（C2 知道是哪个 task）；
      独立跑 C4（CI / 人手动）时可空。
      存在则回写 verify_report.json，让 C5 / 人能回链 task。
  spec_ref:
    type: string
    description: spec.md 路径（L3 检查时用），相对 repo_root 或绝对路径
  ac_list:
    type: array
    items: { type: string, pattern: '^AC-\d+$' }
    description: 本次 verify 期望覆盖的 AC 集合
  levels:
    type: array
    items:
      enum: [L1, L2, L3, L4, L5]
    default: [L1, L2]
    description: 'P0 MVP 只支持 L1/L2；L3-L5 在 P3+'
  repo_root:
    type: string
    description: 绝对路径
  toolchain_hints:
    type: object
    description: 业务项目语言/工具提示，缺省时 contract 自动探测
    properties:
      languages:
        type: array
        items: { enum: [python, dart, typescript, javascript, go, rust] }
      test_runner: { type: string }
      lint_runner: { type: string }
```

### 2.2 Output Schema — `verify_report.json`

```yaml
type: object
required: [target, overall_verdict, levels, generated_at, contract_version]
properties:
  target: { type: object, description: '同 §2.1 target' }
  task_id:
    type: string
    pattern: '^T-\d{3,}$'
    description: optional；input.task_id 透传，让 C5 / 人能回链 task
  overall_verdict:
    enum: [pass, fail, warn_only]
  generated_at: { type: string, format: date-time }
  contract_version: { type: string, pattern: '^v\d+\.\d+\.\d+$' }
  levels:
    type: object
    properties:
      L1:
        type: object
        properties:
          status: { enum: [pass, fail, skipped] }
          checks:
            type: array
            items:
              type: object
              properties:
                name: { type: string, description: 'lint / format / typecheck / ...' }
                tool: { type: string, description: 'eslint / dart analyze / mypy / ...' }
                exit_code: { type: integer }
                stdout_tail: { type: string, maxLength: 4000 }
                duration_seconds: { type: number }
      L2:
        type: object
        properties:
          status: { enum: [pass, fail, skipped] }
          test_results:
            type: array
            items:
              type: object
              properties:
                test_name: { type: string }
                ac_prefix:
                  type: string
                  pattern: '^AC-\d+$'
                  description: '解析自 test_name，无 prefix 时为空字符串'
                status: { enum: [passed, failed, skipped] }
                duration_seconds: { type: number }
                failure_message: { type: string }
          summary:
            type: object
            properties:
              total: { type: integer }
              passed: { type: integer }
              failed: { type: integer }
              skipped: { type: integer }
      L3:
        type: object
        description: 'P0 阶段 status=skipped；P3 落地'
        properties:
          status: { enum: [pass, fail, skipped] }
          ac_coverage:
            type: array
            items:
              type: object
              properties:
                ac: { type: string, pattern: '^AC-\d+$' }
                covering_tests: { type: array, items: { type: string } }
                status: { enum: [covered, missing, multi_ac_violation] }
      L4:
        type: object
        description: 'P0 skipped；P3 落地（AI 跑 constitution check）'
      L5:
        type: object
        description: 'P0 skipped；coverage delta，warn-only'
  ac_summary:
    type: object
    description: 'P0 即可填（基于 L2 解析），帮助 C5/C6 早期决策'
    properties:
      requested: { type: array, items: { type: string } }
      covered: { type: array, items: { type: string } }
      missing: { type: array, items: { type: string } }
      multi_ac_violations:
        type: array
        items:
          type: object
          properties:
            test_name: { type: string }
            ac_prefixes_found: { type: array, items: { type: string } }
```

### 2.3 Error Schema

```yaml
type: object
required: [code, message]
properties:
  code:
    enum:
      - TOOLCHAIN_NOT_FOUND        # 没探测到 test_runner / lint_runner
      - WORKTREE_NOT_FOUND         # target.worktree_path 不存在
      - SPEC_PARSE_FAILED          # spec.md 找不到 §5 AC 段
      - LEVEL_NOT_IMPLEMENTED      # 请求 L3/L4 但当前阶段不支持
      - LEFTHOOK_CONFIG_MISSING    # 选 (a) 实现谱系但 lefthook.yml 不存在
      - REPORT_WRITE_FAILED        # verify_report.json 落盘失败
  message: { type: string }
  details: { type: object }
```

## 3. Behavior Contract

### 3.1 Invariants

- **I1**: `overall_verdict=pass` ⇔ 所有 **请求且实现** 的 level 都 `status=pass`（L5 例外：warn-only 不阻断）
- **I2**: **AC ↔ test 命名约定**（Fork G）—— test 名 prefix 必须严格匹配 `AC-\d+:?\s?` 或 Python `test_AC_\d+_`。**1 个 test 名只能 prefix 1 个 AC-N**（出现 ≥2 个 AC-N prefix → `multi_ac_violation`，L3 fail）。1 个 AC 可被多个 test 覆盖（OK）。
- **I3**: `ac_summary` 即使在 P0 不跑 L3 时也要填（基于 L2 test name 解析），让 C5/C6 提前感知"AC 没 test 覆盖"
- **I4**: `verify_report.json` schema 版本号写在 `contract_version`，schema breaking change → MAJOR bump
- **I5**: contract 不规定**怎么跑**，只规定**报告什么**。同一份 report schema 在 lefthook / CI / SaaS 谱系下保持一致
- **I6**: P0 阶段 `levels: [L3, L4, L5]` 显式请求时返回 `LEVEL_NOT_IMPLEMENTED` 而非静默 skip（避免误以为 pass）
- **I7**: AC 重命名 protocol —— 改 AC 编号必须 `grep -rn 'AC-X' .` 全 repo 替换，C4 L3（P3+）兜底检查"spec AC 集合 = test prefix 集合"完全 match

### 3.2 Side Effects

- 写 `verify_report.json` 到约定路径（默认 worktree 内 `.suiyin/verify/<timestamp>.json` + 一份 `latest.json` 软链）
- 跑业务项目工具链（pytest / flutter test / eslint / ...）—— 可能改 `.coverage` / `.pytest_cache` 等
- **不**修改源码、不 commit、不 push（contract 是只读校验）
- 选 (a) 谱系时，lefthook 会安装 `.git/hooks/*` —— 这是 lefthook install 一次性，C4 contract 不重复挂

### 3.3 Failure Modes

| 失败类型 | 触发条件 | 处理 |
|---|---|---|
| `TOOLCHAIN_NOT_FOUND` | 无 `pytest` / 无 `flutter` / 无 `eslint`... | 立即报错，要求 `toolchain_hints` 显式声明或安装工具链 |
| `WORKTREE_NOT_FOUND` | `target.worktree_path` 不存在 | 立即报错 |
| `SPEC_PARSE_FAILED` | spec.md 没有 `## 5. Acceptance Criteria` 段 / 段内无 `AC-N` 编号 | 立即报错（spec 不合法） |
| `LEVEL_NOT_IMPLEMENTED` | 请求 L3/L4/L5 但当前 contract version 未实现 | 报错且 `verify_report.json` 不生成 |
| L1 / L2 内部 fail | 工具退出非 0 | report 中标记 `status=fail`，**overall_verdict=fail**，但 C4 自身不报 error（这是正常业务结果） |

## 4. AI Prompt Template

**N/A** —— C4 是声明式契约，不跑 AI prompt。L4 (constitution compliance) 在 P3 落地时是**契约下挂的 imperative 子能力**，那时它会有独立 prompt（不在本 spec）。

## 5. Acceptance Criteria

- **AC-1**: 给定 worktree 含 1 个 passing test 名为 `test_AC_1_xxx`，请求 `levels: [L1, L2]`，返回 `overall_verdict=pass`、`ac_summary.covered = ['AC-1']`
- **AC-2**: 给定 worktree 含 1 个 failing test，返回 `overall_verdict=fail`、L2.summary.failed=1
- **AC-3**: 给定 test 名为 `test_AC_1_AC_2_combined`（2 个 AC prefix），返回 `multi_ac_violations` 非空且 `ac_summary` 标记为 violation
- **AC-4**: 给定请求 `levels: [L3]` 但 contract_version v0.1，返回 error `LEVEL_NOT_IMPLEMENTED`
- **AC-5**: 给定 spec.md 缺 §5 AC 段，返回 error `SPEC_PARSE_FAILED`
- **AC-6**: 给定 spec 含 `AC-1 / AC-2 / AC-3` 但 test 只覆盖 `AC-1`，`ac_summary.missing = ['AC-2', 'AC-3']`（即使 L2 全 pass，`overall_verdict` 仍由 caller 决定，C4 只报实况）
- **AC-7**: `verify_report.json` 严格符合 §2.2 schema（schema validation 100% 通过，跨 100 次 sample）
- **AC-8**: lefthook 实现谱系下，`lefthook run pre-commit` 跑出的 report 跟 P1+ CI 谱系跑出的 report `levels.L1` / `levels.L2` 结构完全一致（schema 跨谱系不漂）

## 6. Open Questions

- **Q4-1（已拍）**: AC ↔ test 映射 = 命名约定（Fork G）✅
- **Q4-2**: P0 阶段 `ac_summary.missing` 非空时 `overall_verdict` 是 `pass` 还是 `warn_only`？当前设计：**L1/L2 pass 即 overall pass**，AC coverage 是 L3 的责任（P3 起阻断）。这避免 P0 阶段死板要求 AC test 一一映射（业务可能 AC 还没拆好测试）
- **Q4-3**: lefthook 命中"修改了非代码文件"时是否跳过 L1/L2？例如改 README → L1 lint 仍然跑可能误报。建议加 `path_filters` 配置，但 P0 默认不过滤（lefthook 自带 glob）
- **Q4-4**: test name parser 的健壮度 —— Dart `test('AC-1: ...', () {...})` 嵌套在 `group()` 内时如何拿到完整 name？P0 spike 时验证 `flutter test --reporter json` 输出格式
- **Q4-5**: `multi_ac_violation` 是 L2 期就 fail，还是 L3 期才 fail？当前设计：**L2 期检测但不阻断**（只在 ac_summary 标记），L3 期（P3）作为 fail 项。理由：P0 还没 L3，先以"暴露问题"为主
- **Q4-6**: 跨语言 toolchain 探测策略 —— 同时有 `package.json` + `pyproject.toml` 的 monorepo 怎么办？P0 spike 时定（暂定 `toolchain_hints` 显式传）

## 7. Implementation Notes

### P0 实现谱系：本地 lefthook

```yaml
# lefthook.yml（业务项目根，由 v4 init.sh 安装）
pre-commit:
  parallel: true
  commands:
    lint:
      run: <由 toolchain_hints 决定>
    typecheck:
      run: <由 toolchain_hints 决定>
    format-check:
      run: <由 toolchain_hints 决定>
pre-push:
  commands:
    tests:
      run: <由 toolchain_hints 决定>
```

C4 contract layer 包一层 `suiyin-flow verify run` CLI：
1. 探测 `toolchain_hints`（读 `package.json` / `pyproject.toml` / `pubspec.yaml`）
2. 调用 `lefthook run pre-commit` + `lefthook run pre-push`
3. 解析 lefthook 输出 + 各 runner 的 JSON reporter（pytest `--json-report` / flutter `--reporter json` / vitest `--reporter=json`）
4. 写 `verify_report.json`

### 跨语言 reporter 适配

| 语言 | test runner | JSON reporter | 命名 prefix 提取 |
|---|---|---|---|
| Python | pytest | `pytest-json-report` plugin | `test_AC_(\d+)_` 正则 |
| Dart/Flutter | flutter test | `--reporter json` 内置 | `AC-(\d+)[:：]` 正则（test name string）|
| TS/JS | vitest / jest | `--reporter=json` 内置 | `AC-(\d+)[:：]` |
| Go | go test | `-json` | `Test_AC_(\d+)_` |
| Rust | cargo test | `cargo nextest --message-format json` | `test_AC_(\d+)_` |

P0 MVP 先实现 Python + Dart（v4 自身 + v5 业务）。其他语言 P1+ 按需加。

### 跨平台兼容性（macOS / Linux / Windows）

**这是 constitution NC-5（跨平台支持）的具体实现**。C4 contract 自身是 Python 包装 + shell 命令调度，跨平台约束同 C2 §7：

| 项 | 规则 |
|---|---|
| 路径处理 | `pathlib.Path`；verify_report.json 中所有 path 字段标"绝对路径" |
| subprocess | `shell=False` + `list[str]` 调 `pytest` / `flutter` / `eslint` 等 runner |
| lefthook | lefthook 本身跨平台 OK，但 `run:` 后的 shell 命令要写跨平台版本（避免 bash-only 语法如 `[[ ]]` / heredoc） |
| 工具探测 | `shutil.which('pytest')` / `shutil.which('flutter')` + **venv binary fallback**（见下方"Venv portability"节）|
| 文件编码 | 读取 reporter JSON 输出强制 `encoding='utf-8'`，避免 Windows 默认 cp936 / cp1252 |
| 测试 reporter 调用 | Windows 上 `flutter` / `pytest` 是 `.bat` shim，subprocess 必须用 `shell=False` 但允许 `executable=shutil.which('flutter.bat')` 兜底 |

**P0 阶段**：macOS + Linux 必跑通；Windows spike 时手测一次确认无致命问题，Windows CI 进 P1+。

### Venv portability — `require_tool` fallback（PR #22 实证）

`shutil.which('ruff')` 在 dev 没 activate venv 时找不到工具（subprocess 默认 PATH 不含 venv binary），导致 `suiyin-flow verify run` 在 `.venv/bin/suiyin-flow` 直接调用时报 `TOOLCHAIN_NOT_FOUND`。

**Fallback 链**:

```python
def require_tool(name: str) -> str:
    # 1. PATH 优先 (尊重业务项目环境)
    path = shutil.which(name)
    if path:
        return path
    # 2. Fallback: 当前 Python 解释器的 bin/Scripts 目录
    #    (subprocess 默认 PATH 不含 venv binary 时兜底)
    bin_dir = Path(sys.executable).parent
    for candidate in [bin_dir / name, bin_dir / f"{name}.exe", bin_dir / f"{name}.bat"]:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    raise VerifyContractError("TOOLCHAIN_NOT_FOUND", ...)
```

**关键**:
- `Path(sys.executable).parent` 跨平台映射到 venv `bin/` (macOS/Linux) 或 `Scripts/` (Windows)
- Windows 还要加 `.exe` / `.bat` 后缀 (因为 Windows 没"无后缀可执行")
- 找不到时 error 含 `searched_path` + `searched_venv_bin` 帮 dev debug

### 模块拆分建议

```
suiyin_flow/
  c4_verify/
    __init__.py
    cli.py            # `suiyin-flow verify run`
    contract.py       # §2 schema (Pydantic)
    runners/
      __init__.py
      pytest.py
      flutter.py
      eslint.py
      ...
    parser.py         # test name → AC-N prefix 解析
    report.py         # verify_report.json 落盘 + ac_summary 汇总
```

### 跟其他 C 模块协作

- **被 C2 Task Executor 调用**：C2 的 `verify_cmd` 落到 `suiyin-flow verify run --target worktree --worktree-path X`
- **输出给 C5 AI Reviewer**：C5 prompt 注入 `verify_report.json`，特别 `ac_summary` 和 L2 失败 test
- **输出给 C6 Gate Contract**：C6 读 `overall_verdict` 决定 merge / hold
- **L3/L4 落地后**：L3 是 AC↔test 一致性的 imperative 子能力；L4 是 AI 跑 constitution check 的 imperative 子能力。两者都是"契约下挂的 imperative"，不改 contract schema 主框架，只填 `levels.L3 / .L4` 内容

### 跟 constitution 的关系

- **NC-1**（零 SaaS）：P0 选 (a) 本地 lefthook ✅
- **NC-2**（spec-kit Layer 1 backbone）：C4 跑在 spec-kit 产出的 spec.md / plan.md 之上，不重造协商 ✅
- **NC-5**（跨平台）：上方"跨平台兼容性" + "Venv portability" 两节直接 enforce ✅
- **PC-1**（最简实现）：实现谱系明确从 (a) 起步，禁默认 SaaS ✅
- **PC-2**（组件 vs 契约分离）：本 spec 明确标"行为契约"，imperative 子能力归各 level（P3+）✅

### v4 自身 dogfood

- P0 第一次 dogfood：跑 C4 校验 C2 Task Executor 的实现（C2 自己写完 → C4 verify L1/L2 → 看 ac_summary 是否对得上 C2 spec §5 AC）
- 如果 C2 spec 的 9 个 AC 在 test 里命名跑不通，回头修 C2 spec 或 test 命名 —— 这是契约的实际功效检验

---

**Version**: v0.1.2-draft
**Last Updated**: 2026-05-24
**Status**: draft — P0 阶段 L1+L2 已实现 (PR #20+22)；P3 阶段补 L3/L4

**Changelog**:
- v0.1.2 (2026-05-24): **P1.1.2 反推** — §7 跨平台节加 NC-5 reference；§7 加 "Venv portability — require_tool fallback" 节（PR #22 实证）；§7 跟 constitution 关系加 NC-5
- v0.1.1 (2026-05-20): §0 实现谱系简化为"(a) 唯一首选，其他业务项目自决"；§2.1 Input 加 optional `task_id`；§2.2 verify_report 加 optional `task_id`；§7 加"跨平台兼容性"节
- v0.1.0 (2026-05-20): 初稿
