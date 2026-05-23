"""Venv portability tests for require_tool (v0.1.2 hotfix).

Bug: P0 spike (PR #21 mini-dogfood) 发现 `shutil.which("ruff")` 在没 activate venv
时找不到 venv 装的工具 → TOOLCHAIN_NOT_FOUND. 修复: 加 sys.executable.parent fallback.

非 AC test (不映射 spec §5 AC), 只是 hotfix 行为验证.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from suiyin_flow.c4_verify.contract import VerifyContractError
from suiyin_flow.c4_verify.runners._subprocess import require_tool


def test_require_tool_finds_venv_binary_when_path_excludes_venv(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """收窄 PATH 不含 venv bin/ 时, require_tool 应 fallback 到 sys.executable.parent."""
    venv_bin = Path(sys.executable).parent
    sep = os.pathsep  # ':' on Unix, ';' on Windows

    # 排除 venv bin from PATH, 保留其他系统目录
    original_path = os.environ.get("PATH", "")
    filtered_paths = [
        p for p in original_path.split(sep) if Path(p).resolve() != venv_bin.resolve()
    ]
    monkeypatch.setenv("PATH", sep.join(filtered_paths))

    # shutil.which 当前 PATH 找不到 ruff (因为 PATH 不含 venv)
    # require_tool 应该走 fallback 找到 venv_bin/ruff
    ruff_path = require_tool("ruff")
    resolved = Path(ruff_path).resolve()
    assert resolved.is_file()
    assert resolved.parent == venv_bin.resolve(), (
        f"Expected fallback to venv bin {venv_bin}, got {resolved.parent}"
    )


def test_require_tool_raises_when_truly_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """真找不到 (PATH 空 + venv 也没) → TOOLCHAIN_NOT_FOUND."""
    monkeypatch.setenv("PATH", str(tmp_path))  # tmp dir 是空的
    with pytest.raises(VerifyContractError) as exc_info:
        require_tool("definitely-not-a-real-tool-zzz9876")
    assert exc_info.value.error.code == "TOOLCHAIN_NOT_FOUND"
    # error details 应该含搜索过的位置 (帮 dev debug)
    details = exc_info.value.error.details
    assert "searched_path" in details
    assert "searched_venv_bin" in details


def test_require_tool_prefers_path_over_venv_fallback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """v0.1.2 优先级: PATH 上找到的优先, fallback 只在 PATH miss 时启用."""
    # 在 tmp_path 造一个 'fake-ruff' 可执行
    fake_tool = tmp_path / "ruff"
    fake_tool.write_text("#!/bin/sh\necho fake\n")
    fake_tool.chmod(0o755)

    # PATH 优先含 tmp_path → 应该找到 fake, 不走 fallback
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")
    found = require_tool("ruff")
    assert Path(found).resolve() == fake_tool.resolve()
