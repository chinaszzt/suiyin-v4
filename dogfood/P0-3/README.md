# P0-3 mutation 探针 — 拍板验收 evidence (2026-08-12)

**gen4-plan §三 P0-3 验收判据：v4lab B 产物五处空心全部检出 —— ✅ 5/5 达成。**

- 场地: `~/suiyin-desk-v4lab` @ `v4lab/e4-cross`（8-08 002·T001 条件 B 产物 + desk E4 工具链 overlay）
- lane mongo: docker mongo:7 replSet @ **38027**（desk 守卫测试锁死此端口——8-08 E4 大量"无法判定"系 lane 起在 38124 的端口错配）
- catalog: [desk-mutants.yaml](desk-mutants.yaml)（[build_desk_catalog.py](build_desk_catalog.py) 生成，match 串逐条对 ref blob 断言存在）
- 命令: `suiyin-flow mutation run --catalog desk-mutants.yaml --repo-root ~/suiyin-desk-v4lab --ref v4lab/e4-cross --env MONGO_TEST_URI=mongodb://127.0.0.1:38027/?directConnection=true`

结果（[results/desk-probe-report.json](results/desk-probe-report.json)）：

| mutant | class | E4 blocker 对应 | outcome |
|---|---|---|---|
| M-bson-tag-rename | tag_rename | BSON 全字段护栏漏断（schemas_roundtrip_test） | **survived** |
| M-iface-method-rename | method_rename（extra_edits 双点） | TestContractShapes 不冻结方法集 | **survived** |
| M-audit-field-drop | assert_field_drop | 审计断言缺 before/after 字段（registry_test） | **survived** |
| M-taint-escape | taint_escape | 只追加扫描器条件重绑定清 taint | **survived** |
| M-scratch-shallow-copy | shallow_copy | ScratchState 浅拷贝可篡改 | **survived** |

`verdict=fail, baseline_ok=true, killed=0, survived=5`——未变异基线全套 `go test ./internal/topic/...` 真绿，五个 mutant 注入后**测试全部仍绿** = 空心铁证。机器零 token 复现 E4（gpt-5.6-sol high）人工审查的全部五条 quality blocker。

现场收尾: v4lab 保持实验基线 `6753721` 未动，throwaway 全清，lane 容器 `suiyin-testmongo-p03` 已停（保留复用）。
