"""C2 session — Claude headless CLI 调用 + stream-json + psutil kill.

按 C2 spec §7 Implementation Notes:
- `claude --print --output-format stream-json`
- subprocess.Popen + 实时读 stdout NDJSON
- 落盘 worktree/.suiyin/sessions/attempt-{N}.log (let user tail -f)
- Watchdog timer 强制 kill 整树 (Q2-1: timeout 默认 2h)

跨平台 (C2 spec §7 跨平台节):
- shell=False + list args (避免 Windows shell 语义差异)
- shutil.which 探测 claude binary
- psutil.Process.kill() 跨平台 SIGKILL / TerminateProcess 映射
- pathlib.Path 路径
- encoding='utf-8' 强制
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psutil

from suiyin_flow.c2_executor.schema import TaskExecutorError

# Q2-1 已拍: 单 session 上限 2h, 超时强制 kill -9
DEFAULT_TIMEOUT_SECONDS = 7200.0


@dataclass
class SessionResult:
    """单次 attempt 的 session 结果."""

    exit_code: int
    duration_seconds: float
    log_path: Path
    final_output_json: dict[str, Any] | None
    """实现者最后一行 JSON (含 verify_cmd_exit_code / commit_sha 等)."""
    timed_out: bool = False


def _kill_tree(pid: int) -> None:
    """跨平台 kill 进程树 (整棵子进程也 kill).

    使用 psutil 替代 os.killpg (POSIX only); Windows 上自动映射 TerminateProcess.
    """
    try:
        parent = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return
    # 先 kill children (递归), 再 kill parent
    for child in parent.children(recursive=True):
        try:
            child.kill()
        except psutil.NoSuchProcess:
            pass
    try:
        parent.kill()
    except psutil.NoSuchProcess:
        pass


def _resolve_claude_cmd(claude_cmd: list[str] | None, task_id: str) -> list[str]:
    """探测 claude CLI (默认 PATH 上的 'claude'); 测试时可 inject mock 脚本."""
    if claude_cmd is not None:
        return claude_cmd
    path = shutil.which("claude")
    if not path:
        raise TaskExecutorError(
            "SESSION_CRASHED",
            "claude CLI not found on PATH (install Claude Code first)",
            task_id=task_id,
            tool="claude",
        )
    # Bug 1 fix (v0.1.3): --permission-mode bypassPermissions
    #   C2 是 autonomous 设计, AI 在 worktree 隔离内全自动 (worktree 边界即安全边界).
    #   不加这个 flag 时 Write/Edit/Bash 全被拒, AI 无法做实际工作 → SESSION_CRASHED.
    # Bug 2 fix (v0.1.3): --verbose
    #   Claude CLI 强制要求 `--print + --output-format stream-json` 必须配 --verbose,
    #   不加这个 flag 时 session 启动即报错 "stream-json requires --verbose".
    # (Bug 1+2 由 2026-05-24 阶段 2.C dogfood spike 发现)
    return [
        path,
        "--print",
        "--output-format",
        "stream-json",
        "--verbose",
        "--permission-mode",
        "bypassPermissions",
    ]


# JSON in markdown code block:  ```json\n{...}\n```  (or no language tag)
_CODE_BLOCK_PATTERN = re.compile(r"```(?:json)?\s*\n?(\{.*?\})\s*\n?```", re.DOTALL)

# Inline JSON object (fallback for "just JSON in text"). Use greedy + outermost braces.
_INLINE_JSON_PATTERN = re.compile(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", re.DOTALL)


def _is_implementer_final(data: Any) -> bool:
    """Final JSON 特征: dict 含 task_id 且 含 verify_cmd_exit_code."""
    return (
        isinstance(data, dict)
        and "task_id" in data
        and "verify_cmd_exit_code" in data
    )


def _extract_json_from_text(text: str) -> dict[str, Any] | None:
    """从 assistant 文本里抽 implementer final JSON.

    支持几种形态:
    1. 整个 text 就是 JSON
    2. JSON 在 ```json``` 或 ``` ``` code block 内
    3. JSON 散在 text 中 (fallback, 用 inline pattern)
    """
    stripped = text.strip()
    if not stripped:
        return None

    # 1. Whole text is JSON
    if stripped.startswith("{") and stripped.endswith("}"):
        try:
            data: Any = json.loads(stripped)
            if _is_implementer_final(data):
                # json.loads 返回 Any, _is_implementer_final 已校验 dict 形态
                return data  # type: ignore[no-any-return]
        except json.JSONDecodeError:
            pass

    # 2. Code block JSON (优先, 因为 prompt template 就教 AI 用 ``` 包)
    for match in _CODE_BLOCK_PATTERN.finditer(text):
        try:
            data = json.loads(match.group(1))
            if _is_implementer_final(data):
                return data  # type: ignore[no-any-return]
        except json.JSONDecodeError:
            continue

    # 3. Inline JSON (fallback, 偶尔 AI 不用 code block)
    for match in _INLINE_JSON_PATTERN.finditer(text):
        try:
            data = json.loads(match.group(0))
            if _is_implementer_final(data):
                return data  # type: ignore[no-any-return]
        except json.JSONDecodeError:
            continue

    return None


def _maybe_parse_final_output(line: str) -> dict[str, Any] | None:
    """检测一行 stream-json event 是否含实现者最终 JSON.

    Claude `--print --output-format stream-json` 输出多种 event type:
    - system / rate_limit_event: ignore
    - assistant: message.content[].text 可能含 final JSON
    - result (subtype=success): result 字段是最后 assistant text (优先级最高)
    - Legacy/mock: 整 line 直接是 final JSON

    C2 §4 Prompt 要求实现者 session 最后输出:
        {"task_id": ..., "files_changed": [...], "verify_cmd_exit_code": int, "commit_sha": ...}
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

    # 优先 1: 整 line 直接是 final JSON (legacy / mock path)
    if _is_implementer_final(event):
        return event

    # 优先 2: result event (subtype=success) 的 result 字段
    if event.get("type") == "result" and event.get("subtype") == "success":
        result_text = event.get("result", "")
        if isinstance(result_text, str):
            extracted = _extract_json_from_text(result_text)
            if extracted is not None:
                return extracted

    # 优先 3: assistant message content text
    if event.get("type") == "assistant":
        message = event.get("message", {})
        if isinstance(message, dict):
            for content in message.get("content", []):
                if isinstance(content, dict) and content.get("type") == "text":
                    text = content.get("text", "")
                    if isinstance(text, str):
                        extracted = _extract_json_from_text(text)
                        if extracted is not None:
                            return extracted

    return None


