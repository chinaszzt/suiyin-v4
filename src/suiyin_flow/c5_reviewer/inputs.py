"""C5 typed inputs — v0.4.0 (M3 件 1, gen4-plan 拍板 7).

review 输入面显式化: 每个输入带 kind (闭集) / authority (由 kind 派生) /
required / content_sha256。session 启动前 fail-closed 校验:
required 缺失 → REVIEW_INPUT_MISSING; hash 漂移 → REVIEW_INPUT_HASH_DRIFT。

背景 (尺子对照实验, dogfood/P0-attribution/): 同一 C5 同一 diff, spec 输入
approve/0 findings; 契约进输入面 block/1 真 finding —— 审查质量是尺子的函数,
所以尺子必须显式声明、可校验、有权威序。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from suiyin_flow.acgate.gate import content_hash
from suiyin_flow.c5_reviewer.contract import (
    AUTHORITY_ORDER,
    ResolvedReviewInput,
    ReviewerError,
    ReviewInput,
    ReviewInputEntry,
)

MANIFEST_SCHEMA_VERSION = "v0.1.0"


def load_inputs_manifest(manifest_path: Path) -> list[ReviewInputEntry]:
    """解析 --inputs-manifest yaml → entries。不可解析/schema 不符 → fail-closed."""
    try:
        raw: Any = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as e:
        raise ReviewerError(
            "REVIEW_INPUT_MANIFEST_INVALID",
            f"inputs manifest unreadable: {e}",
            manifest_path=str(manifest_path),
        ) from e
    if not isinstance(raw, dict) or raw.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise ReviewerError(
            "REVIEW_INPUT_MANIFEST_INVALID",
            f"inputs manifest schema_version must be {MANIFEST_SCHEMA_VERSION}",
            manifest_path=str(manifest_path),
            got=raw.get("schema_version") if isinstance(raw, dict) else type(raw).__name__,
        )
    entries_raw = raw.get("inputs")
    if not isinstance(entries_raw, list) or not entries_raw:
        raise ReviewerError(
            "REVIEW_INPUT_MANIFEST_INVALID",
            "inputs manifest must contain a non-empty `inputs` list",
            manifest_path=str(manifest_path),
        )
    try:
        return [ReviewInputEntry(**e) for e in entries_raw]
    except (TypeError, ValidationError) as e:
        raise ReviewerError(
            "REVIEW_INPUT_MANIFEST_INVALID",
            f"inputs manifest entry invalid: {e}",
            manifest_path=str(manifest_path),
        ) from e


def synthesize_core_inputs(review_input: ReviewInput) -> list[ReviewInputEntry]:
    """核心三件 (constitution/spec/plan) + verify_report 转 typed entries。

    调用方 (含旧调用方) 不必在 review_inputs 里重复声明核心件 —— 输入面永远
    至少包含它们; SPEC_NOT_FOUND 语义由 validate_refs 保留 (向后兼容错误码)。
    """
    entries = [
        ReviewInputEntry(kind="constitution", path=review_input.constitution_ref),
        ReviewInputEntry(kind="spec", path=review_input.spec_ref),
        ReviewInputEntry(kind="plan", path=review_input.plan_ref),
    ]
    if review_input.verify_report_path:
        entries.append(
            ReviewInputEntry(
                kind="verify_report",
                path=review_input.verify_report_path,
                required=False,
            )
        )
    return entries


def resolve_inputs(
    entries: list[ReviewInputEntry],
    repo_root: Path,
) -> list[ResolvedReviewInput]:
    """fail-closed 解析: 存在性 + hash 校验, 输出按权威序排序的 resolved 清单."""
    resolved: list[ResolvedReviewInput] = []
    for entry in entries:
        path = Path(entry.path)
        if not path.is_absolute():
            path = repo_root / path
        if not path.is_file():
            if entry.required:
                raise ReviewerError(
                    "REVIEW_INPUT_MISSING",
                    f"required review input missing: {entry.kind} at {entry.path}",
                    kind=entry.kind,
                    path=str(path),
                )
            resolved.append(
                ResolvedReviewInput(
                    kind=entry.kind,
                    path=str(path),
                    authority=entry.authority,
                    status="skipped_missing",
                )
            )
            continue
        actual = content_hash(path.read_bytes())
        if entry.content_sha256 is not None and actual != entry.content_sha256:
            raise ReviewerError(
                "REVIEW_INPUT_HASH_DRIFT",
                f"review input content drifted: {entry.kind} at {entry.path}",
                kind=entry.kind,
                path=str(path),
                declared_sha256=entry.content_sha256,
                actual_sha256=actual,
            )
        resolved.append(
            ResolvedReviewInput(
                kind=entry.kind,
                path=str(path),
                authority=entry.authority,
                status="loaded",
                content_sha256=actual,
            )
        )
    resolved.sort(key=lambda r: AUTHORITY_ORDER.index(r.authority))
    return resolved
