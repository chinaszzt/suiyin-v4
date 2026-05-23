"""C2 retry policy — §3.3 Failure Modes 实现.

策略:
- VERIFY_FAILED / SESSION_CRASHED → retry ≤ max_retries (默认 3, PC-1)
- TIMEOUT → 单独限 ≤ 1 次 (疑似 AI 死循环, 多次重试浪费)
- 其他 (WORKTREE_CONFLICT / SPEC_NOT_FOUND / HIGH_CRITICALITY_REJECT /
  INVALID_TASK_ID / CONTEXT_SEEDS_MISSING) → 立即终态, 不重试
"""

from __future__ import annotations

from suiyin_flow.c2_executor.schema import TaskErrorCode

# TIMEOUT 单独的重试上限 (spec Q2-3 implementation note)
TIMEOUT_RETRY_LIMIT = 1

# 重试白名单 — 这些 error code 可被 retry (受 max_retries 上限约束)
_RETRYABLE_CODES: set[TaskErrorCode] = {
    "VERIFY_FAILED",
    "SESSION_CRASHED",
}


def should_retry(
    error_code: TaskErrorCode,
    *,
    attempts_so_far: int,
    max_retries: int,
    timeout_retries_so_far: int = 0,
) -> bool:
    """决定是否还能再跑一次 attempt.

    attempts_so_far: 已经跑过的 attempt 数 (含本轮失败那次).
    max_retries: spec input.max_retries (默认 3).
    Total attempts 上限 = max_retries + 1 (spec §2.2 output description).

    Args:
        error_code: 上一轮失败的 error code.
        attempts_so_far: 已跑的 attempt 计数.
        max_retries: TaskInput.max_retries.
        timeout_retries_so_far: 已跑的 TIMEOUT 失败次数 (用于 TIMEOUT 单独限).
    """
    # 总额度: attempts_so_far ≤ max_retries 意味着下次 attempt 是 attempts_so_far+1 ≤ max_retries+1
    if attempts_so_far > max_retries:
        return False

    if error_code == "TIMEOUT":
        return timeout_retries_so_far < TIMEOUT_RETRY_LIMIT

    if error_code in _RETRYABLE_CODES:
        return True

    return False
