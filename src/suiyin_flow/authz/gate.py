"""Purely static authorization-manifest gate."""

from __future__ import annotations

import fnmatch
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from suiyin_flow.authz.schema import (
    AuthzError,
    AuthzFinding,
    AuthzGrant,
    AuthzManifest,
    AuthzReport,
)
from suiyin_flow.c2_executor.batch import (
    BatchAdapterError,
    BatchManifest,
    load_tasks_yaml,
    resolve_feature_id,
)

_OLD_HEADER = re.compile(r"^--- (?P<path>[^\t\r\n]+)(?:\t.*)?$")
_NEW_HEADER = re.compile(r"^\+\+\+ (?P<path>[^\t\r\n]+)(?:\t.*)?$")


def _posix_path(value: str, *, prefix: str) -> str:
    normalized = value.replace("\\", "/")
    if normalized.startswith(prefix):
        normalized = normalized[len(prefix) :]
    return normalized


def diff_touched_paths(diff_text: str) -> list[str]:
    """Extract ordered unique POSIX paths from unified-diff file headers.

    Added/modified files use the ``+++`` path. A deletion's ``+++ /dev/null``
    instead uses the paired ``---`` path.
    """
    paths: list[str] = []
    seen: set[str] = set()
    old_path: str | None = None
    saw_file_header = False

    for line in diff_text.splitlines():
        old_match = _OLD_HEADER.match(line)
        if old_match is not None:
            old_path = old_match.group("path")
            continue

        new_match = _NEW_HEADER.match(line)
        if new_match is None:
            continue

        saw_file_header = True
        new_path = new_match.group("path")
        if new_path == "/dev/null":
            if old_path is None or old_path == "/dev/null":
                raise ValueError("deletion header has no corresponding source path")
            touched = _posix_path(old_path, prefix="a/")
        else:
            touched = _posix_path(new_path, prefix="b/")
        old_path = None

        if not touched:
            raise ValueError("diff file header contains an empty path")
        if touched not in seen:
            seen.add(touched)
            paths.append(touched)

    if diff_text.strip() and not saw_file_header:
        raise ValueError("no unified-diff file headers found")
    return paths


def _load_manifest(path: Path) -> AuthzManifest:
    try:
        text = path.read_text(encoding="utf-8")
        data: Any = yaml.safe_load(text)
        if not isinstance(data, dict):
            raise ValueError("authorization manifest top level must be a mapping")
        return AuthzManifest.model_validate(data)
    except (OSError, UnicodeError, yaml.YAMLError, ValidationError, ValueError) as exc:
        raise AuthzError(
            "AUTHZ_MANIFEST_UNREADABLE",
            f"could not read or parse authorization manifest: {exc}",
            path=str(path),
        ) from exc


def _load_tasks(path: Path) -> BatchManifest:
    try:
        return load_tasks_yaml(path)
    except (BatchAdapterError, OSError, UnicodeError, ValueError) as exc:
        raise AuthzError(
            "AUTHZ_TASKS_UNREADABLE",
            f"could not read or parse tasks.yaml: {exc}",
            path=str(path),
        ) from exc


