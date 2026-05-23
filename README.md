# suiyin-flow

碎银 v4 SDD 工具链。当前 P1.1 阶段 2 实现中：

- **C4 Verify Contract** — L1 (lint/typecheck) + L2 (tests) 自动化验证（本仓 PR）
- **C2 Task Executor** — 单 task 自动从 spec 到 PR（下一 PR）

Spec 在 `docs/sdd/components/`：
- [`c4-verify-contract.md`](docs/sdd/components/c4-verify-contract.md) (v0.1.1)
- [`c2-task-executor.md`](docs/sdd/components/c2-task-executor.md) (v0.1.1)

## Dev quickstart

```bash
# Python 3.11+
python -m venv .venv
source .venv/bin/activate           # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

# 跑 lint / typecheck / tests
ruff check src tests
mypy
pytest

# lefthook（git hook，可选 — brew install lefthook / npm i -g lefthook）
lefthook install
```

## 项目结构

```
src/suiyin_flow/
  c4_verify/                # 本 PR 实现
    contract.py             # Pydantic schema (§2)
    parser.py               # test name → AC-N prefix
    report.py               # verify_report.json
    runners/
      pytest.py
      flutter.py
    cli.py                  # `suiyin-flow verify run`
tests/
  c4_verify/                # AC-1..AC-8 tests
```
