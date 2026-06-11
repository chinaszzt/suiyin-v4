#!/usr/bin/env python3
"""T-009 mini-dogfood — C1 Planning Engine.

按 dogfood/T-009/spec.md 4 场景. Run:

    PYTHONPATH=src python dogfood/T-009/run.py

Output:
    - dogfood/T-009/results/README.md (汇总)
    - dogfood/T-009/results/1-r3-plan.json / 1-r3-rewritten.yaml 等 evidence
    - 退出码 0 = 全 pass
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

WORKTREE_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = WORKTREE_ROOT / "dogfood" / "T-009" / "fixtures"
RESULTS_DIR = WORKTREE_ROOT / "dogfood" / "T-009" / "results"
SUIYIN_FLOW_CMD = [sys.executable, "-m", "suiyin_flow.cli"]


def _run_cli(args: list[str]) -> tuple[int, str, str]:
    proc = subprocess.run(
        SUIYIN_FLOW_CMD + args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        shell=False,
        check=False,
        env={**__import__("os").environ, "PYTHONPATH": str(WORKTREE_ROOT / "src")},
    )
    return proc.returncode, proc.stdout, proc.stderr


def main() -> int:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    all_pass = True
    lines: list[str] = ["# T-009 mini-dogfood results — C1 Planning Engine", ""]

    def check(ok: bool, label: str) -> None:
        nonlocal all_pass
        if not ok:
            all_pass = False
        lines.append(f"  {'✓' if ok else '✗'} {label}")

    tmp_root = Path(tempfile.mkdtemp(prefix="t009-"))
    try:
        # ============================================================
        # 场景 1: r3 依赖链重生成 (AC-1 真实版)
        # ============================================================
        lines.append("## Scenario 1: r3 5-task 依赖链重生成 (modifies 声明版)")
        y = tmp_root / "login-core-r3.yaml"
        shutil.copy(FIXTURE_DIR / "login-core-r3.yaml", y)
        rc, out, err = _run_cli(
            ["plan", "run", "--tasks-yaml", str(y), "--repo-root", str(tmp_root)]
        )
        (RESULTS_DIR / "1-r3-plan.json").write_text(out, encoding="utf-8")
        check(rc == 0, f"exit 0 (got {rc}); stderr={err.strip()[:120]}")
        try:
            payload = json.loads(out)
        except json.JSONDecodeError:
            payload = {}
            check(False, "stdout JSON 可解析")
        plan = [(e["phase"], e["parallel"]) for e in payload.get("execution_plan", [])]
        expected = [
            (1, ["T-001"]),
            (2, ["T-002", "T-003", "T-004"]),
            (3, ["T-005"]),
        ]
        check(plan == expected, f"复现 r3 手写 3-phase 计划: {plan}")
        check(payload.get("phases_count") == 3, "phases_count == 3")
        check(payload.get("conflict_splits") == [], "无冲突拆分 (modifies 互不重叠)")
        # 写回文件给 C7 重读 (AC-5/6)
        shutil.copy(y, RESULTS_DIR / "1-r3-rewritten.yaml")
        from suiyin_flow.c7_coordinator.plan import load_manifest_and_plan

        try:
            _m, phases, base = load_manifest_and_plan(y)
            check(
                len(phases) == 3 and base == "claude/login-core-r3",
                f"C7 重读写回文件 OK: {len(phases)} phases base={base}",
            )
        except Exception as e:  # dogfood 兜底报告而非崩
            check(False, f"C7 重读抛异常: {type(e).__name__}: {e}")
        lines.append("")

        # ============================================================
        # 场景 2: 幂等 (AC-8)
        # ============================================================
        lines.append("## Scenario 2: 幂等重跑 (AC-8)")
        after_first = y.read_text(encoding="utf-8")
        rc2, _, _ = _run_cli(
            ["plan", "run", "--tasks-yaml", str(y), "--repo-root", str(tmp_root)]
        )
        after_second = y.read_text(encoding="utf-8")
        check(rc2 == 0, "重跑 exit 0")
        check(after_first == after_second, "byte-identical (幂等)")
        from suiyin_flow.c1_planning.planner import MARKER

        check(after_second.count(MARKER) == 1, "marker 不叠加")
        lines.append("")

        # ============================================================
        # 场景 3: I3 FP 实证 / Q1-3 动机 (去 modifies → 过度串行)
        # ============================================================
        lines.append("## Scenario 3: 缺 modifies → context_seeds fallback 过度串行 (I3 FP)")
        y3 = tmp_root / "no-modifies.yaml"
        shutil.copy(FIXTURE_DIR / "login-core-no-modifies.yaml", y3)
        rc3, out3, _ = _run_cli(
            ["plan", "run", "--tasks-yaml", str(y3), "--repo-root", str(tmp_root)]
        )
        (RESULTS_DIR / "3-no-modifies-plan.json").write_text(out3, encoding="utf-8")
        p3 = json.loads(out3)
        phases3 = [(e["phase"], e["parallel"]) for e in p3["execution_plan"]]
        check(rc3 == 0, "exit 0")
        check(
            p3["phases_count"] > 3,
            f"中间三模块被串行化 → phases={p3['phases_count']} > 3 (对比场景1的3): {phases3}",
        )
        check(
            any(s["reason"] == "context_seeds_overlap" for s in p3["conflict_splits"]),
            "conflict_splits 记 context_seeds_overlap (fallback 触发)",
        )
        lines.append(
            "  → 结论: 缺 modifies 时 C1 保守串行 (I3 FP, 安全但慢); "
            "声明 modifies (场景1) 拿回并行。实证 Q1-3 动机。"
        )
        lines.append("")

        # ============================================================
        # 场景 4: 语义 pass fallback (AC-11)
        # ============================================================
        lines.append("## Scenario 4: --semantic-pass + 崩溃 claude → fallback (AC-11)")
        crash = tmp_root / "claude_crash.py"
        crash.write_text(
            textwrap.dedent(
                """\
                import sys
                sys.stdin.read()
                sys.stderr.write("boom\\n")
                sys.exit(1)
                """
            ),
            encoding="utf-8",
        )
        y4 = tmp_root / "sem.yaml"
        shutil.copy(FIXTURE_DIR / "login-core-r3.yaml", y4)
        # 语义 pass 需 claude_cmd 注入 → 程序化 (CLI 不暴露 claude_cmd)
        from suiyin_flow.c1_planning.cli import run_plan

        out4 = run_plan(
            y4,
            tmp_root,
            semantic_pass=True,
            claude_cmd=[sys.executable, str(crash)],
        )
        (RESULTS_DIR / "4-semantic-fallback.json").write_text(
            out4.model_dump_json(indent=2), encoding="utf-8"
        )
        check(out4.status == "written", "崩溃后静态结果仍落盘")
        check(
            out4.semantic_pass is not None and out4.semantic_pass.completed is False,
            "semantic_pass.completed == False",
        )
        check(
            bool(out4.semantic_pass and out4.semantic_pass.fallback_reason),
            "fallback_reason 非空",
        )
        plan4 = [(e["phase"], e["parallel"]) for e in out4.execution_plan]
        check(plan4 == expected, "fallback 后仍是正确的 3-phase 静态计划")
        lines.append("")
    except Exception as e:  # 兜底报告而非崩
        check(False, f"unexpected exception: {type(e).__name__}: {e}")
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)

    lines.append("---")
    lines.append(f"## Overall: {'✓ ALL PASS' if all_pass else '✗ AT LEAST ONE FAILURE'}")
    (RESULTS_DIR / "README.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
