"""Feature 收口 harness — 确定性步进 (gen4-plan P0-4).

步序 (固定, fail-closed, 每步后落盘):
  human_block → acgate → mutation(触发键) → verify(C4 全量) → review(C5) → gate(C6)

- acgate / mutation 的工件 (ac-manifest.yaml / mutants.yaml) 约定与 tasks.yaml
  同目录; 缺失 → skipped_warning 放行 (迁移期语义, M3 门内转强制 — acgate QA-1)
- verify: C4 结构化 runner 只有 python/dart; 其余栈走 verify_cmd 兜底
  (gen4-plan P0-2 "Go verify 接线走 verify_cmd"), 合成 C4 §2.2 形状的
  verify_report (overall_verdict 由 exit code 决定), C6 照常消费
- review subject=feature: task_id=feature_id + task_ids=[...] (C5 v0.3.0)
- gate: 复用 C6 CLI (exit 0 merged / 1 held / 2 error)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from suiyin_flow.acgate.gate import run_gate
from suiyin_flow.acgate.schema import AcGateError
from suiyin_flow.c2_executor.batch import (
    BatchAdapterError,
    BatchManifest,
    load_tasks_yaml,
    resolve_feature_id,
)
from suiyin_flow.c4_verify.contract import (
    CONTRACT_VERSION as C4_VERSION,
)
from suiyin_flow.c4_verify.contract import (
    AcSummary,
    LevelsReport,
    TargetWorktree,
    VerifyReport,
)
from suiyin_flow.c5_reviewer.contract import (
    Criticality,
    InputKind,
    ReviewerError,
    ReviewInput,
    ReviewInputEntry,
)
from suiyin_flow.c6_gate import cli as c6_cli
from suiyin_flow.close_harness.blocks import load_block
from suiyin_flow.close_harness.schema import (
    CloseError,
    CloseReport,
    CloseStep,
    CloseVerdict,
    StepName,
)
from suiyin_flow.identity import safe_ref
from suiyin_flow.mutation.runner import run_probe
from suiyin_flow.mutation.schema import MutationError


@dataclass
class CloseConfig:
    tasks_yaml: Path
    repo_root: Path
    verify_cmd: str
    target_branch: str = "main"
    probe_env: dict[str, str] = field(default_factory=dict)
    gate_dry_run: bool = False  # C6 只评估不 merge (测试/预览)
    claude_cmd: list[str] | None = None  # C5 session 注入 (测试 mock)
    session_timeout_seconds: int = 1800


def _log(msg: str) -> None:
    print(msg, file=sys.stderr)


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, encoding="utf-8", shell=False, check=False,
    )


def _changed_files(repo: Path, target: str, feature: str) -> set[str]:
    r = _git(repo, "diff", "--name-only", f"{target}...{feature}")
    if r.returncode != 0:
        raise CloseError(
            "GIT_ERROR",
            f"diff {target}...{feature} failed: {r.stderr.strip()[-300:]}",
        )
    return {line.strip() for line in r.stdout.splitlines() if line.strip()}


# -------------------------------------------------------------------
# run_close
# -------------------------------------------------------------------


def run_close(cfg: CloseConfig) -> CloseReport:
    """跑完整收口. Raises CloseError (run 级)."""
    repo_root = cfg.repo_root.resolve()
    if not repo_root.exists() or not repo_root.is_dir():
        raise CloseError(
            "REPO_ROOT_NOT_FOUND", f"repo_root not a directory: {repo_root}"
        )
    try:
        manifest = load_tasks_yaml(cfg.tasks_yaml)
    except BatchAdapterError as e:
        raise CloseError(
            e.error.code,  # 枚举子集透传 (BatchErrorCode ⊂ CloseErrorCode)
            e.error.message,
            **e.error.details,
        ) from e

    feature_id = resolve_feature_id(manifest)
    bases = {t.base_branch for t in manifest.tasks}
    if len(bases) > 1:
        raise CloseError(
            "INVALID_MANIFEST", f"tasks must share one base_branch, got {sorted(bases)}"
        )
    base_branch = bases.pop()

    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + f"-{os.getpid()}"
    art_dir = repo_root / ".suiyin" / "close" / safe_ref(feature_id) / run_id
    art_dir.mkdir(parents=True, exist_ok=True)

    steps: list[CloseStep] = []
    report = CloseReport(
        feature_id=feature_id,
        base_branch=base_branch,
        target_branch=cfg.target_branch,
        verdict="held",
        steps=steps,
        run_id=run_id,
    )

    def finalize(verdict: CloseVerdict, held_at: StepName | None = None) -> CloseReport:
        report.verdict = verdict
        report.held_at = held_at
        _fill_not_reached(steps)
        report.steps = list(steps)  # pydantic 构造时拷贝过, 终态回填
        report.updated_at = datetime.now(UTC).isoformat()
        _write_report(repo_root, feature_id, run_id, report)
        return report

    # ---- step 1: human_block (最高优先级, 同 C6 I8) ----
    block = load_block(repo_root, feature_id)
    if block.blocked:
        steps.append(CloseStep(
            name="human_block", status="failed",
            detail=f"blocked locally: {block.reason}",
        ))
        return finalize("blocked", "human_block")
    steps.append(CloseStep(name="human_block", status="passed", detail="no local block"))

    manifest_dir = cfg.tasks_yaml.resolve().parent
    changed = _changed_files(repo_root, cfg.target_branch, base_branch)

    # ---- step 2: acgate ----
    if not _step_acgate(cfg, repo_root, manifest_dir, base_branch, art_dir, steps):
        return finalize("held", "acgate")

    # ---- step 3: mutation (触发键) ----
    if not _step_mutation(cfg, repo_root, manifest_dir, base_branch, changed, art_dir, steps):
        return finalize("held", "mutation")

    # ---- step 4: verify (C4 全量, verify_cmd 兜底) ----
    verify_path = _step_verify(cfg, repo_root, base_branch, art_dir, steps)
    if verify_path is None:
        return finalize("held", "verify")

    # ---- step 5: review (C5 subject=feature) ----
    review_path = _step_review(
        cfg, repo_root, manifest, feature_id, base_branch, verify_path, steps
    )
    if review_path is None:
        return finalize("held", "review")

    # ---- step 6: gate (C6) ----
    ok = _step_gate(cfg, repo_root, base_branch, verify_path, review_path, steps)
    return finalize("merged" if ok else "held", None if ok else "gate")


def _fill_not_reached(steps: list[CloseStep]) -> None:
    done = {s.name for s in steps}
    order: list[StepName] = ["human_block", "acgate", "mutation", "verify", "review", "gate"]
    for name in order:
        if name not in done:
            steps.append(CloseStep(name=name, status="not_reached"))


def _write_report(
    repo_root: Path, feature_id: str, run_id: str, report: CloseReport
) -> None:
    d = repo_root / ".suiyin" / "close"
    d.mkdir(parents=True, exist_ok=True)
    payload = report.model_dump_json(indent=2)
    (d / f"{safe_ref(feature_id)}-{run_id}.json").write_text(payload, encoding="utf-8")
    (d / f"latest-{safe_ref(feature_id)}.json").write_text(payload, encoding="utf-8")


# -------------------------------------------------------------------
# steps
# -------------------------------------------------------------------


def _step_acgate(
    cfg: CloseConfig, repo_root: Path, manifest_dir: Path,
    base_branch: str, art_dir: Path, steps: list[CloseStep],
) -> bool:
    ac_path = manifest_dir / "ac-manifest.yaml"
    if not ac_path.exists():
        steps.append(CloseStep(
            name="acgate", status="skipped_warning",
            detail="ac-manifest.yaml missing — 迁移期放行 (M3 门内转强制, acgate QA-1)",
        ))
        return True
    try:
        gate_report = run_gate(
            repo_root=repo_root, manifest_path=ac_path,
            base_ref=cfg.target_branch, head_ref=base_branch,
        )
    except AcGateError as e:
        raise CloseError("STEP_ERROR", f"acgate error: {e.message}", step="acgate") from e
    out = art_dir / "acgate_report.json"
    out.write_text(gate_report.model_dump_json(indent=2), encoding="utf-8")
    ok = gate_report.verdict == "pass"
    steps.append(CloseStep(
        name="acgate", status="passed" if ok else "failed",
        detail=f"verdict={gate_report.verdict}, findings={len(gate_report.findings)}",
        report_path=str(out),
    ))
    return ok


def _step_mutation(
    cfg: CloseConfig, repo_root: Path, manifest_dir: Path, base_branch: str,
    changed: set[str], art_dir: Path, steps: list[CloseStep],
) -> bool:
    mut_path = manifest_dir / "mutants.yaml"
    if not mut_path.exists():
        steps.append(CloseStep(
            name="mutation", status="skipped_warning",
            detail="mutants.yaml missing — 迁移期放行 (M3 门内转强制)",
        ))
        return True

    # 触发键 (拍板 1): AC/守卫测试变更 ∪ mutant 目录变更 ∪ 被测面变更 (target_file 近似)
    triggers: set[str] = set()
    try:
        rel_mut = str(mut_path.resolve().relative_to(repo_root))
        triggers.add(rel_mut)
    except ValueError:
        pass
    import yaml as _yaml

    try:
        mut_raw = _yaml.safe_load(mut_path.read_text(encoding="utf-8")) or {}
        for m in mut_raw.get("mutants", []):
            if isinstance(m, dict) and m.get("target_file"):
                triggers.add(str(m["target_file"]))
    except _yaml.YAMLError:
        pass  # 交给 run_probe 的 INVALID_CATALOG 报清晰错误
    ac_path = manifest_dir / "ac-manifest.yaml"
    if ac_path.exists():
        try:
            ac_raw = _yaml.safe_load(ac_path.read_text(encoding="utf-8")) or {}
            for e in ac_raw.get("entries", []):
                if isinstance(e, dict) and e.get("test_ref"):
                    triggers.add(str(e["test_ref"]))
        except _yaml.YAMLError:
            pass

    hit = sorted(changed & triggers)
    if not hit:
        steps.append(CloseStep(
            name="mutation", status="skipped",
            detail="触发键未命中 (AC/守卫测试、mutants.yaml、被测面均未变更)",
        ))
        return True

    try:
        probe = run_probe(
            repo_root=repo_root, catalog_path=mut_path,
            ref=base_branch, env_extra=cfg.probe_env,
        )
    except MutationError as e:
        raise CloseError("STEP_ERROR", f"mutation error: {e.message}", step="mutation") from e
    out = art_dir / "mutation_report.json"
    out.write_text(probe.model_dump_json(indent=2), encoding="utf-8")
    ok = probe.verdict == "pass"
    steps.append(CloseStep(
        name="mutation", status="passed" if ok else "failed",
        detail=(
            f"trigger={hit[:3]}, killed={probe.killed_count}, "
            f"survived={probe.survived_count}, baseline_ok={probe.baseline_ok}"
        ),
        report_path=str(out),
    ))
    return ok


def _step_verify(
    cfg: CloseConfig, repo_root: Path, base_branch: str,
    art_dir: Path, steps: list[CloseStep],
) -> str | None:
    """feature HEAD 全量 verify: throwaway worktree + verify_cmd (shell).

    合成 C4 §2.2 verify_report (C6 消费 overall_verdict; ac_summary 留空 —
    结构化 runner 后补时替换, gen4-plan P0-2 既定路线)。
    """
    wt = repo_root / ".suiyin" / "close-wt" / uuid.uuid4().hex[:12]
    wt.parent.mkdir(parents=True, exist_ok=True)
    r = _git(repo_root, "worktree", "add", "--detach", str(wt), base_branch)
    if r.returncode != 0:
        raise CloseError(
            "GIT_ERROR", f"verify worktree add failed: {r.stderr.strip()[-300:]}"
        )
    try:
        try:
            proc = subprocess.run(
                cfg.verify_cmd,
                cwd=str(wt),
                capture_output=True, text=True, encoding="utf-8",
                shell=True,  # 用户 shell 命令 (ADR-0005 例外)
                check=False,
                env={**os.environ, **cfg.probe_env},
            )
            exit_code: int | None = proc.returncode
            tail = ((proc.stdout or "") + (proc.stderr or ""))[-2000:]
        except OSError as e:
            exit_code, tail = None, f"verify_cmd failed to start: {e}"
    finally:
        _git(repo_root, "worktree", "remove", "--force", str(wt))

    verdict = "pass" if exit_code == 0 else "fail"
    report = VerifyReport(
        target=TargetWorktree(worktree_path=str(wt)),
        task_id=None,
        overall_verdict=verdict,  # type: ignore[arg-type]
        generated_at=datetime.now(UTC),
        contract_version=C4_VERSION,
        levels=LevelsReport(),
        ac_summary=AcSummary(),
    )
    out = art_dir / "verify_report.json"
    payload = json.loads(report.model_dump_json())
    payload["synthesized_by"] = "close_harness verify_cmd fallback"
    payload["verify_cmd_exit_code"] = exit_code
    payload["output_tail"] = tail
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    ok = verdict == "pass"
    steps.append(CloseStep(
        name="verify", status="passed" if ok else "failed",
        detail=f"verify_cmd exit={exit_code}",
        report_path=str(out),
    ))
    return str(out) if ok else None


def _detect_feature_review_inputs(
    repo_root: Path, spec_ref: str
) -> list[ReviewInputEntry] | None:
    """spec 同目录的契约资产自动进 C5 输入面 (v0.4.0 typed inputs).

    尺子对照实验 (dogfood/P0-attribution/): 契约不进输入面 = 接缝全盲。
    存在才收 (required=True, 此时文件已确认在盘上); 全缺 → None (纯 spec/plan review)。
    """
    spec_path = Path(spec_ref)
    if not spec_path.is_absolute():
        spec_path = repo_root / spec_ref
    feature_dir = spec_path.parent
    candidates: list[tuple[InputKind, Path]] = [
        ("ac_map", feature_dir / "ac-map.md"),
        ("failure_modes", feature_dir / "failure-modes.md"),
    ]
    # seam manifest: 正式版优先, 没有再收 draft (M2 产物是 draft; M3 件 2 转正式)
    for seam_name in ("seam-manifest.yaml", "seam-manifest.draft.yaml"):
        if (feature_dir / seam_name).is_file():
            candidates.append(("seam_manifest", feature_dir / seam_name))
            break
    entries = [
        ReviewInputEntry(kind=kind, path=str(p))
        for kind, p in candidates
        if p.is_file()
    ]
    contracts_dir = feature_dir / "contracts"
    if contracts_dir.is_dir():
        entries.extend(
            ReviewInputEntry(kind="contract", path=str(p))
            for p in sorted(contracts_dir.glob("*.md"))
        )
    return entries or None


def _step_review(
    cfg: CloseConfig, repo_root: Path, manifest: BatchManifest, feature_id: str,
    base_branch: str, verify_path: str, steps: list[CloseStep],
) -> str | None:
    from suiyin_flow.c5_reviewer.cli import execute_review

    t0 = manifest.tasks[0]
    order: dict[Criticality, int] = {"low": 0, "medium": 1, "high": 2}
    crit: Criticality = max((t.criticality for t in manifest.tasks), key=lambda c: order[c])
    review_input = ReviewInput(
        pr_ref=base_branch,
        spec_ref=t0.spec_ref,
        plan_ref=t0.plan_ref,
        constitution_ref=t0.constitution_ref,
        verify_report_path=verify_path,
        task_id=feature_id,       # subject=feature: task_id 槽位放 feature_id
        feature_id=feature_id,
        task_ids=[t.task_id for t in manifest.tasks],
        review_inputs=_detect_feature_review_inputs(repo_root, t0.spec_ref),
        criticality=crit,
        repo_root=str(repo_root),
        session_timeout_seconds=cfg.session_timeout_seconds,
    )
    try:
        verdict, report_path = execute_review(review_input, claude_cmd=cfg.claude_cmd)
    except ReviewerError as e:
        raise CloseError(
            "STEP_ERROR", f"review error: {e.error.code}: {e.error.message}",
            step="review",
        ) from e
    ok = verdict == "approve"
    steps.append(CloseStep(
        name="review", status="passed" if ok else "failed",
        detail=f"verdict={verdict} (subject=feature, tasks={len(manifest.tasks)})",
        report_path=str(report_path),
    ))
    return str(report_path) if ok else None


def _step_gate(
    cfg: CloseConfig, repo_root: Path, base_branch: str,
    verify_path: str, review_path: str, steps: list[CloseStep],
) -> bool:
    argv = [
        "gate", "run",
        "--pr-ref", base_branch,
        "--verify-report", verify_path,
        "--review-report", review_path,
        "--repo-root", str(repo_root),
    ]
    if cfg.gate_dry_run:
        argv.append("--dry-run")
    rc = c6_cli.main(argv)
    if rc == 2:
        raise CloseError("STEP_ERROR", "C6 gate run-level error (see stderr)", step="gate")
    ok = rc == 0
    steps.append(CloseStep(
        name="gate", status="passed" if ok else "failed",
        detail=f"C6 exit={rc} ({'merged' if ok else 'held'})"
        + (" [dry-run]" if cfg.gate_dry_run else ""),
    ))
    _log(f"close: gate {'merged' if ok else 'held'} (exit={rc})")
    return ok
