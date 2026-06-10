# T-008 mini-dogfood results

## Scenario 1: R2 chain (block → feedback retry)
  ✓ round-1 success
  ✓ round-1 applied=false
  ✓ round-1 prompt 无 feedback 节
  ✓ round-2 success
  ✓ round-2 applied=true
  ✓ worktree 复用 (I1, 不从头重写)
  ✓ round-2 prompt 含 feedback 节
  ✓ round-2 prompt 含全部 findings location
  ✓ findings severity 降序 (high 在 low 前)
  ✓ CLI --review-feedback flag 接线

## Scenario 2: live lock rejects run (finding #8)
  ✓ code == WORKTREE_LOCKED
  ✓ details.holder_pid == 持有者 pid
  ✓ 未启动 session (无 attempt log)
  ✓ 锁未被动 (仍属持有者)

## Scenario 3: stale lock takeover + release on terminal state
  ✓ stale 接管后正常 success
  ✓ 终态锁释放 (AC-14)

---
## Overall: ✓ ALL PASS