def _read_diff(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
        return diff_touched_paths(text)
    except (OSError, UnicodeError, ValueError) as exc:
        raise AuthzError(
            "AUTHZ_DIFF_UNREADABLE",
            f"could not read or parse diff: {exc}",
            path=str(path),
        ) from exc


def _matches_any(path: str, patterns: list[str]) -> bool:
    normalized_patterns = (pattern.replace("\\", "/") for pattern in patterns)
    return any(fnmatch.fnmatch(path, pattern) for pattern in normalized_patterns)


def _ordered_unique(groups: Iterable[Iterable[str]]) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for value in group:
            if value not in seen:
                seen.add(value)
                values.append(value)
    return values


def _resolve_matching_feature_id(
    manifest: AuthzManifest,
    tasks_manifest: BatchManifest,
) -> str:
    tasks_feature_id = resolve_feature_id(tasks_manifest)
    if manifest.feature_id != tasks_feature_id:
        raise AuthzError(
            "AUTHZ_FEATURE_MISMATCH",
            (
                f"authorization feature_id {manifest.feature_id!r} does not match "
                f"tasks.yaml feature_id {tasks_feature_id!r}"
            ),
            manifest_feature_id=manifest.feature_id,
            tasks_feature_id=tasks_feature_id,
        )
    return tasks_feature_id


def _path_findings(
    *,
    touched_paths: list[str],
    denied_paths: list[str],
    effective_paths: list[str],
    subject_id: str,
    authority_scope: str,
) -> list[AuthzFinding]:
    findings: list[AuthzFinding] = []
    for touched_path in touched_paths:
        if _matches_any(touched_path, denied_paths):
            findings.append(
                AuthzFinding(
                    code="AUTHZ_PATH_DENIED",
                    dimension="path",
                    detail=f"path {touched_path!r} matches a feature-level deny",
                    task_id=subject_id,
                )
            )
        elif not _matches_any(touched_path, effective_paths):
            findings.append(
                AuthzFinding(
                    code="AUTHZ_PATH_UNGRANTED",
                    dimension="path",
                    detail=f"path {touched_path!r} is outside {authority_scope}",
                    task_id=subject_id,
                )
            )
    return findings


def _report(
    *,
    manifest_file: Path,
    subject_id: str,
    findings: list[AuthzFinding],
    declared_db_writes: list[str],
    declared_network: list[str],
) -> AuthzReport:
    counts = {
        "path": sum(finding.dimension == "path" for finding in findings),
        "command": sum(finding.dimension == "command" for finding in findings),
    }
    return AuthzReport(
        manifest_path=str(manifest_file),
        task_id=subject_id,
        counts=counts,
        findings=findings,
        passed=not findings,
        declared_db_writes=declared_db_writes,
        declared_network=declared_network,
    )


def run_check(
    manifest_path: str | Path,
    tasks_yaml_path: str | Path,
    diff_path: str | Path,
    task_id: str,
    command: str | None = None,
) -> AuthzReport:
    """Check one task's touched paths and optional command against its authority."""
    manifest_file = Path(manifest_path)
    tasks_file = Path(tasks_yaml_path)
    diff_file = Path(diff_path)

    manifest = _load_manifest(manifest_file)
    tasks_manifest = _load_tasks(tasks_file)
    touched_paths = _read_diff(diff_file)
    _resolve_matching_feature_id(manifest, tasks_manifest)

    task = next((entry for entry in tasks_manifest.tasks if entry.task_id == task_id), None)
    if task is None:
        raise AuthzError(
            "AUTHZ_TASK_UNKNOWN",
            f"task_id {task_id!r} is not present in tasks.yaml",
            task_id=task_id,
        )

    grant = next(
        (entry for entry in manifest.grants if entry.task_id == task_id),
        AuthzGrant(task_id=task_id),
    )
    effective_paths = [*task.modifies, *grant.write_paths]
    findings = _path_findings(
        touched_paths=touched_paths,
        denied_paths=manifest.denies.paths,
        effective_paths=effective_paths,
        subject_id=task_id,
        authority_scope="the task's write grants",
    )

    if command is not None:
        requested_command = command.strip()
        command_granted = requested_command == task.verify_cmd.strip() or any(
            requested_command == allowed.strip() for allowed in grant.run_commands
        )
        if not command_granted:
            findings.append(
                AuthzFinding(
                    code="AUTHZ_COMMAND_UNGRANTED",
                    dimension="command",
                    detail=f"command {command!r} is not granted for the task",
                    task_id=task_id,
                )
            )

    return _report(
        manifest_file=manifest_file,
        subject_id=task_id,
        findings=findings,
        declared_db_writes=list(grant.db_writes),
        declared_network=list(grant.network),
    )


def run_feature_check(
    manifest_path: str | Path,
    tasks_yaml_path: str | Path,
    diff_path: str | Path,
) -> AuthzReport:
    """Check a whole feature diff against the union of all task authorities."""
    manifest_file = Path(manifest_path)
    tasks_file = Path(tasks_yaml_path)
    diff_file = Path(diff_path)

    manifest = _load_manifest(manifest_file)
    tasks_manifest = _load_tasks(tasks_file)
    touched_paths = _read_diff(diff_file)
    feature_id = _resolve_matching_feature_id(manifest, tasks_manifest)

    effective_paths = _ordered_unique(
        [
            *(task.modifies for task in tasks_manifest.tasks),
            *(grant.write_paths for grant in manifest.grants),
        ]
    )
    findings = _path_findings(
        touched_paths=touched_paths,
        denied_paths=manifest.denies.paths,
        effective_paths=effective_paths,
        subject_id=feature_id,
        authority_scope="the feature's combined write grants",
    )
    return _report(
        manifest_file=manifest_file,
        subject_id=feature_id,
        findings=findings,
        declared_db_writes=_ordered_unique(
            grant.db_writes for grant in manifest.grants
        ),
        declared_network=_ordered_unique(
            grant.network for grant in manifest.grants
        ),
    )
