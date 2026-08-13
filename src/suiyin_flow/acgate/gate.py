"""AC 冻结闸 — 判定核心 (纯机械, 零模型).

闭集判定 (gen4-plan 拍板 1):
- 冻结测试文件 删除 / 改名 / 新增 skip / 删除 def test_* → 明确弱化类
- 有删除行但不属上述闭集 → TEST_WEAKENED_UNKNOWN, **同样不放行** (fail-closed)
- 纯新增 (无删除行) = 加强, 放行

合法修改通道 (机械特征识别, 语义合法性交 C5/人):
- spec_changed: 该 AC 的权威来源文件 (spec/plan) 同 diff 变更 → Type B/C 放行
- projection_fix: spec 未变, diff 附 `.specify/**/projection-fixes/<ac_id>*` 证据 → 放行

hash 规约: sha256 over CRLF→LF 归一化字节 (NC-5; PR #64 Windows autocrlf 教训)。
"""

from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path

import yaml
from pydantic import ValidationError

from suiyin_flow.acgate.schema import (
    AcEntry,
    AcGateError,
    AcManifest,
    Channel,
    GateFinding,
    GateReport,
    GateVerdict,
)

_SKIP_RE = re.compile(
    r"@pytest\.mark\.skip|pytest\.skip\(|@unittest\.skip", re.IGNORECASE
)
_DEF_TEST_RE = re.compile(r"^\s*def\s+(test_[A-Za-z0-9_]+)\s*\(")
_PROJECTION_FIX_RE = re.compile(r"(^|/)projection-fixes/", re.IGNORECASE)


def norm_bytes(b: bytes) -> bytes:
    """CRLF→LF 归一化 (哈希与比较统一走这里)."""
    return b.replace(b"\r\n", b"\n")


def content_hash(b: bytes) -> str:
    return hashlib.sha256(norm_bytes(b)).hexdigest()


def ref_file_part(ref: str) -> str:
    """Return the file path portion of a manifest ref, preserving plain paths."""
    return ref.partition("#")[0]


# -------------------------------------------------------------------
# git 原语
# -------------------------------------------------------------------


def _git(repo_root: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            ["git", "-C", str(repo_root), *args],
            capture_output=True,
            shell=False,
            check=False,
        )
    except (subprocess.SubprocessError, FileNotFoundError, OSError) as e:
        raise AcGateError("GIT_ERROR", f"git {' '.join(args)}: {e}") from e


def _git_text(repo_root: Path, *args: str) -> str:
    r = _git(repo_root, *args)
    if r.returncode != 0:
        raise AcGateError(
            "GIT_ERROR",
            f"git {' '.join(args)} failed: {r.stderr.decode('utf-8', 'replace')[-300:]}",
        )
    return r.stdout.decode("utf-8", "replace")


def show_bytes(repo_root: Path, ref: str, path: str) -> bytes | None:
    """git show ref:path; 不存在返回 None."""
    r = _git(repo_root, "show", f"{ref}:{path}")
    if r.returncode != 0:
        return None
    return r.stdout


def changed_files(repo_root: Path, base_ref: str, head_ref: str) -> dict[str, str]:
    """diff 文件清单: path → status (A/M/D/R). rename 拆成旧 D + 新 A 语义."""
    out = _git_text(
        repo_root, "diff", "--name-status", "-M", f"{base_ref}...{head_ref}"
    )
    result: dict[str, str] = {}
    for line in out.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        status = parts[0]
        if status.startswith("R") and len(parts) >= 3:
            result[parts[1]] = "D"  # 旧路径视为删除 (manifest 指向旧路径)
            result[parts[2]] = "A"
        elif len(parts) >= 2:
            result[parts[-1]] = status[0]
    return result


def file_diff(repo_root: Path, base_ref: str, head_ref: str, path: str) -> str:
    return _git_text(
        repo_root, "diff", f"{base_ref}...{head_ref}", "--", path
    )


# -------------------------------------------------------------------
# manifest 加载
# -------------------------------------------------------------------


