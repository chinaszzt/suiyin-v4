"""Pydantic schemas for seam manifests and lint reports."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from suiyin_flow.identity import LOCAL_ID_PATTERN

SEAMLINT_SCHEMA_VERSION = "v0.1.0"
PENDING_TEST_AUTHOR = "PENDING-TEST-AUTHOR"

FindingCode = Literal[
    "SEAM_SCHEMA_INVALID",
    "SEAM_ENTRY_INVALID",
    "SEAM_TASK_UNKNOWN",
    "SEAM_DEPENDENCY_MISSING",
    "SEAM_TEST_PENDING",
]
LocalId = Annotated[str, Field(pattern=LOCAL_ID_PATTERN)]


def validate_schema_version(value: str) -> str:
    """Accept only the promoted v0.1.0 manifest schema."""
    if value == "draft-v0.1":
        raise ValueError("draft 需转正: seam manifest 必须人工确认并改为 v0.1.0")
    if value != SEAMLINT_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported schema_version: {value!r}; expected {SEAMLINT_SCHEMA_VERSION!r}"
        )
    return value


class SeamEntry(BaseModel):
    """One cross-task interface, schema, error, or dependency contract."""

    seam_id: str = Field(pattern=r"^SEAM-[A-Z0-9][A-Z0-9-]{0,62}$")
    kind: Literal["interface", "schema", "error", "dependency"]
    declaration: str = Field(min_length=1)
    provider_task: str = Field(pattern=LOCAL_ID_PATTERN)
    consumer_tasks: list[LocalId] = Field(min_length=1)
    source: str = Field(min_length=1)
    test_ref: str | None = None
    note: str | None = None

    @model_validator(mode="after")
    def _provider_is_not_a_consumer(self) -> SeamEntry:
        if self.provider_task in self.consumer_tasks:
            raise ValueError(
                f"consumer_tasks must not contain provider_task {self.provider_task!r}"
            )
        return self


class SeamManifest(BaseModel):
    """Formal seam manifest schema v0.1.0."""

    schema_version: str
    feature_id: str = Field(pattern=LOCAL_ID_PATTERN)
    source_basis: str | None = None
    entries: list[SeamEntry] = Field(min_length=1)

    @field_validator("schema_version")
    @classmethod
    def _validate_version(cls, value: str) -> str:
        return validate_schema_version(value)

    @model_validator(mode="after")
    def _unique_seam_ids(self) -> SeamManifest:
        seen: set[str] = set()
        for entry in self.entries:
            if entry.seam_id in seen:
                raise ValueError(f"duplicate seam_id: {entry.seam_id!r}")
            seen.add(entry.seam_id)
        return self


class LintFinding(BaseModel):
    """A manifest finding with stable machine-readable code."""

    code: FindingCode
    seam_id: str | None
    message: str


class LintReport(BaseModel):
    """Complete deterministic result of one seam lint run."""

    schema_version: str = SEAMLINT_SCHEMA_VERSION
    manifest_path: str
    feature_id: str
    counts: dict[str, int]
    findings: list[LintFinding]
    passed: bool


SeamLintErrorCode = Literal[
    "SEAMLINT_MANIFEST_UNREADABLE",
    "SEAMLINT_TASKS_UNREADABLE",
]


class SeamLintError(Exception):
    """Run-level failure that prevents a trustworthy lint report."""

    def __init__(self, code: SeamLintErrorCode, message: str, **details: Any) -> None:
        self.code: SeamLintErrorCode = code
        self.message = message
        self.details = details
        super().__init__(f"{code}: {message}")
