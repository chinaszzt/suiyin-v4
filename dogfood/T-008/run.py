#!/usr/bin/env python3
"""T-008 mini-dogfood — C2 v0.3.0 R2 retry-with-feedback + I8 worktree 锁.

按 dogfood/T-008/spec.md 3 场景. Run:

    PYTHONPATH=src python dogfood/T-008/run.py

Output:
    - dogfood/T-008/results/README.md (汇总)
    - dogfood/T-008/results/1-round2-prompt.txt 等 evidence
    - 退出码 0 = 全 pass
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
from pathlib import Path

WORKTREE_ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = WORKTREE_ROOT / "dogfood" / "T-008" / "results"

# 把 stdin prompt 落盘到 cwd (= task worktree) 再输出成功 JSON 的假 claude.
# round 文件名靠 argv[1] 区分 (round1 / round2).
_FAKE_CLAUDE_SCRIPT = textwrap.dedent(
    """\
    import json
    import pathlib
    import sys

    tag = sys.argv[1] if len(sys.argv) > 1 else "round"
    prompt = sys.stdin.read()
    pathlib.Path(f"prompt_{tag}.txt").write_text(prompt, encoding="utf-8")
    print(json.dumps({
        "task_id": "T-stub",
        "files_changed": [],
        "verify_cmd_exit_code": 0,
        "commit_sha": "abc1234",
    }))
    """
)

# 伪造的 C5 block report — 按 c5 contract v0.1.1 完整 shape (realism;
# C2 只读 findings 字段, 其余字段供人看 evidence).
_C5_BLOCK_REPORT = {
    "verdict": "block",
    "findings": [
        {
            "severity": "low",
            "category": "reusable_knowledge_not_captured",
            "location": "src/util.py:10",
            "suggested_fix": "extract duplicated parsing into shared helper",
        },
        {
            "severity": "high",
            "category": "spec_drift",
            "location": "src/core.py:42",
            "suggested_fix": "return type must match spec §2.2 (dict, not list)",
        },
    ],
    "reviewed_at": "2026-06-10T00:00:00+00:00",
    "session_id": "00000000-0000-0000-0000-000000000008",
    "task_id": "T-001",
    "pr_ref": "task/T-001",
    "contract_version": "v0.1.1",
}


def _setup_throwaway_repo(repo: Path) -> None:
    """最小 git repo (同 T-006 _setup_throwaway_repo)."""

    def _git(*args: str) -> None:
        subprocess.run(
            ["git", "-C", str(repo), *args],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            shell=False,
        )

    repo.mkdir(parents=True, exist_ok=True)
    _git("init", "-b", "main")
    _git("config", "user.email", "dogfood@suiyin.local")
    _git("config", "user.name", "T-008")
    _git("config", "commit.gpgsign", "false")
    (repo / "spec.md").write_text(
        "# T-008 throwaway spec\n\n## 5. Acceptance Criteria\n\n- **AC-1**: example\n",
        encoding="utf-8",
    )
    (repo / "plan.md").write_text("# Plan\n", encoding="utf-8")
    (repo / "constitution.md").write_text("# Constitution\n", encoding="utf-8")
    (repo / "context.md").write_text("# Context seed\n", encoding="utf-8")
    _git("add", ".")
    _git("commit", "-m", "initial")


def main() -> int:
    try:
        from suiyin_flow.c2_executor.cli import _make_parser, execute_task
        from suiyin_flow.c2_executor.schema import TaskExecutorError, TaskInput
        from suiyin_flow.c2_executor.worktree import ensure_worktree, lock_path_for
    except ImportError as e:
        print(f"import suiyin_flow failed: {e} (跑法: PYTHONPATH=src python {__file__})")
        return 1

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    all_pass = True
    lines: list[str] = ["# T-008 mini-dogfood results", ""]

    def check(ok: bool, label: str) -> None:
        nonlocal all_pass
        if not ok:
            all_pass = False
        lines.append(f"  {'✓' if ok else '✗'} {label}")

    def make_input(repo: Path, **overrides: object) -> TaskInput:
        defaults: dict[str, object] = dict(
            task_id="T-001",
            spec_ref="spec.md",
            plan_ref="plan.md",
            constitution_ref="constitution.md",
            context_seeds=["context.md"],
            verify_cmd="true",
            criticality="medium",
            repo_root=str(repo),
            ac_list=["AC-1"],
            open_pr=False,  # dogfood 不碰 remote
        )
        defaults.update(overrides)
        return TaskInput(**defaults)  # type: ignore[arg-type]

    tmp_root = Path(tempfile.mkdtemp(prefix="t008-"))
    script_path = tmp_root / "fake_claude.py"
    script_path.write_text(_FAKE_CLAUDE_SCRIPT, encoding="utf-8")

    try:
        # ============================================================
        # 场景 1: R2 链路 — round-1 普通跑 → C5 block → round-2 带 feedback
        # ============================================================
        lines.append("## Scenario 1: R2 chain (block → feedback retry)")
        repo = tmp_root / "repo1"
        _setup_throwaway_repo(repo)

        out1 = execute_task(
            make_input(repo),
            claude_cmd=[sys.executable, str(script_path), "round1"],
        )
        wt = Path(out1.worktree_path)
        prompt1 = (wt / "prompt_round1.txt").read_text(encoding="utf-8")
        check(out1.status == "success", "round-1 success")
        check(out1.review_feedback_applied is False, "round-1 applied=false")
        check("上次 Review 发现的问题" not in prompt1, "round-1 prompt 无 feedback 节")

        # 伪造 C5 block report (现实里由 C5 review 产出, 落 .suiyin/reviews/)
        report_path = tmp_root / "review_report.json"
        report_path.write_text(json.dumps(_C5_BLOCK_REPORT), encoding="utf-8")

        out2 = execute_task(
            make_input(repo, review_feedback=str(report_path)),
            claude_cmd=[sys.executable, str(script_path), "round2"],
        )
        prompt2 = (wt / "prompt_round2.txt").read_text(encoding="utf-8")
        shutil.copy(wt / "prompt_round2.txt", RESULTS_DIR / "1-round2-prompt.txt")
        check(out2.status == "success", "round-2 success")
        check(out2.review_feedback_applied is True, "round-2 applied=true")
        check(out2.worktree_path == out1.worktree_path, "worktree 复用 (I1, 不从头重写)")
        check("上次 Review 发现的问题" in prompt2, "round-2 prompt 含 feedback 节")
        check(
            "src/core.py:42" in prompt2 and "src/util.py:10" in prompt2,
            "round-2 prompt 含全部 findings location",
        )
        check(
            prompt2.index("src/core.py:42") < prompt2.index("src/util.py:10"),
            "findings severity 降序 (high 在 low 前)",
        )
        # CLI flag 接线 (subprocess 层只能验到 parser)
        parser = _make_parser()
        ns = parser.parse_args(
            [
                "task", "run", "--task-id", "T-001", "--spec", "s", "--plan", "p",
                "--verify-cmd", "true", "--repo-root", ".",
                "--review-feedback", "r.json",
            ]
        )
        check(ns.review_feedback == "r.json", "CLI --review-feedback flag 接线")
        lines.append("")

        # ============================================================
        # 场景 2: 活跃锁拒跑 (发现 #8)
        # ============================================================
        lines.append("## Scenario 2: live lock rejects run (finding #8)")
        repo = tmp_root / "repo2"
        _setup_throwaway_repo(repo)
        wt2 = ensure_worktree(repo, "T-001", base_branch="main")
        holder = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"], shell=False
        )
        try:
            lock = lock_path_for(wt2)
            lock.parent.mkdir(parents=True, exist_ok=True)
            lock.write_text(
                json.dumps({"pid": holder.pid, "task_id": "T-001"}), encoding="utf-8"
            )
            try:
                execute_task(
                    make_input(repo),
                    claude_cmd=[sys.executable, str(script_path), "locked"],
                )
                check(False, "应 raise WORKTREE_LOCKED (没 raise)")
            except TaskExecutorError as e:
                (RESULTS_DIR / "2-locked-error.json").write_text(
                    e.error.model_dump_json(indent=2), encoding="utf-8"
                )
                check(e.error.code == "WORKTREE_LOCKED", "code == WORKTREE_LOCKED")
                check(
                    e.error.details.get("holder_pid") == holder.pid,
                    "details.holder_pid == 持有者 pid",
                )
            check(
                not (wt2 / ".suiyin" / "sessions").exists(),
                "未启动 session (无 attempt log)",
            )
            check(
                json.loads(lock.read_text(encoding="utf-8"))["pid"] == holder.pid,
                "锁未被动 (仍属持有者)",
            )
        finally:
            holder.kill()
            holder.wait(timeout=10)
        lines.append("")

        # ============================================================
        # 场景 3: stale 锁接管 + 终态释放
        # ============================================================
        lines.append("## Scenario 3: stale lock takeover + release on terminal state")
        repo = tmp_root / "repo3"
        _setup_throwaway_repo(repo)
        wt3 = ensure_worktree(repo, "T-001", base_branch="main")
        dead = subprocess.Popen([sys.executable, "-c", "pass"], shell=False)
        dead.wait(timeout=10)
        time.sleep(0.05)
        lock3 = lock_path_for(wt3)
        lock3.parent.mkdir(parents=True, exist_ok=True)
        lock3.write_text(
            json.dumps({"pid": dead.pid, "task_id": "T-001"}), encoding="utf-8"
        )

        out3 = execute_task(
            make_input(repo),
            claude_cmd=[sys.executable, str(script_path), "stale"],
        )
        check(out3.status == "success", "stale 接管后正常 success")
        check(not lock3.exists(), "终态锁释放 (AC-14)")
        lines.append("")
    except Exception as e:  # dogfood 兜底报告而非崩
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
