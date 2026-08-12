"""模型调用成本台账（P0-6 最小版）.

台账只提供观测能力；任何写盘或 usage 解析错误都不得影响主流程。
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

Role = Literal["implementer", "reviewer"]
Status = Literal["running", "success", "crashed", "timeout"]
TerminalStatus = Literal["success", "crashed", "timeout"]


class CostRecord(BaseModel):
    """单次模型调用的成本记录."""

    invocation_id: str
    run_id: str | None
    feature_id: str
    task_id: str
    role: Role
    model: str | None
    attempt: int
    start_ts: str
    end_ts: str | None
    status: Status
    input_tokens: int | None
    cache_read_tokens: int | None
    output_tokens: int | None
    error: str | None
    cost_log_error: str | None


def _utc_now() -> str:
    """返回 ISO 8601 UTC 时间戳."""
    return datetime.now(UTC).isoformat()


def _append_record(repo_root: Path, record: CostRecord) -> None:
    """向 append-only JSONL 台账追加一行."""
    log_path = repo_root / ".suiyin" / "cost" / "log.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as log_file:
        payload = record.model_dump(mode="json")
        log_file.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _safe_append(repo_root: Path, record: CostRecord) -> None:
    """写台账；失败时只警告，不改变调用方控制流."""
    try:
        _append_record(repo_root, record)
    except Exception as exc:  # 观测链路必须与主流程完全隔离
        print(f"warning: cost ledger write failed: {exc}", file=sys.stderr)


def open_invocation(
    repo_root: Path,
    *,
    feature_id: str,
    task_id: str,
    role: Role,
    attempt: int,
) -> CostRecord:
    """创建模型调用记录并在 session 启动前写入 running 行."""
    record = CostRecord(
        invocation_id=str(uuid.uuid4()),
        run_id=None,
        feature_id=feature_id,
        task_id=task_id,
        role=role,
        model=os.environ.get("ANTHROPIC_MODEL"),
        attempt=attempt,
        start_ts=_utc_now(),
        end_ts=None,
        status="running",
        input_tokens=None,
        cache_read_tokens=None,
        output_tokens=None,
        error=None,
        cost_log_error=None,
    )
    _safe_append(repo_root, record)
    return record


def _parse_token(usage: dict[str, Any], key: str) -> int | None:
    """读取可选 token 字段，并拒绝异常类型."""
    value = usage.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"usage.{key} must be int or null, got {type(value).__name__}")
    return value


def _parse_usage(
    usage: object | None,
) -> tuple[int | None, int | None, int | None, str | None]:
    """解析 Claude usage；异常显式落到 cost_log_error."""
    if usage is None:
        return None, None, None, None
    try:
        if not isinstance(usage, dict):
            raise TypeError(f"usage must be a dict, got {type(usage).__name__}")
        return (
            _parse_token(usage, "input_tokens"),
            _parse_token(usage, "cache_read_input_tokens"),
            _parse_token(usage, "output_tokens"),
            None,
        )
    except Exception as exc:  # 解析错误要记账，不能影响主流程
        return None, None, None, f"usage parse failed: {exc}"


def close_invocation(
    repo_root: Path,
    record: CostRecord,
    *,
    status: TerminalStatus,
    usage: dict[str, Any] | None,
    error: str | None,
) -> None:
    """追加同 invocation_id 的终态完整行."""
    input_tokens, cache_read_tokens, output_tokens, cost_log_error = _parse_usage(usage)
    terminal = record.model_copy(
        update={
            "end_ts": _utc_now(),
            "status": status,
            "input_tokens": input_tokens,
            "cache_read_tokens": cache_read_tokens,
            "output_tokens": output_tokens,
            "error": error,
            "cost_log_error": cost_log_error,
        }
    )
    _safe_append(repo_root, terminal)
