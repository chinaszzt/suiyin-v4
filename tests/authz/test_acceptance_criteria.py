"""Authorization manifest component spec §4 acceptance criteria."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from suiyin_flow.authz import cli as authz_cli
from suiyin_flow.authz.gate import run_check

FEATURE_ID = "002-authz-feature"
TASK_ID = "T-001"


def _write_yaml(path: Path, data: dict[str, Any]) -> None:
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def _write_case(
    tmp_path: Path,
    *,
    modifies: list[str] | None = None,
    denies: list[str] | None = None,
    grant: dict[str, Any] | None = None,
    diff: str = "",
) -> tuple[Path, Path, Path]:
    tasks_path = tmp_path / "tasks.yaml"
    manifest_path = tmp_path / "authorization.yaml"
    diff_path = tmp_path / "change.patch"
    _write_yaml(
        tasks_path,
        {
            "schema_version": "v0.2.0",
            "feature_id": FEATURE_ID,
            "tasks": [
                {
                    "task_id": TASK_ID,
                    "spec_ref": "specs/002/spec.md",
                    "plan_ref": "specs/002/plan.md",
                    "verify_cmd": "pytest -q",
                    "modifies": modifies if modifies is not None else ["src/app/**"],
                }
            ],
        },
    )
    manifest: dict[str, Any] = {
        "schema_version": "v0.1.0",
        "feature_id": FEATURE_ID,
        "denies": {"paths": denies if denies is not None else []},
        "grants": [] if grant is None else [{"task_id": TASK_ID, **grant}],
    }
    _write_yaml(manifest_path, manifest)
    diff_path.write_text(diff, encoding="utf-8")
    return manifest_path, tasks_path, diff_path


def _diff(path: str) -> str:
    return f"--- a/{path}\n+++ b/{path}\n@@ -0,0 +1 @@\n+new\n"


def _deletion_diff(path: str) -> str:
    return f"--- a/{path}\n+++ /dev/null\n@@ -1 +0,0 @@\n-old\n"


def _cli_args(
    manifest_path: Path,
    tasks_path: Path,
    diff_path: Path,
    *extra: str,
) -> list[str]:
    return [
        "authz",
        "check",
        "--manifest",
        str(manifest_path),
        "--tasks-yaml",
        str(tasks_path),
        "--diff",
        str(diff_path),
        "--task-id",
        TASK_ID,
        *extra,
    ]


@pytest.mark.ac
def test_AC_1_modifies_path_passes(tmp_path: Path) -> None:
    """AC-1: a touched path covered by modifies passes."""
    paths = _write_case(tmp_path, diff=_diff("src/app/main.py"))
    assert authz_cli.main(_cli_args(*paths)) == 0


@pytest.mark.ac
def test_AC_2_deny_wins_even_for_modifies_deletion(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC-2: deny wins over modifies, including a deleted file header."""
    paths = _write_case(
        tmp_path,
        modifies=["docs/legacy/**"],
        denies=["docs/legacy/**"],
        diff=_deletion_diff("docs/legacy/old.md"),
    )
    assert authz_cli.main(_cli_args(*paths)) == 1
    output = capsys.readouterr().out
    assert "AUTHZ_PATH_DENIED path" in output
    assert "docs/legacy/old.md" in output