def load_manifest(path: Path) -> AcManifest:
    if not path.exists() or not path.is_file():
        raise AcGateError(
            "MANIFEST_NOT_FOUND", f"ac-manifest not found: {path}", path=str(path)
        )
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise AcGateError("INVALID_MANIFEST", f"YAML parse error: {e}") from e
    if not isinstance(data, dict):
        raise AcGateError("INVALID_MANIFEST", "top level must be a mapping")
    try:
        return AcManifest.model_validate(data)
    except ValidationError as e:
        raise AcGateError("INVALID_MANIFEST", f"schema validation failed: {e}") from e


# -------------------------------------------------------------------
# diff 解析
# -------------------------------------------------------------------


def _added_removed_lines(diff_text: str) -> tuple[list[str], list[str]]:
    added: list[str] = []
    removed: list[str] = []
    for line in diff_text.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            added.append(line[1:])
        elif line.startswith("-"):
            removed.append(line[1:])
    return added, removed


def _test_defs(lines: list[str]) -> set[str]:
    names: set[str] = set()
    for line in lines:
        m = _DEF_TEST_RE.match(line)
        if m:
            names.add(m.group(1))
    return names


# -------------------------------------------------------------------
# 核心判定
# -------------------------------------------------------------------


def run_gate(
    *,
    repo_root: Path,
    manifest_path: Path,
    base_ref: str,
    head_ref: str,
) -> GateReport:
    """跑一次 AC 冻结闸判定. Raises AcGateError (run 级错误)."""
    if not repo_root.exists() or not repo_root.is_dir():
        raise AcGateError(
            "REPO_ROOT_NOT_FOUND", f"repo_root not a directory: {repo_root}"
        )
    manifest = load_manifest(manifest_path)
    changed = changed_files(repo_root, base_ref, head_ref)

    findings: list[GateFinding] = []

    # 1) manifest 基准一致性 (fail-closed: manifest 必须反映 base 现实)
    findings.extend(_staleness_findings(repo_root, base_ref, manifest))

    # 2) 冻结测试文件逐个判定
    by_test: dict[str, list[AcEntry]] = {}
    for e in manifest.entries:
        by_test.setdefault(ref_file_part(e.test_ref), []).append(e)

    for test_ref, entries in sorted(by_test.items()):
        status = changed.get(test_ref)
        if status is None:
            continue  # 未动 → 冻结完好
        ac_ids = [e.ac_id for e in entries]
        channel = _resolve_channel(entries, changed)
        if status == "D":
            findings.append(
                _finding(
                    "TEST_FILE_DELETED",
                    test_ref,
                    ac_ids,
                    "冻结测试文件被删除/改名",
                    channel,
                )
            )
            continue
        diff_text = file_diff(repo_root, base_ref, head_ref, test_ref)
        added, removed = _added_removed_lines(diff_text)

        if any(_SKIP_RE.search(line) for line in added):
            findings.append(
                _finding(
                    "TEST_SKIPPED", test_ref, ac_ids, "新增 skip 标记", channel
                )
            )

        frozen_names = {n for e in entries for n in e.test_names}
        removed_defs = _test_defs(removed)
        added_defs = _test_defs(added)
        gone = removed_defs - added_defs  # 删了且没有同名新增 = 删除/改名
        if frozen_names:
            gone &= frozen_names
        if gone:
            findings.append(
                _finding(
                    "TEST_DELETED",
                    test_ref,
                    ac_ids,
                    f"冻结测试函数被删除/改名: {', '.join(sorted(gone))}",
                    channel,
                )
            )

        already = any(f.file == test_ref for f in findings)
        if removed and not already:
            # 有删除行但不属闭集 → UNKNOWN, fail-closed 不放行
            findings.append(
                _finding(
                    "TEST_WEAKENED_UNKNOWN",
                    test_ref,
                    ac_ids,
                    f"冻结测试文件有 {len(removed)} 处删除行, 机械闭集无法归类 → UNKNOWN 不放行",
                    channel,
                )
            )
        # 纯新增 (removed 为空) = 加强, 放行

    verdict: GateVerdict = "block" if any(f.blocking for f in findings) else "pass"
    return GateReport(
        feature_id=manifest.feature_id,
        verdict=verdict,
        base_ref=base_ref,
        head_ref=head_ref,
        findings=findings,
    )


