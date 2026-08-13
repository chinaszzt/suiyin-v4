"""C4 Verify Contract — Pydantic schema.

按 docs/sdd/components/c4-verify-contract.md v0.1.1 §2 schema 实现.

I5 invariant: contract 不规定怎么跑，只规定报告什么. 同一份 schema
跨 (a) 本地 lefthook / (b) 通用 CI 等实现谱系保持一致.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

# 跟 docs/sdd/components/c4-verify-contract.md 顶部 Version 同步.
# Breaking change → MAJOR bump (I4 invariant).
# v0.2.0 (2026-08-13): MINOR — report 加可选 target_tree_sha 新鲜度锚.
CONTRACT_VERSION: str = "v0.2.0"

# -------------------------------------------------------------------
# §2.1 Input Schema
# -------------------------------------------------------------------

Language = Literal["python", "dart", "typescript", "javascript", "go", "rust"]
Level = Literal["L1", "L2", "L3", "L4", "L5"]


class ToolchainHints(BaseModel):
    """业务项目语言/工具提示，缺省时 contract 自动探测."""

    languages: list[Language] = Field(default_factory=list)
    test_runner: str | None = None
    lint_runner: str | None = None


class TargetWorktree(BaseModel):
    """跑在 worktree 内的 working state."""

    kind: Literal["worktree"] = "worktree"
    worktree_path: str = Field(description="绝对路径")


class TargetPr(BaseModel):
    """跑在 PR diff 上."""

    kind: Literal["pr"] = "pr"
    pr_ref: str = Field(description="PR URL 或本地分支名")


Target = Annotated[TargetWorktree | TargetPr, Field(discriminator="kind")]


class VerifyInput(BaseModel):
    """C4 §2.1 Input Schema."""

    target: Target
    task_id: str | None = Field(
        default=None,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$",  # LOCAL_ID_PATTERN (P0-1 cascade)
        description="C2 闭环时透传；独立跑 C4 (CI / 人手动) 时可空",
    )
    spec_ref: str = Field(description="spec.md 路径，相对 repo_root 或绝对路径")
    ac_list: list[str] = Field(description="本次 verify 期望覆盖的 AC 集合")
    levels: list[Level] = Field(
        # default 用 list literal 而非 lambda — Pydantic v2 自动 deepcopy，
        # 同时避免 mypy 对 lambda 返回类型推断 list[str] 报错.
        default=["L1", "L2"],
        description="P0 MVP 只支持 L1/L2；L3-L5 在 P3+",
    )
    repo_root: str = Field(description="绝对路径")
    toolchain_hints: ToolchainHints | None = None


# -------------------------------------------------------------------
# §2.2 Output Schema — verify_report.json
# -------------------------------------------------------------------

LevelStatus = Literal["pass", "fail", "skipped"]
TestStatus = Literal["passed", "failed", "skipped"]
OverallVerdict = Literal["pass", "fail", "warn_only"]


class L1Check(BaseModel):
    """L1 Static check 单条记录 (lint / typecheck / format)."""

    name: str = Field(description="lint / format / typecheck / ...")
    tool: str = Field(description="ruff / mypy / dart analyze / ...")
    exit_code: int
    stdout_tail: str = Field(max_length=4000, default="")
    duration_seconds: float = 0.0


class L1Report(BaseModel):
    status: LevelStatus
    checks: list[L1Check] = Field(default_factory=list)


class TestOutcome(BaseModel):
    # pytest opt-out: Pydantic model 不是 test class, 阻止 pytest 试图收集.
    __test__ = False

    test_name: str
    ac_prefix: str = Field(
        default="",
        description="解析自 test_name；无 prefix 时为空字符串",
    )
    status: TestStatus
    duration_seconds: float = 0.0
    failure_message: str | None = None


class L2Summary(BaseModel):
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0


class L2Report(BaseModel):
    status: LevelStatus
    test_results: list[TestOutcome] = Field(default_factory=list)
    summary: L2Summary = Field(default_factory=L2Summary)


class LevelReportSkipped(BaseModel):
    """L3 / L4 / L5 in P0 — skipped placeholder.

    P0 阶段请求 L3/L4/L5 返回 LEVEL_NOT_IMPLEMENTED error (I6 invariant)，
    本类型用于报告里**自动跳过**的情况；显式请求未实现 level 走 error 路径.
    """

    status: Literal["skipped"] = "skipped"


class LevelsReport(BaseModel):
    L1: L1Report | None = None
    L2: L2Report | None = None
    L3: LevelReportSkipped | None = None
    L4: LevelReportSkipped | None = None
    L5: LevelReportSkipped | None = None


class MultiAcViolation(BaseModel):
    """I2 invariant 违反: 1 test 名带 ≥2 个 AC-N prefix."""

    test_name: str
    ac_prefixes_found: list[str]


class AcSummary(BaseModel):
    """I3 invariant: 即使 P0 不跑 L3 也要填，让 C5/C6 提前感知 AC 覆盖率."""

    requested: list[str] = Field(default_factory=list)
    covered: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    multi_ac_violations: list[MultiAcViolation] = Field(default_factory=list)


class VerifyReport(BaseModel):
    """C4 §2.2 Output Schema — verify_report.json."""

    target: Target
    target_tree_sha: str | None = None
    task_id: str | None = None
    overall_verdict: OverallVerdict
    generated_at: datetime
    contract_version: str = Field(pattern=r"^v\d+\.\d+\.\d+$")
    levels: LevelsReport
    ac_summary: AcSummary


# -------------------------------------------------------------------
# §2.3 Error Schema
# -------------------------------------------------------------------

ErrorCode = Literal[
    "TOOLCHAIN_NOT_FOUND",
    "WORKTREE_NOT_FOUND",
    "SPEC_PARSE_FAILED",
    "LEVEL_NOT_IMPLEMENTED",
    "LEFTHOOK_CONFIG_MISSING",
    "REPORT_WRITE_FAILED",
]


class VerifyError(BaseModel):
    """C4 §2.3 Error Schema."""

    code: ErrorCode
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class VerifyContractError(Exception):
    """Python exception wrapping VerifyError, raised inside runners."""

    def __init__(self, code: ErrorCode, message: str, **details: Any) -> None:
        self.error = VerifyError(code=code, message=message, details=details)
        super().__init__(f"{code}: {message}")
