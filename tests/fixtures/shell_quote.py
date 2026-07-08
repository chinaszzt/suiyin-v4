"""跨平台 `shell=True` 命令片段引用 util (NC-5 test infra 共享逻辑).

背景: `c7_coordinator.integrate.run_verify` 故意用 `shell=True` 跑 verify_cmd
字符串 (POSIX 走 `/bin/sh`, Windows 走 `cmd.exe`) —— 测试里常用
`sys.executable` 拼一个"总能跑"的 no-op verify_cmd (如 `<python> -c pass`),
拼接时解释器路径需要加引用 (防路径带空格被切成多个参数)。

`shlex.quote` 是 POSIX shell 语法, 在 Windows 上完全不适用: Windows 路径全是
反斜杠 (`C:\\...\\python.exe`), `shlex.quote` 的"不安全字符"判定 (基于 POSIX
shell 语法, 反斜杠是转义符) 会把反斜杠也判成不安全, 从而把整个路径套上
**单引号**。但 cmd.exe 根本不认单引号当引用符 —— 它会把
`'C:\\...\\python.exe'` (含字面单引号) 当成一个整体文件名去找, 100% 报
"The filename, directory name, or volume label syntax is incorrect."
(issue #60 windows-latest 首跑实测踩到, tests/c7_coordinator 下 reverify 相关
测试全挂)。

修法: 按平台分别用对的引用机制 —— POSIX 走 `shlex.quote` (正确处理空格/
特殊字符), Windows 套双引号 (`cmd.exe` 的引用符)。
"""

from __future__ import annotations

import shlex
import sys


def quote_for_shell(s: str) -> str:
    """给 `subprocess.run(cmd_str, shell=True)` 用的命令片段加引用, 跨平台。

    POSIX: `shlex.quote(s)`。
    Windows: `f'"{s}"'` (cmd.exe 引用符; `shlex.quote` 在这里会产生 cmd.exe
    不认的单引号, 见模块 docstring)。
    """
    if sys.platform == "win32":
        return f'"{s}"'
    return shlex.quote(s)