def run_session(
    *,
    task_id: str,
    prompt: str,
    worktree_path: Path,
    attempt: int,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    claude_cmd: list[str] | None = None,
) -> SessionResult:
    """跑一次 Claude headless session.

    Args:
        task_id: for error reporting
        prompt: 已渲染的 prompt 字符串 (由 prompt.render_prompt 产出)
        worktree_path: cwd, AI session 在此运行
        attempt: 1-indexed (log 文件名 attempt-{N}.log)
        timeout_seconds: 超时上限 (默认 2h, Q2-1)
        claude_cmd: injectable claude 命令; 测试用 ['python', 'mock_script.py']

    Returns:
        SessionResult — exit_code / duration / log_path / final_output_json / timed_out

    Raises:
        TaskExecutorError(SESSION_CRASHED) — claude CLI 找不到时
    """
    log_dir = worktree_path / ".suiyin" / "sessions"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"attempt-{attempt}.log"

    cmd = _resolve_claude_cmd(claude_cmd, task_id)

    start = time.monotonic()
    final_output: dict[str, Any] | None = None
    timed_out_flag = threading.Event()

    with open(log_path, "w", encoding="utf-8") as log_file:
        proc = subprocess.Popen(
            cmd,
            cwd=worktree_path,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # merge stderr 到 stdout 简化处理
            text=True,
            encoding="utf-8",
            shell=False,
            bufsize=1,  # line-buffered
        )

        # 写 prompt 到 stdin, 关闭让 Claude 开始
        if proc.stdin is not None:
            proc.stdin.write(prompt)
            proc.stdin.close()

        # Watchdog 在 timeout 后 kill 整树, 子进程死 → stdout EOF → 主循环退出
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
                    # 持续扫描 final output JSON (会被后面的 line 覆盖, 保留最后一个)
                    parsed = _maybe_parse_final_output(line)
                    if parsed is not None:
                        final_output = parsed
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
        final_output_json=final_output,
        timed_out=timed_out_flag.is_set(),
    )
