"""C1 语义冲突 pass — 可选 AI 增强 (默认关, §3.1 I4 只收紧).

骨架实现: 起一个只读 claude session 判断静态检测漏掉的"会动同一资源"对。
**fallback-safe**: session 任何失败 (crash/timeout/输出不可解析) → 返回空集 +
fallback_reason, 绝不阻塞 plan 产出 (§3.3; 语义 pass 是优化不是正确性)。

prompt 调优等真 dogfood 数据 (Q1); v0.1.0 先把骨架 + fallback 路径钉死。
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

from suiyin_flow.c1_planning.schema import SemanticPassResult
from suiyin_flow.c2_executor.batch import BatchManifest

# 复用 C2 §7 Session 调用模式 4 flag (只读分析, 不写)
_DEFAULT_FLAGS = [
    "--print",
    "--output-format",
    "stream-json",
    "--verbose",
    "--permission-mode",
    "bypassPermissions",
]

_PROMPT = """\
# C1 Planning Engine — Semantic Conflict Pass

你是 C1 的语义冲突分析 pass. **只读分析**, 判断候选并行 task 对会不会动同一资源.

## 候选并行对 (静态检测后同 phase, 需你复核)
{pairs}

## 每个 task 的语义
{tasks}

## 判断标准
逐对判断"并行实现是否会写同一文件 / 改同一接口 / 依赖对方未完成的产物".
**只输出有冲突的对**; 拿不准 = 不输出 (false positive 代价是过度串行, 安全网在 C7,
宁可漏报不误报 —— 注意这跟常规 reviewer 心智相反).

## Output (最后一行, 严格 JSON)
{{"conflicts": [{{"task_a": "T-002", "task_b": "T-003"}}]}}
无冲突则 {{"conflicts": []}}.
"""


def _resolve_cmd(claude_cmd: list[str] | None) -> list[str] | None:
    if claude_cmd is not None:
        return claude_cmd
    path = shutil.which("claude")
    if not path:
        return None
    return [path, *_DEFAULT_FLAGS]


def _render_prompt(
    manifest: BatchManifest, candidate_pairs: list[tuple[str, str]]
) -> str:
    entry_of = {t.task_id: t for t in manifest.tasks}
    pairs = "\n".join(f"- ({a}, {b})" for a, b in candidate_pairs)
    tasks_lines = []
    for tid in sorted({t for pair in candidate_pairs for t in pair}):
        e = entry_of[tid]
        foot = e.modifies or e.context_seeds
        tasks_lines.append(
            f"- {tid}: spec={e.spec_ref} modifies/seeds={foot}"
        )
    return _PROMPT.format(pairs=pairs, tasks="\n".join(tasks_lines))


def _parse_conflicts(stdout: str) -> list[tuple[str, str]] | None:
    """从 session stdout 抽 {"conflicts": [...]}; 不可解析返回 None."""
    found: list[tuple[str, str]] | None = None
    for m in re.finditer(r'\{[^{}]*"conflicts"[^{}]*\[.*?\][^{}]*\}', stdout, re.DOTALL):
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            continue
        conflicts = data.get("conflicts")
        if isinstance(conflicts, list):
            pairs: list[tuple[str, str]] = []
            for c in conflicts:
                if isinstance(c, dict) and isinstance(c.get("task_a"), str) and isinstance(
                    c.get("task_b"), str
                ):
                    pairs.append((c["task_a"], c["task_b"]))
            found = pairs  # 取最后一个合法 conflicts (final answer)
    return found


def run_semantic_pass(
    manifest: BatchManifest,
    repo_root: Path,
    candidate_pairs: list[tuple[str, str]],
    *,
    claude_cmd: list[str] | None = None,
    timeout_seconds: float = 600.0,
) -> tuple[frozenset[frozenset[str]], SemanticPassResult]:
    """跑语义 pass; 返回 (强制冲突对集合, 结果记录).

    I4: 只收紧 —— 返回的对仅限 candidate_pairs (静态同 phase 的), AI 不能放宽。
    fallback-safe: 任何失败 → (空集, completed=False + fallback_reason).
    """
    candidate_set = {frozenset(p) for p in candidate_pairs}

    if not candidate_pairs:
        return frozenset(), SemanticPassResult(completed=True, adjustments=0)

    cmd = _resolve_cmd(claude_cmd)
    if cmd is None:
        return frozenset(), SemanticPassResult(
            completed=False, fallback_reason="claude CLI not found on PATH"
        )

    prompt = _render_prompt(manifest, candidate_pairs)
    try:
        proc = subprocess.run(
            cmd,
            input=prompt,
            cwd=repo_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            shell=False,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return frozenset(), SemanticPassResult(
            completed=False, fallback_reason="semantic session timed out"
        )
    except (OSError, subprocess.SubprocessError) as e:
        return frozenset(), SemanticPassResult(
            completed=False, fallback_reason=f"semantic session failed to start: {e}"
        )

    if proc.returncode != 0:
        return frozenset(), SemanticPassResult(
            completed=False,
            fallback_reason=f"semantic session exited {proc.returncode}",
        )

    parsed = _parse_conflicts(proc.stdout)
    if parsed is None:
        return frozenset(), SemanticPassResult(
            completed=False,
            fallback_reason="semantic session output had no parseable conflicts JSON",
        )

    # I4: 只保留候选集内的对 (AI 越界放宽/乱报的丢弃)
    forced = {frozenset(p) for p in parsed if frozenset(p) in candidate_set}
    return frozenset(forced), SemanticPassResult(
        completed=True, adjustments=len(forced)
    )
