"""Independent test author pipeline."""

from __future__ import annotations

import fnmatch
import json
import re
import subprocess
import uuid
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import ValidationError

from suiyin_flow.acgate.gate import freeze_manifest, load_manifest
from suiyin_flow.acgate.schema import AcEntry, AcGateError, AcManifest
from suiyin_flow.c2_executor.batch import (
    BatchAdapterError,
    BatchTaskEntry,
    load_tasks_yaml,
    resolve_feature_id,
)
from suiyin_flow.c5_reviewer.contract import (
    ResolvedReviewInput,
    ReviewerError,
    ReviewInputEntry,
)
from suiyin_flow.c5_reviewer.inputs import load_inputs_manifest, resolve_inputs
from suiyin_flow.c5_reviewer.session import run_session
from suiyin_flow.identity import safe_ref
from suiyin_flow.testauthor.schema import (
    FrozenInfo,
    PathCheck,
    RedCheck,
    TargetResult,
    TargetsManifest,
    TestAuthorError,
    TestAuthorReport,
    TestTarget,
)
from suiyin_flow.treesha import resolve_tree_sha

DEFAULT_TIMEOUT_SECONDS = 1800.0
_JSON_BLOCK = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def load_targets(path: Path) -> TargetsManifest:
    """Load and validate a v0.1.0 target manifest, fail-closed."""
    try:
        data: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise TestAuthorError(
            "TESTAUTHOR_TARGETS_INVALID",
            f"targets manifest unreadable: {exc}",
            path=str(path),
        ) from exc
    if not isinstance(data, dict):
        raise TestAuthorError(
            "TESTAUTHOR_TARGETS_INVALID",
            "targets manifest top level must be a mapping",
            path=str(path),
        )
    try:
        return TargetsManifest.model_validate(data)
    except ValidationError as exc:
        raise TestAuthorError(
            "TESTAUTHOR_TARGETS_INVALID",
            f"targets manifest schema validation failed: {exc}",
            path=str(path),
        ) from exc


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            shell=False,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise TestAuthorError(
            "TESTAUTHOR_SESSION_CRASHED",
            f"git {' '.join(args)} failed to start: {exc}",
        ) from exc


def _make_author_worktree(
    repo_root: Path,
    *,
    feature_id: str,
    task_id: str,
    base_ref: str,
    run_id: str,
) -> tuple[Path, str]:
    safe_feature = safe_ref(feature_id)
    safe_task = safe_ref(task_id)
    worktree = (
        repo_root
        / ".suiyin"
        / "testauthor-wt"
        / f"{safe_feature}-{safe_task}"
        / run_id
    ).resolve()
    branch = f"testauthor/{safe_feature}/{safe_task}-{run_id}"
    worktree.parent.mkdir(parents=True, exist_ok=True)
    result = _git(
        repo_root,
        "worktree",
        "add",
        str(worktree),
        "-b",
        branch,
        base_ref,
    )
    if result.returncode != 0:
        raise TestAuthorError(
            "TESTAUTHOR_BASE_UNAVAILABLE",
            f"author worktree could not be created: {result.stderr.strip()[-500:]}",
            base_ref=base_ref,
            author_branch=branch,
            author_worktree=str(worktree),
        )
    return worktree, branch


def _render_typed_inputs(inputs: list[ResolvedReviewInput]) -> str:
    lines: list[str] = []
    for item in inputs:
        if item.status == "loaded":
            lines.append(
                f"- **{item.kind}** [{item.authority}]: {item.path} (required reading)"
            )
        else:
            lines.append(
                f"- **{item.kind}** [{item.authority}]: missing optional input (skip)"
            )
    return "\n".join(lines)


