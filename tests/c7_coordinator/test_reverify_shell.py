"""C7 reverify shell 支持 + 诊断输出 — r4 真闭环发现 #2/#3 防回归.

#2 根因: run_verify 旧版用 shlex.split + shell=False, verify_cmd 含 `&&` 时
`&&` 被当字面参数 → 复合命令 (npm install && typecheck && vitest) 必失败 →
REVERIFY_FAILED 误 park 健康代码。修法: shell=True 跑 verify_cmd 字符串。
#3: run_verify 返回 (bool, output_tail), park 时存 TaskRecord.reverify_output 供诊断。
"""

from __future__ import annotations

import shlex
import sys
from pathlib import Path

from suiyin_flow.c7_coordinator.integrate import run_verify

_PY = shlex.quote(sys.executable)
_OK = f"{_PY} -c pass"
_FAIL = f'{_PY} -c "raise SystemExit(1)"'


def test_run_verify_compound_second_stage_runs(tmp_path: Path) -> None:
    """`OK && FAIL` → 整体 False: 证明 `&&` 第二段真的跑了 (发现 #2 防回归).

    旧版 shell=False 会 shlex.split → 只跑第一段 (OK, exit 0) + `&&`/FAIL 当字面
    参数 → 误返 True。本断言改回 shell=False 必挂。
    """
    ok, _out = run_verify(tmp_path, f"{_OK} && {_FAIL}")
    assert ok is False


def test_run_verify_compound_both_pass(tmp_path: Path) -> None:
    """`OK && OK` → True: 复合命令两段都绿 (r4 的 npm install && typecheck && vitest 形态)."""
    ok, _out = run_verify(tmp_path, f"{_OK} && {_OK}")
    assert ok is True


def test_run_verify_pipe_operator(tmp_path: Path) -> None:
    """`|` 也该被 shell 解释 (verify_cmd 不限于 &&)."""
    ok, _out = run_verify(tmp_path, f"{_OK} | {_OK}")
    assert ok is True


def test_run_verify_failure_captures_output(tmp_path: Path) -> None:
    """失败时返回非空 output tail 供诊断 (发现 #3)."""
    cmd = f'{_PY} -c "import sys; sys.stderr.write(\'BOOM-xyz\'); sys.exit(1)"'
    ok, out = run_verify(tmp_path, cmd)
    assert ok is False
    assert "BOOM-xyz" in out


def test_run_verify_success_returns_tuple(tmp_path: Path) -> None:
    """成功路径也返回 (True, output) 二元组 (签名一致)."""
    result = run_verify(tmp_path, _OK)
    assert isinstance(result, tuple) and result[0] is True
