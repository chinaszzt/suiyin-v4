"""Pydantic schemas for seam manifests and lint reports."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from suiyin_flow.identity import LOCAL_ID_PATTERN

SEAMLINT_SCHEMA_VERSION = "v0.2.0"
# v0.2.0 (M4 finding): SeamEntry 加 external_consumers (跨 feature/跨边界消费方,
# 不参与 L2/L3——M4 回放实证: 强塞 feature 内消费者会制造假 L3 依赖信号)。
# v0.1.0 文件继续接受 (纯增量)。
ACCEPTED_SCHEMA_VERSIONS = frozenset({"v0.1.0", SEAMLINT_SCHEMA_VERSION})
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
    """Accept promoted manifest schemas (v0.1.0 / v0.2.0)."""
    if value == "draft-v0.1":
        raise ValueError(
            f"draft 需转正: seam manifest 必须人工确认并改为 {SEAMLINT_SCHEMA_VERSION}"
        )
    if value not in ACCEPTED_SCHEMA_VERSIONS:
        raise ValueError(
            f"unsupported schema_version: {value!r}; "
            f"expected one of {sorted(ACCEPTED_SCHEMA_VERSIONS)}"
        )
    return value


class SeamEntry(BaseModel):
    """One cross-task interface, schema, error, or dependency contract."""

    seam_id: str = Field(pattern=r"^SEAM-[A-Z0-9][A-Z0-9-]{0,62}$")
    kind: Literal["interface", "schema", "error", "dependency"]
    declaration: str = Field(min_length=1)
    provider_task: str = Field(pattern=LOCAL_ID_PATTERN)
    consumer_tasks: list[LocalId] = Field(
        default_factory=list,
        description="feature 内消费 task (L2/L3 检查对象); external 非空时可为空",
    )
    external_consumers: list[str] = Field(
        default_factory=list,
        description=(
            "v0.2.0: 跨 feature/跨边界消费方 (如 '003-workbench' / 'cmd/server' / 'ops'); "
            "自由标识, 不对 tasks.yaml 校验, 不参与 L2/L3 依赖闭合"
        ),
    )
    source: str = Field(min_length=1)
    test_ref: str | None = None
    note: str | None = None

    @model_validator(mode="after")
    def _consumers_wellformed(self) -> SeamEntry:
        if self.provider_task in self.consumer_tasks:
            raise ValueError(
                f"consumer_tasks must not contain provider_task {self.provider_task!r}"
            )
        if not self.consumer_tasks and not self.external_consumers:
            raise ValueError(
                "seam must have at least one consumer "
                "(consumer_tasks or external_consumers)"
            )
        if any(not c.strip() for c in self.external_consumers):
            raise ValueError("external_consumers entries must be non-empty")
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
