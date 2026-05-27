"""Shared fixtures for C6 Gate Contract AC tests.

Strategy: real git repo (for ff_check) + mock `gh` CLI on PATH (for label/comment).

C6 不调 Claude → 无 mock claude session 需求 (跟 C4 测试同纯度，比 C5 简单)。
"""

from __future__ import annotations

import json
import os
import subprocess
import textwrap
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest


def _git(repo: Path, *args: str) -> str:
    res = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        shell=False,
    )
    return res.stdout


@pytest.fixture
def fixture_repo(tmp_path: Path) -> Path:
    """最小 git repo + 真 bare origin remote + main + feature 分支 (ff 可达).

    Returns repo path. AC-9 真 merge 路径需要可用的 origin remote (本地 bare repo).
    """
    bare = tmp_path / "origin.git"
    subprocess.run(
        ["git", "init", "--bare", "-b", "main", str(bare)],
        check=True, capture_output=True, text=True,
    )

    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "t@t.local")
    _git(repo, "config", "user.name", "t")
    _git(repo, "config", "commit.gpgsign", "false")
    _git(repo, "remote", "add", "origin", str(bare))

    (repo / "README.md").write_text("# initial\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "initial main")
    _git(repo, "push", "-u", "origin", "main")

    # feature 分支 — base 是 main, 加一个 commit (ff 可达)
    _git(repo, "checkout", "-b", "feature")
    (repo / "feature.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "feat")
    _git(repo, "checkout", "main")
    return repo


@pytest.fixture
def fixture_repo_worktree(tmp_path: Path) -> tuple[Path, Path]:
    """Bug 1 fixture: 主仓 checkout main + 子 worktree checkout feature.

    复现 Bug 1 场景：父 worktree 一直占着 main，子 worktree 跑 ff_merge_to_main
    时旧 impl `git checkout main` 会 fail。新 refs-direct impl 不 checkout，
    应成功。

    Returns: (parent_repo, child_worktree)
    """
    bare = tmp_path / "origin.git"
    subprocess.run(
        ["git", "init", "--bare", "-b", "main", str(bare)],
        check=True, capture_output=True, text=True,
    )

    parent = tmp_path / "parent"
    parent.mkdir()
    _git(parent, "init", "-b", "main")
    _git(parent, "config", "user.email", "t@t.local")
    _git(parent, "config", "user.name", "t")
    _git(parent, "config", "commit.gpgsign", "false")
    _git(parent, "remote", "add", "origin", str(bare))
    (parent / "README.md").write_text("# init\n", encoding="utf-8")
    _git(parent, "add", ".")
    _git(parent, "commit", "-m", "init main")
    _git(parent, "push", "-u", "origin", "main")

    # 子 worktree on feature — 父 worktree 仍 checkout main (Bug 1 复现条件)
    child = tmp_path / "child-worktree"
    _git(parent, "worktree", "add", "-b", "feature", str(child))
    (child / "feature.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    _git(child, "add", ".")
    _git(child, "commit", "-m", "feat")

    return (parent, child)


@pytest.fixture
def fixture_repo_diverged(tmp_path: Path) -> Path:
    """跟 fixture_repo 类似但 main 也 advance 了 → feature 不是 ff 可达."""
    bare = tmp_path / "origin.git"
    subprocess.run(
        ["git", "init", "--bare", "-b", "main", str(bare)],
        check=True, capture_output=True, text=True,
    )

    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "t@t.local")
    _git(repo, "config", "user.name", "t")
    _git(repo, "config", "commit.gpgsign", "false")
    _git(repo, "remote", "add", "origin", str(bare))

    (repo / "README.md").write_text("# initial\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "initial main")
    _git(repo, "push", "-u", "origin", "main")

    _git(repo, "checkout", "-b", "feature")
    (repo / "feature.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "feat")

    # main advance — feature 不再是 ff
    _git(repo, "checkout", "main")
    (repo / "main_only.py").write_text("def m():\n    return 2\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "main moved")
    _git(repo, "push", "origin", "main")
    return repo


def _write_report(path: Path, payload: Mapping[str, Any]) -> Path:
    path.write_text(json.dumps(dict(payload), indent=2), encoding="utf-8")
    return path


@pytest.fixture
def verify_report_pass(tmp_path: Path) -> Path:
    """C4 verify_report.json with overall_verdict=pass (§3.1 I1 字段名)."""
    return _write_report(
        tmp_path / "verify_pass.json",
        {
            "target": "fixture",
            "overall_verdict": "pass",
            "levels": [],
            "ac_summary": {"covered": [], "missing": []},
            "generated_at": "2026-05-25T12:00:00Z",
            "contract_version": "v0.1.2",
        },
    )


@pytest.fixture
def verify_report_fail(tmp_path: Path) -> Path:
    return _write_report(
        tmp_path / "verify_fail.json",
        {
            "target": "fixture",
            "overall_verdict": "fail",
            "levels": [],
            "ac_summary": {"covered": [], "missing": []},
            "generated_at": "2026-05-25T12:00:00Z",
            "contract_version": "v0.1.2",
        },
    )


@pytest.fixture
def verify_report_missing_field(tmp_path: Path) -> Path:
    """缺 overall_verdict 字段 → AC-6b INVALID_REPORT."""
    return _write_report(
        tmp_path / "verify_missing.json",
        {"target": "fixture", "levels": []},  # no overall_verdict
    )


@pytest.fixture
def review_report_approve(tmp_path: Path) -> Path:
    return _write_report(
        tmp_path / "review_approve.json",
        {
            "verdict": "approve",
            "findings": [],
            "reviewed_at": "2026-05-25T12:00:00Z",
            "session_id": "test-sess",
            "task_id": "T-test",
            "pr_ref": "feature",
            "contract_version": "v0.1.1",
        },
    )


@pytest.fixture
def review_report_block(tmp_path: Path) -> Path:
    return _write_report(
        tmp_path / "review_block.json",
        {
            "verdict": "block",
            "findings": [
                {
                    "severity": "high",
                    "category": "nc_violation",
                    "location": "src/foo.py:42",
                    "suggested_fix": "remove the violation",
                },
                {
                    "severity": "medium",
                    "category": "spec_drift",
                    "location": "spec.md §3.1",
                    "suggested_fix": "align with C2 contract",
                },
            ],
            "reviewed_at": "2026-05-25T12:00:00Z",
            "session_id": "test-sess",
            "task_id": "T-test",
            "pr_ref": "33",
            "contract_version": "v0.1.1",
        },
    )


@pytest.fixture
def feature_sha(fixture_repo: Path) -> str:
    """Resolve feature branch HEAD SHA — 给 mock gh 用 (pr_ref=33 时 gh 返这个)."""
    return _git(fixture_repo, "rev-parse", "feature").strip()


@pytest.fixture
def feature_sha_diverged(fixture_repo_diverged: Path) -> str:
    """同 feature_sha 但用 diverged repo."""
    return _git(fixture_repo_diverged, "rev-parse", "feature").strip()


@pytest.fixture
def mock_gh_on_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """放一个 Python mock gh 到 PATH — 记录调用、可控制返回码.

    Mock 行为:
      - `gh pr view <id> --json headRefOid -q .headRefOid` → 输出固定 sha (来自 env)
      - `gh pr view <id> --json labels -q .labels[].name` → 输出 labels (env)
      - `gh pr edit <id> --add-label "human:block"` → exit 0 + append 到 log
      - `gh pr comment <id> --body <body>` → exit 0 + append 到 log + 输出 comment URL

    Env vars (test 设置):
      C6_MOCK_GH_SHA       — headRefOid 返回值
      C6_MOCK_GH_LABELS    — labels (newline-separated)
      C6_MOCK_GH_LABEL_FAIL — 设了就 label add 返回 1
      C6_MOCK_GH_COMMENT_FAIL — 设了就 comment 返回 1
      C6_MOCK_GH_FAIL_RESOLVE_N — fail 前 N 次 `pr view --json headRefOid` 调用
                                  (Bug 2 retry 测试用), 计数文件 C6_MOCK_GH_RESOLVE_COUNTER
      C6_MOCK_GH_FAIL_LABELS_N  — fail 前 N 次 `pr view --json labels` 调用
                                  (Bug 2 retry 测试用), 计数文件 C6_MOCK_GH_LABELS_COUNTER
      C6_MOCK_GH_LOG       — 调用 log 文件路径
    """
    bin_dir = tmp_path / "mock_bin"
    bin_dir.mkdir()
    gh_path = bin_dir / "gh"
    script = textwrap.dedent(
        """\
        #!/usr/bin/env python3
        import os, sys, json
        args = sys.argv[1:]
        log_path = os.environ.get("C6_MOCK_GH_LOG")
        if log_path:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(" ".join(args) + "\\n")

        def _consume_fail_counter(env_n, counter_env):
            \"\"\"Returns True if this call should fail (and increments counter).\"\"\"
            n_str = os.environ.get(env_n, "")
            counter = os.environ.get(counter_env, "")
            if not n_str or not counter:
                return False
            try:
                n = int(n_str)
            except ValueError:
                return False
            cur = 0
            if os.path.exists(counter):
                try:
                    cur = int(open(counter).read().strip() or "0")
                except ValueError:
                    cur = 0
            if cur < n:
                with open(counter, "w") as f:
                    f.write(str(cur + 1))
                return True
            return False

        # gh pr view <id> --json <field> -q <expr>
        if len(args) >= 5 and args[0] == "pr" and args[1] == "view":
            json_field = args[4] if args[3] == "--json" else ""
            if json_field == "headRefOid":
                if _consume_fail_counter("C6_MOCK_GH_FAIL_RESOLVE_N", "C6_MOCK_GH_RESOLVE_COUNTER"):
                    print('Post "https://api.github.com/graphql": EOF', file=sys.stderr)
                    sys.exit(1)
                print(os.environ.get("C6_MOCK_GH_SHA", "deadbeef"))
                sys.exit(0)
            if json_field == "labels":
                if _consume_fail_counter("C6_MOCK_GH_FAIL_LABELS_N", "C6_MOCK_GH_LABELS_COUNTER"):
                    print('Post "https://api.github.com/graphql": EOF', file=sys.stderr)
                    sys.exit(1)
                labels = os.environ.get("C6_MOCK_GH_LABELS", "")
                if labels:
                    print(labels)
                sys.exit(0)
        # gh pr edit <id> --add-label "human:block"
        if len(args) >= 3 and args[0] == "pr" and args[1] == "edit":
            if os.environ.get("C6_MOCK_GH_LABEL_FAIL"):
                print("forbidden", file=sys.stderr)
                sys.exit(1)
            print("ok")
            sys.exit(0)
        # gh pr comment <id> --body <body>
        if len(args) >= 3 and args[0] == "pr" and args[1] == "comment":
            if os.environ.get("C6_MOCK_GH_COMMENT_FAIL"):
                print("comment too long", file=sys.stderr)
                sys.exit(1)
            print("https://github.com/test/test/pull/33#issuecomment-fake")
            sys.exit(0)
        print(f"mock gh: unknown args {args}", file=sys.stderr)
        sys.exit(2)
        """
    )
    gh_path.write_text(script, encoding="utf-8")
    gh_path.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    # 默认空 labels
    monkeypatch.setenv("C6_MOCK_GH_LABELS", "")
    log_file = tmp_path / "gh.log"
    log_file.write_text("", encoding="utf-8")
    monkeypatch.setenv("C6_MOCK_GH_LOG", str(log_file))
    # Bug 2 retry 计数文件路径 — 每个 mock fixture instance 独立
    monkeypatch.setenv("C6_MOCK_GH_RESOLVE_COUNTER", str(tmp_path / "_resolve_counter.txt"))
    monkeypatch.setenv("C6_MOCK_GH_LABELS_COUNTER", str(tmp_path / "_labels_counter.txt"))
    # Bug 2 retry: 跑测试时不要真 sleep（指数退避 7s 会拖慢测试套件）
    monkeypatch.setenv("C6_GH_RETRY_NO_SLEEP", "1")
    return log_file


@pytest.fixture
def no_gh_on_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """PATH 不含 gh — 测 fallback / 本地 branch 模式."""
    bin_dir = tmp_path / "empty_bin"
    bin_dir.mkdir()
    # PATH 只放空目录 + system git 所在的目录
    git_dir = ""
    for p in os.environ["PATH"].split(os.pathsep):
        if (Path(p) / "git").exists() or (Path(p) / "git.exe").exists():
            git_dir = p
            break
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{git_dir}")
