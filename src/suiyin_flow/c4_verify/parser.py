"""Test name → AC-N prefix 解析.

Fork G (命名约定) + I2 invariant (1 test 名只能 1 AC prefix) 实现.

跨语言正则:
- Python pytest:    `test_AC_1_xxx`
- Dart/Flutter:     `AC-1: xxx` (test name string)
- JS/TS jest/vitest: `AC-1: xxx`
- Go:               `TestAC1_xxx` 或 `test_AC_1_...` (我们用 pytest 风格)
"""

from __future__ import annotations

import re

# Python 风格: test_AC_<digits>_<rest>
_AC_PATTERN_PYTHONIC = re.compile(r"(?<![A-Za-z])AC_(\d+)(?:_|$)")

# String 风格: AC-<digits> (Dart / JS / TS 测试名)
_AC_PATTERN_STRING = re.compile(r"\bAC-(\d+)\b")


def extract_ac_prefixes(test_name: str) -> list[str]:
    """从 test_name 提取**所有** AC-N 编号 (作为 'AC-N' 字符串).

    顺序保留. 同一 AC-N 多次出现也重复记录 (caller 决定 dedupe).
    支持 Python (test_AC_1_...) 和 string (AC-1: ...) 两种风格混合.
    """
    found: list[str] = []
    for m in _AC_PATTERN_PYTHONIC.finditer(test_name):
        found.append(f"AC-{m.group(1)}")
    for m in _AC_PATTERN_STRING.finditer(test_name):
        ac = f"AC-{m.group(1)}"
        if ac not in found:  # 避免 'AC-1' 同时匹配两套正则时重复
            found.append(ac)
    return found


def primary_ac_prefix(test_name: str) -> str:
    """返回 test_name 中**第一个** AC-N，没找到返回空串.

    用于 TestResult.ac_prefix 字段填充. caller 仍需调
    `is_multi_ac_violation` 检查 I2.
    """
    prefixes = extract_ac_prefixes(test_name)
    return prefixes[0] if prefixes else ""


def is_multi_ac_violation(test_name: str) -> tuple[bool, list[str]]:
    """I2 检查: test_name 是否含 ≥2 个**不同** AC-N prefix.

    Returns:
        (violated, unique_prefixes) — unique_prefixes 顺序保留.
    """
    prefixes = extract_ac_prefixes(test_name)
    unique = list(dict.fromkeys(prefixes))  # 顺序 dedupe
    return len(unique) >= 2, unique
