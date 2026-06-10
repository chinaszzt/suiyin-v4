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

## 给业务项目跑 `suiyin-flow task batch` 前

```bash
# 1) CLI 必须从 v4 main checkout 装（editable）——
#    不要在 v4 的某个 worktree 里 pip install -e（worktree 删掉后 CLI 指向悬空旧代码），
#    pyyaml 等依赖随 pyproject 一起装上（缺 pyyaml = 装的是 P1.2.5 之前的旧环境，重装即可）
cd /path/to/suiyin-v4 && .venv/bin/pip install -e .

# 2) 代理网络注意：C2 用 subprocess 起 claude session，shell alias 不生效。
#    如果你平时靠 `alias claude='https_proxy=... claude'` 上网，跑 batch 前先 export：
export https_proxy=http://127.0.0.1:<port> http_proxy=http://127.0.0.1:<port>
suiyin-flow task batch --tasks-yaml specs/<feature>/tasks.yaml --repo-root .

# 3) /sy-specify / /sy-plan / /sy-tasks 的产物必须已 commit 到 base_branch ——
#    task worktree 从 base HEAD 分叉，看不到未提交文件（batch 会 fail-fast 提示）
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
