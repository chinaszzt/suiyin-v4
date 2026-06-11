# T-009 mini-dogfood results — C1 Planning Engine

## Scenario 1: r3 5-task 依赖链重生成 (modifies 声明版)
  ✓ exit 0 (got 0); stderr=
  ✓ 复现 r3 手写 3-phase 计划: [(1, ['T-001']), (2, ['T-002', 'T-003', 'T-004']), (3, ['T-005'])]
  ✓ phases_count == 3
  ✓ 无冲突拆分 (modifies 互不重叠)
  ✓ C7 重读写回文件 OK: 3 phases base=claude/login-core-r3

## Scenario 2: 幂等重跑 (AC-8)
  ✓ 重跑 exit 0
  ✓ byte-identical (幂等)
  ✓ marker 不叠加

## Scenario 3: 缺 modifies → context_seeds fallback 过度串行 (I3 FP)
  ✓ exit 0
  ✓ 中间三模块被串行化 → phases=5 > 3 (对比场景1的3): [(1, ['T-001']), (2, ['T-002']), (3, ['T-003']), (4, ['T-004']), (5, ['T-005'])]
  ✓ conflict_splits 记 context_seeds_overlap (fallback 触发)
  → 结论: 缺 modifies 时 C1 保守串行 (I3 FP, 安全但慢); 声明 modifies (场景1) 拿回并行。实证 Q1-3 动机。

## Scenario 4: --semantic-pass + 崩溃 claude → fallback (AC-11)
  ✓ 崩溃后静态结果仍落盘
  ✓ semantic_pass.completed == False
  ✓ fallback_reason 非空
  ✓ fallback 后仍是正确的 3-phase 静态计划

---
## Overall: ✓ ALL PASS