def _render_prompt(
    *,
    task_id: str,
    worktree: Path,
    targets: list[TestTarget],
    test_paths: list[str],
    resolved_inputs: list[ResolvedReviewInput],
) -> str:
    target_lines: list[str] = []
    for target in targets:
        suggestion = (
            f"; suggested test ref: {target.suggested_test_ref}"
            if target.suggested_test_ref
            else ""
        )
        target_lines.append(
            f"- {target.target_id} ({target.kind}), source={target.source}{suggestion}\n"
            f"  directive: {target.directive}"
        )
    target_block = "\n".join(target_lines)
    path_block = "\n".join(f"- {pattern}" for pattern in test_paths)
    example = {target.target_id: ["path/to/test_file.py::test_named_case"] for target in targets}
    return f"""\
# Independent Test Author

You are an independent test author. Write truth-discriminating tests from declarations only.
Never infer assertions from the current implementation's behavior, and never read implementer
artifacts or `.suiyin/sessions/*`. You may inspect base code only to learn import/build surfaces.

AUTHOR_WORKTREE: {worktree}
TASK_ID: {task_id}

All file reads and writes for the authored tests MUST happen inside AUTHOR_WORKTREE. Your process
already starts there; do not write in the caller repository.

## Typed inputs (highest authority first)

{_render_typed_inputs(resolved_inputs)}

## Targets (each directive is the only test-writing instruction for that target)

{target_block}

## Allowed test paths

{path_block}

## Constraints

- Write only files matched by the allowed test paths. Do not modify implementation or contracts.
- Produce at least one named test function for every target you can author.
- Every authored target must be non-green when the implementation is absent; compile/import
  failure is a valid red result.
- Never skip, xfail, short-circuit, or weaken a test.
- Your final output line must be a JSON code block mapping target_id to test refs exactly like:
```json
{json.dumps(example, ensure_ascii=False)}
```
"""


def _json_objects(text: str) -> list[dict[str, Any]]:
    objects: list[dict[str, Any]] = []
    stripped = text.strip()
    try:
        direct: Any = json.loads(stripped)
    except (json.JSONDecodeError, TypeError):
        direct = None
    if isinstance(direct, dict):
        objects.append(direct)
    for match in _JSON_BLOCK.finditer(text):
        try:
            candidate: Any = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        if isinstance(candidate, dict):
            objects.append(candidate)
    return objects


def _mapping_from_log(log_path: Path, target_ids: set[str]) -> dict[str, list[str]] | None:
    candidates: list[dict[str, Any]] = []
    try:
        lines = log_path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return None
    for line in lines:
        for event in _json_objects(line):
            candidates.append(event)
            result = event.get("result")
            if isinstance(result, str):
                candidates.extend(_json_objects(result))
            message = event.get("message")
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and isinstance(block.get("text"), str):
                            candidates.extend(_json_objects(block["text"]))
    for candidate in reversed(candidates):
        if not set(candidate).issubset(target_ids):
            continue
        if not all(
            isinstance(refs, list) and all(isinstance(ref, str) for ref in refs)
            for refs in candidate.values()
        ):
            continue
        mapping: dict[str, list[str]] = {}
        for target_id, raw_refs in candidate.items():
            refs = [ref.strip() for ref in raw_refs if ref.strip()]
            mapping[target_id] = list(dict.fromkeys(refs))
        return mapping
    return None


def _commit_if_changed(worktree: Path, message: str) -> bool:
    added = _git(worktree, "add", "-A")
    if added.returncode != 0:
        raise TestAuthorError(
            "TESTAUTHOR_SESSION_CRASHED",
            f"git add failed in author worktree: {added.stderr.strip()[-500:]}",
            author_worktree=str(worktree),
        )
    changed = _git(worktree, "diff", "--cached", "--quiet")
    if changed.returncode == 0:
        return False
    if changed.returncode != 1:
        raise TestAuthorError(
            "TESTAUTHOR_SESSION_CRASHED",
            f"could not inspect staged author output: {changed.stderr.strip()[-500:]}",
            author_worktree=str(worktree),
        )
    committed = _git(worktree, "commit", "-m", message)
    if committed.returncode != 0:
        raise TestAuthorError(
            "TESTAUTHOR_SESSION_CRASHED",
            f"git commit failed in author worktree: {committed.stderr.strip()[-500:]}",
            author_worktree=str(worktree),
        )
    return True


def _touched_paths(worktree: Path, base_ref: str) -> list[str]:
    result = _git(worktree, "diff", "--name-only", f"{base_ref}...HEAD")
    if result.returncode != 0:
        raise TestAuthorError(
            "TESTAUTHOR_SESSION_CRASHED",
            f"could not inspect author diff: {result.stderr.strip()[-500:]}",
            author_worktree=str(worktree),
        )
    return list(dict.fromkeys(line.replace("\\", "/") for line in result.stdout.splitlines()))


