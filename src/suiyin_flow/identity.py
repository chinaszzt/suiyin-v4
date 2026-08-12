"""Canonical identity — feature_id + local task_id (gen4-plan P0-1).

单一权威: worktree 路径 / task 分支 / C7 phase-state 键 / C5 review 落盘键 /
(P0-6) 成本台账键全部从这里取, 不许各组件自拼。

背景 (gen4-plan §三 P0-1): 旧身份是全局单键 `T-\\d{3,}`, 三处后果:
- 002·T001 沙盒实验里 task_id "T-001B" 被 schema 直接拒收 (pattern 写死数字);
- 不同 feature 的同名 T-001 在 worktrees/ 与 task/* 分支上互撞;
- C5 review 落盘用随机 uuid, 与 task 身份完全脱钩, 无法按键定位。

canonical key = (feature_id, local_task_id)。feature_id 约定 = spec-kit
feature 目录名 (例 '002-归入引擎'→ ASCII slug 化后的 '002-...'); 缺省时从
base_branch 派生 (safe_ref)。
"""

from __future__ import annotations

import re

# local id (feature_id / task_id 共用): 字母数字开头, 允许 . _ - , ≤64 字符。
# 模板仍推荐 T-NNN 风格, 但不再强制纯数字 (T-001B 合法)。
LOCAL_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$"
_LOCAL_ID_RE = re.compile(LOCAL_ID_PATTERN)

# 同 C6 §3.2 / C7 state 转义规则 (跨平台文件名安全, NC-5)
_UNSAFE_CHARS = re.compile(r'[/\\:?"<>|\s]+')


def safe_ref(name: str) -> str:
    """任意 ref/名字 → 文件名安全字符串. 例 'claude/login-core-r2' → 'claude-login-core-r2'."""
    return _UNSAFE_CHARS.sub("-", name).strip("-") or "unknown"


def is_valid_local_id(value: str) -> bool:
    return bool(_LOCAL_ID_RE.match(value))


def derive_feature_id(feature_name: str | None, base_branch: str) -> str:
    """feature_id 缺省派生: feature_name 合法则用之, 否则从 base_branch 转义.

    v0.1.0 时代 manifest 没有 feature_id 字段, 兼容读时走这里 (caller 应
    stderr 提示派生结果, 让用户知道身份键实际取了什么)。
    """
    if feature_name:
        candidate = safe_ref(feature_name)
        if is_valid_local_id(candidate):
            return candidate
    return safe_ref(base_branch)


def worktree_relpath(feature_id: str, task_id: str) -> str:
    """task worktree 相对 repo_root 的路径: worktrees/<feature_id>/<task_id>."""
    return f"worktrees/{feature_id}/{task_id}"


def task_branch(feature_id: str, task_id: str) -> str:
    """task 分支名: task/<feature_id>/<task_id> (不同 feature 的同名 task 不撞)."""
    return f"task/{feature_id}/{task_id}"


def review_key(feature_id: str | None, task_id: str) -> str:
    """C5 review 落盘目录键: <safe_feature>-<task_id>; feature 缺省时退化 task_id."""
    if feature_id:
        return f"{safe_ref(feature_id)}-{safe_ref(task_id)}"
    return safe_ref(task_id)
