# 测试占位文件（will-be-deleted）

> 这是 split-view PR preview 功能的测试目标文件。**不要手动改它**。
>
> 它的存在是为了让"删除文件"场景的测试 PR 有靶子可以删。
> 后续的 PR-delete 测试会删除本文件，但**不会 merge**，所以 main 上本文件长期保留。
> 等不需要测试时，开 cleanup PR 一并删除 `docs/sdd/_test/`。

## 内容

测试用占位 markdown，无实际意义。

- 列表项 1
- 列表项 2
- 列表项 3

```python
# 测试 code block 渲染
def hello():
    return "world"
```
