"""Test C2 session.py default claude cmd contains required flags (v0.1.3 bug 1+2 fix).

Bug 1 (P0 spike 2026-05-24 dogfood):
- 默认 cmd 缺 `--permission-mode bypassPermissions` → Write/Edit/Bash tools 被拒
- 修后 default cmd 必须含 ["--permission-mode", "bypassPermissions"]

Bug 2 (同 spike):
- 默认 cmd 缺 `--verbose` → Claude CLI 启动报错 "stream-json requires --verbose"
- 修后 default cmd 必须含 "--verbose"
"""

from __future__ import annotations

from suiyin_flow.c2_executor.session import _resolve_claude_cmd


def test_default_cmd_includes_bypass_permissions_flag() -> None:
    """v0.1.3 Bug 1 fix: default cmd 必须含 --permission-mode bypassPermissions."""
    cmd = _resolve_claude_cmd(None, task_id="T-001")
    # 顺序敏感: --permission-mode 后必须紧跟 bypassPermissions
    idx = cmd.index("--permission-mode")
    assert cmd[idx + 1] == "bypassPermissions"


def test_default_cmd_includes_verbose_flag() -> None:
    """v0.1.3 Bug 2 fix: default cmd 必须含 --verbose (stream-json + --print 强制要求)."""
    cmd = _resolve_claude_cmd(None, task_id="T-001")
    assert "--verbose" in cmd


def test_default_cmd_includes_stream_json_output_format() -> None:
    """Regression: stream-json output format 必须保留 (PR #23 解析依赖)."""
    cmd = _resolve_claude_cmd(None, task_id="T-001")
    idx = cmd.index("--output-format")
    assert cmd[idx + 1] == "stream-json"


def test_default_cmd_includes_print_mode() -> None:
    """Regression: --print 必须保留 (non-interactive mode)."""
    cmd = _resolve_claude_cmd(None, task_id="T-001")
    assert "--print" in cmd


def test_injectable_cmd_overrides_default() -> None:
    """测试时 inject mock script 仍然 work (default flag 不影响 injection 路径)."""
    custom = ["/usr/bin/python", "/tmp/mock_claude.py"]
    cmd = _resolve_claude_cmd(custom, task_id="T-001")
    assert cmd == custom  # 完全使用 caller 传入, 不附加 default flag
