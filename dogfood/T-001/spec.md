# Spec: ADR-0002 — v4 工具链技术栈 = Python 3.11+

## 1. Purpose

User 在 P1.1 阶段 1 拍板 Q-C-2: v4 自身技术栈 = Python 3.11+. 现按 constitution
governance §8.1 写 ADR-0002 追溯, 并 bump constitution v0.2.0 → v0.2.1
(PATCH — 关 open question, 不改 NC).

## 2. Public API

N/A — 文档类 task.

## 3. Behavior Contract

无 imperative logic. AC 全部是文件存在 + 内容含特定字符串.

## 5. Acceptance Criteria

> 注: 用 AC-101 / AC-102 而非 AC-1 / AC-2 避免跟 C2/C4 spec 已有 AC-N 冲突
> (parser 全局扫 AC-\d+).

- **AC-101**: 新文件 `docs/sdd/adrs/0002-python-tech-stack.md` 存在,
  Status="accepted", 决策为 Python 3.11+ over shell / Bun / Go.
  内容必须含字符串 "Python 3.11+" 和 "## Status" 段.
- **AC-102**: `docs/sdd/constitution.md` 内 §6b Q-C-2 行更新为
  "已拍: 见 ADR-0002 (Python 3.11+)", §9 Version History 表
  加 v0.2.1 行 (2026-05-24), 顶部 metadata `**Version**: v0.2.1`.

## 6. Open Questions

无.

## 7. Implementation Notes

### ADR-0002 内容要点

- **Status**: accepted
- **Context**: PR #20 C4 实现时 + P1.1 阶段 1 spec PR #11 user 拍板
- **Decision**: Python 3.11+ + pydantic 2.x + pytest + ruff + mypy + psutil
- **候选对比**: 列 shell / Bun / Go 各自优劣, 解释为什么选 Python (PC-1 最简实现优先)
- **Consequences**:
  - + Python 生态成熟 (pydantic / pytest / mypy)
  - + 强类型 + AI 友好
  - + 跨平台 (subprocess / pathlib / psutil)
  - − 业务项目要装 Python (Flutter dev box 通常已有 / 否则 brew install)
- **Cascade**: 影响 C1-C11 所有 imperative 组件实现选型
- **Version History**: 1 行 v0.1.0 (本次新增)

### constitution.md 改动

- §6b Q-C-2 line (around line 304): 从 "待 C2/C4 实现时定" 改为
  "已拍: 见 ADR-0002 (Python 3.11+)"
- §9 Version History 表加 v0.2.1 行:
  `| v0.2.1 | 2026-05-24 | PATCH: 关闭 Q-C-2 open question (v4 技术栈 = Python 3.11+, 见 ADR-0002) |`
- 顶部 `**Version**: v0.2.0` → `**Version**: v0.2.1`
- 顶部 `**Last Updated**: 2026-05-18` → `**Last Updated**: 2026-05-24`

### 测试

写 `tests/dogfood/test_adr_0002.py` (新建 dir + __init__.py + test 文件):

```python
def test_AC_101_adr_0002_exists_with_template_structure():
    ...
def test_AC_102_constitution_bumped_to_v0_2_1():
    ...
```

每个 test 名严格 prefix `AC-N`, C4 parser 会识别为 covering AC.

---

**Version**: v0.1.0
**Last Updated**: 2026-05-24
**Status**: draft (dogfood task input)
