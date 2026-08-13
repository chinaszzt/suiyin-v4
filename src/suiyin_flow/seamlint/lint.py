"""Static seam manifest linting against a validated tasks.yaml graph."""

from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator

from suiyin_flow.c2_executor.batch import (
    BatchAdapterError,
    BatchManifest,
    load_tasks_yaml,
    resolve_feature_id,
)
from suiyin_flow.identity import LOCAL_ID_PATTERN
from suiyin_flow.seamlint.schema import (
    PENDING_TEST_AUTHOR,
    FindingCode,
    LintFinding,
    LintReport,
    SeamEntry,
    SeamLintError,
    validate_schema_version,
)

_FINDING_CODES: tuple[FindingCode, ...] = (
    "SEAM_SCHEMA_INVALID",
    "SEAM_ENTRY_INVALID",
    "SEAM_TASK_UNKNOWN",
    "SEAM_DEPENDENCY_MISSING",
    "SEAM_TEST_PENDING",
)
_BLOCKING_CODES = frozenset(_FINDING_CODES[:-1])


def _one_line(value: object) -> str:
    """Keep process-level CLI errors on their specified single stderr line."""
    return " ".join(str(value).splitlines())


class _ManifestEnvelope(BaseModel):
    """Top-level fields, deliberately leaving entries for per-item validation."""

    schema_version: str
    feature_id: str = Field(pattern=LOCAL_ID_PATTERN)
    source_basis: str | None = None
    entries: list[Any] = Field(min_length=1)

    @field_validator("schema_version")
    @classmethod
    def _validate_version(cls, value: str) -> str:
        return validate_schema_version(value)


def _load_manifest(path: Path) -> tuple[_ManifestEnvelope, list[SeamEntry], list[LintFinding]]:
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SeamLintError(
            "SEAMLINT_MANIFEST_UNREADABLE",
            f"could not read seam manifest {path}: {_one_line(exc)}",
        ) from exc

    try:
        data = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        raise SeamLintError(
            "SEAMLINT_MANIFEST_UNREADABLE",
            f"YAML parse error in {path}: {_one_line(exc)}",
        ) from exc

    if not isinstance(data, dict):
        raise SeamLintError(
            "SEAMLINT_MANIFEST_UNREADABLE",
            f"seam manifest top level must be a mapping, got {type(data).__name__}",
        )

    try:
        envelope = _ManifestEnvelope.model_validate(data)
    except ValidationError as exc:
        raise SeamLintError(
            "SEAMLINT_MANIFEST_UNREADABLE",
            f"manifest schema validation failed: {_one_line(exc)}",
        ) from exc

    entries: list[SeamEntry] = []
    findings: list[LintFinding] = []
    seen: set[str] = set()
    for index, raw_entry in enumerate(envelope.entries):
        seam_id = raw_entry.get("seam_id") if isinstance(raw_entry, dict) else None
        finding_seam_id = seam_id if isinstance(seam_id, str) else None
        try:
            entry = SeamEntry.model_validate(raw_entry)
        except ValidationError as exc:
            findings.append(
                LintFinding(
                    code="SEAM_ENTRY_INVALID",
                    seam_id=finding_seam_id,
                    message=f"entries[{index}] is invalid: {exc}",
                )
            )
            continue
        if entry.seam_id in seen:
            findings.append(
                LintFinding(
                    code="SEAM_ENTRY_INVALID",
                    seam_id=entry.seam_id,
                    message=f"entries[{index}] has duplicate seam_id {entry.seam_id!r}",
                )
            )
            continue
        seen.add(entry.seam_id)
        entries.append(entry)
    return envelope, entries, findings


def _load_tasks(path: Path) -> BatchManifest:
    try:
        return load_tasks_yaml(path)
    except BatchAdapterError as exc:
        raise SeamLintError(
            "SEAMLINT_TASKS_UNREADABLE",
            f"could not load tasks.yaml {path}: {_one_line(exc.error.message)}",
        ) from exc


def _provider_reachable(
    consumer_id: str,
    provider_id: str,
    dependencies: dict[str, list[str]],
) -> bool:
    """BFS over depends_on edges from consumer towards its prerequisites."""
    queue = deque(dependencies[consumer_id])
    visited: set[str] = set()
    while queue:
        task_id = queue.popleft()
        if task_id == provider_id:
            return True
        if task_id in visited:
            continue
        visited.add(task_id)
        queue.extend(dependencies[task_id])
    return False


def run_lint(manifest_path: Path, tasks_yaml_path: Path) -> LintReport:
    """Run all seam lint layers and return their full aggregate report."""
    manifest, entries, findings = _load_manifest(manifest_path)
    tasks_manifest = _load_tasks(tasks_yaml_path)

    if (
        tasks_manifest.feature_id is not None
        and manifest.feature_id != resolve_feature_id(tasks_manifest)
    ):
        findings.append(
            LintFinding(
                code="SEAM_SCHEMA_INVALID",
                seam_id=None,
                message=(
                    f"feature_id {manifest.feature_id!r} does not match tasks.yaml "
                    f"feature_id {tasks_manifest.feature_id!r}"
                ),
            )
        )

    dependencies = {task.task_id: task.depends_on for task in tasks_manifest.tasks}
    task_ids = set(dependencies)

    # L2: identity. One finding per unknown provider or consumer occurrence.
    for entry in entries:
        if entry.provider_task not in task_ids:
            findings.append(
                LintFinding(
                    code="SEAM_TASK_UNKNOWN",
                    seam_id=entry.seam_id,
                    message=(
                        f"seam {entry.seam_id} provider_task "
                        f"{entry.provider_task!r} is not present in tasks.yaml"
                    ),
                )
            )
        for consumer_id in entry.consumer_tasks:
            if consumer_id not in task_ids:
                findings.append(
                    LintFinding(
                        code="SEAM_TASK_UNKNOWN",
                        seam_id=entry.seam_id,
                        message=(
                            f"seam {entry.seam_id} consumer_task "
                            f"{consumer_id!r} is not present in tasks.yaml"
                        ),
                    )
                )

    # L3: dependency closure. Unknown ids were already reported at L2.
    for entry in entries:
        if entry.provider_task not in task_ids:
            continue
        for consumer_id in entry.consumer_tasks:
            if consumer_id not in task_ids:
                continue
            if not _provider_reachable(consumer_id, entry.provider_task, dependencies):
                findings.append(
                    LintFinding(
                        code="SEAM_DEPENDENCY_MISSING",
                        seam_id=entry.seam_id,
                        message=(
                            f"seam {entry.seam_id}: consumer {consumer_id!r} cannot reach "
                            f"provider {entry.provider_task!r} through depends_on"
                        ),
                    )
                )

    # L4: absent and explicitly pending hooks are warnings only.
    for entry in entries:
        if entry.test_ref is None or entry.test_ref == PENDING_TEST_AUTHOR:
            findings.append(
                LintFinding(
                    code="SEAM_TEST_PENDING",
                    seam_id=entry.seam_id,
                    message=f"seam {entry.seam_id} has no completed test_ref",
                )
            )

    counts: dict[str, int] = {code: 0 for code in _FINDING_CODES}
    for finding in findings:
        counts[finding.code] += 1
    passed = not any(finding.code in _BLOCKING_CODES for finding in findings)
    return LintReport(
        manifest_path=str(manifest_path),
        feature_id=manifest.feature_id,
        counts=counts,
        findings=findings,
        passed=passed,
    )
