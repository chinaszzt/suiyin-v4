# Lane Isolation — Component Spec

> gen4-plan M3 清单件 5。desk 实证：并行 session 仅做 Mongo 端口隔离仍会**构建互踩团灭**
> （CPU 争抢 + tmp/DB 共享污染）。lane = 一个并行执行槽的完整资源包：
> **port（DB 端口）/ db_suffix（库名后缀）/ tmp_dir（独占临时目录）**，外加一个全局
> **构建 semaphore**（有限并发的重型构建/测试槽）。

## 0. Type

- [x] 自建组件 (imperative logic)

**实现栈**: Python 3.11+。CLI `suiyin-flow lane {acquire,release,status}` + `lane slot run`。

## 1. Purpose

给 C2/C7/mutation 等并行调用方一个**确定性、崩溃可回收**的资源分配器：
- 同 repo 下 N 个并行 session 各拿互不重叠的 port/db/tmp（lane 租约）
- 重型命令（构建/全量测试）过全局 semaphore，最多 K 个并发（防 CPU 互踩）

## 2. 状态与布局（全部在 `<repo_root>/.suiyin/lanes/`，运行时工件不入库）

```
.suiyin/lanes/
  config.yml            # 可选; 无则用默认 (见 §3)
  leases/lane-<N>/      # 目录存在 = 租约持有 (mkdir 原子性, 全平台)
    lease.json          # {pid, hostname, acquired_at, purpose}
  slots/slot-<N>/       # 构建 semaphore 槽位, 同 mkdir 协议
    holder.json         # {pid, hostname, acquired_at, cmd}
  tmp/lane-<N>/         # lane 独占 tmp; 在租约目录外 (release 的 rmdir 不能连带删它),
                        # acquire 时清空后交付 (I4)
```

**并发协议（不依赖 flock——Windows 无 flock）**：获取 = `mkdir`（原子，成功即持有）；
释放 = 删目录。**stale 回收**：lease/holder 的 pid 在本机已死（psutil.pid_exists，
hostname 匹配本机时才判）或 acquired_at 超过 `stale_after_seconds` → 回收（先删 json 再删目录，
删失败视为他人已回收，重试下一槽）。

## 3. 配置（config.yml，全有默认值）

```yaml
schema_version: v0.1.0
max_lanes: 4                # lane-0..lane-3
port_base: 38100            # lane-N 的 port = port_base + N (desk lane mongo 38027 是特例
                            #   由调用方显式指定, 不走分配器——守卫测试硬钉端口的场景本就不该并行)
db_suffix_template: "lane{n}"   # 库名后缀; 调用方拼 <base_db>_<suffix>
max_build_slots: 2          # 构建 semaphore 并发上限
stale_after_seconds: 7200   # 兜底回收 (kill -9 残留)
```

## 4. Public API

### 4.1 Python

```python
from suiyin_flow.lane import acquire_lane, release_lane, build_slot

lease = acquire_lane(repo_root, purpose="mutation:AC-3")   # → LaneLease
# lease.lane_id / lease.port / lease.db_suffix / lease.tmp_dir (已建好且为空)
release_lane(repo_root, lease.lane_id)

with build_slot(repo_root, cmd="go build ./..."):          # 阻塞等槽, timeout 可配
    subprocess.run(...)
```

### 4.2 CLI

```
suiyin-flow lane acquire --repo-root <p> [--purpose <s>]   # stdout 一行 JSON: LaneLease
suiyin-flow lane release --repo-root <p> --lane-id <n>
suiyin-flow lane status  --repo-root <p>                   # 各 lane/slot 持有情况 JSON
suiyin-flow lane slot run --repo-root <p> [--timeout <s>] -- <cmd...>   # 拿槽→shell 跑 cmd→放槽
```

## 5. Invariants

- **I1 原子性**：获取/释放全走 mkdir/rmdir 原子原语；无 TOCTOU 窗口内的双持有
- **I2 崩溃可回收**：kill -9 后残留租约可被下一个调用方按 §2 协议回收；回收判定
  只对同 hostname 的死 pid 或超时租约，**不误杀活租约**
- **I3 无可用 lane/slot**：acquire 默认阻塞轮询（间隔 1s）至 `--timeout`（默认 lane 60s /
  slot 1800s），超时 → 明确错误 `LANE_EXHAUSTED` / `SLOT_TIMEOUT`（exit 2），不静默降级共享
- **I4 tmp_dir 交付即空**：acquire 时若 lane tmp 有残留（上任崩溃）→ 清空后交付
- **I5 释放幂等**：release 不存在的租约 = no-op 成功
- **I6 lane slot run 透传**：子命令 exit code 原样透传；拿槽失败 exit 2
- **I7 全部状态可见**：status 输出含 stale 判定结果（谁持有/是否已死）

## 6. Acceptance Criteria

- **AC-1**: 顺序 acquire ×2 → lane-0/lane-1，port/db_suffix/tmp 互不重叠；release 后可复得
- **AC-2**: 并发 acquire（多进程/多线程 ×8, max_lanes=4）→ 恰好 4 成功且无重复 lane_id，其余阻塞至超时 `LANE_EXHAUSTED`
- **AC-3**: 伪造死 pid 租约（写入不存在的 pid）→ 下一个 acquire 回收并复用该 lane
- **AC-4**: 活租约（当前进程 pid）不被回收
- **AC-5**: tmp_dir 有残留文件时 acquire → 交付时已清空
- **AC-6**: build_slot 并发 ×4（max_build_slots=2）→ 同时持有 ≤2（用文件计数器探针验证）
- **AC-7**: `lane slot run -- <cmd>` 透传 exit code；cmd 失败槽位仍被释放
- **AC-8**: release 幂等（重复 release 不报错）
- **AC-9**: config.yml 缺失 → 默认值生效；schema_version 未知 → 明确报错
- **AC-10**: status 列出持有者 pid/alive 状态

## 7. Implementation Notes

- 模块 `src/suiyin_flow/lane/{__init__,schema,allocator,semaphore,cli}.py`
- psutil 已是依赖（C2 用）；hostname 用 `socket.gethostname()`
- 跨平台：mkdir/rmdir 原子性三平台成立；路径 pathlib；json/yaml `encoding="utf-8"`
- 调用方接线（C2/C7/mutation 把 `--env` 注入换成 lane 分配）**不在本件**——M4 回放前按需接，
  分配器先独立成立（mutation 现有 `--env` 注入通道即消费点）

---

**Version**: v0.1.0-draft
**Last Updated**: 2026-08-13
**Status**: draft — M3 件 5；分配器 + semaphore 待实现（codex 外包）

**Changelog**:
- v0.1.0 (2026-08-13): 初稿。mkdir 原子租约（无 flock，Windows 兼容）+ psutil 死进程回收 + 构建 semaphore；desk"仅 mongo 隔离仍互踩"实证驱动。
