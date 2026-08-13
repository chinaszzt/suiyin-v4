"""Independent test author v0.1.0 schemas."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from suiyin_flow.identity import LOCAL_ID_PATTERN

SCHEMA_VERSION: Literal["v0.1.0"] = "v0.1.0"


class TestTarget(BaseModel):
    """One declaration-derived test-writing target."""

    __test__ = False

    target_id: str
    kind: Literal["ac", "guard", "seam"]
    source: str
    directive: str
    suggested_test_ref: str | None = None

    @field_validator("target_id", "source", "directive")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value


class TargetsManifest(BaseModel):
    """On-disk test target manifest."""

    schema_version: Literal["v0.1.0"]
    task_id: str = Field(pattern=LOCAL_ID_PATTERN)
    targets: list[TestTarget] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_target_ids(self) -> TargetsManifest:
        seen: set[str] = set()
        for target in self.targets:
            if target.target_id in seen:
                raise ValueError(f"duplicate target_id: {target.target_id!r}")
            seen.add(target.target_id)
        return self


class TargetResult(BaseModel):
    target_id: str
    status: Literal["authored", "skipped"]
    test_refs: list[str] = Field(default_factory=list)
    note: str | None = None


class PathCheck(BaseModel):
    touched: list[str] = Field(default_factory=list)
    violations: list[str] = Field(default_factory=list)


class RedCheck(BaseModel):
    cmd: str
    exit_code: int
    red: bool


class FrozenInfo(BaseModel):
    manifest_path: str
    entries: int


class TestAuthorReport(BaseModel):
    __test__ = False

    schema_version: Literal["v0.1.0"] = SCHEMA_VERSION
    task_id: str = Field(pattern=LOCAL_ID_PATTERN)
    session_id: str
    target_tree_sha: str | None
    targets: list[TargetResult]
    path_check: PathCheck
    red_check: RedCheck
    frozen: FrozenInfo | None = None
    verdict: Literal["pass", "fail"]
    author_branch: str
    author_worktree: str


TestAuthorErrorCode = Literal[
    "TESTAUTHOR_TARGETS_INVALID",
    "TESTAUTHOR_SESSION_CRASHED",
    "TESTAUTHOR_TIMEOUT",
    "TESTAUTHOR_TASK_UNKNOWN",
    "TESTAUTHOR_BASE_UNAVAILABLE",
]


class TestAuthorErrorData(BaseModel):
    code: TestAuthorErrorCode
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class TestAuthorError(Exception):
    """Exception carrying the public testauthor error schema."""

    __test__ = False

    def __init__(
        self,
        code: TestAuthorErrorCode,
        message: str,
        **details: Any,
    ) -> None:
        self.error = TestAuthorErrorData(code=code, message=message, details=details)
        super().__init__(f"{code}: {message}")
