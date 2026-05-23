"""Shared subprocess helpers for runners.

跨平台:
- shell=False + list args (避免 Windows shell 语义差异)
- encoding='utf-8' (避免 Windows 默认 cp936)
- shutil.which 探测工具路径 (跨 macOS / Linux / Windows .exe / .bat shim)
"""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

from suiyin_flow.c4_verify.contract import VerifyContractError

# subprocess stdout_tail 最大保留长度 (跟 contract L1Check.stdout_tail.max_length 对齐)
STDOUT_TAIL_MAX = 4000

# subprocess 默认超时 (单个工具 10 分钟，足够大多数项目)
DEFAULT_TIMEOUT_SECONDS = 600.0


def require_tool(name: str) -> str:
    """探测工具二进制绝对路径; 找不到 raise TOOLCHAIN_NOT_FOUND."""
    path = shutil.which(name)
    if not path:
        raise VerifyContractError(
            "TOOLCHAIN_NOT_FOUND",
            f"Tool not found on PATH: {name}",
            tool=name,
        )
    return path


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
