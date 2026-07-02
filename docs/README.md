# AI Daily — 微信公众号每日 AI 资讯发布工具

每天自动抓取 AI 资讯，改写后发布到微信公众号（草稿箱）。

## 它能做什么

- 每天 10:00 自动抓取国内外 AI 新闻
- 用 LLM 改写内容，生成符合公众号风格的文章
- 自动生成头图（900×500 报纸风格）
- 发布到微信公众号的草稿箱，你登录公众号手动群发即可
- 10:05 弹出通知，告诉你发布结果

## 你需要准备什么

### 1. 一个微信公众号
- 个人或机构号都可以
- 在公众号后台 → 设置与开发 → 基本配置 → 获取 AppID 和 AppSecret
- 把服务器 IP 添加到 IP 白名单（本机是 113.244.65.188，换了网络要重新加）

### 2. 一个 LLM API 密钥
用来改写文章，支持的格式与 OpenAI API 兼容，比如：
- DeepSeek / 月之暗面 / 阿里通义千问 等

### 3. 安装 Python
项目需要 Python 3.11+，添加环境变量。
安装后打开命令提示符，测试：
```bash
python --version
```
能正常显示版本号就可以。

### 4. 安装依赖
在项目根目录运行：
```bash
pip install -r requirements.txt
```

## 快速开始

### 1. 配置

在项目根目录新建 `.env` 文件（不是 .env.txt），填写：

```ini
LLM_API_KEY=sk-你的密钥
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
WECHAT_APP_ID=wx你的AppID
WECHAT_APP_SECRET=你的AppSecret
```

### 2. 启动 Web 界面

双击 `run.bat` 或命令行运行：
```bash
python app/main.py
```

浏览器打开 http://127.0.0.1:5000
- 定时设置：设定每天几点发布（默认 10:00）
- 手动测试：点「拉取并预览」查看当天文章，点「发布」手动发到公众号
- 配置管理：API 密钥、公众号参数

### 3. 开启自动发布

在 Web 界面点「部署定时任务」，自动创建两个 Windows 任务：
- **AI Daily Publisher**（每天 10:00）
- **AI Daily Publisher - Check**（每天 10:05，弹窗通知结果）

也可以在命令行手动部署：
```bash
python app/scheduler.py
```

## 每天发生了什么

| 时间 | 动作 |
|------|------|
| 10:00 | 抓取当天 AI 资讯 → LLM 改写 → 生成封面图 → 发布到公众号草稿箱 |
| 10:05 | 弹窗告诉你发布成功还是失败 |

如果电脑在休眠，任务会自动唤醒电脑执行。
如果没插电源，任务也会正常执行（默认不会）。

## 目录结构

```
app/              # 主程序
  main.py           # Web 界面 (Flask)
  pipeline.py       # 发布流程编排
  scraper.py        # 抓取 AI 资讯
  rewriter.py       # LLM 改写内容
  formatter.py      # 格式化公众号文章
  cover_generator.py # 生成封面图
  publisher.py      # 发布到微信
  scheduler.py      # Windows 定时任务管理
  check_daily.py    # 10:05 结果检查
  env.py            # 环境变量读取
docs/             # 文档
design/           # 设计参考
```

## 参数说明（在 Web 界面修改）

| 参数 | 说明 | 默认值 |
|------|------|--------|
| 定时时间 | 每天自动发布的时间 | 10:00 |
| 封面标题 | 封面图上的大标题 | 今日AI日报 |
| 封面署名 | 封面图上的小字 | AI Daily |
| 署名链接 | 点击署名跳转的链接 | (空) |
| 署名二维码 | 署名旁边的二维码图片 URL | (空) |

## 常见问题

**发布成功但公众号草稿箱里看不到？**
检查 IP 白名单：公众号后台 → 设置 → 基本配置 → IP 白名单，把运行本工具的服务器 IP 加进去。

**定时任务没有运行？**
Windows 可能因电源设置跳过了任务。在 Web 界面重新「部署定时任务」会自动修正电源设置。

**文章内容不全？**
检查 LLM API 密钥余额是否充足。改写需要较大上下文，如果模型不支持长输出可能需要调整 `max_tokens`。
