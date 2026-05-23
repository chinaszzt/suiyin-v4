"""Unified CLI dispatcher tests (v0.1.3 Bug 3 fix).

P0 spike 发现旧 entry point 只挂 c4_verify.cli, 导致 `suiyin-flow task ...`
报 "invalid choice: 'task'". 修后用 dispatcher 路由 verify / task.
"""

from __future__ import annotations

from typing import Any

import pytest

from suiyin_flow import cli as dispatcher


def test_dispatcher_routes_verify_to_c4(monkeypatch: pytest.MonkeyPatch) -> None:
    """`suiyin-flow verify ...` 应该调 c4_verify.cli.main."""
    captured: dict[str, Any] = {}

    def fake_c4_main(argv: list[str] | None = None) -> int:
        captured["argv"] = argv
        return 0

    monkeypatch.setattr("suiyin_flow.cli.c4_cli.main", fake_c4_main)
    rc = dispatcher.main(["verify", "run", "--help"])
    assert rc == 0
    assert captured["argv"] == ["verify", "run", "--help"]


def test_dispatcher_routes_task_to_c2(monkeypatch: pytest.MonkeyPatch) -> None:
    """`suiyin-flow task ...` 应该调 c2_executor.cli.main."""
    captured: dict[str, Any] = {}

    def fake_c2_main(argv: list[str] | None = None) -> int:
        captured["argv"] = argv
        return 0

    monkeypatch.setattr("suiyin_flow.cli.c2_cli.main", fake_c2_main)
    rc = dispatcher.main(["task", "run", "--help"])
    assert rc == 0
    assert captured["argv"] == ["task", "run", "--help"]


def test_dispatcher_unknown_subcommand_returns_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """未知 subcommand 报错且 exit code 2."""
    rc = dispatcher.main(["bogus"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "unknown subcommand: bogus" in err


def test_dispatcher_no_args_shows_usage_and_errors(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """无参数时打印 usage 到 stderr + exit 2."""
    rc = dispatcher.main([])
    assert rc == 2
    err = capsys.readouterr().err
    assert "suiyin-flow" in err and "verify" in err and "task" in err


def test_dispatcher_help_flag_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    """--help / -h 显示 usage 且 exit 0."""
    for flag in ("-h", "--help"):
        rc = dispatcher.main([flag])
        assert rc == 0
        out = capsys.readouterr().out
        assert "suiyin-flow" in out and "verify" in out and "task" in out


def test_dispatcher_propagates_c4_exit_code(monkeypatch: pytest.MonkeyPatch) -> None:
    """c4 main 返回非 0 时, dispatcher 透传."""
    monkeypatch.setattr("suiyin_flow.cli.c4_cli.main", lambda argv: 1)
    assert dispatcher.main(["verify", "anything"]) == 1


def test_dispatcher_propagates_c2_exit_code(monkeypatch: pytest.MonkeyPatch) -> None:
    """c2 main 返回非 0 时, dispatcher 透传."""
    monkeypatch.setattr("suiyin_flow.cli.c2_cli.main", lambda argv: 2)
    assert dispatcher.main(["task", "anything"]) == 2
