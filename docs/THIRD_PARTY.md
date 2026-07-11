# 第三方代码说明

## Baoyu 发布器

- 来源：`JimLiu/baoyu-skills`
- 本地快照：Git 提交 `9cef0a9c644c5a2cee3364ad66e0c5cd69aa1693` 中纳入项目
- 位置：`app/vendor/baoyu-post-to-wechat/`
- 用途：通过 Bun 创建微信公众号草稿；项目不自行实现微信发布协议。

升级此目录后，必须运行：

```powershell
Push-Location app/vendor/baoyu-post-to-wechat
bun install --frozen-lockfile
bun test
Pop-Location
```

Python 侧还必须运行完整测试。发布器会清理临时 Markdown 文件，并复用日报已生成的封面。

## Baoyu Markdown 工具

- 来源：同一上游快照
- 位置：`app/vendor/baoyu-format-markdown/`
- 当前状态：保留为受控第三方资产；当前主流程不直接调用它。
