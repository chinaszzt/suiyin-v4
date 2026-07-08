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
from tests.fixtures.mock_cli import write_mock_cli


def test_require_tool_finds_venv_binary_when_path_excludes_venv(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """收窄 PATH 不含 venv bin/ 时, require_tool 应 fallback 到 sys.executable 同级目录.

    Windows 上解释器所在目录不一定就是工具所在目录 —— CI runner (setup-python
    产物, "base install" 布局) 里解释器在根目录、pip 装的 console script 在
    根目录下的 Scripts\\ 子目录; 真 venv (`python -m venv`) 则两者同目录。两种
    布局都要接受, 断言按 fallback candidate 集合校验 (而非死等于 sys.executable
    的 parent), 见 _venv_bin_candidates 的两层布局说明。
    """
    venv_bin = Path(sys.executable).parent
    scripts_dir = venv_bin / "Scripts"  # Windows base-install 布局才有意义
    sep = os.pathsep  # ':' on Unix, ';' on Windows

    # 排除 venv bin (以及 Windows base-install 布局下的 Scripts 子目录) from
    # PATH, 保留其他系统目录 —— 否则 Scripts\\ 仍在 PATH 上时 shutil.which
    # 会在 require_tool 走到 fallback 分支之前就直接命中, 测试没验到 fallback 本身。
    exclude = {venv_bin.resolve(), scripts_dir.resolve()}
    original_path = os.environ.get("PATH", "")
    filtered_paths = [
        p for p in original_path.split(sep) if Path(p).resolve() not in exclude
    ]
    monkeypatch.setenv("PATH", sep.join(filtered_paths))

    # shutil.which 当前 PATH 找不到 ruff (因为 PATH 不含 venv bin / Scripts)
    # require_tool 应该走 fallback 找到 venv_bin (或其 Scripts 子目录) 下的 ruff
    ruff_path = require_tool("ruff")
    resolved = Path(ruff_path).resolve()
    assert resolved.is_file()
    expected_dirs = {venv_bin.resolve(), scripts_dir.resolve()}
    assert resolved.parent in expected_dirs, (
        f"Expected fallback to venv bin {venv_bin} (or its Scripts/ subdir "
        f"{scripts_dir} on Windows base installs), got {resolved.parent}"
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
    # 造一个假 ruff 可执行 (跨平台: POSIX shebang 脚本 / Windows .bat shim —
    # 见 tests/fixtures/mock_cli.py, shutil.which 在 Windows 上按 PATHEXT
    # 匹配扩展名, 无扩展名的 bare 文件不会被命中).
    bin_dir = tmp_path / "fakebin"
    fake_tool = write_mock_cli(bin_dir, "ruff", "#!/bin/sh\necho fake\n")

    # PATH 优先含 bin_dir → 应该找到 fake, 不走 fallback
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    found = require_tool("ruff")
    assert Path(found).resolve() == fake_tool.resolve()
