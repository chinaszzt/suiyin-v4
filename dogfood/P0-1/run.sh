#!/bin/bash
# P0-1 canonical identity dogfood — v4lab 真仓 clone, 零 token (不起 claude session)
set -u
LAB=~/suiyin-desk-v4lab
SF=/Users/zhangtuo/Documents/suiyin-v4/.venv/bin/suiyin-flow
PY=/Users/zhangtuo/Documents/suiyin-v4/.venv/bin/python
BR=v4lab/002-t001-replay-b
BASE_SHA=6753721d82158564ceae449e8cbf5dafa68194e2
EV=/private/tmp/claude-501/-Users-zhangtuo-Documents-suiyin-v4/0b2291cd-c227-4c76-af99-218e34c9a3ed/scratchpad/p0_1_evidence
mkdir -p "$EV"
cd "$LAB" || exit 1

echo "=== [1] v0.1.0 manifest + T-001B: dry-run 放行 (repo 外) ==="
cat > /tmp/p01-tasks-v010.yaml <<YAML
schema_version: v0.1.0
feature_name: 002-t001-replay
tasks:
  - task_id: T-001B
    spec_ref: README.md
    plan_ref: README.md
    constitution_ref: README.md
    verify_cmd: "true"
    base_branch: $BR
YAML
$SF task batch --tasks-yaml /tmp/p01-tasks-v010.yaml --repo-root "$LAB" --dry-run > "$EV/1-dryrun-v010.json" 2> "$EV/1-dryrun-v010.err"
echo "exit=$? (expect 0)"; head -c 300 "$EV/1-dryrun-v010.json"

echo; echo "=== [2] 未提交 manifest → 真跑 fail-fast INVALID_MANIFEST (session 前) ==="
cp /tmp/p01-tasks-v010.yaml "$LAB/p01-tasks.yaml"
$SF task batch --tasks-yaml "$LAB/p01-tasks.yaml" --repo-root "$LAB" > "$EV/2-uncommitted.out" 2> "$EV/2-uncommitted.err"
echo "exit=$? (expect 2)"; grep -o "not committed on base_branch[^\"]*" "$EV/2-uncommitted.err" | head -1

echo; echo "=== [3] 提交后 precheck 放行 (python API, 不起 session); 盘上再改 → 漂移拒 ==="
git -C "$LAB" add p01-tasks.yaml && git -C "$LAB" commit -q -m "[p0-1 dogfood] manifest"
$PY - <<PYEOF
from pathlib import Path
from suiyin_flow.c2_executor.batch import load_tasks_yaml, precheck_refs_on_base, resolve_feature_id
p = Path("$LAB/p01-tasks.yaml")
m = load_tasks_yaml(p)
precheck_refs_on_base(m, "$LAB", p)
print("precheck PASS (committed, consistent); resolved feature_id =", resolve_feature_id(m))
PYEOF
printf "\n# drift\n" >> "$LAB/p01-tasks.yaml"
$SF task batch --tasks-yaml "$LAB/p01-tasks.yaml" --repo-root "$LAB" > "$EV/3-drift.out" 2> "$EV/3-drift.err"
echo "exit=$? (expect 2)"; grep -o "differs from base_branch[^\"]*" "$EV/3-drift.err" | head -1

echo; echo "=== [4] v0.2.0 manifest + 显式 feature_id → phase dry-run 新落盘键 ==="
git -C "$LAB" checkout -q -- p01-tasks.yaml
cat > /tmp/p01-tasks-v020.yaml <<YAML
schema_version: v0.2.0
feature_id: p0-1-dogfood
tasks:
  - task_id: T-001B
    spec_ref: README.md
    plan_ref: README.md
    constitution_ref: README.md
    verify_cmd: "true"
    base_branch: $BR
YAML
$SF phase run --tasks /tmp/p01-tasks-v020.yaml --repo-root "$LAB" --dry-run > "$EV/4-phase-dryrun.json" 2> "$EV/4-phase-dryrun.err"
echo "exit=$? (expect 0)"
$PY - <<PYEOF
import json, glob
out = json.load(open("$EV/4-phase-dryrun.json"))
print("output.feature_id =", out.get("feature_id"), "| status =", out["status"])
vs = glob.glob("$LAB/.suiyin/phase-state/p0-1-dogfood-*.json")
print("versioned state keyed by feature:", [v.split('/')[-1] for v in vs])
import os
print("latest NOT written (dry_run 边界):", not os.path.exists("$LAB/.suiyin/phase-state/latest-p0-1-dogfood.json"))
PYEOF

echo; echo "=== [5] 真 git worktree 双段命名 ==="
$PY - <<PYEOF
from pathlib import Path
from suiyin_flow.c2_executor.worktree import ensure_worktree, remove_worktree
import subprocess
repo = Path("$LAB")
wt = ensure_worktree(repo, "p0-1-dogfood", "T-001B", "$BR")
print("worktree path:", wt.relative_to(repo))
b = subprocess.run(["git","-C",str(wt),"branch","--show-current"],capture_output=True,text=True).stdout.strip()
print("branch:", b)
assert str(wt.relative_to(repo)) == "worktrees/p0-1-dogfood/T-001B" and b == "task/p0-1-dogfood/T-001B"
remove_worktree(repo, "p0-1-dogfood", "T-001B", force=True)
subprocess.run(["git","-C",str(repo),"branch","-D","task/p0-1-dogfood/T-001B"],capture_output=True)
print("cleanup ok:", not wt.exists())
PYEOF

echo; echo "=== [6] 还原 v4lab 到实验基线 ==="
git -C "$LAB" reset -q --hard "$BASE_SHA"
rm -f "$LAB/p01-tasks.yaml" /tmp/p01-tasks-v010.yaml /tmp/p01-tasks-v020.yaml
rm -f "$LAB"/.suiyin/phase-state/p0-1-dogfood-*.json
git -C "$LAB" rev-parse HEAD
git -C "$LAB" status --short | head -5
