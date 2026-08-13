"""Typed models and errors for lane isolation."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

LANE_SCHEMA_VERSION: Literal["v0.1.0"] = "v0.1.0"
LaneErrorCode = Literal[
    "LANE_EXHAUSTED",
    "SLOT_TIMEOUT",
    "LANE_CONFIG_INVALID",
]


class LaneConfig(BaseModel):
    """Repository-local lane allocator configuration."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["v0.1.0"] = LANE_SCHEMA_VERSION
    max_lanes: int = Field(default=4, ge=1)
    port_base: int = Field(default=38100, ge=1, le=65535)
    db_suffix_template: str = "lane{n}"
    max_build_slots: int = Field(default=2, ge=1)
    stale_after_seconds: int = Field(default=7200, gt=0)

    @model_validator(mode="after")
    def _validate_derived_values(self) -> LaneConfig:
        if self.port_base + self.max_lanes - 1 > 65535:
            raise ValueError("configured lane ports exceed 65535")
        try:
            first_suffix = self.db_suffix_template.format(n=0)
            second_suffix = self.db_suffix_template.format(n=1)
        except (IndexError, KeyError, ValueError) as exc:
            raise ValueError("db_suffix_template must be format-compatible with {n}") from exc
        if first_suffix == second_suffix:
            raise ValueError("db_suffix_template must produce a distinct suffix for each {n}")
        return self


class LaneLease(BaseModel):
    """Resources and holder metadata returned for one acquired lane."""

    lane_id: int
    port: int
    db_suffix: str
    tmp_dir: str
    pid: int
    hostname: str
    acquired_at: datetime
    purpose: str | None = None


class SlotHolder(BaseModel):
    """Metadata persisted for one held build slot."""

    pid: int
    hostname: str
    acquired_at: datetime
    cmd: str | None = None


class LaneState(BaseModel):
    """Current state of one configured lane."""

    lane_id: int
    held: bool
    holder: LaneLease | None = None
    alive: bool | None = None
    stale: bool = False


class SlotState(BaseModel):
    """Current state of one configured build slot."""

    slot_id: int
    held: bool
    holder: SlotHolder | None = None
    alive: bool | None = None
    stale: bool = False


class LaneStatus(BaseModel):
    """Machine-readable snapshot of all configured lanes and build slots."""

    lanes: list[LaneState]
    slots: list[SlotState]


class _LaneErrorPayload(BaseModel):
    code: LaneErrorCode
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class LaneError(Exception):
    """Stable public error raised by lane and slot allocation operations."""

    def __init__(self, code: LaneErrorCode, message: str, **details: Any) -> None:
        self.error = _LaneErrorPayload(code=code, message=message, details=details)
        self.code = self.error.code
        self.message = self.error.message
        self.details = self.error.details
        super().__init__(f"{code}: {message}")