@pytest.mark.ac
def test_AC_3_path_outside_effective_grant_is_rejected(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC-3: a path outside modifies plus write_paths is ungranted."""
    paths = _write_case(tmp_path, diff=_diff("docs/unowned.md"))
    assert authz_cli.main(_cli_args(*paths)) == 1
    output = capsys.readouterr().out
    assert "AUTHZ_PATH_UNGRANTED path" in output
    assert "docs/unowned.md" in output


@pytest.mark.ac
def test_AC_4_unlisted_command_is_rejected(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC-4: command authorization is stripped exact-string equality."""
    paths = _write_case(
        tmp_path,
        grant={"run_commands": ["ruff check src"]},
        diff=_diff("src/app/main.py"),
    )
    assert authz_cli.main(_cli_args(*paths, "--command", "mypy src")) == 1
    output = capsys.readouterr().out
    assert "AUTHZ_COMMAND_UNGRANTED command" in output
    assert "mypy src" in output


@pytest.mark.ac
@pytest.mark.parametrize("db_writes", [["*"], [""], ["db."]])
def test_AC_5_db_wildcards_empty_and_prefixes_fail_schema(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    db_writes: list[str],
) -> None:
    """AC-5: db grants must be non-wildcard db.collection literals."""
    paths = _write_case(
        tmp_path,
        grant={"db_writes": db_writes},
        diff=_diff("src/app/main.py"),
    )
    assert authz_cli.main(_cli_args(*paths)) == 2
    error = capsys.readouterr().err
    assert error.startswith("ERROR AUTHZ_MANIFEST_UNREADABLE:")
    assert len(error.splitlines()) == 1


@pytest.mark.ac
def test_AC_6_manifest_parse_and_feature_mismatch_fail_closed(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC-6: malformed authorization and mismatched feature identity exit 2."""
    malformed_dir = tmp_path / "malformed"
    malformed_dir.mkdir()
    malformed_paths = _write_case(malformed_dir, diff=_diff("src/app/main.py"))
    malformed_paths[0].write_text("grants: [unclosed", encoding="utf-8")
    assert authz_cli.main(_cli_args(*malformed_paths)) == 2
    assert "ERROR AUTHZ_MANIFEST_UNREADABLE:" in capsys.readouterr().err

    mismatch_dir = tmp_path / "mismatch"
    mismatch_dir.mkdir()
    mismatch_paths = _write_case(mismatch_dir, diff=_diff("src/app/main.py"))
    manifest_data = yaml.safe_load(mismatch_paths[0].read_text(encoding="utf-8"))
    assert isinstance(manifest_data, dict)
    manifest_data["feature_id"] = "different-feature"
    _write_yaml(mismatch_paths[0], manifest_data)
    assert authz_cli.main(_cli_args(*mismatch_paths)) == 2
    assert "ERROR AUTHZ_FEATURE_MISMATCH:" in capsys.readouterr().err


@pytest.mark.ac
def test_AC_7_missing_grant_uses_minimum_authority(tmp_path: Path) -> None:
    """AC-7: no grant still permits modifies and declares no DB/network authority."""
    manifest_path, tasks_path, diff_path = _write_case(
        tmp_path,
        diff=_diff("src/app/main.py"),
    )
    report = run_check(manifest_path, tasks_path, diff_path, TASK_ID, command=" pytest -q ")
    assert report.passed is True
    assert report.declared_db_writes == []
    assert report.declared_network == []


@pytest.mark.ac
def test_AC_8_all_violation_classes_are_reported(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC-8: deny, ungranted path, and command findings are aggregated."""
    paths = _write_case(
        tmp_path,
        modifies=["docs/legacy/**"],
        denies=["docs/legacy/**"],
        diff=_diff("docs/legacy/old.md") + _diff("outside/new.py"),
    )
    assert authz_cli.main(_cli_args(*paths, "--command", "python deploy.py")) == 1
    output = capsys.readouterr().out
    assert output.count("AUTHZ_PATH_DENIED") == 1
    assert output.count("AUTHZ_PATH_UNGRANTED") == 1
    assert output.count("AUTHZ_COMMAND_UNGRANTED") == 1


@pytest.mark.ac
def test_AC_9_write_paths_extend_modifies(tmp_path: Path) -> None:
    """AC-9: write_paths adds a scoped exception beyond modifies."""
    paths = _write_case(
        tmp_path,
        grant={"write_paths": ["generated/**"]},
        diff=_diff("generated/client.py"),
    )
    assert authz_cli.main(_cli_args(*paths)) == 0


@pytest.mark.ac
def test_AC_10_report_json_has_stable_shape(tmp_path: Path) -> None:
    """AC-10: JSON report contains dimension counts, findings, and declarations."""
    manifest_path, tasks_path, diff_path = _write_case(
        tmp_path,
        grant={
            "db_writes": ["suiyin_desk.topics"],
            "network": ["api.internal.example"],
        },
        diff=_diff("outside/new.py"),
    )
    report_path = tmp_path / "authz-report.json"
    args = _cli_args(
        manifest_path,
        tasks_path,
        diff_path,
        "--command",
        "python deploy.py",
        "--report",
        str(report_path),
    )
    assert authz_cli.main(args) == 1

    data = json.loads(report_path.read_text(encoding="utf-8"))
    assert data["schema_version"] == "v0.1.0"
    assert data["counts"] == {"path": 1, "command": 1}
    assert isinstance(data["findings"], list)
    assert {"code", "dimension", "detail", "task_id"} == set(data["findings"][0])
    assert data["declared_db_writes"] == ["suiyin_desk.topics"]
    assert data["declared_network"] == ["api.internal.example"]
