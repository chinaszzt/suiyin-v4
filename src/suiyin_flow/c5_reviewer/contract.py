"""C5 AI Reviewer — Pydantic schema.

按 docs/sdd/components/c5-ai-reviewer.md v0.1.1 §2 schema 实现.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from suiyin_flow.identity import LOCAL_ID_PATTERN

# 跟 docs/sdd/components/c5-ai-reviewer.md 顶部 Version 同步.
# v0.1.1 (2026-05-24): verdict 二元化 + 按 category 决定 + Block Recovery.
# v0.2.0 (2026-08-12): MINOR — P0-1 canonical identity:
#   task_id pattern 放宽 (LOCAL_ID_PATTERN, T-001B 合法) + 输入加 feature_id
#   (可选) + 落盘 reviews/<uuid> → reviews/<review_key>/<uuid> (可按身份键定位)
# v0.3.0 (2026-08-12): MINOR — P0-4: 输入加可选 task_ids[] (subject=feature 收口 review)
# v0.4.0 (2026-08-13): MINOR — M3 件 1 (gen4-plan 拍板 7) typed inputs:
#   review_inputs[] (kind/path/authority/required/content_sha256), 权威序
#   nc > acceptance > design > failure_modes > advisory; required 缺失 /
#   hash 漂移 fail-closed (session 不启动); report 记录 resolved inputs。
#   尺子对照实验实证: 契约进输入面 = 同 diff approve/0 → block/1 (dogfood/P0-attribution/)
# v0.5.0 (2026-08-13): MINOR — report 加可选 target_tree_sha 新鲜度锚.
CONTRACT_VERSION: str = "v0.5.0"

# -------------------------------------------------------------------
# Enums
# -------------------------------------------------------------------

Severity = Literal["low", "medium", "high", "critical"]
Criticality = Literal["low", "medium", "high"]
Verdict = Literal["approve", "block"]  # v0.1.1: 去 request_changes

# Finding categories (C5 spec §2.2 + §7 Finding Category 设计要点)
Category = Literal[
    "complexity",                       # Fork L: C11 query + jscpd
    "spec_drift",                       # PR diff 跟 spec 不对齐
    "ac_uncovered",                     # spec AC 缺对应 test
    "nc_violation",                     # 违反 constitution NC-1..NC-5
    "pc_violation",                     # 违反 PC-1..PC-3
    "cross_platform",                   # NC-5 跨平台违规
    "security",                         # hardcoded secret / injection / 等
    "reusable_knowledge_not_captured",  # C12 触发, I6 必输出
]

# Block 集合 (v0.1.1 I5): finding 含其中任一 category → verdict=block.
# 其他 category → approve + finding audit trail.
BLOCK_SET: frozenset[Category] = frozenset(
    {"nc_violation", "security", "spec_drift", "ac_uncovered"}
)

# -------------------------------------------------------------------
# v0.4.0 Typed inputs (M3 件 1, gen4-plan 拍板 7)
# -------------------------------------------------------------------

# 输入 kind 闭集. 每个 kind 有固定的权威档 (KIND_AUTHORITY), 不由调用方自定.
InputKind = Literal[
    "constitution",   # 宪法 (NC/PC) — 最高权威
    "spec",           # spec.md — 意图与 AC
    "ac_map",         # M2 产物 ac-map.md / ac-manifest.yaml — AC 映射
    "plan",           # plan.md — 实施策略
    "contract",       # contracts/*.md — 接口契约 (尺子对照实验的关键输入)
    "seam_manifest",  # seam-manifest.yaml — 接缝声明 (M3 件 2 正式 schema)
    "authorization",  # authorization.yaml — 写权声明 (M3 件 3; db/network 越界审查的尺子)
    "failure_modes",  # failure-modes.md — 已知坑 + 复发判据
    "verify_report",  # C4 verify_report.json — 辅助信息
    "advisory",       # 其他辅助材料 (研究笔记 / quickstart 等)
]

# 权威档 (高 → 低). 判据冲突时高档为准; finding 归类按档位钉死 (见 prompt).
Authority = Literal["nc", "acceptance", "design", "failure_modes", "advisory"]

# 权威序 (index 越小越高). prompt 渲染与冲突裁决共用这一张表.
AUTHORITY_ORDER: tuple[Authority, ...] = (
    "nc", "acceptance", "design", "failure_modes", "advisory"
)

# kind → authority 固定映射 (单一权威, 调用方不可越级声明).
KIND_AUTHORITY: dict[str, Authority] = {
    "constitution": "nc",
    "spec": "acceptance",
    "ac_map": "acceptance",
    "plan": "design",
    "contract": "design",
    "seam_manifest": "design",
    "authorization": "design",
    "failure_modes": "failure_modes",
    "verify_report": "advisory",
    "advisory": "advisory",
}


class ReviewInputEntry(BaseModel):
    """review_inputs[] 单条 (v0.4.0).

    authority 由 kind 派生 (KIND_AUTHORITY), 不接受调用方覆盖 —— 权威序是
    尺子的一部分, 允许自定就等于允许把契约降级成参考资料.
    """

    kind: InputKind
    path: str = Field(description="相对 repo_root 或绝对路径")
    required: bool = Field(
        default=True,
        description="True 时文件缺失 → REVIEW_INPUT_MISSING fail-closed (session 不启动)",
    )
    content_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
        description=(
            "optional; 提供时对盘上内容做 CRLF→LF 归一化 sha256 校验, "
            "不一致 → REVIEW_INPUT_HASH_DRIFT fail-closed (防审到漂移后的输入)"
        ),
    )

    @property
    def authority(self) -> Authority:
        return KIND_AUTHORITY[self.kind]


class ResolvedReviewInput(BaseModel):
    """report 里记录的 resolved input (v0.4.0) — 审的是哪些输入、什么内容版本."""

    kind: InputKind
    path: str = Field(description="解析后的绝对路径")
    authority: Authority
    status: Literal["loaded", "skipped_missing"] = Field(
        description="loaded=进入 review 输入面; skipped_missing=非 required 且缺失"
    )
    content_sha256: str | None = Field(
        default=None,
        description="loaded 时盘上内容的 CRLF→LF 归一化 sha256 (实测值, 非声明值)",
    )


# -------------------------------------------------------------------
# §2.1 Input Schema
# -------------------------------------------------------------------


class ReviewInput(BaseModel):
    """C5 §2.1 Input Schema (v0.1.1: task_id 进 required)."""

    pr_ref: str = Field(description="PR URL (gh 可达) 或本地分支名 (无 remote 时降级)")
    spec_ref: str = Field(description="spec.md 路径 (相对 repo_root 或绝对)")
    plan_ref: str = Field(description="plan.md 路径")
    constitution_ref: str = Field(
        default=".specify/memory/constitution.md",
        description="constitution.md 路径",
    )
    verify_report_path: str | None = Field(
        default=None,
        description=(
            "optional; C4 verify_report.json 绝对路径; "
            "缺失时 C5 仍 work 但 AC 覆盖判断变弱"
        ),
    )
    task_id: str = Field(
        pattern=LOCAL_ID_PATTERN,
        description=(
            "v0.1.1 required: 所有 PR 必须来自 task (含 hotfix / Initiative). "
            "C5 不审'非 task PR' (应先把任务 task 化). "
            "v0.2.0: local id (feature 内唯一), 全局身份 = feature_id + task_id"
        ),
    )
    feature_id: str | None = Field(
        default=None,
        pattern=LOCAL_ID_PATTERN,
        description=(
            "canonical key 上半 (P0-1, 可选); 提供时 review 落盘键 = "
            "<safe_feature>-<task_id>, 缺省退化 task_id"
        ),
    )
    task_ids: list[str] | None = Field(
        default=None,
        description=(
            "v0.3.0 (P0-4): subject=feature 时的成员 task 清单; 提供时 "
            "task_id 槽位放 feature_id, review 覆盖整个 feature diff。"
            "单 task review (subject=task) 不传"
        ),
    )
    review_inputs: list[ReviewInputEntry] | None = Field(
        default=None,
        description=(
            "v0.4.0 (M3 件 1): typed inputs 清单, 在 spec/plan/constitution 三件核心输入"
            "之外追加 (contract / seam_manifest / failure_modes / ...)。核心三件由 "
            "synthesize_core_inputs 自动转成 entries, 调用方不必重复声明"
        ),
    )
    criticality: Criticality = Field(
        description="low/medium → 单次 review; high → N=2 仲裁 (P1.2 spike 后启用)"
    )
    repo_root: str = Field(description="业务项目根目录绝对路径")
    session_timeout_seconds: int = Field(
        default=1800,
        description="单 review session 上限 (默认 30 min, kill -9 整树)",
    )
    max_retries: int = Field(
        default=2,
        ge=0,
        le=2,
        description="SESSION_CRASHED / PR_DIFF_FETCH_FAILED 重试上限",
    )


# -------------------------------------------------------------------
# §2.2 Output Schema — review_report.json
# -------------------------------------------------------------------


class Finding(BaseModel):
    """单条 finding (C5 spec §I2: 必 4 字段齐)."""

    # pytest opt-out: Pydantic model 不是 test class
    __test__ = False

    severity: Severity
    category: Category
    location: str = Field(
        description="file:line 或 spec section reference, 例 'src/foo.py:42' / 'spec.md §3.1'"
    )
    suggested_fix: str = Field(
        description="具体可操作的修复建议 (不是泛泛 '改进代码')"
    )


ArbitrationMode = Literal["single", "n2_consensus", "n2_arbitrated"]


class Arbitration(BaseModel):
    """N=2 仲裁模式信息 (v0.1.x 阶段未启用, P1.2 spike 后实际生效)."""

    mode: ArbitrationMode = "single"
    reviewer_count: int = 1
    arbiter_session_id: str | None = None


class ReviewReport(BaseModel):
    """C5 §2.2 Output Schema — review_report.json (v0.1.1)."""

    verdict: Verdict = Field(
        description="always; 按 finding category 决定 (block 集合任一 → block; 其他 → approve)"
    )
    findings: list[Finding] = Field(
        default_factory=list,
        description="always; 每条 Finding 4 字段齐 (I2); 空数组合法 (无 issue → approve)",
    )
    reviewed_at: datetime = Field(description="always; ISO 8601")
    session_id: str = Field(description="always; 本次 review session UUID")
    task_id: str | None = Field(
        default=None,
        pattern=LOCAL_ID_PATTERN,
        description="conditional (when input.task_id 非空, v0.1.1 实际 always)",
    )
    pr_ref: str = Field(description="always; 回传 input.pr_ref")
    target_tree_sha: str | None = None
    contract_version: str = Field(
        pattern=r"^v\d+\.\d+\.\d+$",
        description="always; 本 spec 版本号",
    )
    arbitration: Arbitration | None = Field(
        default=None,
        description="conditional (when criticality=high 走 N=2 模式)",
    )
    review_inputs: list[ResolvedReviewInput] | None = Field(
        default=None,
        description=(
            "v0.4.0; 本次 review 实际的输入面 (kind/authority/实测 hash) — "
            "审计 '这个 verdict 是用什么尺子量出来的'; 为报告新鲜度绑定 (M3 件 4) 铺路"
        ),
    )


# -------------------------------------------------------------------
# §2.3 Error Schema
# -------------------------------------------------------------------

ErrorCode = Literal[
    "SESSION_CRASHED",
    "TIMEOUT",
    "SPEC_NOT_FOUND",
    "PR_DIFF_FETCH_FAILED",
    "INVALID_PR_REF",
    "VERIFY_REPORT_PARSE_FAILED",
    "ARBITRATION_DEADLOCK",
    "REPO_ROOT_NOT_FOUND",
    "INVALID_TASK_ID",  # task_id required after v0.1.1, schema 校验失败
    # v0.4.0 typed inputs (fail-closed, session 不启动):
    "REVIEW_INPUT_MISSING",           # required entry 文件缺失
    "REVIEW_INPUT_HASH_DRIFT",        # content_sha256 声明值 != 盘上实测值
    "REVIEW_INPUT_MANIFEST_INVALID",  # --inputs-manifest 文件不可解析 / schema 不符
]


class ReviewError(BaseModel):
    """C5 §2.3 Error Schema."""

    code: ErrorCode
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ReviewerError(Exception):
    """Python exception wrapping ReviewError, raised inside C5 components."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        **details: Any,
    ) -> None:
        self.error = ReviewError(code=code, message=message, details=details)
        super().__init__(f"{code}: {message}")
