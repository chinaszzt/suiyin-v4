"""Authorization manifest and gate report schemas (v0.1.0)."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from suiyin_flow.identity import LOCAL_ID_PATTERN

AUTHZ_SCHEMA_VERSION: Literal["v0.1.0"] = "v0.1.0"

AuthzFindingCode = Literal[
    "AUTHZ_PATH_DENIED",
    "AUTHZ_PATH_UNGRANTED",
    "AUTHZ_COMMAND_UNGRANTED",
]
AuthzDimension = Literal["path", "command"]
AuthzErrorCode = Literal[
    "AUTHZ_MANIFEST_UNREADABLE",
    "AUTHZ_TASKS_UNREADABLE",
    "AUTHZ_DIFF_UNREADABLE",
    "AUTHZ_TASK_UNKNOWN",
    "AUTHZ_FEATURE_MISMATCH",
]

_DB_COLLECTION = re.compile(r"^[A-Za-z0-9_-]+\.[A-Za-z0-9_.-]+$")


def _validate_path_globs(values: list[str], *, field_name: str) -> list[str]:
    """Reject empty/full-repository path grants while retaining ordinary globs."""
    for value in values:
        if not value.strip():
            raise ValueError(f"{field_name} entries must not be empty")
        if value.strip() == "**":
            raise ValueError(f"{field_name} must not contain the bare '**' glob")
    return values


class AuthzDenies(BaseModel):
    """Feature-level path deny list; deny matches take priority over every grant."""

    paths: list[str] = Field(
        default_factory=list,
        description=(
            "POSIX path globs. '**' is accepted inside a scoped pattern and uses "
            "fnmatch '*' approximation semantics; a bare '**' is forbidden."
        ),
    )

    @field_validator("paths")
    @classmethod
    def _check_paths(cls, values: list[str]) -> list[str]:
        return _validate_path_globs(values, field_name="denies.paths")


class AuthzGrant(BaseModel):
    """Additional per-task authorization beyond tasks.yaml modifies/verify_cmd."""

    task_id: str = Field(pattern=LOCAL_ID_PATTERN)
    write_paths: list[str] = Field(
        default_factory=list,
        description=(
            "Additional POSIX path globs. '**' uses fnmatch '*' approximation semantics "
            "when scoped by other path text; a bare '**' is forbidden."
        ),
    )
    run_commands: list[str] = Field(default_factory=list)
    db_writes: list[str] = Field(default_factory=list)
    network: list[str] = Field(default_factory=list)

    @field_validator("write_paths")
    @classmethod
    def _check_write_paths(cls, values: list[str]) -> list[str]:
        return _validate_path_globs(values, field_name="write_paths")

    @field_validator("run_commands", "db_writes", "network")
    @classmethod
    def _check_literal_entries(
        cls,
        values: list[str],
        info: Any,
    ) -> list[str]:
        field_name = str(info.field_name)
        for value in values:
            if not value.strip():
                raise ValueError(f"{field_name} entries must not be empty")
            if "*" in value:
                raise ValueError(f"{field_name} entries must not contain '*'")
            if field_name == "db_writes" and _DB_COLLECTION.fullmatch(value) is None:
                raise ValueError(
                    "db_writes entries must be literal db.collection names"
                )
        return values


class AuthzManifest(BaseModel):
    """Typed authorization manifest stored alongside a feature specification."""

    schema_version: Literal["v0.1.0"]
    feature_id: str = Field(pattern=LOCAL_ID_PATTERN)
    denies: AuthzDenies = Field(default_factory=AuthzDenies)
    grants: list[AuthzGrant] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_unique_task_ids(self) -> AuthzManifest:
        seen: set[str] = set()
        for grant in self.grants:
            if grant.task_id in seen:
                raise ValueError(f"duplicate task_id in grants: {grant.task_id!r}")
            seen.add(grant.task_id)
        return self


class AuthzFinding(BaseModel):
    """One concrete path or command authorization violation."""

    code: AuthzFindingCode
    dimension: AuthzDimension
    detail: str
    task_id: str


class AuthzReport(BaseModel):
    """Stable machine-readable result of one authorization check."""

    schema_version: Literal["v0.1.0"] = AUTHZ_SCHEMA_VERSION
    manifest_path: str
    task_id: str
    counts: dict[str, int]
    findings: list[AuthzFinding]
    passed: bool
    declared_db_writes: list[str]
    declared_network: list[str]


class _AuthzErrorPayload(BaseModel):
    """Typed error payload, mirroring the C5 ReviewerError wrapper style."""

    code: AuthzErrorCode
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class AuthzError(Exception):
    """Fail-closed input/identity error raised before a report can be produced."""

    def __init__(self, code: AuthzErrorCode, message: str, **details: Any) -> None:
        self.error = _AuthzErrorPayload(code=code, message=message, details=details)
        self.code = self.error.code
        self.message = self.error.message
        self.details = self.error.details
        super().__init__(f"{code}: {message}")
