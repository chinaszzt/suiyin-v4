"""Mutation 探针 — runner (纯机械; 模型零参与).

隔离模型 (C4 "只读" invariant 与 mutation 要改代码的冲突解法, desk E4 现成模式):
- 每个 mutant 在 **throwaway git worktree** 内注入 (detached, 从 ref checkout)
- 跑完即删 (worktree remove --force); 原 worktree / 主树全程零接触
- DB 等运行时隔离靠 env 注入 (--env, 例 lane mongo 的 MONGO_URI), 探针不管服务生命周期

fail-closed 三条 (拍板 1):
- 零适用 mutant (catalog 空由 schema 拦; ref 上 target 全缺) → 不算 pass
- match 失配 (target 里找不到) → apply_failed → fail (catalog stale)
- 测试命令起不来 → error → fail

test_cmd 是用户 shell 命令字符串 → shell=True (同 C7 reverify 先例, ADR-0005 例外)。
"""

from __future__ import annotations

import subprocess
import sys
import uuid
from pathlib import Path

import yaml
from pydantic import ValidationError

from suiyin_flow.mutation.schema import (
    MutantCatalog,
    MutantResult,
    MutantSpec,
    MutationError,
    ProbeReport,
    ProbeVerdict,
)

_TAIL = 2000


def load_catalog(path: Path) -> MutantCatalog:
    if not path.exists() or not path.is_file():
        raise MutationError(
            "CATALOG_NOT_FOUND", f"mutants.yaml not found: {path}", path=str(path)
        )
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise MutationError("INVALID_CATALOG", f"YAML parse error: {e}") from e
    if not isinstance(data, dict):
        raise MutationError("INVALID_CATALOG", "top level must be a mapping")
    try:
        catalog = MutantCatalog.model_validate(data)
    except ValidationError as e:
        raise MutationError(
            "INVALID_CATALOG", f"schema validation failed: {e}"
        ) from e
    for m in catalog.mutants:
        if m.match == m.replacement:
            raise MutationError(
                "INVALID_CATALOG",
                f"mutant {m.mutant_id}: match == replacement (无效变异)",
                mutant_id=m.mutant_id,
            )
    return catalog


# -------------------------------------------------------------------
# throwaway worktree
# -------------------------------------------------------------------


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            shell=False,
            check=False,
        )
    except (subprocess.SubprocessError, FileNotFoundError, OSError) as e:
        raise MutationError("GIT_ERROR", f"git {' '.join(args)}: {e}") from e


def _make_throwaway(repo_root: Path, ref: str) -> Path:
    wt = repo_root / ".suiyin" / "mutation-wt" / uuid.uuid4().hex[:12]
    wt.parent.mkdir(parents=True, exist_ok=True)
    r = _git(repo_root, "worktree", "add", "--detach", str(wt), ref)
    if r.returncode != 0:
        raise MutationError(
            "GIT_ERROR",
            f"throwaway worktree add failed: {r.stderr.strip()[-300:]}",
            ref=ref,
        )
    return wt


def _drop_throwaway(repo_root: Path, wt: Path) -> None:
    r = _git(repo_root, "worktree", "remove", "--force", str(wt))
    if r.returncode != 0:  # best-effort 清理; 失败仅警告
        print(
            f"mutation: warning: throwaway cleanup failed: {wt}", file=sys.stderr
        )


# -------------------------------------------------------------------
# 单 mutant 执行
# -------------------------------------------------------------------


def _apply_mutant(wt: Path, m: MutantSpec) -> str | None:
    """在 throwaway 内做第 N 处字面替换. 返回 None=成功, str=失败原因."""
    target = wt / m.target_file
    if not target.exists():
        return f"target_file not found at ref: {m.target_file}"
    text = target.read_text(encoding="utf-8")
    idx = -1
    for _ in range(m.occurrence):
        idx = text.find(m.match, idx + 1)
        if idx < 0:
            return (
                f"match not found (occurrence {m.occurrence}): {m.match[:80]!r} "
                "— catalog stale?"
            )
    mutated = text[:idx] + m.replacement + text[idx + len(m.match):]
    target.write_text(mutated, encoding="utf-8")
    return None


def _run_test(wt: Path, cmd: str, env_extra: dict[str, str]) -> tuple[int | None, str]:
    """throwaway 内跑杀手测试. 返回 (exit_code|None, output_tail)."""
    import os

    env = {**os.environ, **env_extra}
    try:
        r = subprocess.run(
            cmd,
            cwd=str(wt),
            capture_output=True,
            text=True,
            encoding="utf-8",
            shell=True,  # 用户 shell 命令字符串 (ADR-0005 例外, 同 C7 reverify)
            check=False,
            env=env,
        )
    except OSError as e:
        return None, f"test command failed to start: {e}"
    tail = ((r.stdout or "") + (r.stderr or ""))[-_TAIL:]
    return r.returncode, tail


def run_probe(
    *,
    repo_root: Path,
    catalog_path: Path,
    ref: str,
    env_extra: dict[str, str] | None = None,
) -> ProbeReport:
    """跑完整探针: 每个 mutant 独立 throwaway worktree → 注入 → 杀手测试必须红.

    Raises MutationError (run 级).
    """
    if not repo_root.exists() or not repo_root.is_dir():
        raise MutationError(
            "REPO_ROOT_NOT_FOUND", f"repo_root not a directory: {repo_root}"
        )
    catalog = load_catalog(catalog_path)
    env = env_extra or {}

    results: list[MutantResult] = []
    for m in catalog.mutants:
        results.append(_probe_one(repo_root, ref, m, catalog.default_test_cmd, env))

    killed = sum(1 for r in results if r.outcome == "killed")
    survived = sum(1 for r in results if r.outcome == "survived")
    all_killed = killed == len(results) and killed >= 1
    verdict: ProbeVerdict = "pass" if all_killed else "fail"
    return ProbeReport(
        feature_id=catalog.feature_id,
        ref=ref,
        verdict=verdict,
        results=results,
        survived_count=survived,
        killed_count=killed,
    )


def _probe_one(
    repo_root: Path,
    ref: str,
    m: MutantSpec,
    default_cmd: str,
    env: dict[str, str],
) -> MutantResult:
    wt = _make_throwaway(repo_root, ref)
    try:
        fail_reason = _apply_mutant(wt, m)
        if fail_reason is not None:
            return MutantResult(
                mutant_id=m.mutant_id,
                mutant_class=m.mutant_class,
                target_file=m.target_file,
                outcome="apply_failed",
                output_tail=fail_reason,
            )
        exit_code, tail = _run_test(wt, m.test_cmd or default_cmd, env)
        if exit_code is None:
            outcome = "error"
        elif exit_code == 0:
            outcome = "survived"  # mutant 活 = 测试空心
        else:
            outcome = "killed"
        return MutantResult(
            mutant_id=m.mutant_id,
            mutant_class=m.mutant_class,
            target_file=m.target_file,
            outcome=outcome,  # type: ignore[arg-type]
            test_exit_code=exit_code,
            output_tail=tail,
        )
    finally:
        _drop_throwaway(repo_root, wt)
