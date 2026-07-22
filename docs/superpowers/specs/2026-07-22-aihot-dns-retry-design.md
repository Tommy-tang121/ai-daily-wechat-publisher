# AIHot 短时 DNS 故障重试设计

**日期：** 2026-07-22
**状态：** 已实施并通过真实定时任务验证

## 要解决的问题

当天 10:00 的正式任务连续两次停在 `scraping`。数据库保存的根因是 `NameResolutionError`：Windows 当时无法解析 `aihot.virxact.com`。旧逻辑在第一次失败后立即使用第二次机会，两次尝试只相隔约 12 秒，因此无法抵抗短时 DNS 或网络波动。

## 设计决策

1. 正式任务仍然只有首次和重试一次，总次数不变。
2. 第一次从 AIHot 抓取阶段抛出 `requests.ConnectionError` 时等待 60 秒，再执行第二次完整流程。
3. 其他允许重试的发布前异常保持原有节奏，不统一增加等待。
4. 第二次仍失败才进入既有 Windows 失败弹窗。
5. 若错误包含 AIHot 域名及 `NameResolutionError`、`Failed to resolve` 或 `getaddrinfo failed`，用户提示统一为“资讯源域名解析失败，请检查网络、VPN 或 DNS”。
6. 一旦进入微信 `publishing`，任何结果未知仍按 `publication_uncertain` 处理，绝不因为本设计重新调用微信发布接口。

## 非目标

- 不增加第三次尝试或任务计划程序级重启。
- 不增加新的资讯源、服务器或持久缓存。
- 不改变 AI 改写、文章排版、封面、Web 页面和微信发布器。
- 不把正文、密钥、token 或完整异常堆栈写入弹窗。

## 验收证据

- 新增测试先证明旧逻辑没有等待，再验证执行顺序为“第一次 → 等待 60 秒 → 第二次”。
- 新增测试验证 DNS 技术异常会转换为中文安全提示。
- 项目全量 148 项 Python 测试通过，`git diff --check` 通过。
- 2026-07-22 真实 Windows 定时任务从 `scraping` 进入 `ready`、`publishing`、`published`；微信官方草稿接口确认当天草稿为 1 篇。
