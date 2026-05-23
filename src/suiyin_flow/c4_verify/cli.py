"""CLI entry: `suiyin-flow verify run`.

P0 子命令仅含 `verify run`. 未来 (C2) 加 `task run` / `task list`.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from suiyin_flow.c4_verify.contract import (
    Level,
    LevelReportSkipped,
    LevelsReport,
    Target,
    TargetPr,
    TargetWorktree,
    ToolchainHints,
    VerifyContractError,
    VerifyInput,
)
from suiyin_flow.c4_verify.report import build_report, write_report
from suiyin_flow.c4_verify.runners import flutter as flutter_runner
from suiyin_flow.c4_verify.runners import pytest as pytest_runner

# spec.md §5 标题匹配，宽松匹配 (允许有无空格 / 不同前缀)
_AC_SECTION_PATTERN = re.compile(r"^##\s+5\.\s+Acceptance Criteria", re.MULTILINE)
_AC_ENTRY_PATTERN = re.compile(r"\bAC-\d+\b")


def validate_spec_has_ac_section(spec_path: Path) -> None:
    """SPEC_PARSE_FAILED: spec.md 不存在/缺 §5/§5 内无 AC-N 编号.

    P0 仅做最小校验; L3 (P3+) 会解析具体 AC 集合做 coverage 比对.
    """
    if not spec_path.exists():
        raise VerifyContractError(
            "SPEC_PARSE_FAILED",
            f"Spec file not found: {spec_path}",
            spec_ref=str(spec_path),
        )
    content = spec_path.read_text(encoding="utf-8")
    if not _AC_SECTION_PATTERN.search(content):
        raise VerifyContractError(
            "SPEC_PARSE_FAILED",
            "Spec missing '## 5. Acceptance Criteria' section",
            spec_ref=str(spec_path),
        )
    if not _AC_ENTRY_PATTERN.search(content):
        raise VerifyContractError(
            "SPEC_PARSE_FAILED",
            "Spec §5 contains no AC-N entries",
            spec_ref=str(spec_path),
        )


def _build_target(args: argparse.Namespace) -> Target:
    if args.target == "worktree":
        if not args.worktree_path:
            raise SystemExit("--worktree-path required when --target worktree")
        return TargetWorktree(worktree_path=str(Path(args.worktree_path).resolve()))
    if args.target == "pr":
        if not args.pr_ref:
            raise SystemExit("--pr-ref required when --target pr")
        return TargetPr(pr_ref=args.pr_ref)
    raise SystemExit(f"Unknown --target: {args.target}")


def _detect_languages(repo_root: Path) -> list[str]:
    """自动探测语言 (when toolchain_hints 没传)."""
    detected: list[str] = []
    if (repo_root / "pyproject.toml").exists():
        detected.append("python")
    if (repo_root / "pubspec.yaml").exists():
        detected.append("dart")
    return detected


def run_verify(verify_input: VerifyInput) -> int:
    """跑一次 verify, 落盘 verify_report.json, 返回 process exit code."""
    # I6: 显式请求 L3/L4/L5 → LEVEL_NOT_IMPLEMENTED (不静默 skip)
    for level in verify_input.levels:
        if level in ("L3", "L4", "L5"):
            raise VerifyContractError(
                "LEVEL_NOT_IMPLEMENTED",
                f"Level {level} not implemented in P0; available: L1, L2",
                requested_level=level,
            )

    # 探测 / 选 runner. 用 set[str] 避免 mypy 对 Literal list 的 invariant 报错.
    repo_root = Path(verify_input.repo_root)
    hints = verify_input.toolchain_hints
    languages: set[str] = set(hints.languages) if hints else set()
    if not languages:
        languages.update(_detect_languages(repo_root))

    if "python" in languages:
        l1_fn = pytest_runner.run_l1
        l2_fn = pytest_runner.run_l2
    elif "dart" in languages:
        l1_fn = flutter_runner.run_l1
        l2_fn = flutter_runner.run_l2
    else:
        raise VerifyContractError(
            "TOOLCHAIN_NOT_FOUND",
            "Could not detect Python or Dart project (no pyproject.toml / pubspec.yaml)",
            languages=sorted(languages),
        )

    # Target root: worktree 跑 worktree_path 内，pr 跑 repo_root
    target_root = (
        Path(verify_input.target.worktree_path)
        if verify_input.target.kind == "worktree"
        else repo_root
    )

    # 跑各 level
    levels_report = LevelsReport()
    if "L1" in verify_input.levels:
        levels_report.L1 = l1_fn(target_root)
    if "L2" in verify_input.levels:
        levels_report.L2 = l2_fn(target_root)

    # 未请求的 level 标 skipped (清晰)
    for level_name in ("L3", "L4", "L5"):
        if level_name not in verify_input.levels:
            setattr(levels_report, level_name, LevelReportSkipped())

    # 组装 + 落盘
    report = build_report(
        target=verify_input.target,
        task_id=verify_input.task_id,
        levels=levels_report,
        requested_acs=verify_input.ac_list,
    )

    output_dir = target_root / ".suiyin" / "verify"
    latest_path = write_report(report, output_dir)

    print(f"verify_report → {latest_path}")
    print(f"overall_verdict: {report.overall_verdict}")
    print(
        f"ac_summary: covered={len(report.ac_summary.covered)} "
        f"missing={len(report.ac_summary.missing)} "
        f"violations={len(report.ac_summary.multi_ac_violations)}"
    )

    return 0 if report.overall_verdict == "pass" else 1


def _make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="suiyin-flow", description="碎银 v4 SDD 工具链 CLI"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    verify_parser = subparsers.add_parser("verify", help="C4 Verify Contract")
    verify_sub = verify_parser.add_subparsers(dest="verify_command", required=True)

    run_parser = verify_sub.add_parser("run", help="跑一次 verify")
    run_parser.add_argument("--target", choices=["worktree", "pr"], required=True)
    run_parser.add_argument("--worktree-path", help="target=worktree 时必填")
    run_parser.add_argument("--pr-ref", help="target=pr 时必填")
    run_parser.add_argument(
        "--spec", dest="spec_ref", required=True, help="spec.md 路径"
    )
    run_parser.add_argument(
        "--ac", dest="ac_list", action="append", default=[], help="AC-N 编号 (可重复)"
    )
    run_parser.add_argument(
        "--level",
        dest="levels",
        action="append",
        choices=["L1", "L2", "L3", "L4", "L5"],
        default=[],
    )
    run_parser.add_argument("--repo-root", required=True)
    run_parser.add_argument("--task-id")
    run_parser.add_argument(
        "--language",
        dest="languages",
        action="append",
        default=[],
        choices=["python", "dart", "typescript", "javascript", "go", "rust"],
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _make_parser()
    args = parser.parse_args(argv)

    if args.command != "verify" or args.verify_command != "run":
        parser.print_help()
        return 2

    try:
        target = _build_target(args)
        levels: list[Level] = list(args.levels) if args.levels else ["L1", "L2"]
        verify_input = VerifyInput(
            target=target,
            task_id=args.task_id,
            spec_ref=args.spec_ref,
            ac_list=args.ac_list,
            levels=levels,
            repo_root=str(Path(args.repo_root).resolve()),
            toolchain_hints=(
                ToolchainHints(languages=args.languages) if args.languages else None
            ),
        )
        return run_verify(verify_input)
    except VerifyContractError as e:
        print(f"ERROR {e.error.code}: {e.error.message}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
