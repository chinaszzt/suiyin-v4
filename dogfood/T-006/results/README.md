# T-006 mini-dogfood results

Worktree: `/Users/zhangtuo/Documents/suiyin-v4/.claude/worktrees/determined-knuth-39baaf`
suiyin-flow cmd: `/Users/zhangtuo/Documents/suiyin-v4/.claude/worktrees/determined-knuth-39baaf/.venv/bin/python -m suiyin_flow.cli`

## Scenario 1-happy-dry-run
- exit_code: `0` (expected 0)
  ✓ exit code = 0
  ✓ status == "dry_run"
  ✓ task order = T-201, T-202, T-203
  ✓ all tasks status = dry_run
  ✓ stopped_at_task_id == null
  ✓ feature_name passed through

## Scenario 2-missing-verify-cmd
- exit_code: `2` (expected 2)
  ✓ exit code = 2
  ✓ stderr.code == "INVALID_MANIFEST"
  ✓ message mentions verify_cmd

## Scenario 3-order-violation
- exit_code: `2` (expected 2)
  ✓ exit code = 2
  ✓ stderr.code == "INVALID_MANIFEST"
  ✓ message mentions BATCH_ORDER_VIOLATION
  ✓ message names offending dep (T-402)

---
## Overall: ✓ ALL PASS