# 启动 BAT 入口修复设计

## 目标

让根目录的 `启动 AI Daily.bat` 能启动本地网页服务，并自动打开 `http://127.0.0.1:5000/`。

## 根因

脚本使用 `python -m ai_daily web`。`ai_daily` 是包而不是可直接运行的模块，因此 Python 在监听端口前就退出。

## 决策

仅把该命令改为 `python -m ai_daily.cli web`。`ai_daily.cli` 已定义 `main()` 和模块运行入口，且支持既有的 `web` 参数。

## 范围

- 修改：根目录 `启动 AI Daily.bat` 的一行启动命令。
- 该文件是本机忽略文件，不进入 Git；因此不新增无法在干净仓库中运行的文件内容测试。
- 验证：实际执行 BAT 后访问本地 5000 端口，确认网页返回 HTTP 200。

## 明确不改

- Windows 定时任务及其 `run_scheduled.bat`。
- DeepSeek、微信和 `.env` 配置。
- 网页功能、端口、样式和日报内容流程。
