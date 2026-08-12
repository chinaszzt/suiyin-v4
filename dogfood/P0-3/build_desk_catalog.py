"""P0-3 拍板验收: 按 E4 五处空心复现手法构建 desk 五 mutant catalog.

每个 match 串先对 ref blob 断言出现次数, 失配即炸 (不产出坏 catalog)。
"""
import subprocess
import sys
from pathlib import Path

import yaml

LAB = Path.home() / "suiyin-desk-v4lab"
REF = "v4lab/e4-cross"
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("desk-mutants.yaml")


def blob(path: str) -> str:
    r = subprocess.run(
        ["git", "-C", str(LAB), "show", f"{REF}:{path}"],
        capture_output=True, text=True, encoding="utf-8", check=True,
    )
    return r.stdout


def assert_count(path: str, needle: str, want: int) -> None:
    got = blob(path).count(needle)
    assert got == want, f"{path}: expect {want}x, got {got}x for {needle[:60]!r}"


SCHEMA = "internal/store/schema.go"
DEPS = "internal/topic/deps.go"
REG = "internal/topic/registry.go"

# M1 tag_rename — OurMember.UpdatedAt bson tag 改坏 (E4 原样复现)
M1_MATCH = (
    "\tDisplayName string        `bson:\"display_name\"`\n"
    "\tEnabled     bool          `bson:\"enabled\"`\n"
    "\tUpdatedAt   time.Time     `bson:\"updated_at\"`"
)
M1_REPL = M1_MATCH.replace('`bson:"updated_at"`', '`bson:"our_member_updated_at_broken"`')
assert_count(SCHEMA, M1_MATCH, 1)

# M2 method_rename — 接口 + stub 同改 (双点, 保持编译)
M2_MATCH = "ScanForCard(ctx context.Context, cardID string) error"
M2_EXTRA_MATCH = "func (stubCrossGroup) ScanForCard(context.Context, string) error"
assert_count(DEPS, M2_MATCH, 1)
assert_count(DEPS, M2_EXTRA_MATCH, 1)

# M3 assert_field_drop — 审计 after.UpdatedAt 不再写入
M3_MATCH = (
    "after := store.OurMember{WxID: m.WxID, DisplayName: m.DisplayName, "
    "Enabled: m.Enabled, UpdatedAt: now}"
)
M3_REPL = (
    "after := store.OurMember{WxID: m.WxID, DisplayName: m.DisplayName, "
    "Enabled: m.Enabled}"
)
assert_count(REG, M3_MATCH, 1)

# M4 taint_escape — 条件重绑定清 taint 后写 config_ops (E4 snippet 原样)
M4_ANCHOR = "// 存在则置 enabled=false，与 config_ops 留痕同事务提交。同 op_id 重放同 UpsertMember。"
M4_SNIPPET = (
    "// sweepEscape 探针注入 (E4 taint 逃逸复现): 条件重绑定清掉受限句柄 taint。\n"
    "func (r *registry) sweepEscape(ctx context.Context, safe bool) error {\n"
    "\tc := r.st.ConfigOps()\n"
    "\tif safe {\n"
    "\t\tc = r.st.Cards()\n"
    "\t}\n"
    "\t_, err := c.UpdateOne(ctx, bson.M{\"probe\": true}, bson.M{\"$set\": bson.M{\"x\": 1}})\n"
    "\treturn err\n"
    "}\n\n"
)
assert_count(REG, M4_ANCHOR, 1)

# M5 shallow_copy — Cards() 连浅拷贝都不做, 直接共享底层数组
M5_MATCH = (
    "\tout := make([]store.TopicCard, len(s.cards))\n"
    "\tcopy(out, s.cards)\n"
    "\treturn out"
)
M5_REPL = "\treturn s.cards"
assert_count(DEPS, M5_MATCH, 1)

catalog = {
    "schema_version": "v0.1.0",
    "feature_id": "002-t001-replay",
    "default_test_cmd": "go test ./internal/topic/...",
    "mutants": [
        {
            "mutant_id": "M-bson-tag-rename",
            "mutant_class": "tag_rename",
            "target_file": SCHEMA,
            "match": M1_MATCH,
            "replacement": M1_REPL,
            "description": "E4 空心 1: OurMember.UpdatedAt 落库 tag 改坏, TestTopicSchemas 全字段护栏漏断 → 仍绿",
        },
        {
            "mutant_id": "M-iface-method-rename",
            "mutant_class": "method_rename",
            "target_file": DEPS,
            "match": M2_MATCH,
            "replacement": M2_MATCH.replace("ScanForCard(", "ScanForCardRenamed("),
            "extra_edits": [{
                "target_file": DEPS,
                "match": M2_EXTRA_MATCH,
                "replacement": M2_EXTRA_MATCH.replace("ScanForCard(", "ScanForCardRenamed("),
            }],
            "description": "E4 空心 2: CrossGroup.ScanForCard 接口+stub 同改名, TestContractShapes 不冻结方法集 → 仍绿",
        },
        {
            "mutant_id": "M-audit-field-drop",
            "mutant_class": "assert_field_drop",
            "target_file": REG,
            "match": M3_MATCH,
            "replacement": M3_REPL,
            "description": "E4 空心 3: 审计 after.UpdatedAt 缺失, assertConfigOpFull 不读该字段 → 仍绿",
        },
        {
            "mutant_id": "M-taint-escape",
            "mutant_class": "taint_escape",
            "target_file": REG,
            "match": M4_ANCHOR,
            "replacement": M4_SNIPPET + M4_ANCHOR,
            "description": "E4 空心 4: 条件重绑定清 taint 后 UpdateOne config_ops, TestAppendOnlyCollections 扫描器漏检 → 仍绿",
        },
        {
            "mutant_id": "M-scratch-shallow-copy",
            "mutant_class": "shallow_copy",
            "target_file": DEPS,
            "match": M5_MATCH,
            "replacement": M5_REPL,
            "description": "E4 空心 5: ScratchState.Cards() 退化为直接共享底层数组, 无对抗测试 → 仍绿",
        },
    ],
}

OUT.write_text(yaml.safe_dump(catalog, allow_unicode=True, sort_keys=False), encoding="utf-8")
print(f"catalog OK → {OUT} (5 mutants, all match-verified against {REF})")
