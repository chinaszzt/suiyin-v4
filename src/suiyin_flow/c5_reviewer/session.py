"""C5 session — Claude headless CLI 调用 (复用 C2 §7 Session 调用模式).

按 C5 spec §7 "Session 调用模式": 直接复用 C2 §7 定义的 4 个必需 flag
(--print --output-format stream-json --verbose --permission-mode bypassPermissions).
唯一差异 (I1): prompt 不含 implementer .suiyin/sessions/* 路径.

跨平台 + 整树 kill + watchdog timeout 设计同 C2 session.py.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psutil

from suiyin_flow.c5_reviewer.contract import ReviewerError

# Default 30 min (跟 spec §2.1 session_timeout_seconds default 一致)
DEFAULT_TIMEOUT_SECONDS = 1800.0


@dataclass
class SessionResult:
    """单次 review session 的运行结果."""

    exit_code: int
    duration_seconds: float
    log_path: Path
    final_review_json: dict[str, Any] | None
    """C5 实际 final JSON (含 verdict + findings)."""
    timed_out: bool = False


def _kill_tree(pid: int) -> None:
    """跨平台 kill 整棵进程树 (复用 C2 模式, NC-5 跨平台)."""
    try:
        parent = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return
    for child in parent.children(recursive=True):
        try:
            child.kill()
        except psutil.NoSuchProcess:
            pass
    try:
        parent.kill()
    except psutil.NoSuchProcess:
        pass


def _resolve_claude_cmd(
    claude_cmd: list[str] | None,
    task_id: str,
) -> list[str]:
    """探测 claude CLI; 跟 C2 §7 同 4 个必需 flag.

    Args:
        claude_cmd: injectable mock script for tests; None → 用 shutil.which("claude")
        task_id: error reporting only

    Raises:
        ReviewerError(SESSION_CRASHED): claude CLI 找不到
    """
    if claude_cmd is not None:
        return claude_cmd
    path = shutil.which("claude")
    if not path:
        raise ReviewerError(
            "SESSION_CRASHED",
            "claude CLI not found on PATH (install Claude Code first)",
            tool="claude",
            task_id=task_id,
        )
    # 4 必需 flag (跟 C2 v0.1.3 完全一致, 见 C2 spec §7 Session 调用模式)
    return [
        path,
        "--print",
        "--output-format",
        "stream-json",
        "--verbose",
        "--permission-mode",
        "bypassPermissions",
    ]


# JSON in markdown code block (同 C2)
_CODE_BLOCK_PATTERN = re.compile(r"```(?:json)?\s*\n?(\{.*?\})\s*\n?```", re.DOTALL)
_INLINE_JSON_PATTERN = re.compile(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", re.DOTALL)


def _is_reviewer_final(data: Any) -> bool:
    """Final review JSON 特征: dict 含 verdict + findings."""
    return (
        isinstance(data, dict)
        and "verdict" in data
        and "findings" in data
    )


def _extract_review_json_from_text(text: str) -> dict[str, Any] | None:
    """从 assistant 文本里抽 reviewer final JSON (类似 C2 _extract_json_from_text)."""
    stripped = text.strip()
    if not stripped:
        return None

    if stripped.startswith("{") and stripped.endswith("}"):
        try:
            data: Any = json.loads(stripped)
            if _is_reviewer_final(data):
                return data  # type: ignore[no-any-return]
        except json.JSONDecodeError:
            pass

    for match in _CODE_BLOCK_PATTERN.finditer(text):
        try:
            data = json.loads(match.group(1))
            if _is_reviewer_final(data):
                return data  # type: ignore[no-any-return]
        except json.JSONDecodeError:
            continue

    for match in _INLINE_JSON_PATTERN.finditer(text):
        try:
            data = json.loads(match.group(0))
            if _is_reviewer_final(data):
                return data  # type: ignore[no-any-return]
        except json.JSONDecodeError:
            continue

    return None


def _maybe_parse_final_output(line: str) -> dict[str, Any] | None:
    """检测一行 stream-json event 是否含 reviewer 最终 JSON.

    Claude `--print --output-format stream-json` 多 event 类型 (system / result /
    assistant / etc); final JSON 通常藏在 result.result 或 assistant.message.content[].text.

    解析优先级 (跟 C2 同 3 级):
    1. Top-level JSON (legacy / mock 路径)
    2. result event subtype=success 的 result 字段
    3. assistant event message.content[].text
    """
    stripped = line.strip()
    if not (stripped.startswith("{") and stripped.endswith("}")):
        return None
    try:
        event: Any = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    if not isinstance(event, dict):
        return None

    # 优先 1
    if _is_reviewer_final(event):
        return event

    # 优先 2: result event
    if event.get("type") == "result" and event.get("subtype") == "success":
        result_text = event.get("result", "")
        if isinstance(result_text, str):
            extracted = _extract_review_json_from_text(result_text)
            if extracted is not None:
                return extracted

    # 优先 3: assistant message
    if event.get("type") == "assistant":
        message = event.get("message", {})
        if isinstance(message, dict):
            for content in message.get("content", []):
                if isinstance(content, dict) and content.get("type") == "text":
                    text = content.get("text", "")
                    if isinstance(text, str):
                        extracted = _extract_review_json_from_text(text)
                        if extracted is not None:
                            return extracted

    return None


def run_session(
    *,
    task_id: str,
    prompt: str,
    review_dir: Path,
    session_id: str,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    claude_cmd: list[str] | None = None,
) -> SessionResult:
    """跑一次 C5 review session.

    Args:
        task_id: 关联 task (error reporting / log naming)
        prompt: 已渲染的 review prompt (从 prompt.render_prompt)
        review_dir: 临时 review dir (review_dir / "sessions" / "<session_id>.log")
        session_id: UUID for this session
        timeout_seconds: 超时上限 (默认 1800s = 30 min)
        claude_cmd: injectable mock for tests

    Returns:
        SessionResult — exit_code / duration / log_path / final_review_json / timed_out

    Raises:
        ReviewerError(SESSION_CRASHED): claude CLI 找不到 时
    """
    log_dir = review_dir / "sessions"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{session_id}.log"

    cmd = _resolve_claude_cmd(claude_cmd, task_id)

    start = time.monotonic()
    final_review: dict[str, Any] | None = None
    timed_out_flag = threading.Event()

    with open(log_path, "w", encoding="utf-8") as log_file:
        proc = subprocess.Popen(
            cmd,
            cwd=review_dir,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            shell=False,
            bufsize=1,
            # 跟 C2 session.py 同一个坑: encoding="utf-8" 只管父进程这端的
            # 管道编解码, 子进程自己的 sys.stdin 默认走 locale 编码 ——
            # Windows 非 UTF-8 locale 下读入含中文的 prompt 会用
            # surrogateescape 静默吞掉解不出的字节, 直到子进程后面把它重新
            # 编码 (如落盘) 才炸 UnicodeEncodeError。强制子进程 UTF-8 I/O
            # 从根上避免编解码不对齐; 对真 claude CLI 是无害 no-op。
            env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"},
        )

        if proc.stdin is not None:
            proc.stdin.write(prompt)
            proc.stdin.close()

        def _watchdog() -> None:
            if proc.poll() is None:
                timed_out_flag.set()
                _kill_tree(proc.pid)

        watchdog = threading.Timer(timeout_seconds, _watchdog)
        watchdog.daemon = True
        watchdog.start()

        try:
            if proc.stdout is not None:
                for line in proc.stdout:
                    log_file.write(line)
                    log_file.flush()
                    parsed = _maybe_parse_final_output(line)
                    if parsed is not None:
                        final_review = parsed
        finally:
            watchdog.cancel()
            try:
                exit_code = proc.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                _kill_tree(proc.pid)
                exit_code = -9

    duration = time.monotonic() - start

    return SessionResult(
        exit_code=exit_code,
        duration_seconds=duration,
        log_path=log_path,
        final_review_json=final_review,
        timed_out=timed_out_flag.is_set(),
    )
