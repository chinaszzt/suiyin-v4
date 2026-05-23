"""Shared subprocess helpers for runners.

跨平台:
- shell=False + list args (避免 Windows shell 语义差异)
- encoding='utf-8' (避免 Windows 默认 cp936)
- shutil.which 探测工具路径 (跨 macOS / Linux / Windows .exe / .bat shim)
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from suiyin_flow.c4_verify.contract import VerifyContractError

# subprocess stdout_tail 最大保留长度 (跟 contract L1Check.stdout_tail.max_length 对齐)
STDOUT_TAIL_MAX = 4000

# subprocess 默认超时 (单个工具 10 分钟，足够大多数项目)
DEFAULT_TIMEOUT_SECONDS = 600.0


def _venv_bin_candidates(name: str) -> list[Path]:
    """当前 Python 解释器的 bin/Scripts 目录下的工具候选路径 (跨平台)."""
    bin_dir = Path(sys.executable).parent
    candidates = [bin_dir / name]
    if os.name == "nt":  # Windows
        candidates.extend([bin_dir / f"{name}.exe", bin_dir / f"{name}.bat"])
    return candidates


def require_tool(name: str) -> str:
    """探测工具二进制绝对路径; 找不到 raise TOOLCHAIN_NOT_FOUND.

    查找顺序 (P0 spike 发现的 venv portability bug 修复):
    1. PATH 上找 (shutil.which, 尊重业务项目环境)
    2. Fallback 到当前 Python 解释器的 bin/Scripts 目录 (venv 没 activate
       时仍能找到 ruff/mypy/pytest)
    """
    # 1. PATH 优先
    path = shutil.which(name)
    if path:
        return path

    # 2. Venv fallback (跟 suiyin-flow 装在一起的工具)
    for candidate in _venv_bin_candidates(name):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)

    raise VerifyContractError(
        "TOOLCHAIN_NOT_FOUND",
        f"Tool not found on PATH or in {Path(sys.executable).parent}: {name}",
        tool=name,
        searched_path=os.environ.get("PATH", ""),
        searched_venv_bin=str(Path(sys.executable).parent),
    )


def run_subprocess(
    cmd: list[str],
    cwd: Path,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> tuple[int, str, str, float]:
    """跑 subprocess (shell=False)，返回 (exit_code, stdout, stderr, duration_seconds).

    Caller 自己用 truncate_tail 截断用于 L1Check.stdout_tail.
    """
    start = time.monotonic()
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
            shell=False,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return -1, "", f"TIMEOUT after {timeout}s", time.monotonic() - start
    duration = time.monotonic() - start
    return result.returncode, result.stdout or "", result.stderr or "", duration


def truncate_tail(stdout: str, stderr: str, max_len: int = STDOUT_TAIL_MAX) -> str:
    """合并 stdout + stderr 取尾部，用于 L1Check.stdout_tail."""
    combined = stdout + (f"\n--- stderr ---\n{stderr}" if stderr else "")
    return combined[-max_len:]
