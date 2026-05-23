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
    return [path, "--print", "--output-format", "stream-json"]


def _maybe_parse_final_output(line: str) -> dict[str, Any] | None:
    """检测一行是否是实现者的最终 JSON 输出.

    C2 §4 Prompt 要求实现者 session 最后一行输出:
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
    # 实现者 final JSON 特征: 含 task_id 且 含 verify_cmd_exit_code
    if "task_id" in event and "verify_cmd_exit_code" in event:
        return event
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
