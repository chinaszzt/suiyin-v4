"""Independent test author v0.1.0 AC-1..AC-10."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import textwrap
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
import yaml

from suiyin_flow.acgate.gate import load_manifest, run_gate
from suiyin_flow.c5_reviewer.contract import ReviewerError
from suiyin_flow.testauthor.runner import run_author
from suiyin_flow.testauthor.schema import TestAuthorError
from suiyin_flow.treesha import resolve_tree_sha
from tests.fixtures.shell_quote import quote_for_shell


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        shell=False,
    )
    return result.stdout.strip()


@pytest.fixture
def author_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "src_mod").mkdir(parents=True)
    (repo / "tests_dir").mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "testauthor@suiyin.local")
    _git(repo, "config", "user.name", "testauthor")
    _git(repo, "config", "commit.gpgsign", "false")
    (repo / ".gitignore").write_text(".suiyin/\n__pycache__/\n.pytest_cache/\n", encoding="utf-8")
    (repo / "src_mod" / "__init__.py").write_text("", encoding="utf-8")
    (repo / "src_mod" / "thing.py").write_text("VALUE = 1\n", encoding="utf-8")
    (repo / "tests_dir" / "test_old.py").write_text(
        "from src_mod.thing import VALUE\n\n\ndef test_old():\n    assert VALUE == 1\n",
        encoding="utf-8",
    )
    (repo / "spec.md").write_text("# Spec\n\n- AC-NEW: add new behavior\n", encoding="utf-8")
    (repo / "plan.md").write_text("# Plan\n", encoding="utf-8")
    (repo / "constitution.md").write_text("# Constitution\n", encoding="utf-8")
    (repo / "contract.md").write_text("# Contract\n", encoding="utf-8")
    tasks = {
        "schema_version": "v0.2.0",
        "feature_id": "001-demo",
        "tasks": [
            {
                "task_id": "T001",
                "spec_ref": "spec.md",
                "plan_ref": "plan.md",
                "constitution_ref": "constitution.md",
                "context_seeds": [],
                "verify_cmd": f"{quote_for_shell(sys.executable)} -m pytest -q",
                "criticality": "low",
                "ac_list": ["AC-NEW"],
                "modifies": ["src_mod/**", "tests_dir/**"],
                "base_branch": "main",
            }
        ],
    }
    (repo / "tasks.yaml").write_text(
        yaml.safe_dump(tasks, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "base fixture")
    return repo


def _write_targets(repo: Path, target_ids: tuple[str, ...] = ("AC-NEW",)) -> Path:
    path = repo.parent / f"targets-{'-'.join(target_ids)}.yaml"
    payload = {
        "schema_version": "v0.1.0",
        "task_id": "T001",
        "targets": [
            {
                "target_id": target_id,
                "kind": "ac" if target_id.startswith("AC-") else "guard",
                "source": f"spec.md {target_id}",
                "directive": f"prove missing behavior for {target_id}",
                "suggested_test_ref": f"tests_dir/test_new.py::test_{target_id.replace('-', '_')}",
            }
            for target_id in target_ids
        ],
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def _mock_session(
    tmp_path: Path,
    *,
    writes: Mapping[str, str],
    mapping: Mapping[str, list[str]],
    marker: Path | None = None,
) -> list[str]:
    body = textwrap.dedent(
        f"""\
        import json
        import pathlib
        import sys

        prompt = sys.stdin.read()
        worktree_line = next(
            line for line in prompt.splitlines()
            if line.startswith("AUTHOR_WORKTREE: ")
        )
        worktree = pathlib.Path(worktree_line.split(": ", 1)[1])
        marker = {str(marker) if marker is not None else None!r}
        if marker is not None:
            pathlib.Path(marker).write_text("started", encoding="utf-8")
        writes = {dict(writes)!r}
        for relative, content in writes.items():
            destination = worktree / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(content, encoding="utf-8")
        final = {dict(mapping)!r}
        print(json.dumps({{"type": "system", "subtype": "init"}}))
        result = "done\\n```json\\n" + json.dumps(final) + "\\n```"
        print(json.dumps({{
            "type": "result", "subtype": "success", "is_error": False, "result": result
        }}))
        """
    )
    script = tmp_path / f"mock-author-{len(list(tmp_path.glob('mock-author-*.py')))}.py"
    script.write_text(body, encoding="utf-8")
    return [sys.executable, str(script)]


def _red_test(name: str = "test_new_behavior") -> str:
    return (
        "from src_mod.thing import NOT_IMPLEMENTED\n\n\n"
        f"def {name}():\n"
        "    assert NOT_IMPLEMENTED == 42\n"
    )


def _run(
    repo: Path,
    targets: Path,
    claude_cmd: list[str],
    *,
    inputs_manifest: Path | None = None,
) -> Any:
    return run_author(
        repo_root=repo,
        tasks_yaml_path=repo / "tasks.yaml",
        task_id="T001",
        targets_path=targets,
        test_paths=["tests_dir/**"],
        inputs_manifest_path=inputs_manifest,
        claude_cmd=claude_cmd,
    )


def test_AC_1_valid_author_output_passes(author_repo: Path, tmp_path: Path) -> None:
    targets = _write_targets(author_repo)
    mock = _mock_session(
        tmp_path,
        writes={"tests_dir/test_new.py": _red_test()},
        mapping={"AC-NEW": ["tests_dir/test_new.py::test_new_behavior"]},
    )
    report = _run(author_repo, targets, mock)
    assert report.verdict == "pass"
    assert report.path_check.violations == []
    assert report.red_check.red is True
    assert report.frozen is not None
    assert report.freeze_error is None
    assert report.targets[0].status == "authored"


def test_AC_2_out_of_scope_path_fails(author_repo: Path, tmp_path: Path) -> None:
    targets = _write_targets(author_repo)
    mock = _mock_session(
        tmp_path,
        writes={
            "tests_dir/test_new.py": _red_test(),
            "src_mod/thing.py": "VALUE = 2\n",
        },
        mapping={"AC-NEW": ["tests_dir/test_new.py::test_new_behavior"]},
    )
    report = _run(author_repo, targets, mock)
    assert report.verdict == "fail"
    assert report.path_check.violations == ["src_mod/thing.py"]
    assert report.frozen is None


def test_AC_3_green_on_base_fails(author_repo: Path, tmp_path: Path) -> None:
    targets = _write_targets(author_repo)
    green = "def test_already_true():\n    assert 1 == 1\n"
    mock = _mock_session(
        tmp_path,
        writes={"tests_dir/test_new.py": green},
        mapping={"AC-NEW": ["tests_dir/test_new.py::test_already_true"]},
    )
    report = _run(author_repo, targets, mock)
    assert report.red_check.exit_code == 0
    assert report.red_check.red is False
    assert report.verdict == "fail"
    assert report.targets[0].status == "skipped"


def test_AC_4_compile_or_import_failure_counts_as_red(
    author_repo: Path, tmp_path: Path
) -> None:
    targets = _write_targets(author_repo)
    mock = _mock_session(
        tmp_path,
        writes={"tests_dir/test_new.py": _red_test()},
        mapping={"AC-NEW": ["tests_dir/test_new.py::test_new_behavior"]},
    )
    report = _run(author_repo, targets, mock)
    assert report.red_check.exit_code != 0
    assert report.red_check.red is True
    assert report.verdict == "pass"


def test_AC_5_freeze_entries_and_existing_gate_block_deletion(
    author_repo: Path, tmp_path: Path
) -> None:
    targets = _write_targets(author_repo)
    mock = _mock_session(
        tmp_path,
        writes={"tests_dir/test_new.py": _red_test()},
        mapping={"AC-NEW": ["tests_dir/test_new.py::test_new_behavior"]},
    )
    report = _run(author_repo, targets, mock)
    worktree = Path(report.author_worktree)
    assert report.frozen is not None
    manifest_path = worktree / report.frozen.manifest_path
    manifest = load_manifest(manifest_path)
    entry = next(item for item in manifest.entries if item.ac_id == "AC-NEW")
    assert len(entry.test_hash) == 64
    assert all(character in "0123456789abcdef" for character in entry.test_hash)
    frozen_commit = _git(worktree, "rev-parse", "HEAD")
    _git(worktree, "rm", "tests_dir/test_new.py")
    _git(worktree, "commit", "-m", "delete frozen test")
    gate = run_gate(
        repo_root=worktree,
        manifest_path=manifest_path,
        base_ref=frozen_commit,
        head_ref="HEAD",
    )
    assert gate.verdict == "block"
    assert any(finding.kind == "TEST_FILE_DELETED" for finding in gate.findings)


def test_AC_6_empty_or_malformed_targets_fail_before_session(
    author_repo: Path, tmp_path: Path
) -> None:
    marker = tmp_path / "session-started"
    mock = _mock_session(tmp_path, writes={}, mapping={}, marker=marker)
    empty = tmp_path / "empty.yaml"
    empty.write_text("schema_version: v0.1.0\ntask_id: T001\ntargets: []\n", encoding="utf-8")
    malformed = tmp_path / "malformed.yaml"
    malformed.write_text("targets: [\n", encoding="utf-8")
    for path in (empty, malformed):
        with pytest.raises(TestAuthorError) as caught:
            _run(author_repo, path, mock)
        assert caught.value.error.code == "TESTAUTHOR_TARGETS_INVALID"
    assert not marker.exists()


def test_AC_6b_invalid_target_id_fails_before_session_with_prefix_hint(
    author_repo: Path, tmp_path: Path
) -> None:
    marker = tmp_path / "session-started-invalid-id"
    mock = _mock_session(tmp_path, writes={}, mapping={}, marker=marker)
    targets = _write_targets(author_repo, ("SEAM-INGEST-OPTS-FACE",))

    with pytest.raises(TestAuthorError) as caught:
        _run(author_repo, targets, mock)

    assert caught.value.error.code == "TESTAUTHOR_TARGETS_INVALID"
    assert "AC- or GUARD-" in caught.value.error.message
    assert not marker.exists()


def test_AC_7_partial_output_reports_skipped_but_can_pass(
    author_repo: Path, tmp_path: Path
) -> None:
    targets = _write_targets(author_repo, ("AC-NEW", "GUARD-NEW"))
    mock = _mock_session(
        tmp_path,
        writes={"tests_dir/test_new.py": _red_test()},
        mapping={"AC-NEW": ["tests_dir/test_new.py::test_new_behavior"]},
    )
    report = _run(author_repo, targets, mock)
    assert report.verdict == "pass"
    statuses = {target.target_id: target.status for target in report.targets}
    assert statuses == {"AC-NEW": "authored", "GUARD-NEW": "skipped"}
    skipped = next(target for target in report.targets if target.status == "skipped")
    assert skipped.note


def test_AC_8_report_has_base_tree_sha(author_repo: Path, tmp_path: Path) -> None:
    targets = _write_targets(author_repo)
    expected = resolve_tree_sha(author_repo, "main")
    mock = _mock_session(
        tmp_path,
        writes={"tests_dir/test_new.py": _red_test()},
        mapping={"AC-NEW": ["tests_dir/test_new.py::test_new_behavior"]},
    )
    report = _run(author_repo, targets, mock)
    assert report.target_tree_sha == expected


def _tracked_tree_hash(repo: Path) -> str:
    digest = hashlib.sha256()
    for relative in _git(repo, "ls-files").splitlines():
        digest.update(relative.encode("utf-8"))
        digest.update((repo / relative).read_bytes())
    return digest.hexdigest()


def test_AC_9_main_worktree_unchanged_and_author_handoff_retained(
    author_repo: Path, tmp_path: Path
) -> None:
    targets = _write_targets(author_repo)
    before_status = _git(author_repo, "status", "--porcelain")
    before_hash = _tracked_tree_hash(author_repo)
    mock = _mock_session(
        tmp_path,
        writes={"tests_dir/test_new.py": _red_test()},
        mapping={"AC-NEW": ["tests_dir/test_new.py::test_new_behavior"]},
    )
    report = _run(author_repo, targets, mock)
    assert _git(author_repo, "status", "--porcelain") == before_status
    assert _tracked_tree_hash(author_repo) == before_hash
    assert Path(report.author_worktree).is_dir()
    assert _git(author_repo, "show-ref", "--verify", f"refs/heads/{report.author_branch}")


@pytest.mark.parametrize("mode", ["missing", "drift"])
def test_AC_10_typed_inputs_fail_closed_before_session(
    author_repo: Path, tmp_path: Path, mode: str
) -> None:
    targets = _write_targets(author_repo)
    marker = tmp_path / f"started-{mode}"
    mock = _mock_session(tmp_path, writes={}, mapping={}, marker=marker)
    entry: dict[str, Any] = {
        "kind": "contract",
        "path": "missing.md" if mode == "missing" else "contract.md",
    }
    if mode == "drift":
        entry["content_sha256"] = "0" * 64
    inputs = tmp_path / f"inputs-{mode}.yaml"
    inputs.write_text(
        yaml.safe_dump({"schema_version": "v0.1.0", "inputs": [entry]}),
        encoding="utf-8",
    )
    with pytest.raises(ReviewerError) as caught:
        _run(author_repo, targets, mock, inputs_manifest=inputs)
    expected = "REVIEW_INPUT_MISSING" if mode == "missing" else "REVIEW_INPUT_HASH_DRIFT"
    assert caught.value.error.code == expected
    assert not marker.exists()


def test_AC_11_freeze_failure_reports_diagnostic(
    author_repo: Path, tmp_path: Path
) -> None:
    (author_repo / "ac-manifest.yaml").write_text("entries: [\n", encoding="utf-8")
    _git(author_repo, "add", "ac-manifest.yaml")
    _git(author_repo, "commit", "-m", "add malformed manifest")
    targets = _write_targets(author_repo)
    mock = _mock_session(
        tmp_path,
        writes={"tests_dir/test_new.py": _red_test()},
        mapping={"AC-NEW": ["tests_dir/test_new.py::test_new_behavior"]},
    )

    report = _run(author_repo, targets, mock)

    assert report.verdict == "fail"
    assert report.frozen is None
    assert report.freeze_error is not None
    assert "INVALID_MANIFEST" in report.freeze_error


def test_AC_1_report_json_round_trips(author_repo: Path, tmp_path: Path) -> None:
    targets = _write_targets(author_repo)
    mock = _mock_session(
        tmp_path,
        writes={"tests_dir/test_new.py": _red_test()},
        mapping={"AC-NEW": ["tests_dir/test_new.py::test_new_behavior"]},
    )
    report = _run(author_repo, targets, mock)
    artifact = (
        author_repo
        / ".suiyin"
        / "testauthor"
        / "001-demo-T001"
        / report.session_id
        / "testauthor_report.json"
    )
    assert json.loads(artifact.read_text(encoding="utf-8"))["verdict"] == "pass"
