"""Smoke test — 确认 Python 项目 setup 正确."""

import suiyin_flow
import suiyin_flow.c4_verify


def test_package_imports() -> None:
    """suiyin_flow + c4_verify 两个包能 import."""
    assert suiyin_flow.__version__ == "0.1.0"
    assert suiyin_flow.c4_verify is not None
