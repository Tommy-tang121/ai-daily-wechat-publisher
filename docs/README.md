# AI Daily

本地运行的 AI 日报编辑与微信公众号草稿工具。它抓取当天全部可用资讯，按批改写，生成封面；只有收到微信草稿回执后，才会标为已发布。

## 日常使用

1. 双击 `app/scripts/run_preview.bat` 做生成、预览和封面测试。预览模式禁止创建微信草稿。
2. 双击 `app/scripts/run_web.bat` 打开正式 Web 页面。
3. 在页面选择日期，点击“抓取”。页面会显示本次运行进度；处理中的运行、已生成未发布的文章和创建草稿失败后的待重试内容会临时保留，刷新或重新打开后可继续查看。
4. 文章状态显示“已生成，尚未发布”时，可预览、复制或查看封面；确认后再点击“发布”。
5. 设置每日时间并点击“保存”，会更新唯一的 Windows 任务 `AI Daily Publisher`。任务失败后每 15 分钟重试，最多 3 次。

## 首次安装

在项目根目录运行：

```powershell
py -m pip install --user uv
Copy-Item app/.env.example app/.env
py -m uv sync --project app --locked
```

编辑 `app/.env`，填写 `LLM_API_KEY`、`LLM_BASE_URL` 和 `LLM_MODEL`。密钥不进入 Git。

还需要安装 Bun，供已复用的微信草稿发布器运行。

## 运行边界

- 不需要服务器；Windows 电脑必须开机且当前用户保持登录，计划任务才能执行。
- 微信 IP 白名单仍需每天由你手动更新；这是当前明确保留的人工步骤。
- 本地只暂存处理中的运行、`ready` 文章和尚未调用微信草稿接口前失败的可重试内容。微信草稿创建成功后，会立即清除本地文章、事件、封面和运行记录；不保留已发布历史或草稿回执。
- 手动选择任意日期点击“抓取”会开始一次新的生成；同一天已完成或失败的旧内容不会被复用。
- 抓取和改写每次上报有效进度都会刷新运行心跳；只有连续超过 30 分钟没有进度的排队、抓取、改写或发布任务，才允许定时重试接管。清理开始后，旧线程再上报进度会被忽略，页面也不会显示旧事件。
- 定时任务按运行日期生成标题。调用微信草稿发布器前的生成失败可以重试；一旦开始调用发布器，任何异常都视为远端结果未知，必须先在微信草稿箱核对并由你确认，系统绝不自动再次发布。
- 本地设置和保存的计划时间会继续保留；草稿成功后的运行清理不会改动它们。

## 开发验证

```powershell
py -m uv run --project app python -m unittest discover -s app/tests -v
Push-Location app/vendor/baoyu-post-to-wechat; bun test; Pop-Location
py -m uv pip check
git diff --check
```

## 目录

```text
app/     运行代码、依赖、脚本、测试、第三方发布器
design/  当前页面的视觉和交互参考
docs/    产品说明、技术规格、实施记录和第三方说明
```

回退到重构前版本可使用 Git 标签 `checkpoint-20260710-before-stability-refactor`。