def _finding(
    kind: str, file: str, ac_ids: list[str], detail: str, channel: Channel
) -> GateFinding:
    return GateFinding(
        kind=kind,  # type: ignore[arg-type]
        file=file,
        ac_ids=ac_ids,
        detail=detail,
        channel=channel,
        blocking=channel == "none",
    )


def _resolve_channel(entries: list[AcEntry], changed: dict[str, str]) -> Channel:
    """合法通道机械识别 (任一 entry 命中即放行整文件 finding).

    - spec_changed: 权威来源同 diff 变更 (Type B 补 spec+AC / Type C 改 spec+ADR;
      B/C 语义区分与 ADR 是否齐由 C5/人管, 闸只认"spec 动了")
    - projection_fix: diff 含 projection-fixes/<ac_id>* 证据文件 (新旧 oracle)
    """
    for e in entries:
        if ref_file_part(e.spec_ref) in changed:
            return "spec_changed"
    changed_paths = [p for p, s in changed.items() if s in ("A", "M")]
    for e in entries:
        for p in changed_paths:
            if _PROJECTION_FIX_RE.search(p) and e.ac_id.lower() in p.lower():
                return "projection_fix"
    return "none"


def _staleness_findings(
    repo_root: Path, base_ref: str, manifest: AcManifest
) -> list[GateFinding]:
    """manifest hash 必须与 base 侧实际文件一致; 不符 = 基准漂移, 恒 blocking.

    (spec_changed 不豁免 stale —— 基准坏了先重新 freeze, 否则后续判定全不可信)
    """
    findings: list[GateFinding] = []
    seen: set[tuple[str, str]] = set()
    for e in manifest.entries:
        for ref, expect, what in (
            (e.spec_ref, e.spec_hash, "spec"),
            (e.test_ref, e.test_hash, "test"),
        ):
            if (ref, expect) in seen:
                continue
            seen.add((ref, expect))
            b = show_bytes(repo_root, base_ref, ref_file_part(ref))
            actual = content_hash(b) if b is not None else None
            if actual != expect:
                findings.append(
                    GateFinding(
                        kind="MANIFEST_STALE",
                        file=ref,
                        ac_ids=[e.ac_id],
                        detail=(
                            f"manifest {what}_hash 与 base ({base_ref}) 实际不符"
                            f" (expect {expect[:12]}, actual "
                            f"{actual[:12] if actual else 'MISSING'}); "
                            "先 `suiyin-flow acgate freeze` 重新冻结"
                        ),
                        channel="none",
                        blocking=True,
                    )
                )
    return findings


# -------------------------------------------------------------------
# freeze: 生成/刷新 manifest hash
# -------------------------------------------------------------------


def freeze_manifest(
    *, repo_root: Path, manifest_path: Path, ref: str
) -> AcManifest:
    """按 ref 侧文件内容刷新 manifest 的 spec_hash/test_hash/baseline_ref 并写回.

    entries 骨架 (ac_id/spec_ref/test_ref/test_names) 由人/AI 先写好;
    freeze 只负责把 hash 钉到 ref 基准 (冻结动作本身要走 PR, 受 C5/人审).
    """
    manifest = load_manifest(manifest_path)
    for e in manifest.entries:
        for what, ref_path in (("spec", e.spec_ref), ("test", e.test_ref)):
            b = show_bytes(repo_root, ref, ref_file_part(ref_path))
            if b is None:
                raise AcGateError(
                    "INVALID_MANIFEST",
                    f"{what}_ref not found at {ref}: {ref_path}",
                    ac_id=e.ac_id,
                )
            if what == "spec":
                e.spec_hash = content_hash(b)
            else:
                e.test_hash = content_hash(b)
        e.baseline_ref = ref
    payload = yaml.safe_dump(
        manifest.model_dump(), allow_unicode=True, sort_keys=False
    )
    manifest_path.write_text(payload, encoding="utf-8")
    return manifest
