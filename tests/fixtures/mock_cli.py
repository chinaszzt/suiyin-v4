"""跨平台假 CLI 落盘 util — NC-5 test infra 共享逻辑 (todo.md Insight F)。

背景: 伪造一个"可执行 CLI" (mock `gh` / 探测 PATH 上的假 `ruff` 等) 在 POSIX 上
标准做法是写一个带 `#!/usr/bin/env python3` shebang 的文件 + `chmod 0o755`。
这套手法在 Windows 上整体失效, 原因有两层:

1. Windows 不识别 `#!` shebang —— 一个无扩展名的文件哪怕内容是合法 Python,
   系统也不知道该用什么解释器执行它。
2. `shutil.which(name)` 在 Windows 上按 `PATHEXT` (`.COM;.EXE;.BAT;.CMD;...`)
   遍历扩展名匹配候选文件 —— 一个 bare-name (无扩展名) 文件永远不会被命中,
   即使 PATH 目录正确、文件本身可读。生产代码里 `shutil.which("gh")` 直接拿到
   None, 连 subprocess 那步都走不到。

修法: POSIX 下照旧写 shebang 脚本 (维持"能被直接 exec"的假设); Windows 下额外
写一份 `<name>.py`（跟 POSIX 版本同一份逻辑, shebang 行在这里只是无害注释) +
一个 `<name>.bat` shim 转发调用。`.bat` 命中默认 PATHEXT, 之后
`shutil.which(name)` 以及生产代码常见的「先 which 解析出绝对路径、再
subprocess.run([resolved_path, ...], shell=False)」写法都能正确命中并执行它。

**重要**: 部分被测代码是在 subprocess 里真的调用外部 CLI (例如 c6_gate 里
`shutil.which("gh")` 拿到路径后 `subprocess.run([gh, ...])`) —— 这不是
`monkeypatch.setattr(subprocess, "run", ...)` 能拦截的, shim 必须是真落盘、
靠 PATH 生效的文件。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest


def write_mock_cli(bin_dir: Path, name: str, script_body: str) -> Path:
    """在 bin_dir 下写一个跨平台、可被 PATH 解析 + 直接执行的假 CLI。

    Args:
        bin_dir: 目标目录 (自动创建; 调用方负责把它加进 PATH)。
        name: CLI 名字, 不带扩展名 (如 "gh")。
        script_body: Python 脚本源码。POSIX 下直接落成可执行文件内容;
            Windows 下落成同名 `.py`, 由 `.bat` shim 转发调用 —— 两边跑的是
            同一份逻辑, 调用方不需要写两份 mock 行为。

    Returns:
        实际生效、可被 `shutil.which(name)` 命中的文件路径:
          - POSIX: `bin_dir/name` (shebang + chmod 0o755)
          - Windows: `bin_dir/name.bat` (内部 `<python> bin_dir/name.py %*`)
    """
    bin_dir.mkdir(parents=True, exist_ok=True)

    if sys.platform == "win32":
        py_path = bin_dir / f"{name}.py"
        py_path.write_text(script_body, encoding="utf-8")
        bat_path = bin_dir / f"{name}.bat"
        # 双引号包裹 python / 脚本路径防止空格 (如 "C:\\Program Files\\...");
        # %* 透传所有参数给假 CLI 脚本。
        bat_path.write_text(
            f'@"{sys.executable}" "{py_path}" %*\n',
            encoding="utf-8",
        )
        return bat_path

    posix_path = bin_dir / name
    posix_path.write_text(script_body, encoding="utf-8")
    posix_path.chmod(0o755)
    return posix_path


def mock_cli_on_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    script_body: str,
) -> Path:
    """`write_mock_cli` + 把它所在目录塞进 PATH 最前面 —— 最常见用法一步到位。

    独立子目录 (`tmp_path/mock_bin`) 跟 caller 自己往 tmp_path 塞的其它文件
    (repo / log 等) 分开。同一个 tmp_path 多次调用 (不同 name) 复用同一个
    bin_dir, PATH 只会被塞一次前缀。
    """
    bin_dir = tmp_path / "mock_bin"
    exe_path = write_mock_cli(bin_dir, name, script_body)
    current_path = os.environ.get("PATH", "")
    if str(bin_dir) not in current_path.split(os.pathsep):
        monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{current_path}")
    return exe_path
