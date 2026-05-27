#!/usr/bin/env python3
"""T-005 mini-dogfood — 跑 C6 真 CLI 评估 4 个场景 + 落 evidence.

按 dogfood/T-005/spec.md AC-401..AC-410 + plan.md 步骤 2-3.

Run:
    python dogfood/T-005/run.py

Output:
    - dogfood/T-005/results/<scenario>-gate_report.json × 4
    - dogfood/T-005/results/README.md (汇总)
    - 退出码 0 = 全 pass，非 0 = 至少一个场景 actual ≠ expected
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

# T-005 worktree root — dogfood 必须从 worktree 跑 (NC-4)
WORKTREE_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = WORKTREE_ROOT / "dogfood" / "T-005" / "fixtures"
RESULTS_DIR = WORKTREE_ROOT / "dogfood" / "T-005" / "results"

# C6 CLI entry — 用 sys.executable 跨平台 (Windows .venv\\Scripts\\python.exe / POSIX .venv/bin/python)
SUIYIN_FLOW_CMD = [sys.executable, "-m", "suiyin_flow.cli"]

# PR #30 = C5 impl merged commit. T-005 用这个作 dogfood target.
PR_REF_URL = "https://github.com/chinaszzt/suiyin-v4/pull/30"

# 场景定义 — 每个场景:
#   - mutate: function 对 fixture dict 做 in-place 改造 (verify / review)
#   - expected_result + expected_reason
#   - pr_ref: 可重写 (e.g. 场景 4 用 diverged ref)
SCENARIOS = [
    {
        "name": "1-baseline-merged",
        "mutate_verify": None,
        "mutate_review": None,
        "expected_result": "merged",
        "expected_reason": None,
        "pr_ref": "feature",  # 本地 branch — 走 git fallback (ff_check 测真 ff)
    },
    {
        "name": "2-verify-fail",
        "mutate_verify": lambda d: d.update({"overall_verdict": "fail"}),
        "mutate_review": None,
        "expected_result": "held",
        "expected_reason": "VERIFY_NOT_PASS",
        "pr_ref": "feature",
    },
    {
        "name": "3-review-block",
        "mutate_verify": None,
        "mutate_review": lambda d: d.update({
            "verdict": "block",
            "findings": [
                {
                    "severity": "high",
                    "category": "nc_violation",
                    "location": "src/foo.py:42",
                    "suggested_fix": "remove NC-1 violation",
                },
                {
                    "severity": "medium",
                    "category": "spec_drift",
                    "location": "docs/sdd/components/c5-ai-reviewer.md §3.1",
                    "suggested_fix": "align with C2 contract",
                },
            ],
        }),
        "expected_result": "held",
        "expected_reason": "REVIEW_NOT_APPROVE",
        "pr_ref": "feature",  # 本地 branch — 避免 gh API 命中真 repo (PR #30 sha 不在 dogfood tmp repo); AC-407 用 run.py 末尾直接调 safe_pr_ref 验
    },
    {
        "name": "4-not-ff-mergeable",
        "mutate_verify": None,
        "mutate_review": None,
        "expected_result": "held",
        "expected_reason": "NOT_FF_MERGEABLE",
        "pr_ref": "feature-diverged",  # 单独的 diverged fixture repo, 见 setup_diverged
    },
]


def load_fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURE_DIR / f"{name}.json").read_text(encoding="utf-8"))


def write_temp_fixture(tmpdir: Path, name: str, data: dict[str, Any]) -> Path:
    path = tmpdir / f"{name}_mutated.json"
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def setup_baseline_repo(tmpdir: Path) -> Path:
    """T-005 临时 git repo + bare origin + feature 分支 (ff 可达).

    跟 tests/c6_gate/conftest.py:fixture_repo 同模式, 但 dogfood 用独立 tmpdir.
    """
    bare = tmpdir / "origin.git"
    subprocess.run(
        ["git", "init", "--bare", "-b", "main", str(bare)],
        check=True, capture_output=True, text=True,
    )
    repo = tmpdir / "repo"
    repo.mkdir()
    def g(*args: str) -> None:
        subprocess.run(
            ["git", "-C", str(repo), *args],
            check=True, capture_output=True, text=True,
        )
    g("init", "-b", "main")
    g("config", "user.email", "t005@t.local")
    g("config", "user.name", "t005")
    g("config", "commit.gpgsign", "false")
    g("remote", "add", "origin", str(bare))
    (repo / "README.md").write_text("# T-005 dogfood baseline\n", encoding="utf-8")
    g("add", ".")
    g("commit", "-m", "initial main")
    g("push", "-u", "origin", "main")
    g("checkout", "-b", "feature")
    (repo / "feat.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    g("add", ".")
    g("commit", "-m", "feat")
    g("checkout", "main")
    return repo


def setup_diverged_repo(tmpdir: Path) -> Path:
    """场景 4 — main 推进了, feature 不是 ff 可达."""
    bare = tmpdir / "origin.git"
    subprocess.run(
        ["git", "init", "--bare", "-b", "main", str(bare)],
        check=True, capture_output=True, text=True,
    )
    repo = tmpdir / "repo"
    repo.mkdir()
    def g(*args: str) -> None:
        subprocess.run(
            ["git", "-C", str(repo), *args],
            check=True, capture_output=True, text=True,
        )
    g("init", "-b", "main")
    g("config", "user.email", "t005@t.local")
    g("config", "user.name", "t005")
    g("config", "commit.gpgsign", "false")
    g("remote", "add", "origin", str(bare))
    (repo / "README.md").write_text("# diverged\n", encoding="utf-8")
    g("add", ".")
    g("commit", "-m", "initial main")
    g("push", "-u", "origin", "main")
    g("checkout", "-b", "feature-diverged")
    (repo / "feat.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    g("add", ".")
    g("commit", "-m", "feat on diverged")
    g("checkout", "main")
    (repo / "main_only.py").write_text("def m():\n    return 2\n", encoding="utf-8")
    g("add", ".")
    g("commit", "-m", "main moved")
    g("push", "origin", "main")
    return repo


def run_scenario(
    scenario: dict[str, Any],
    tmpdir: Path,
) -> dict[str, Any]:
    """跑单个场景 → 返回 {expected, actual, pass, gate_report_path}."""
    name = scenario["name"]
    print(f"\n=== {name} ===")

    # 1. fixture: 拷贝 + 应用 mutator
    verify_data = load_fixture("verify_report")
    review_data = load_fixture("review_report")
    if scenario["mutate_verify"]:
        scenario["mutate_verify"](verify_data)
    if scenario["mutate_review"]:
        scenario["mutate_review"](review_data)
    verify_path = write_temp_fixture(tmpdir, f"{name}-verify", verify_data)
    review_path = write_temp_fixture(tmpdir, f"{name}-review", review_data)

    # 2. setup repo per scenario
    if scenario["pr_ref"] == "feature-diverged":
        repo = setup_diverged_repo(tmpdir / name)
    else:
        repo = setup_baseline_repo(tmpdir / name)

    # 3. 跑 C6 CLI --dry-run
    cmd = [
        *SUIYIN_FLOW_CMD,
        "gate", "run",
        "--pr-ref", scenario["pr_ref"],
        "--verify-report", str(verify_path),
        "--review-report", str(review_path),
        "--repo-root", str(repo),
        "--dry-run",
    ]
    print(f"  cmd: {' '.join(cmd[-9:])}")
    proc = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", check=False,
    )
    print(f"  exit={proc.returncode}")
    print(f"  stdout: {proc.stdout.strip()}")
    if proc.stderr.strip():
        print(f"  stderr: {proc.stderr.strip()}")

    # 4. 读 gate_report.json (从 repo/.suiyin/gates/latest-*.json)
    gates_dir = repo / ".suiyin" / "gates"
    latest_files = sorted(gates_dir.glob("latest-*.json"))
    if not latest_files:
        return {
            "name": name,
            "expected_result": scenario["expected_result"],
            "expected_reason": scenario["expected_reason"],
            "actual": None,
            "pass": False,
            "error": "no gate_report.json found",
            "stderr": proc.stderr,
        }
    report = json.loads(latest_files[0].read_text(encoding="utf-8"))

    # 5. 比对
    ok = (
        report["gate_result"] == scenario["expected_result"]
        and report.get("reason") == scenario["expected_reason"]
    )

    # 6. 拷贝 evidence 到 results/
    evidence_path = RESULTS_DIR / f"{name}-gate_report.json"
    evidence_path.write_text(latest_files[0].read_text(encoding="utf-8"), encoding="utf-8")

    return {
        "name": name,
        "expected_result": scenario["expected_result"],
        "expected_reason": scenario["expected_reason"],
        "actual_result": report["gate_result"],
        "actual_reason": report.get("reason"),
        "rules": report["rules"],
        "recovery_action": report.get("recovery_action"),
        "pass": ok,
        "evidence": str(evidence_path.relative_to(WORKTREE_ROOT)),
    }


def write_summary(results: list[dict[str, Any]]) -> None:
    lines = [
        "# T-005 mini-dogfood results",
        "",
        f"PR #34 (C6 impl v0.1.1) → 4 个 mock pre-merge gate 评估场景。",
        "",
        "| # | Scenario | Expected | Actual | Pass |",
        "|---|---|---|---|---|",
    ]
    for r in results:
        if "expected_result" in r:
            exp = f"{r['expected_result']}/{r['expected_reason'] or '-'}"
            act = f"{r.get('actual_result', '?')}/{r.get('actual_reason') or '-'}"
        else:
            # AC-407 unit-verify shape
            exp = "(safe_pr_ref unit)"
            act = "all cases" if r["pass"] else f"failed: {r.get('failed', [])}"
        check = "✅" if r["pass"] else "❌"
        lines.append(f"| {r['name']} | {exp} | {act} | {check} |")
    lines.extend(
        [
            "",
            "## 详细 evidence",
            "",
        ]
    )
    for r in results:
        lines.append(f"### {r['name']}")
        lines.append("")
        lines.append(f"- evidence: `{r.get('evidence', '(none)')}`")
        lines.append(f"- rules: `{json.dumps(r.get('rules', {}))}`")
        ra = r.get("recovery_action")
        if ra:
            lines.append(f"- recovery_action: `{json.dumps(ra)}`")
        lines.append("")
    lines.extend(
        [
            "## I8 precedence + safe_pr_ref 验证",
            "",
            "- **AC-406 I8 precedence**: dogfood 跳过场景 5 (本地无真 PR API 测 human:block label)，"
            "降级到 unit test `tests/c6_gate/test_acceptance_criteria.py::test_AC_5_i8_precedence_human_block_wins_over_verify_fail` 实证 (PR #34 已绿)。",
            "- **AC-407 safe_pr_ref**: 由独立直接单元验证（'AC-407 safe_pr_ref direct unit verify' 行），"
            "覆盖 URL → `pull-N` / branch → 扁平 / `#N` 去 hash 等 case，断言输出**不含** `/` `:` `?` 等 unsafe chars。"
            "原计划场景 3 用真 URL 走 gh API，但本地 tmp repo 没真 PR sha 会触发 GIT_ERROR；改为本地 branch + 直接调 safe_pr_ref unit verify 保留 AC-407 evidence。",
            "",
            "## 跟 spec AC 映射",
            "",
            "| spec AC | 场景 / unit-test 来源 |",
            "|---|---|",
            "| AC-401, 402 | `.suiyin/fixtures/T-005/{verify,review}_report.json` |",
            "| AC-403 | 4 场景全跑 |",
            "| AC-404 | gate_report 文件名扁平验证 (evidence dir 所有文件名) |",
            "| AC-405 | 场景 3 dry_run + review=block → recovery_action.kind=r1 但 label/comment 字段 absent |",
            "| AC-406 | 降级 unit test (AC-5 in c6_gate tests) |",
            "| AC-407 | 'AC-407 safe_pr_ref direct unit verify' 行 (run.py verify_safe_pr_ref_ac_407) |",
            "| AC-408 | 本目录 dogfood/T-005/results/ |",
            "| AC-409 | run.py 全在 tmpdir + .suiyin/ + dogfood/T-005/results/ 操作 |",
            "| AC-410 | post-dogfood 改 todo.md (caller) |",
            "",
        ]
    )
    (RESULTS_DIR / "README.md").write_text("\n".join(lines), encoding="utf-8")


def verify_safe_pr_ref_ac_407() -> dict[str, Any]:
    """AC-407 验证 — 直接调用 safe_pr_ref，断言 URL 形式 → pull-N 扁平命名."""
    from suiyin_flow.c6_gate.report import safe_pr_ref

    cases = [
        (PR_REF_URL, "pull-30"),
        ("https://github.com/owner/repo/pull/9999", "pull-9999"),
        ("claude/c6-gate-impl", "claude-c6-gate-impl"),
        ("#30", "30"),
        ("30", "30"),
    ]
    bad_chars = ["/", ":", "?", "<", ">", "|", '"', "\\"]
    failed = []
    for inp, expected in cases:
        got = safe_pr_ref(inp)
        ok = got == expected and not any(c in got for c in bad_chars)
        if not ok:
            failed.append({"input": inp, "expected": expected, "got": got})
    return {
        "name": "AC-407 safe_pr_ref direct unit verify",
        "cases": cases,
        "pass": len(failed) == 0,
        "failed": failed,
    }


def main() -> int:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="t005-") as tmp:
        tmpdir = Path(tmp)
        results = [run_scenario(s, tmpdir) for s in SCENARIOS]

    # AC-407 单独验 safe_pr_ref (不依赖 git/gh)
    results.append(verify_safe_pr_ref_ac_407())

    write_summary(results)
    fails = [r for r in results if not r["pass"]]
    print("\n" + "=" * 60)
    print(f"T-005 mini-dogfood done: {len(results) - len(fails)}/{len(results)} pass")
    if fails:
        print("FAILED scenarios:")
        for r in fails:
            if "expected_result" in r:
                print(f"  - {r['name']}: expected {r['expected_result']}/{r['expected_reason']} "
                      f"got {r.get('actual_result')}/{r.get('actual_reason')}")
            else:
                print(f"  - {r['name']}: {r.get('failed', [])}")
        return 1
    print(f"summary: dogfood/T-005/results/README.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
