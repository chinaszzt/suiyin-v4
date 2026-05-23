# Plan: ADR-0002 实施

## Steps (按顺序)

1. **读 context** (前置必做):
   - `docs/sdd/adrs/0000-adr-template.md` — ADR 8 章节格式 + Cascade + Status 流转
   - `docs/sdd/adrs/0001-constitution-v0.1-to-v0.2-layering-fix.md` — ADR 范例
   - `docs/sdd/constitution.md` — 看 §6b Q-C-2 / §9 / metadata 当前内容
   - `docs/sdd/todo.md` §P0.3 — task 完整描述

2. **写 ADR**: `docs/sdd/adrs/0002-python-tech-stack.md`
   - 严格按 0000-adr-template.md 8 章节 (Status / Context / Decision / Consequences /
     Cascade / Implementation Notes / Open Questions / Version History)
   - Status: accepted
   - 内容含 "Python 3.11+" 字符串

3. **bump constitution.md** 3 处:
   - §6b Q-C-2 line: 旧 "待 C2/C4 实现时定" → 新 "已拍: 见 ADR-0002 (Python 3.11+)"
   - §9 Version History 表: 加 v0.2.1 行 (PATCH, 关 open question, 2026-05-24)
   - 顶部 metadata: Version v0.2.0 → v0.2.1, Last Updated 2026-05-24

4. **写测试**: `tests/dogfood/__init__.py` (空) + `tests/dogfood/test_adr_0002.py`
   - `test_AC_101_adr_0002_exists_with_template_structure()`:
     断言 docs/sdd/adrs/0002-python-tech-stack.md 存在 + 含 "Python 3.11+" + 含 "## Status" + 含 "accepted"
   - `test_AC_102_constitution_bumped_to_v0_2_1()`:
     断言 constitution.md 含 "v0.2.1" + Q-C-2 line 含 "ADR-0002" + Version Hist 表有 2026-05-24 行

5. **跑 verify_cmd** (worktree 内):
   ```
   /Users/zhangtuo/Documents/suiyin-v4/.claude/worktrees/dogfood-adr-0002/.venv/bin/suiyin-flow verify run \\
     --target worktree --worktree-path . \\
     --spec dogfood/T-001/spec.md \\
     --ac AC-101 --ac AC-102 \\
     --repo-root .
   ```
   全绿 (overall_verdict=pass + ac_summary.covered=[AC-101, AC-102]) 才 commit.

6. **commit**:
   - 标准 commit message: `docs: ADR-0002 Python 技术栈拍板 + constitution v0.2.1`
   - 包含: ADR-0002 文件 + constitution 改动 + dogfood test 文件

## Constraints

- 严禁修改 dogfood/T-001/ 内文件 (这是 task input)
- 严禁修改 docs/sdd/components/ 内任何文件 (跟本 task 无关)
- 严禁修改 src/suiyin_flow/ 内代码 (本 task 是文档类)
- 严格按 §1 spec §5 AC 写测试 (test name prefix `test_AC_101_` / `test_AC_102_`)

## Verify pattern

verify_cmd 内嵌 suiyin-flow CLI 绝对路径 (用 dogfood 工作树自己的 venv).
不依赖 PATH 含 venv bin (PR #22 fallback 兜底).