def _matches_any(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(path, pattern.replace("\\", "/")) for pattern in patterns)


def _run_red(worktree: Path, command: str) -> RedCheck:
    try:
        result = subprocess.run(
            command,
            cwd=worktree,
            capture_output=True,
            text=True,
            encoding="utf-8",
            shell=True,  # user-provided shell command string (ADR-0005 exception)
            check=False,
        )
    except OSError:
        return RedCheck(cmd=command, exit_code=-1, red=False)
    return RedCheck(cmd=command, exit_code=result.returncode, red=result.returncode != 0)


def _relative_repo_path(path_text: str, repo_root: Path, worktree: Path) -> str | None:
    path = Path(path_text)
    if not path.is_absolute():
        return path.as_posix()
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        try:
            return path.resolve().relative_to(worktree.resolve()).as_posix()
        except ValueError:
            return None


def _source_ref(
    target: TestTarget,
    task: BatchTaskEntry,
    repo_root: Path,
    worktree: Path,
) -> str:
    token = target.source.split(maxsplit=1)[0]
    candidate = Path(token)
    on_disk = candidate if candidate.is_absolute() else worktree / candidate
    if on_disk.is_file():
        relative = _relative_repo_path(token, repo_root, worktree)
        if relative is not None and (worktree / relative).is_file():
            return relative
    fallback = _relative_repo_path(task.spec_ref, repo_root, worktree)
    return fallback if fallback is not None else Path(task.spec_ref).as_posix()


def _split_test_ref(test_ref: str, worktree: Path) -> tuple[str, str | None] | None:
    file_part, separator, name_part = test_ref.partition("::")
    relative = _relative_repo_path(file_part, worktree, worktree)
    if relative is None or not (worktree / relative).is_file():
        return None
    test_name = name_part.split("::")[-1].strip() if separator else None
    return relative, test_name or None


def _manifest_path(task: BatchTaskEntry, repo_root: Path, worktree: Path) -> Path | None:
    spec_ref = _relative_repo_path(task.spec_ref, repo_root, worktree)
    if spec_ref is None:
        return None
    return worktree / Path(spec_ref).parent / "ac-manifest.yaml"


def _freeze(
    *,
    repo_root: Path,
    worktree: Path,
    feature_id: str,
    task: BatchTaskEntry,
    targets_by_id: dict[str, TestTarget],
    results: list[TargetResult],
) -> tuple[FrozenInfo | None, str | None]:
    manifest_path = _manifest_path(task, repo_root, worktree)
    if manifest_path is None:
        return None, f"cannot derive manifest path from spec_ref {task.spec_ref!r}"
    try:
        manifest: AcManifest | None
        if manifest_path.is_file():
            manifest = load_manifest(manifest_path)
            if manifest.feature_id != feature_id:
                return None, (
                    "existing manifest feature_id mismatch: "
                    f"expected {feature_id!r}, got {manifest.feature_id!r}"
                )
            entries = list(manifest.entries)
        else:
            entries = []
            manifest = None
        existing_ids = {entry.ac_id for entry in entries}
        new_entries: list[AcEntry] = []
        for result in results:
            if result.status != "authored":
                continue
            if result.target_id in existing_ids:
                return None, f"duplicate ac_id in manifest: {result.target_id!r}"
            target = targets_by_id[result.target_id]
            first = _split_test_ref(result.test_refs[0], worktree)
            if first is None:
                return None, (
                    "authored test_ref does not resolve to a test file: "
                    f"{result.test_refs[0]!r}"
                )
            test_file, first_name = first
            names: list[str] = []
            for test_ref in result.test_refs:
                split = _split_test_ref(test_ref, worktree)
                if split is not None and split[1] is not None:
                    names.append(split[1])
            if first_name is not None and first_name not in names:
                names.insert(0, first_name)
            new_entries.append(
                AcEntry(
                    ac_id=result.target_id,
                    kind="behavior" if target.kind == "ac" else "guard",
                    spec_ref=_source_ref(target, task, repo_root, worktree),
                    spec_hash="",
                    test_ref=test_file,
                    test_hash="",
                    test_names=list(dict.fromkeys(names)),
                    baseline_ref="HEAD",
                )
            )
            existing_ids.add(result.target_id)
        if not new_entries:
            return None, "no authored targets were eligible for freezing"
        if manifest is None:
            manifest = AcManifest(feature_id=feature_id, entries=new_entries)
        else:
            manifest.entries = [*entries, *new_entries]
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            yaml.safe_dump(manifest.model_dump(), allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        frozen = freeze_manifest(
            repo_root=worktree,
            manifest_path=manifest_path,
            ref="HEAD",
        )
        _commit_if_changed(worktree, "testauthor: freeze authored tests")
    except (
        AcGateError,
        OSError,
        ValidationError,
        ValueError,
        IndexError,
        TestAuthorError,
    ) as exc:
        return None, f"{type(exc).__name__}: {exc}"
    relative_manifest = manifest_path.relative_to(worktree).as_posix()
    return FrozenInfo(manifest_path=relative_manifest, entries=len(frozen.entries)), None


def _write_report(report: TestAuthorReport, artifact_dir: Path) -> None:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "testauthor_report.json").write_text(
        report.model_dump_json(indent=2),
        encoding="utf-8",
    )


