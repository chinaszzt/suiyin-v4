# `_test/` 测试目录

这个目录给 split-view PR preview 功能做测试用，不是项目业务内容。

- 不放进 mkdocs `nav`，所以站点 sidebar 看不到
- 但 mkdocs 默认仍渲染（URL 形如 `/_test/<name>/` 能访问）
- 业务专家正常浏览不会撞见

需要彻底清理时，开 cleanup PR 删整个 `docs/sdd/_test/` 即可。
