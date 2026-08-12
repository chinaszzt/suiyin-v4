"""Mutation 探针 — schema (gen4-plan P0-3, 拍板 1 mutation = adequacy 验证).

mutant catalog = 声明式变异清单 (业务 repo 内随 feature 落盘):
`.specify/specs/<feature>/mutants.yaml`

五类 desk mutant class 来源 8-08 交叉审查 (E4 抓到的五处自写测试空心):
tag_rename / method_rename / assert_field_drop / taint_escape / shallow_copy。
class 是开放枚举 (str) —— 探针机制语言无关, 类别只是归因标签。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from suiyin_flow.identity import LOCAL_ID_PATTERN

MUTATION_SCHEMA_VERSION: str = "v0.1.0"


class MutantSpec(BaseModel):
    """catalog 单条: 对目标文件做一次确定性文本替换."""

    mutant_id: str = Field(pattern=r"^M-[A-Za-z0-9._-]+$")
    mutant_class: str = Field(
        description=(
            "归因类别, 例 tag_rename / method_rename / assert_field_drop / "
            "taint_escape / shallow_copy (desk 五类) 或项目自定义"
        ),
    )
    target_file: str = Field(description="被变异文件 (相对 repo_root)")
    match: str = Field(
        min_length=1,
        description="字面匹配串 (非正则; 必须在 target_file 中恰好出现 ≥1 次)",
    )
    replacement: str = Field(description="替换串 (与 match 不同)")
    occurrence: int = Field(
        default=1,
        ge=1,
        description="替换第 N 处出现 (确定性; 默认第 1 处)",
    )
    test_cmd: str | None = Field(
        default=None,
        description="该 mutant 的杀手测试命令 (shell 字符串); 缺省用 catalog 级默认",
    )
    description: str = Field(
        default="",
        description="这个 mutant 模拟什么缺陷 (人读)",
    )


class MutantCatalog(BaseModel):
    """mutants.yaml 顶层."""

    schema_version: str = MUTATION_SCHEMA_VERSION
    feature_id: str = Field(pattern=LOCAL_ID_PATTERN)
    default_test_cmd: str = Field(
        description="缺省杀手测试命令 (throwaway worktree 内 shell 执行)"
    )
    mutants: list[MutantSpec] = Field(min_length=1)

    @field_validator("schema_version")
    @classmethod
    def _check_schema_version(cls, v: str) -> str:
        if v != MUTATION_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported schema_version: {v!r}; "
                f"this build only understands {MUTATION_SCHEMA_VERSION!r}"
            )
        return v


# -------------------------------------------------------------------
# 输出 (mutation attestation)
# -------------------------------------------------------------------


MutantOutcome = Literal[
    "killed",        # 注入后测试变红 → 测试有证伪力
    "survived",      # 注入后测试仍绿 → 空心测试, 探针核心捕获目标
    "apply_failed",  # match 在 target_file 中找不到 → catalog 失配 (fail-closed)
    "error",         # worktree/命令层错误
]

ProbeVerdict = Literal["pass", "fail"]


class MutantResult(BaseModel):
    mutant_id: str
    mutant_class: str
    target_file: str
    outcome: MutantOutcome
    test_exit_code: int | None = None
    output_tail: str = Field(default="", description="测试命令 stdout+stderr 尾部 ≤2000")


class ProbeReport(BaseModel):
    """mutation attestation — 冻结测试证伪力的证据 (拍板 1 ①的第三链)."""

    schema_version: str = MUTATION_SCHEMA_VERSION
    feature_id: str
    ref: str = Field(description="被测 ref (探针在 throwaway worktree 内跑此基准)")
    verdict: ProbeVerdict = Field(
        description=(
            "pass = ≥1 个 mutant 且全部 killed; "
            "其余一律 fail (survived / apply_failed / error / 零适用, fail-closed)"
        )
    )
    results: list[MutantResult]
    survived_count: int
    killed_count: int


MutationErrorCode = Literal[
    "CATALOG_NOT_FOUND",
    "INVALID_CATALOG",
    "REPO_ROOT_NOT_FOUND",
    "GIT_ERROR",
]


class MutationError(Exception):
    def __init__(self, code: MutationErrorCode, message: str, **details: Any) -> None:
        self.code: MutationErrorCode = code
        self.message = message
        self.details = details
        super().__init__(f"{code}: {message}")
