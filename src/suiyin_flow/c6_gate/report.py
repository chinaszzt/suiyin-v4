"""C6 gate_report.json 落盘 + safe_pr_ref 转义.

按 c6 spec §3.2 落盘规则 + §7 safe_pr_ref 实现示意.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from suiyin_flow.c6_gate.contract import GateContractError, GateOutput

# §7 pr_ref 转义 — pull URL 提号 / 其余非安全字符 → "-".
# 不安全字符: / \ : ? " < > | 空白 (跨平台文件名 NC-5 — Windows 也禁这些).
_UNSAFE_CHARS = re.compile(r'[/\\:?"<>|\s]+')
_PULL_URL = re.compile(r"/pull/(\d+)")


def safe_pr_ref(pr_ref: str) -> str:
    """规范 pr_ref → 文件名安全字符串.

    Examples:
        https://github.com/owner/repo/pull/33 → pull-33
        claude/c6-spec → claude-c6-spec
        #33 → 33
        33 → 33
    """
    m = _PULL_URL.search(pr_ref)
    if m:
        return f"pull-{m.group(1)}"
    stripped = pr_ref.lstrip("#")
    return _UNSAFE_CHARS.sub("-", stripped).strip("-") or "unknown"


def gates_dir(repo_root: Path) -> Path:
    """`<repo_root>/.suiyin/gates/` (创建如不存在)."""
    p = repo_root / ".suiyin" / "gates"
    p.mkdir(parents=True, exist_ok=True)
    return p


def now_iso8601_utc() -> str:
    """ISO8601 UTC timestamp — §2.2 timestamp 字段."""
    return datetime.now(UTC).isoformat()


def report_filename(pr_ref: str, ts: str) -> str:
    """`<safe_pr_ref>-<ts>.json` — ts 也需净化 (`:` 不安全)."""
    safe_ts = _UNSAFE_CHARS.sub("-", ts)
    return f"{safe_pr_ref(pr_ref)}-{safe_ts}.json"


def write_gate_report(
    *,
    output: GateOutput,
    repo_root: Path,
    pr_ref: str,
) -> Path:
    """落盘 gate_report.json + 同时维护 latest-<safe_pr_ref>.json (覆盖式).

    Returns 路径 = versioned file (timestamped)。
    latest-* 同时写一份方便 dogfood / debug 直接读最新。
    """
    out_dir = gates_dir(repo_root)
    payload = json.dumps(output.to_dict(), indent=2, ensure_ascii=False)

    versioned = out_dir / report_filename(pr_ref, output.timestamp)
    versioned.write_text(payload, encoding="utf-8")

    # latest 副本 (NC-5: 不用 symlink，直接 copy)
    latest = out_dir / f"latest-{safe_pr_ref(pr_ref)}.json"
    latest.write_text(payload, encoding="utf-8")

    return versioned


def load_report(path: str | Path, *, kind: str) -> dict[str, Any]:
    """读 verify_report / review_report — fail-fast for MISSING / INVALID.

    Args:
        path: 文件路径 (相对或绝对)
        kind: "verify" 或 "review" — error message 用

    Raises:
        GateContractError MISSING_INPUT — 文件不存在 / 不可读
        GateContractError INVALID_REPORT — JSON parse 失败
    """
    p = Path(path)
    if not p.exists():
        raise GateContractError(
            "MISSING_INPUT",
            f"{kind}_report file not found: {path}",
            details={"path": str(path), "kind": kind},
        )
    try:
        text = p.read_text(encoding="utf-8")
    except OSError as e:
        raise GateContractError(
            "MISSING_INPUT",
            f"{kind}_report not readable: {e}",
            details={"path": str(path), "kind": kind, "stderr": str(e)},
        ) from e
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise GateContractError(
            "INVALID_REPORT",
            f"{kind}_report JSON parse failed: {e.msg}",
            details={"path": str(path), "kind": kind, "stderr": str(e)},
        ) from e
    if not isinstance(data, dict):
        raise GateContractError(
            "INVALID_REPORT",
            f"{kind}_report top-level must be JSON object, got {type(data).__name__}",
            details={"path": str(path), "kind": kind},
        )
    return data
