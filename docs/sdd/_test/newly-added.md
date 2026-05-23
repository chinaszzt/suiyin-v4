# 测试新增文件（newly-added）

> **[测试 marker — 本 PR 不合并]**
>
> 这是 split-view PR preview 在「新增文件」场景下的测试目标。
> main 上**不存在**本文件，PR 上**存在**。
>
> 验证点：
>
> 1. 业务专家直接访问 PR preview 上的 \`/_test/newly-added/\`，顶部应见 banner「🔄 本页是 PR 的改动文件 · ⇆ 并排对比 main」
> 2. 点「⇆ 并排对比 main」进 split view：
>    - 左侧 main 版应 **404**（main 上没有此页）
>    - 右侧 PR 版应正常渲染本文件
> 3. 这是新增文件的预期行为，不是 bug —— hook 未做 added / modified / removed 区分

## 内容样例

测试 markdown 渲染：

| 列 A | 列 B |
|---|---|
| 1 | a |
| 2 | b |

```js
// 测试 code block
console.log("hello from a brand new file");
```

> 引用块测试
