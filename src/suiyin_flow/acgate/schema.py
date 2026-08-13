"""AC 冻结闸 — schema (gen4-plan P0-2, 拍板 1 测试分类).

三类测试 + 冻结语义:
- ①行为测试 (spec AC 衍生) 与 ②seam/guard 测试 (plan/宪法衍生) **冻结**:
  spec 未变时对它们的删除/skip/改名/弱化一律阻断
- ③实现测试: 脚手架, 不进 manifest, 闸不管

AC manifest = 冻结集合的清单 (业务 repo 内, 随 feature 落盘):
`.specify/specs/<feature>/ac-manifest.yaml`
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from suiyin_flow.identity import LOCAL_ID_PATTERN

ACGATE_SCHEMA_VERSION: str = "v0.1.0"
AC_ID_PATTERN: str = r"^(AC|GUARD)-[A-Za-z0-9._-]+$"


# -------------------------------------------------------------------
# AC manifest (盘上工件)
# -------------------------------------------------------------------


class AcEntry(BaseModel):
    """manifest 单条: 一个 AC (或 guard 规则) ↔ 它的可执行投影 (测试)."""

    ac_id: str = Field(
        pattern=AC_ID_PATTERN,
        description="AC-N (行为) 或 GUARD-N (seam/守卫); spec/plan 里的编号",
    )
    kind: Literal["behavior", "guard"] = Field(
        default="behavior",
        description="①行为测试 (spec AC 衍生) / ②seam/guard 测试 (plan/宪法衍生)",
    )
    spec_ref: str = Field(
        description="权威来源文件 (相对 repo_root): behavior→spec.md, guard→plan/宪法"
    )
    spec_hash: str = Field(description="冻结时 spec_ref 的 sha256 (hex)")
    test_ref: str = Field(description="测试文件路径 (相对 repo_root)")
    test_hash: str = Field(description="冻结时 test_ref 的 sha256 (hex)")
    test_names: list[str] = Field(
        default_factory=list,
        description="该 AC 对应的测试函数名 (可选; 空 = 整文件冻结粒度)",
    )
    baseline_ref: str = Field(
        description="冻结基准 commit (sha 或 branch); hash 按此基准取"
    )


class AcManifest(BaseModel):
    """`.specify/specs/<feature>/ac-manifest.yaml` 顶层."""

    schema_version: str = ACGATE_SCHEMA_VERSION
    feature_id: str = Field(pattern=LOCAL_ID_PATTERN)
    entries: list[AcEntry] = Field(min_length=1)


# -------------------------------------------------------------------
# Gate 输出
# -------------------------------------------------------------------


FindingKind = Literal[
    "TEST_FILE_DELETED",     # manifest 冻结的测试文件在 diff 中被删除
    "TEST_DELETED",          # 冻结测试函数 def 行被删且无同名新增 (删除/改名)
    "TEST_SKIPPED",          # 冻结测试文件新增 skip 标记
    "TEST_WEAKENED_UNKNOWN", # 冻结测试文件有删除行, 不属上述闭集 → UNKNOWN, 同样不放行
    "MANIFEST_STALE",        # manifest hash 与 base 侧实际文件不符 (基准漂移)
]

Channel = Literal[
    "none",            # 无合法通道 → 阻断
    "spec_changed",    # Type B/C: 权威来源同 diff 变更 → 放行 (语义合法性交 C5/人)
    "projection_fix",  # spec 未变但附新旧 oracle 证据文件 → 放行
]


class GateFinding(BaseModel):
    kind: FindingKind
    file: str
    ac_ids: list[str] = Field(default_factory=list, description="关联的 manifest 条目")
    detail: str
    channel: Channel = "none"
    blocking: bool = Field(description="channel != none 时为 False (放行, 留 audit)")


GateVerdict = Literal["pass", "block"]


class GateReport(BaseModel):
    schema_version: str = ACGATE_SCHEMA_VERSION
    feature_id: str
    verdict: GateVerdict = Field(
        description="任一 blocking finding → block; 否则 pass (fail-closed)"
    )
    base_ref: str
    head_ref: str
    findings: list[GateFinding] = Field(default_factory=list)


# -------------------------------------------------------------------
# 错误
# -------------------------------------------------------------------


AcGateErrorCode = Literal[
    "MANIFEST_NOT_FOUND",
    "INVALID_MANIFEST",
    "GIT_ERROR",
    "REPO_ROOT_NOT_FOUND",
]


class AcGateError(Exception):
    def __init__(self, code: AcGateErrorCode, message: str, **details: Any) -> None:
        self.code: AcGateErrorCode = code
        self.message = message
        self.details = details
        super().__init__(f"{code}: {message}")
