# T-009 mini-dogfood — C1 Planning Engine

> 对应 c1-planning-engine.md v0.1.0。天然验收件 = r3 那份 5-task login-core 依赖链
> （todo.md「第三轮真闭环」），去掉手写 execution_plan 让 C1 重生成对比。

## 场景

| # | 场景 | 验什么 | 期望 |
|---|---|---|---|
| 1 | r3 依赖链重生成（AC-1 真实版） | `login-core-r3.yaml`（modifies 声明、无 execution_plan）跑 `suiyin-flow plan run` | 生成 3 phases `[[T-001],[T-002,3,4],[T-005]]`，**复现 r3 手写计划**；C7 `load_manifest_and_plan` 重读不抛（AC-5/6） |
| 2 | 幂等（AC-8） | 对已含 C1 marker 的文件重跑 | byte-identical，marker 不叠加 |
| 3 | **I3 FP 实证 / Q1-3 动机** | `login-core-no-modifies.yaml`（去 modifies、中间三模块共享 `src/types.ts`） | C1 把中间三个串行化 → phases > 3。证明：缺 modifies → context_seeds fallback 过度串行（安全但慢）；声明 modifies 才拿回并行 |
| 4 | 语义 pass fallback（AC-11） | `--semantic-pass` + 崩溃的 fake claude | 静态结果照常落盘 + `fallback_reason` 非空，exit 0 |

## r3 手写计划（场景 1 的对比基准）

r3 在 v5 手写的 `execution_plan`（scope note 钉死「每文件恰好一个 task 拥有 / barrel 归 T-005」）：

```yaml
execution_plan:
  - {phase: 1, parallel: [T-001]}        # 骨架
  - {phase: 2, parallel: [T-002, T-003, T-004]}  # 三模块并行
  - {phase: 3, parallel: [T-005]}        # 聚合
```

C1 应在仅给 `depends_on` + `modifies` 的情况下**确定性地重算出同一计划**。

## Evidence

`dogfood/T-009/results/README.md` + 各场景生成的 plan JSON / 写回 yaml 片段。