def run_author(
    *,
    repo_root: Path,
    tasks_yaml_path: Path,
    task_id: str,
    targets_path: Path,
    test_paths: list[str],
    inputs_manifest_path: Path | None = None,
    base_ref: str | None = None,
    red_cmd: str | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    claude_cmd: list[str] | None = None,
) -> TestAuthorReport:
    """Run one independent author session and retain its branch/worktree handoff."""
    targets_manifest = load_targets(targets_path)
    if targets_manifest.task_id != task_id:
        raise TestAuthorError(
            "TESTAUTHOR_TARGETS_INVALID",
            "targets manifest task_id does not match requested task",
            requested_task_id=task_id,
            manifest_task_id=targets_manifest.task_id,
        )
    if not test_paths or any(not pattern.strip() for pattern in test_paths):
        raise TestAuthorError(
            "TESTAUTHOR_TARGETS_INVALID",
            "test_paths must contain at least one non-empty glob",
        )
    try:
        tasks_manifest = load_tasks_yaml(tasks_yaml_path)
    except BatchAdapterError as exc:
        raise TestAuthorError(
            "TESTAUTHOR_TASK_UNKNOWN",
            f"tasks.yaml could not be loaded: {exc.error.message}",
            path=str(tasks_yaml_path),
        ) from exc
    task = next((item for item in tasks_manifest.tasks if item.task_id == task_id), None)
    if task is None:
        raise TestAuthorError(
            "TESTAUTHOR_TASK_UNKNOWN",
            f"task_id {task_id!r} is not present in tasks.yaml",
            task_id=task_id,
        )
    feature_id = resolve_feature_id(tasks_manifest)
    effective_base = base_ref or task.base_branch
    try:
        target_tree_sha = resolve_tree_sha(repo_root, effective_base)
    except ValueError as exc:
        raise TestAuthorError(
            "TESTAUTHOR_BASE_UNAVAILABLE",
            str(exc),
            base_ref=effective_base,
        ) from exc

    session_id = str(uuid.uuid4())
    run_id = session_id.replace("-", "")[:8]
    worktree, branch = _make_author_worktree(
        repo_root,
        feature_id=feature_id,
        task_id=task_id,
        base_ref=effective_base,
        run_id=run_id,
    )
    entries = [ReviewInputEntry(kind="constitution", path=task.constitution_ref)]
    if inputs_manifest_path is not None:
        entries.extend(load_inputs_manifest(inputs_manifest_path))
    resolved_inputs = resolve_inputs(entries, worktree)

    artifact_dir = (
        repo_root
        / ".suiyin"
        / "testauthor"
        / f"{safe_ref(feature_id)}-{safe_ref(task_id)}"
        / session_id
    )
    prompt = _render_prompt(
        task_id=task_id,
        worktree=worktree,
        targets=targets_manifest.targets,
        test_paths=test_paths,
        resolved_inputs=resolved_inputs,
    )
    try:
        session = run_session(
            task_id=task_id,
            prompt=prompt,
            review_dir=artifact_dir,
            session_id=session_id,
            timeout_seconds=timeout_seconds,
            claude_cmd=claude_cmd,
            feature_id=feature_id,
            cost_repo_root=repo_root,
            cwd=worktree,
        )
    except ReviewerError as exc:
        raise TestAuthorError(
            "TESTAUTHOR_SESSION_CRASHED",
            exc.error.message,
            **exc.error.details,
        ) from exc
    except (OSError, subprocess.SubprocessError) as exc:
        raise TestAuthorError(
            "TESTAUTHOR_SESSION_CRASHED",
            f"author session could not start: {exc}",
            task_id=task_id,
            session_id=session_id,
        ) from exc
    if session.timed_out:
        raise TestAuthorError(
            "TESTAUTHOR_TIMEOUT",
            f"author session timed out after {timeout_seconds}s",
            task_id=task_id,
            session_id=session_id,
            log_path=str(session.log_path),
        )
    if session.exit_code != 0:
        raise TestAuthorError(
            "TESTAUTHOR_SESSION_CRASHED",
            f"claude session exit_code={session.exit_code}",
            task_id=task_id,
            session_id=session_id,
            log_path=str(session.log_path),
        )
    target_ids = {target.target_id for target in targets_manifest.targets}
    mapping = _mapping_from_log(session.log_path, target_ids)
    if mapping is None:
        raise TestAuthorError(
            "TESTAUTHOR_SESSION_CRASHED",
            "author session finished without a valid target-to-test JSON mapping",
            task_id=task_id,
            session_id=session_id,
            log_path=str(session.log_path),
        )

    session_commit_created = _commit_if_changed(
        worktree, f"testauthor: author tests for {task_id}"
    )
    touched = _touched_paths(worktree, effective_base)
    violations = [path for path in touched if not _matches_any(path, test_paths)]
    path_check = PathCheck(touched=touched, violations=violations)
    effective_red_cmd = red_cmd if red_cmd is not None else task.verify_cmd
    red_check = _run_red(worktree, effective_red_cmd)

    results: list[TargetResult] = []
    for target in targets_manifest.targets:
        refs = mapping.get(target.target_id, [])
        refs_touch_session_output = bool(refs) and all(
            (split := _split_test_ref(test_ref, worktree)) is not None
            and split[0] in touched
            and split[1] is not None
            for test_ref in refs
        )
        if refs and red_check.red and session_commit_created and refs_touch_session_output:
            results.append(
                TargetResult(target_id=target.target_id, status="authored", test_refs=refs)
            )
        else:
            if not refs:
                note = "author session returned no test refs for target"
            elif not session_commit_created:
                note = "author session produced no commit"
            elif not refs_touch_session_output:
                note = "reported test refs are not files authored by this session"
            else:
                note = "red check was green; target cannot be counted as authored"
            results.append(
                TargetResult(
                    target_id=target.target_id,
                    status="skipped",
                    test_refs=refs,
                    note=note,
                )
            )

    authored = [result for result in results if result.status == "authored"]
    frozen: FrozenInfo | None = None
    freeze_error: str | None = None
    if not violations and red_check.red and authored:
        frozen, freeze_error = _freeze(
            repo_root=repo_root,
            worktree=worktree,
            feature_id=feature_id,
            task=task,
            targets_by_id={target.target_id: target for target in targets_manifest.targets},
            results=results,
        )
    verdict: Literal["pass", "fail"] = (
        "pass"
        if not violations and red_check.red and bool(authored) and frozen is not None
        else "fail"
    )
    report = TestAuthorReport(
        task_id=task_id,
        session_id=session_id,
        target_tree_sha=target_tree_sha,
        targets=results,
        path_check=path_check,
        red_check=red_check,
        frozen=frozen,
        freeze_error=freeze_error,
        verdict=verdict,
        author_branch=branch,
        author_worktree=str(worktree),
    )
    _write_report(report, artifact_dir)
    return report
