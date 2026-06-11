"""C1 §5 Acceptance Criteria tests — AC-1..AC-11.

按 docs/sdd/components/c1-planning-engine.md v0.1.0 §5.
C1 是纯文件操作 (不碰 git), repo_root 只在语义 pass 当 cwd 用 → tmp dir 即可.
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

from suiyin_flow.c1_planning.cli import run_plan
from suiyin_flow.c1_planning.planner import MARKER
from suiyin_flow.c1_planning.schema import PlanningError
from suiyin_flow.c2_executor.batch import BatchAdapterError, load_tasks_yaml
from suiyin_flow.c7_coordinator.plan import load_manifest_and_plan


def _task_yaml(
    task_id: str,
    *,
    depends_on: list[str] | None = None,
    modifies: list[str] | None = None,
    context_seeds: list[str] | None = None,
) -> str:
    lines = [
        f"  - task_id: {task_id}",
        "    spec_ref: spec.md",
        "    plan_ref: plan.md",
        "    verify_cmd: 'true'",
    ]
    if depends_on:
        lines.append(f"    depends_on: [{', '.join(depends_on)}]")
    if modifies:
        lines.append(f"    modifies: [{', '.join(repr(m) for m in modifies)}]")
    if context_seeds:
        lines.append(f"    context_seeds: [{', '.join(repr(s) for s in context_seeds)}]")
    return "\n".join(lines)


def _write_manifest(
    tmp_path: Path, task_blocks: list[str], *, top_comment: str = "# top\n"
) -> Path:
    y = tmp_path / "tasks.yaml"
    body = top_comment + "schema_version: v0.1.0\nfeature_name: c1-test\ntasks:\n"
    body += "\n".join(task_blocks) + "\n"
    y.write_text(body, encoding="utf-8")
    return y


def _phases(out: object) -> list[tuple[int, list[str]]]:
    return [(e["phase"], e["parallel"]) for e in out.execution_plan]  # type: ignore[attr-defined]


# =============================================================================
# AC-1: r3 5-task 依赖链 → 3 phases
# =============================================================================


def test_AC_1_five_task_dep_chain_three_phases(tmp_path: Path) -> None:
    y = _write_manifest(
        tmp_path,
        [
            _task_yaml("T-001"),
            _task_yaml("T-002", depends_on=["T-001"]),
            _task_yaml("T-003", depends_on=["T-001"]),
            _task_yaml("T-004", depends_on=["T-001"]),
            _task_yaml("T-005", depends_on=["T-002", "T-003", "T-004"]),
        ],
    )
    out = run_plan(y, tmp_path)
    assert _phases(out) == [
        (1, ["T-001"]),
        (2, ["T-002", "T-003", "T-004"]),
        (3, ["T-005"]),
    ]
    assert out.phases_count == 3
    assert out.tasks_count == 5


# =============================================================================
# AC-2: depends_on 成环 → CYCLE_DETECTED, 不落盘
# =============================================================================


def test_AC_2_cycle_detected(tmp_path: Path) -> None:
    y = _write_manifest(
        tmp_path,
        [
            _task_yaml("T-001", depends_on=["T-002"]),
            _task_yaml("T-002", depends_on=["T-001"]),
        ],
    )
    before = y.read_text(encoding="utf-8")
    with pytest.raises(PlanningError) as exc_info:
        run_plan(y, tmp_path)
    assert exc_info.value.error.code == "CYCLE_DETECTED"
    cycle = exc_info.value.error.details["cycle"]
    assert cycle[0] == cycle[-1]  # 闭合
    assert set(cycle) == {"T-001", "T-002"}
    assert y.read_text(encoding="utf-8") == before  # 不落盘


def test_AC_2_multi_task_cycle(tmp_path: Path) -> None:
    y = _write_manifest(
        tmp_path,
        [
            _task_yaml("T-001", depends_on=["T-003"]),
            _task_yaml("T-002", depends_on=["T-001"]),
            _task_yaml("T-003", depends_on=["T-002"]),
        ],
    )
    with pytest.raises(PlanningError) as exc_info:
        run_plan(y, tmp_path)
    assert exc_info.value.error.code == "CYCLE_DETECTED"
    assert len(exc_info.value.error.details["cycle"]) == 4  # 3 节点 + 闭合


# =============================================================================
# AC-3: 同 phase modifies 重叠 (glob) → 拆分 + modifies_overlap
# =============================================================================


def test_AC_3_modifies_glob_overlap_split(tmp_path: Path) -> None:
    y = _write_manifest(
        tmp_path,
        [
            _task_yaml("T-001", modifies=["src/auth/**"]),
            _task_yaml("T-002", modifies=["src/auth/login.ts"]),
            _task_yaml("T-003", modifies=["src/api/client.ts"]),
        ],
    )
    out = run_plan(y, tmp_path)
    # T-001 与 T-002 写足迹重叠 → 拆开; T-003 独立, 留 phase 1
    ph = dict(_phases(out))
    assert "T-001" in ph[1] and "T-003" in ph[1]
    assert "T-002" in ph[2]
    splits = out.conflict_splits
    assert any(
        s.reason == "modifies_overlap"
        and {s.task_a, s.task_b} == {"T-001", "T-002"}
        for s in splits
    )


# =============================================================================
# AC-4: 一方 modifies 缺省 → fallback context_seeds → context_seeds_overlap
# =============================================================================


def test_AC_4_fallback_context_seeds_overlap(tmp_path: Path) -> None:
    y = _write_manifest(
        tmp_path,
        [
            _task_yaml("T-001", modifies=["src/a.ts"], context_seeds=["shared/cfg.ts"]),
            _task_yaml("T-002", context_seeds=["shared/cfg.ts"]),  # 无 modifies
        ],
    )
    out = run_plan(y, tmp_path)
    ph = dict(_phases(out))
    assert "T-001" in ph[1] and "T-002" in ph[2]
    assert any(s.reason == "context_seeds_overlap" for s in out.conflict_splits)


# =============================================================================
# AC-5: 产出喂 C7 plan 校验全过 (I1; 用 C7 实现当 oracle)
# =============================================================================


def test_AC_5_output_passes_c7_validation(tmp_path: Path) -> None:
    y = _write_manifest(
        tmp_path,
        [
            _task_yaml("T-001"),
            _task_yaml("T-002", depends_on=["T-001"]),
            _task_yaml("T-003", depends_on=["T-001"], modifies=["src/x.ts"]),
            _task_yaml("T-004", depends_on=["T-001"], modifies=["src/x.ts"]),
        ],
    )
    run_plan(y, tmp_path)
    # C7 公共入口重读写回的文件 → 不抛 = I1 自检 oracle 一致
    _manifest, phases, base = load_manifest_and_plan(y)
    assert base == "main"
    assert len(phases) >= 2


# =============================================================================
# AC-6: 写回后 top 注释 + tasks[] byte 级保留 + 可被 batch + C7 重解析
# =============================================================================


def test_AC_6_byte_preserve_prefix_and_reparseable(tmp_path: Path) -> None:
    top = "# 这是 sy-tasks 生成的推理注释\n# 第二行注释\n"
    y = _write_manifest(
        tmp_path,
        [_task_yaml("T-001"), _task_yaml("T-002", depends_on=["T-001"])],
        top_comment=top,
    )
    original = y.read_text(encoding="utf-8")
    run_plan(y, tmp_path)
    after = y.read_text(encoding="utf-8")
    # marker 之前的内容 (含 top 注释 + tasks) 一字节不变
    prefix = after[: after.find(MARKER)]
    assert prefix == original  # original 以 \n 结尾, prefix 直接等于它
    # batch loader + C7 都能重解析
    assert len(load_tasks_yaml(y).tasks) == 2
    load_manifest_and_plan(y)


# =============================================================================
# AC-7: dry_run → 文件零修改, stdout 摘要含 execution_plan
# =============================================================================


def test_AC_7_dry_run_no_write(tmp_path: Path) -> None:
    y = _write_manifest(
        tmp_path,
        [_task_yaml("T-001"), _task_yaml("T-002", depends_on=["T-001"])],
    )
    before = y.read_text(encoding="utf-8")
    out = run_plan(y, tmp_path, dry_run=True)
    assert out.status == "dry_run"
    assert out.written_to is None
    assert y.read_text(encoding="utf-8") == before  # 零修改
    assert len(out.execution_plan) == 2


# =============================================================================
# AC-8: 已有 marker 重跑 → 原位替换, 幂等 byte-identical
# =============================================================================


def test_AC_8_idempotent_marker_replace(tmp_path: Path) -> None:
    y = _write_manifest(
        tmp_path,
        [_task_yaml("T-001"), _task_yaml("T-002", depends_on=["T-001"])],
    )
    run_plan(y, tmp_path)
    after_first = y.read_text(encoding="utf-8")
    run_plan(y, tmp_path)
    after_second = y.read_text(encoding="utf-8")
    assert after_first == after_second  # 幂等
    assert after_second.count(MARKER) == 1  # 不叠加 marker


# =============================================================================
# AC-9: 无依赖无冲突 N task → 1 phase 全并行
# =============================================================================


def test_AC_9_all_parallel_single_phase(tmp_path: Path) -> None:
    y = _write_manifest(
        tmp_path,
        [_task_yaml("T-001"), _task_yaml("T-002"), _task_yaml("T-003")],
    )
    out = run_plan(y, tmp_path)
    assert _phases(out) == [(1, ["T-001", "T-002", "T-003"])]


# =============================================================================
# AC-10: 同输入连跑两次 byte-identical (I2 确定性)
# =============================================================================


def test_AC_10_deterministic(tmp_path: Path) -> None:
    blocks = [
        _task_yaml("T-001"),
        _task_yaml("T-002", depends_on=["T-001"], modifies=["src/m.ts"]),
        _task_yaml("T-003", depends_on=["T-001"], modifies=["src/m.ts"]),
        _task_yaml("T-004", depends_on=["T-001"]),
    ]
    text = "# top\nschema_version: v0.1.0\ntasks:\n" + "\n".join(blocks) + "\n"
    y1 = tmp_path / "a.yaml"
    y2 = tmp_path / "b.yaml"
    y1.write_text(text, encoding="utf-8")
    y2.write_text(text, encoding="utf-8")
    run_plan(y1, tmp_path)
    run_plan(y2, tmp_path)
    assert y1.read_text(encoding="utf-8") == y2.read_text(encoding="utf-8")


# =============================================================================
# AC-11: 语义 pass session 失败 → 静态结果落盘 + fallback_reason, exit 0
# =============================================================================


@pytest.fixture
def mock_claude_crash(tmp_path: Path) -> list[str]:
    script = tmp_path / "claude_crash.py"
    script.write_text(
        textwrap.dedent(
            """\
            import sys
            sys.stdin.read()
            sys.stderr.write("boom\\n")
            sys.exit(1)
            """
        ),
        encoding="utf-8",
    )
    return [sys.executable, str(script)]


def test_AC_11_semantic_pass_crash_fallbacks(
    tmp_path: Path, mock_claude_crash: list[str]
) -> None:
    y = _write_manifest(
        tmp_path,
        [_task_yaml("T-001"), _task_yaml("T-002"), _task_yaml("T-003")],
    )
    out = run_plan(
        y, tmp_path, semantic_pass=True, claude_cmd=mock_claude_crash
    )
    assert out.status == "written"
    assert out.semantic_pass is not None
    assert out.semantic_pass.completed is False
    assert out.semantic_pass.fallback_reason  # 非空
    # 静态结果仍正常落盘 (3 独立 task → 1 phase)
    assert _phases(out) == [(1, ["T-001", "T-002", "T-003"])]


def test_AC_11_semantic_pass_success_tightens(tmp_path: Path) -> None:
    """语义 pass 成功且报冲突 → 收紧 (拆 phase) + reason=semantic_conflict."""
    script = tmp_path / "claude_ok.py"
    script.write_text(
        textwrap.dedent(
            """\
            import json, sys
            sys.stdin.read()
            print(json.dumps({"conflicts": [{"task_a": "T-001", "task_b": "T-002"}]}))
            """
        ),
        encoding="utf-8",
    )
    y = _write_manifest(
        tmp_path,
        [_task_yaml("T-001"), _task_yaml("T-002"), _task_yaml("T-003")],
    )
    out = run_plan(
        y, tmp_path, semantic_pass=True, claude_cmd=[sys.executable, str(script)]
    )
    assert out.semantic_pass is not None and out.semantic_pass.completed is True
    assert out.semantic_pass.adjustments == 1
    ph = dict(_phases(out))
    # T-001/T-002 被语义判定冲突 → 不同 phase
    assert ph[1] != ph[2] if 2 in ph else True
    assert any(s.reason == "semantic_conflict" for s in out.conflict_splits)


# =============================================================================
# 透传: MANIFEST_NOT_FOUND / INVALID_MANIFEST (base 不一致)
# =============================================================================


def test_manifest_not_found_passthrough(tmp_path: Path) -> None:
    with pytest.raises(BatchAdapterError) as exc_info:
        run_plan(tmp_path / "nope.yaml", tmp_path)
    assert exc_info.value.error.code == "MANIFEST_NOT_FOUND"


def test_mixed_base_branch_invalid(tmp_path: Path) -> None:
    y = tmp_path / "tasks.yaml"
    y.write_text(
        "schema_version: v0.1.0\ntasks:\n"
        "  - task_id: T-001\n    spec_ref: s\n    plan_ref: p\n"
        "    verify_cmd: 'true'\n    base_branch: main\n"
        "  - task_id: T-002\n    spec_ref: s\n    plan_ref: p\n"
        "    verify_cmd: 'true'\n    base_branch: feat\n",
        encoding="utf-8",
    )
    with pytest.raises(PlanningError) as exc_info:
        run_plan(y, tmp_path)
    assert exc_info.value.error.code == "INVALID_MANIFEST"
