# AI 日报公众号发布助手 · 产品设计文档 v1.0

> 任何人参照本文档，可完整复刻一套功能、UI、交互、数据结构完全一致的 AI 日报发布工具。
> 最后更新：2026-06-28 | 版本：v1.0（稳定运行中）

---

## 1. 产品概述

### 1.1 一句话描述

一个本地运行的 Web 工具：每天自动抓取 AI 行业热点新闻 → AI 改写避侵权 → 自动排版 → 生成报刊风封面 → 一键发布到微信公众号草稿箱。Windows 计划任务 + 弹窗通知闭环每日流程。

### 1.2 目标用户

- 运营 AI / 科技类微信公众号的个人或小团队
- 每天需要产出行业资讯，没有精力手动搜集、编写、排版、做封面
- 非程序员，需要纯界面操作

### 1.3 核心价值

| 痛点 | 方案 |
|------|------|
| 每天翻十几个网站找 AI 新闻 | 从 aihot 聚合 API 自动抓取当日热门 AI 资讯（~10 条/天） |
| 直接复制粘贴有版权风险 | Agnes AI 用自己的话重写，保留事实换表述 |
| 公众号排版费时 | 管线自动处理中文标点 + 空行规范 |
| 封面图设计耗时 | Pillow + 本地 Google Fonts 自动生成报刊风封面（900×500） |
| 手动登录后台发布 | 一键创建微信草稿 |
| 忘了跑 / 跑了不知道结果 | 10:05 独立检查任务弹窗通知（✅/❌/⚠️） |

---

## 2. 技术栈

### 2.1 总览

| 层 | 选型 | 版本 | 理由 |
|---|------|------|------|
| 后端框架 | Flask | 3.x | 轻量，零配置，Python 原生 |
| 模板引擎 | Jinja2 | Flask 内置 | Flask 标配 |
| 前端 | Vanilla JS (ES6) | — | 零构建工具，直接嵌入 HTML |
| 样式 | 纯 CSS（自定义涂鸦主题） | — | 完整 CSS 变量体系，无任何框架依赖 |
| 封面生成 | Pillow | 12.2.0 | 支持变体字体 (`set_variation_by_name`) |
| AI 改写 | Agnes API (OpenAI 兼容) | agnes-2.0-flash | 速度快，中文质量好 |
| 微信发布 | TypeScript (bun) | 1.3.14 | 已有的 wechat-api.ts 封装 |
| 数据持久化 | JSON 文件 | — | 零运维，单文件读写 |
| 计划任务 | Windows schtasks × 2 | — | 主任务 + 检查任务独立触发 |
| 通知 | ctypes MessageBoxW | — | Python 内置，零依赖 |
| 开发语言 | Python | 3.13+ | — |

### 2.2 Python 运行时依赖

依赖仅 4 个包，写在 `requirements.txt`：

```
flask              # Web 框架
requests           # HTTP 客户端（抓取 + LLM API）
beautifulsoup4     # HTML 解析（备用，scraper 当前仅解析 JSON，无需 BS4）
Pillow             # 封面图像生成
```

### 2.3 外部服务

| 服务 | 用途 | 接口 | 认证方式 | 超时 |
|------|------|------|---------|------|
| aihot.virxact.com | AI 新闻聚合源 | `GET /api/public/daily/{date}` | User-Agent header | 15s |
| apihub.agnes-ai.com | 文本改写 (LLM) | `POST /v1/chat/completions` | Bearer token (`LLM_API_KEY`) | (10, 60)s + 3次重试(指数退避) |
| api.weixin.qq.com | 公众号草稿箱管理 | `cgi-bin/token` / `cgi-bin/draft/add` | appid + secret | 120s (bun) |

### 2.4 系统前置条件

- Windows 10/11（因依赖 schtasks + ctypes MessageBoxW）
- Python 3.13+
- bun 1.x（用于发布 skill）：`powershell -c "irm bun.sh/install.ps1 | iex"`
- 微信公众号（服务号或订阅号），已获取 App ID 和 App Secret
- 微信 IP 白名单：将本机公网 IP 添加到 mp.weixin.qq.com → 开发 → 基本配置

---

## 3. 目录结构与文件规格

### 3.1 完整目录树

```
E:\App Development\AI Daily\
├── .env                              # 密钥（gitignored），约 5 行
├── .gitignore
├── AGENTS.md                         # 使用说明（面向 AI 助手）
├── requirements.txt                  # Python 依赖（4 行）
├── run.bat                           # 手动启动 Web UI
├── run_scheduled.bat                 # 计划任务启动入口
│
├── app/
│   ├── __init__.py                   # 空文件，使 app 为 Python 包（0 行）
│   ├── env.py                        # .env 文件加载（20 行）
│   ├── config.py                     # config.json 读写（38 行）
│   ├── main.py                       # Flask 路由 + SSE 编排（135 行）
│   ├── pipeline.py                   # 流水线编排（46 行）
│   ├── scraper.py                    # 抓取 + 解析 aihot API（74 行）
│   ├── rewriter.py                   # Agnes AI 改写（111 行）
│   ├── markdown.py                   # 文章构建 + CJK 格式化（67 行）
│   ├── cover_generator.py            # Pillow 封面生成（148 行）
│   ├── publisher.py                  # 发布到公众号（91 行）
│   ├── scheduler.py                  # Windows 计划任务管理（71 行）
│   ├── run_daily.py                  # 定时任务运行入口（32 行）
│   ├── check_daily.py                # 定时任务状态检查 + 弹窗（38 行）
│   │
│   ├── prompts/
│   │   └── rewrite.md                # AI 改写 system prompt（68 行）
│   ├── fonts/
│   │   ├── Caveat[wght].ttf          # Google Fonts 英文手写体（变体字体）
│   │   ├── ZCOOLKuaiLe-Regular.ttf   # 中文手写体
│   │   └── Lora[wght].ttf            # 衬线字体（变体字体）
│   ├── data/
│   │   └── config.json               # 用户配置持久化
│   ├── logs/
│   │   ├── scheduled.log             # 定时任务运行日志
│   │   └── server.log                # 服务日志（预留）
│   ├── templates/
│   │   └── index.html                # Jinja2 主模板（170 行）
│   └── static/
│       ├── style.css                 # 涂鸦主题样式（1375 行）
│       ├── app.js                    # 前端交互（296 行）
│       └── covers/                   # 封面图片输出目录
│
├── design/
│   └── ui-components.html            # UI 组件完整参考（自包含 HTML，浏览器打开即可查阅全部组件/状态/动画/SSE/事件）
│
├── docs/
│   ├── AI日报公众号发布助手-产品设计文档.md  # 本文档
│   └── plans/
│       └── 2026-06-26-ai-daily-wechat-publisher.md  # 实施计划
│
└── skills/
    └── baoyu-post-to-wechat/         # 微信公众号发布 skill
        └── scripts/
            ├── wechat-api.ts         # 微信 API 发布入口
            ├── wechat-http.ts        # HTTP 请求封装
            └── ...
```

### 3.2 文件规格摘要

| 文件 | 行数 | 模块类型 | 接口数量 |
|------|------|---------|---------|
| `app/__init__.py` | 0 | 包标记 | 0 |
| `app/env.py` | 20 | 浅模块 | 1 (`load_env()`) |
| `app/config.py` | 38 | 浅模块 | 3 (`get_config`, `set_config`, `reset_config`) |
| `app/main.py` | 135 | 路由层 | 8 Flask 路由 |
| `app/pipeline.py` | 46 | **深模块** | 1 (`run_pipeline`) |
| `app/scraper.py` | 74 | 适中 | 3 (`fetch_and_parse`, `fetch_news`, `parse_news`) |
| `app/rewriter.py` | 134 | 适中 | 1 (`rewrite_news`) |
| `app/markdown.py` | 67 | **深模块** | 2 (`build_markdown`, `format_article`) |
| `app/cover_generator.py` | 148 | 适中 | 1 (`generate_cover`) |
| `app/publisher.py` | 91 | 适中 | 2 (`publish_article`, `publish_to_wechat`) |
| `app/scheduler.py` | 102 | **深模块** | 3 (`create_or_update_tasks`, `get_trigger_time`, `get_task_info`) |
| `app/run_daily.py` | 36 | 入口 | 1 (`run()`) |
| `app/check_daily.py` | 38 | 入口 | 1 (`main()`) |
| `app/templates/index.html` | 170 | 模板 | — |
| `app/static/style.css` | 1375 | 样式 | — |
| `app/static/app.js` | 296 | 前端交互 | — |
| `app/prompts/rewrite.md` | 68 | AI prompt | — |

---

## 4. 模块详解

### 4.1 `app/env.py` — 环境变量加载（20 行）

```python
# 接口
load_env()  # 加载 .env → os.environ，仅执行一次（_ENV_LOADED 守卫）
```

**行为**：
- 读取项目根目录的 `.env` 文件
- 逐行解析 `KEY=VALUE` 格式，跳过 `#` 注释和空行
- `_ENV_LOADED` 全局守卫防止重复加载
- 不抛出异常（文件不存在时静默跳过）
- 被 `main.py` 和 `run_daily.py` 在模块顶部显式调用

**加载变量**：
```
LLM_BASE_URL=https://apihub.agnes-ai.com/v1
LLM_API_KEY=sk-xxxx
LLM_MODEL=agnes-2.0-flash
WECHAT_APP_ID=wx0000000000000000
WECHAT_APP_SECRET=xxxx
```

### 4.2 `app/config.py` — JSON 配置管理（38 行）

```python
# 接口
get_config(key=None) -> dict|Any    # 读全部或单字段
set_config(key, value) -> None      # 写单字段
reset_config() -> None              # 恢复默认
```

**默认配置**：
```python
DEFAULT_CONFIG = {
    "title": "AI 行业热点新闻",
    "author": "Tommy",
    "max_words": 150,
    "schedule_time": "10:00",
    "data_source": "https://aihot.virxact.com/"
}
```

**存储路径**：`app/data/config.json`（首次读取时自动创建）

### 4.3 `app/scraper.py` — 抓取 + 解析（74 行）

```python
# 主要接口
fetch_and_parse(date_str: str) -> List[dict]
    # 返回值: [{"title", "content", "source", "category"}, ...]
    # 异常: RuntimeError("请求超时: {url}") 或 RuntimeError("请求失败: {str(e)}")

# 兼容接口（旧版，保留但 pipeline 不使用）
fetch_news(date_str) -> dict     # 返回原始 JSON 或 {"error": ...}
parse_news(raw_data) -> List     # 从原始 JSON 解析
```

**API 地址**：`GET https://aihot.virxact.com/api/public/daily/{date_str}`
**请求头**：
```python
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ...",
    "Accept": "application/json, text/plain, */*",
}
```
**超时**：15s

**分类映射**（`:SECTION_LABEL_MAP`）：

| API 返回的 section label | 映射后的中文分类 |
|------------------------|----------------|
| 包含"模型" | 模型相关 |
| 包含"产品" | 产品相关 |
| 包含"行业" | 行业动态 |
| 包含"论文" | 论文研究 |
| 包含"观点" 或 "Agent" | Agent技巧 |
| 无匹配 | 行业动态（默认 fallback） |

**JSON 结构解析**：
```python
raw["sections"][i]["label"]       # section 标签 → 映射为 category
raw["sections"][i]["items"][j]    # 单条新闻
  item["title"]                   # 标题
  item["summary"]                 # 摘要（优先）
  item["content"]                 # 内容（fallback）
  item["sourceName"]              # 来源名称（优先）
  item["source"]                  # 来源（fallback）
```

### 4.4 `app/rewriter.py` — AI 改写（134 行）

```python
# 接口
rewrite_news(items: List[dict], max_words=150, progress_callback=None) -> dict
    # 返回值: {"items": [{title, body, link, source, category}], "opening": str, "closing": str}
    # 异常: RuntimeError("API 调用失败: {err}")
```

**流程**：
1. 将 items 拼装为每日摘要文本（`### 条目 N` 格式）
2. 读取 `app/prompts/rewrite.md` 作为 system prompt
3. 替换 prompt 中的 `{{MAX_CHARS}}` 和 `{{DAILY_DATA}}` 占位符
4. 单次调用 Agnes API（OpenAI 兼容格式）
5. 解析返回的 JSON，fallback 处理

**API 调用参数**：
```python
POST {LLM_BASE_URL}/chat/completions
Authorization: Bearer {LLM_API_KEY}
Content-Type: application/json
Body: {
  "model": "agnes-2.0-flash",      # 从 LLM_MODEL 环境变量读取
  "messages": [
    {"role": "system", "content": prompt},
    {"role": "user", "content": "请根据以上要求处理今日的 N 条 AI 新闻。"}
  ],
  "max_tokens": 8000               # 此前 3000 不够 22 条 × 150 字，已修复为 8000
}
timeout: (10, 60)  # 10s 连接 + 60s 读取（此前 180s 太长，改为 60s + 3 次重试兜底）
```

**重试机制**（`_call_agnes`）：
- 最多 3 次尝试
- 指数退避间隔：2s、4s（`time.sleep((2 ** attempt) * 2)`）
- 3 次全部失败才抛出 `RuntimeError("API 调用失败: {err}")`
- 覆盖场景：TCP RST、DNS 抖动、临时限流

**截断修复**（`_try_repair_json`）：
- API 输出可能因 `max_tokens` 不足被截断，JSON 尾部残缺
- `_try_repair_json()` 从右向左逐层剥离尾部 `}`，尝试最多 3 次修复
- 全部失败则 `_fallback()` 回到原始内容（opening/closing 为空）

**响应解析**（`_parse_response`）：
1. 去除 ```json ``` 代码块标记
2. `json.loads()` 解析
3. 按 index 匹配改写后的 items 和原始 items
4. 提取 `todayObservation` → `opening`，`editorComment` → `closing`
5. JSON 解析失败时调用 `_fallback()`：截取原始内容到 max_words 字，opening/closing 为空

**运行时间**：完整 ~22 条新闻 + 观察 + 短评的 prompt 约需 15-30 秒 API 响应。

### 4.5 `app/markdown.py` — 文章构建 + 格式化（67 行）

```python
# 接口
build_markdown(result, date_str="", title="", data_source="") -> str
format_article(text) -> str
```

**`build_markdown()` 输出结构**：
```
**今日观察**
{opening 正文}

**【{分类}】**
**{标题}**
{正文}
来源：{来源}

**【{分类}】**
...

**小编短评**
{closing 正文}

---

数据来源：{data_source}
```

**格式规则**：

| 元素 | Markdown | 条件 |
|------|----------|------|
| 今日观察 | `**今日观察**` + 空行 + 正文 | `result.opening` 非空 |
| 分类标题 | `**【{category}】**` + 空行 | 当前 item 的 category 变化时（判重） |
| 条目标题 | `**{title}**` + 空行 | 每个 item |
| 正文 | 纯文本 | 每个 item |
| 来源 | `来源：{source}` | 每个 item |
| 小编短评 | `**小编短评**` + 空行 + 正文 | `result.closing` 非空 |
| 分隔线 | `---` + 空行 | `data_source` 非空 |
| 数据来源 | `数据来源：{data_source}` | `data_source` 非空 |

**`format_article()` CJK 排版规则**：

| 转换 | 说明 |
|------|------|
| `,` → `，` | 逗号全角化 |
| `!` → `！` | 感叹号全角化 |
| `?` → `？` | 问号全角化 |
| `:` → `：` | 冒号全角化 |
| `;` → `；` | 分号全角化 |
| `(` → `（`, `)` → `）` | 括号全角化 |
| 来源行保护 | `来源：`/`数据来源：` 开头的行跳过标点转换 |
| 空行去重 | 连续多个空行合并为一个 |
| opening/closing flatten | `re.sub(r"\s*\n\s*", " ", text)` 将多行合并为单行 |

### 4.6 `app/cover_generator.py` — 封面生成（148 行）

```python
# 接口
generate_cover(date_str, title="AI 行业热点新闻", author="Tommy") -> str
    # 返回值: "static/covers/{date}.png"
```

**规格参数**：

| 属性 | 值 |
|------|-----|
| 尺寸 | 900 × 500 px |
| 格式 | PNG |
| 背景 | 垂直三色渐变 `EDDDB0` → `F2E4BD` → `EDDDB0` |
| 边框 | 4px INK (`rgb(42,38,32)`)，圆角 8px，mask 合成 |
| 左侧内边距 | 36px |
| Byline 底部 | y=430（WeChat 裁剪安全区） |

**布局坐标系（绝对定位 Y 值）**：

```
y=0   ┌──────────────────────────────────────────────────────┐ INK 边框 4px
      │                                                        │
y=12  │  ▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄ (顶部双横线, 4px+1px 高)  │
y=22  │  ▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄ (M~W-M)                   │
      │                                                        │
y=80  │       AI Daily（居中，红 AI + 黑 Daily, 56px）         │
      │                                                        │
y=158 │     AI 行业热点新闻（居中，88px）                       │
      │       AI: Caveat 88px Bold (INK)                       │
      │       行业热点新闻: ZCOOL KuaiLe 88px (INK)            │
      │                                                        │
y=258 │   ════════════════════════ (下划线 240px, INK, width=3) │
      │                                                        │
y=279 │       2026-06-28（居中，INK 阴影偏移 + RED 正文, 62px） │
      │                                                        │
      │   ~~~~~~~~~~~~~~~~ (波浪线, RED, 24周期 4振幅, width=3)│
      │                                                        │
      │  ┌──────────────────────────────────────────┐           │
      │  │ 周日 · Tommy（BG_TOP 底色 + 2px 上下边框）│           │
      │  │  byline 组: 36px padding + 8px pad        │           │
      │  └──────────────────────────────────────────┘           │
      │                                                        │
y=430 │  ↖ byline 底部位置（微信裁剪安全区底线）                │
      │                                                        │
y=500 └──────────────────────────────────────────────────────┘
```

**字体系列**：

| 用途 | 字体文件 | 字号 | 颜色 | 特殊处理 |
|------|---------|------|------|---------|
| 刊头 "AI" | Caveat[wght].ttf | 56px | RED | `set_variation_by_name("Bold")` |
| 刊头 " Daily" | Caveat[wght].ttf | 56px | INK | `set_variation_by_name("Bold")` |
| 大字 "AI" | Caveat[wght].ttf | 88px | INK | `set_variation_by_name("Bold")` |
| 大字 "行业热点新闻" | ZCOOLKuaiLe-Regular.ttf | 88px | INK | Regular |
| 日期 | ZCOOLKuaiLe-Regular.ttf | 62px | RED (3px INK 阴影偏移) | Regular |
| 星期 | ZCOOLKuaiLe-Regular.ttf | 36px | INK | Regular |
| 作者名 | Caveat[wght].ttf | 36px | INK | `set_variation_by_name("Bold")` |

**边框 mask 实现**：
```python
# 1. 创建纯 INK 背景图
border_img = Image.new("RGB", (900, 500), INK)
# 2. 创建 mask，白色圆角矩形区域表示保留原图
mask = Image.new("L", (900, 500), 0)
md = ImageDraw.Draw(mask)
md.rounded_rectangle([(4, 4), (895, 495)], radius=8, fill=255)
# 3. paste 原图到边框图上，mask 透明区域露出 INK 边框
border_img.paste(img, (0, 0), mask)
```

**颜色表**：

| 名称 | RGB | 用途 |
|------|-----|------|
| BG_TOP | (237,221,176) = `#EDDDB0` | 渐变顶 + byline 背景 |
| BG_MID | (242,228,189) = `#F2E4BD` | 渐变中点 |
| BG_BOT | (237,221,176) = `#EDDDB0` | 渐变底 |
| INK | (42,38,32) = `#2A2620` | 文字、边框、上下划线 |
| INK_SOFT | (90,82,73) = `#5A5249` | 渐隐辅助（当前未使用） |
| RED | (230,57,70) = `#E63946` | AI 红色、日期红色、波浪线 |
| ORANGE | (247,127,0) = `#F77F00` | 预留 |
| WHITE | (255,255,255) = `#FFFFFF` | 预留 |

**输出路径**：`app/static/covers/{date_str}.png`

### 4.7 `app/pipeline.py` — 流水线编排深模块（46 行）

```python
class PipelineError(RuntimeError):
    """流水线错误，带步骤前缀"""

def run_pipeline(
    date_str: str,                # "YYYY-MM-DD"
    max_words: int = 150,         # 单条改写字数上限
    on_progress: Callable = None  # (stage, status, message, percent) -> None
) -> dict:
    """
    返回值:
    {
        "items":    [{"title", "body", "link", "source", "category"}, ...],
        "opening":  str,   # 今日观察
        "closing":  str,   # 小编短评
        "markdown": str,   # 格式化后完整文章
    }
    异常: PipelineError
    """
```

**执行序列**：

| 步序 | 步骤名 | 调用 | 进度回调 |
|------|--------|------|---------|
| 1 | scraping | `fetch_and_parse(date_str)` | 完成 → 25%, "抓取完成 (N条)" |
| 2 | rewriting | `rewrite_news(items, max_words)` | 每 N% → "重写中 (n/N)..." |
| 3 | formatting | `build_markdown()` + `format_article()` | 完成 → 75%, "排版完成" |
| 4 | cover | `generate_cover()` | 完成 → 100%（在 SSE 中触发 done） |
| 5 | done | 返回 result dict | — |

**错误处理**：`fetch_and_parse` 抛出 `RuntimeError` 时包装为 `PipelineError`。

### 4.8 `app/publisher.py` — 统一发布（91 行）

```python
# 接口
publish_article(date_str: str, result: dict) -> dict
    # 内部: 读取 config → build_markdown → format_article → generate_cover → publish_to_wechat
    # 返回值: {"success": True, "media_id": "xxx"} | {"success": False, "error": "xxx"}

publish_to_wechat(title, content, cover_path, author) -> dict
    # subprocess → bun run wechat-api.ts
    # 返回值同上
```

**发布流程**：
1. 从 `get_config()` 读取最新标题、作者、数据源
2. 重新调用 `build_markdown()` + `format_article()`（使用最新配置）
3. 重新调用 `generate_cover()`（使用最新标题和作者）
4. 写入临时 `.md` 文件
5. 从 `.env` 手动加载微信凭证到环境变量
6. `subprocess.run` 执行 `bun run wechat-api.ts`
7. 解析 stdout JSON，删除临时文件

**subprocess 命令**：
```bash
bun run wechat-api.ts /tmp/draft_xxx.md --title "标题" --author "作者" --cover "cover.png" --no-cite --theme default
```

**发布 skill 目录**：`skills/baoyu-post-to-wechat/scripts/`
**Bun 路径检测**：`shutil.which("bun") or "bun.cmd"`

### 4.9 `app/scheduler.py` — Windows 计划任务管理（71 行）

```python
# 常量
TASK_NAME = "AI Daily Publisher"
CHECK_TASK_NAME = "AI Daily Publisher - Check"

# 接口
create_or_update_tasks(schedule_time: str) -> None
    # 1. schtasks /change 更新主任务的 /st
    # 2. 删除重建检查任务（主任务时间 + 5 分钟）

get_trigger_time(task_name: str) -> str | None
    # 读取 schtasks /query /tn {name} /xml
    # 解析 <StartBoundary> 节点中的 T{HH}:{MM} 部分
    # 返回 "HH:MM" 格式

get_task_info(task_name: str) -> dict | None
    # schtasks /query /v /fo csv
    # 解析 CSV 第 5/6/2 列
    # 返回 {"last_run": str, "last_result": str, "next_run": str}
```

**检查任务创建 PowerShell**：
```powershell
$action = New-ScheduledTaskAction -Execute 'python' -Argument 'check_daily.py'
$trigger = New-ScheduledTaskTrigger -Daily -At '{check_time}'
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName 'AI Daily Publisher - Check' -Action $action -Trigger $trigger -Principal $principal -Force
```

**时间联动**：`_add_minutes("10:00", 5) → "10:05"`（处理跨小时进位）

### 4.10 `app/run_daily.py` — 定时运行入口（32 行）

```python
def run():
    date_str = datetime.now().strftime("%Y-%m-%d")
    result = run_pipeline(date_str, get_config("max_words"))
    pub_result = publish_article(date_str, result)
    # 打印结果到 stdout（run_scheduled.bat 捕获到日志）
```

**被 `run_scheduled.bat` 调用**：`python app/run_daily.py`

### 4.11 `app/check_daily.py` — 状态检查 + 弹窗 + 自动重触（41 行）

```python
def main():
    info = get_task_info(TASK_NAME)
    # 检查逻辑:
    # - last_run 以今天开头 + 结果码 == 0 → ✅ 弹窗 (MB_ICONINFORMATION 0x40)
    # - last_run 以今天开头 + 结果码 != 0 → ❌ 弹窗 (MB_ICONERROR 0x10)
    # - last_run 不是今天 → schtasks /run 重新触发主任务 + ⚠️ 弹窗 (MB_ICONWARNING 0x30)
    ctypes.windll.user32.MessageBoxW(0, msg, title, icon | 0x1000)
```

**弹窗类型**：
```
✅ 今日已成功执行 → MB_ICONINFORMATION (0x40)  蓝色 i
❌ 执行失败 (代码: X) → MB_ICONERROR (0x10)     红色 ✕
⚠️ 今日尚未触发，已自动重新触发 → MB_ICONWARNING (0x30)  黄色 ⚠
所有弹窗带 MB_TOPMOST (0x1000) 置顶
```

---

## 5. 模块依赖图

```
main.py ──→ config.py (get_config)
         → pipeline.py
         │    → scraper.py (fetch_and_parse)
         │    → rewriter.py (rewrite_news)
         │    │    → prompts/rewrite.md
         │    → markdown.py (build_markdown, format_article)
         │    → cover_generator.py (generate_cover)
         │    → config.py (get_config)
         → publish_article() [via publisher.py]
         │    → config.py (get_config)
         │    → markdown.py (build_markdown, format_article)
         │    → cover_generator.py (generate_cover)
         │    → publisher.py (publish_to_wechat)
         │         → skills/baoyu-post-to-wechat/scripts/wechat-api.ts (bun)
         → scheduler.py (create_or_update_tasks, get_trigger_time)

run_daily.py → env.py (load_env)
             → config.py (get_config)
             → pipeline.py (run_pipeline)
             → publisher.py (publish_article)

check_daily.py → scheduler.py (get_task_info)
```

---

## 6. API 路由一览

### 6.1 路由表

| 方法 | 路径 | 请求体 | 返回值 | 行号 |
|------|------|--------|--------|------|
| GET | `/` | — | HTML (`render_template`) | 19 |
| POST | `/api/fetch` | `{"date": "...", "max_words": N}` | `{"status": "ok"}` | 24 |
| GET | `/api/progress` | — | SSE stream | 36 |
| GET | `/api/preview` | — | `{items[], opening, closing}` | 82 |
| GET | `/api/article-text` | — | `{"text": "..."}` | 90 |
| GET | `/api/cover` | — | `{"url": "static/covers/{date}.png"}` | 100 |
| POST | `/api/publish` | — | `{success, media_id}` | 108 |
| GET | `/api/config` | — | full config dict | 118 |
| POST | `/api/config` | 任意配置字段 | `{"status": "ok"}` | 118 |

### 6.2 `/api/config` 特殊行为

**GET**：先读 `config.json`，再查 Windows 计划任务的 `<StartBoundary>` XML 节点，用真实触发时间覆盖 `schedule_time` 字段返回（UI 显示的是 schtasks 真实时间，非缓存值）。

**POST 带 `schedule_time`**：除写入 `config.json` 外，还执行 `scheduler.create_or_update_tasks(t)`：
1. `schtasks /change /tn "AI Daily Publisher" /st {新时间}`
2. 删除并重新创建 `AI Daily Publisher - Check` 任务，触发时间 = 主时间 + 5 分钟

### 6.3 内部状态（app.config）

```python
app.config["CURRENT_ARTICLE"] = None   # pipeline 返回值 dict
app.config["CURRENT_DATE"] = None       # 当前选中日期 "YYYY-MM-DD"
app.config["CURRENT_MAX_WORDS"] = 150   # 当前字数限制
```

**流程**：
1. `POST /api/fetch` → 存入 `CURRENT_DATE` 和 `CURRENT_MAX_WORDS`，清空 `CURRENT_ARTICLE`
2. `GET /api/progress` → 启动后台线程调用 `run_pipeline()`，通过 `queue.Queue` 传递事件给 SSE generator
3. SSE generator 死循环 `q.get(timeout=0.5)`：
   - `stage` 类型 → yield SSE event
   - `result` 类型 → 存入 `CURRENT_ARTICLE`，yield done 事件，返回
   - `error` 类型 → yield error 事件，返回
   - `queue.Empty` → continue（保持连接）
4. `GET /api/preview` / `POST /api/publish` → 从 `CURRENT_ARTICLE` 读取数据

### 6.4 SSE 协议

```
事件名: stage
数据格式: {"stage": str, "status": str, "message": str, "percent": int}

正常序列:
  event: stage
  data: {"stage":"scraping","status":"complete","message":"抓取完成 (10条)","percent":25}

  event: stage
  data: {"stage":"rewriting","status":"progress","message":"重写中 (3/10)...","percent":32}

  event: stage
  data: {"stage":"rewriting","status":"complete","message":"重写完成","percent":50}

  event: stage
  data: {"stage":"formatting","status":"complete","message":"排版完成","percent":75}

  event: stage
  data: {"stage":"done","status":"complete","message":"全部完成","percent":100}

异常序列:
  event: stage
  data: {"stage":"error","status":"error","message":"抓取失败: xxx","percent":0}
```

**前端消费**：
```javascript
const es = new EventSource('/api/progress');
es.addEventListener('stage', function(e) {
  const d = JSON.parse(e.data);
  updateProg(d);  // → Timeline 状态推进
});
```

---

## 7. 前端架构

### 7.1 JavaScript 状态管理（296 行，app.js）

所有共享状态集中在单个 `state` 对象：

```javascript
const state = {
  selDate: '',         // 当前选中日期 "2026-06-28"
  eventSource: null,   // SSE EventSource 实例
  calY: 0,             // 日历当前年
  calM: 0,             // 日历当前月 (0-11)
};
```

### 7.2 事件绑定表

| 事件 | 选择器 | 触发操作 |
|------|--------|---------|
| day click | `.cal-grid .d` | `pickDate(ds)` → 高亮选中、更新日期/星期/标题、启用抓取、自动保存标题 |
| prev month | `#calPrev` | `renderCal(y, m-1)` |
| next month | `#calNext` | `renderCal(y, m+1)` |
| fetch click | `#btnFetch` | 按钮 disabled → POST /api/fetch → startSSE() |
| SSE stage | `EventSource` | `updateProg(d)` → Timeline 状态推进 |
| SSE done | — | 关闭连接 → loadPreview() → 启用发布按钮 |
| SSE error | — | 关闭连接 → toast + 恢复按钮 |
| view switch | `.pv-btn` | 切换 正文预览 / 封面预览 display |
| title change | `#inputTitle` | `change` → POST /api/config 自动保存 |
| author change | `#inputAuthor` | `change` → POST /api/config 自动保存 |
| max_words change | `#inputMaxWords` | `change` → POST /api/config 自动保存 |
| save time | `#btnSaveTime` | click → POST /api/config {schedule_time} |
| copy | `#btnCopy` | click → `clipboard.writeText()` → toast |
| publish | `#btnPublish` | click → POST /api/publish → toast |

### 7.3 Timeline 状态机

```javascript
const stepNames = ['scraping', 'rewriting', 'formatting', 'cover', 'done'];

// setStep(step, cls, msg):
//   cls = 'active' | 'done' | 'fail' | '' (reset)
//   msg = 状态文本

// updateProg(d):
//   scraping:complete → setStep('scraping','done') + setStep('rewriting','active')
//   rewriting:progress → setStep('rewriting','active', msg)
//   rewriting:complete → setStep('rewriting','done') + setStep('formatting','active')
//   formatting:complete → setStep('formatting','done') + setStep('cover','active')
//   done → setStep('cover','done') + setStep('done','done')
//   error → 找到当前的 active step → setStep(step,'fail', msg)
```

### 7.4 预览渲染（`loadPreviewHtml`）

从 `/api/preview` JSON 渲染 HTML 到 `#pvContent`：
```html
<!-- 今日观察 -->
<div style="font-weight:700;color:var(--spray-orange);...">今日观察</div>
<div>{{opening}}</div>

<!-- 分类（判重） -->
<div style="...">【{{category}}】</div>

<!-- 单条 -->
<div><strong>{{title}}</strong><br>{{body}}<br>
<span style="font-size:10px;color:var(--ink-faint);">来源：{{source}}</span></div>

<!-- 小编短评 -->
<div style="...">小编短评</div>
<div>{{closing}}</div>
```

### 7.5 封面预览

`/static/covers/{date}.png?t={timestamp}`（时间戳防止缓存）

---

## 8. UI 主题系统

### 8.1 设计定位

"涂鸦草稿本"（Graffiti Notebook）：泛黄纸张 + 棋盘格线 + 手写字体 + 喷漆标签 + 咖啡渍装饰。全部由纯 CSS 实现（无图片、无框架依赖）。

### 8.2 CSS 变量体系（完整）

```css
:root {
  --paper: #F2E4BD;          /* 纸张底色 rgb(242,228,189) */
  --paper-warm: #EDDDB0;     /* 暖色纸张 rgb(237,221,176) */
  --paper-edge: #D8C58E;     /* 纸张边缘 rgb(216,197,142) */
  --ink: #2A2620;            /* 墨水黑 (42,38,32) 主文字/边框 */
  --ink-soft: #5A5249;       /* 中墨 (90,82,73) 次要文字 */
  --ink-faint: #8C847A;      /* 淡墨 (140,132,122) 提示文本 */
  --spray-red: #E63946;      /* 喷漆红 (230,57,70) 错误/高亮 */
  --spray-orange: #F77F00;   /* 喷漆橙 (247,127,0) 警告/标签 */
  --spray-yellow: #FFB627;   /* 喷漆黄 (255,182,39) 封面步骤 */
  --line: rgba(42,38,32,0.16);     /* 网格线 */
  --line-soft: rgba(42,38,32,0.08);/* 淡网格线 */
  --coffee: rgba(101,67,33,0.15);  /* 咖啡渍 */
  --f-serif: 'Lora', 'Noto Serif SC', serif;
  --f-hand: 'Caveat', cursive;
  --f-cn-hand: 'ZCOOL KuaiLe', 'Caveat', cursive;
}
```

### 8.3 布局结构

```css
/* 双栏 Grid，100vh 无 body 滚动 */
.app {
  display: grid;
  grid-template-columns: 280px 1fr;
  gap: 24px;
  max-width: 1200px;
  margin: 0 auto;
  align-items: stretch;
  height: 100%;
}

/* Body 背景 */
body {
  background: #C9B888;  /* 木质桌面色 */
  height: 100vh;
  overflow: hidden;
}
body::before { /* 网格线 overlay */
  background-image:
    linear-gradient(to right, transparent 0, transparent 39px, var(--line) 39px, var(--line) 40px),
    linear-gradient(to bottom, transparent 0, transparent 27px, var(--line) 27px, var(--line) 28px);
}
body::after {  /* 咖啡渍装饰 */
  background:
    radial-gradient(ellipse at top left, transparent 70%, rgba(101,67,33,0.08) 100%),
    radial-gradient(ellipse at bottom right, transparent 70%, rgba(101,67,33,0.10) 100%);
}
```

### 8.4 组件完整清单

以下每个组件的 CSS 类名、作用、关键样式和状态：

| # | 组件 | CSS 类 | 说明 |
|---|------|--------|------|
| 1 | 控制面板 | `.controls` | 280px 左侧面板，2px INK 边框，不规则圆角 `4px 20px 4px 24px / 20px 4px 24px 4px`，6px 阴影偏移，右下折角 |
| 2 | 主卡片 | `.mockup` | 右侧弹性区域，2.5px 边框，圆角 `8px 24px 6px 20px / 20px 6px 24px 8px`，10px 阴影偏移，右下折角 |
| 3 | 板块标题 | `.ctrl-section-title` | Caveat 20px 700，橙虚线底边 1.5px，红色圆点 `::before` |
| 4 | Logo | `.logo` | Caveat 34px 700 italic，红色 `AI` + 黑色 `Daily` |
| 5 | 日历 | `.cal-card` `.cal-grid` | 7×6 网格，箭头按钮不规则圆角，三种状态：default/today(.today)/selected(.sel) |
| 6 | 选中日期 | `.fetch-row` `.fetch-date` | Caveat 22px 700 red，背景 rgba(247,127,0,0.06) |
| 7 | 抓取按钮 | `.btn-fetch` | 全宽，Caveat 20px 700，圆角 `18px 4px` 组，3px 阴影，hover 上移 2px，disabled 40% 透明度 |
| 8 | Timeline | `.tl-step` `.tl-dot` `.tl-line` | 5 步垂直布局，彩色圆点/连接线，4 状态：等待中/active（脉冲）/done（绿勾弹入）/fail（红色抖动） |
| 9 | 进度条 | `.status-card` `.bar-track` `.bar-fill` | 进度 pill（不规则形状 `border-radius: 35% 65%...`），进度条 6px 高，橙色/红色 |
| 10 | 字数输入 | `.word-input` `.config-row` | 52px 宽，Caveat 14px，黑色边框，focus 橙高亮 |
| 11 | 标语 | `.main-header` | Caveat 30px 700 italic，居中，虚线底边 |
| 12 | 标题/作者输入 | `.field-input` `.field-label` | 无边框，底部虚线，focus 实线橙 |
| 13 | 视图切换 | `.pv-btn` | Caveat 15px 700，不规则圆角，active 黑色实底 |
| 14 | 正文预览 | `.pv-content` | 2px INK 边框，内滚动 overflow-y:auto，13px 字体 |
| 15 | 封面预览 | `.pv-cover` | 同边框，flex 居中 |
| 16 | 封面图片 | `.cover-img` | 2.5px 边框，6px 阴影，`max-height:420px` |
| 17 | 喷漆标签 | `.spray-badge` | 不规则背景 `border-radius: 35% 65%...`，喷溅斑点 `::after`，糊状边框 |
| 18 | 状态药丸 | `.status-bar` | 喷漆橙 bg，旋转 -1.5deg，脉冲动画 1.6s，模糊辉光 `::before`，点缀点 `::after` |
| 19 | 咖啡渍 | `.coffee-stain` | 径向渐变椭圆，pointer-events:none，两个位置 |
| 20 | 挂角标签 | `.corner-tag` | 右上悬挂，tag-swing 动画 3s，默认隐藏 `.show` 时显示 |
| 21 | Toast | `.toast` | 右下固定，3 秒消失，成功绿/错误红，tin 动画 0.25s |
| 22 | 操作按钮 | `.btn` | Caveat 18px 700，圆角 `18px 4px` 组，3px 阴影，hover 上移 |
| 23 | 定时输入 | `.time-input` | Caveat 14px 700，80px 宽，黑色边框，focus 橙高亮 |
| 24 | 状态栏 | `.status-info` | 显示 IDLE/RUNNING/DONE/FAIL，detail 文字灰斜体 |

### 8.5 动画规格

| 动画名 | keyframes | 触发元素 | 属性变化 | 时长 | 曲线 | 状态 |
|--------|-----------|---------|---------|------|------|------|
| tl-pulse | `@keyframes tl-pulse` | `.tl-step.active .tl-dot` | box-shadow 3↔6px | 1.2s infinite | ease-in-out | active |
| tl-pop | `@keyframes tl-pop` | `.tl-step.done .tl-dot` | scale 0.6→1.2→1 | 0.3s | cubic-bezier(0.34,1.56,0.64,1) | done |
| shake | `@keyframes shake` | `.tl-step.fail .tl-dot` | rotate ±3°, translateX | 0.4s | ease-in-out | fail |
| tin | `@keyframes tin` | `.toast` 出现 | translateY 10→0px, opacity | 0.25s | ease | 弹入 |
| pulse | `@keyframes pulse` | `.status-bar` (IDLE) | scale 1↔1.04, rotate -1.5° | 1.6s infinite | ease-in-out | idle |
| tag-swing | `@keyframes tag-swing` | `.corner-tag` | rotate 4↔6° | 3s infinite | ease-in-out | 显示时 |
| btn-hover | transition | `.btn:hover` | translate(-2,-2), box-shadow | 0.2s | ease | hover |
| btn-active | transition | `.btn:active` | translate(0,0), box-shadow 1px | 0.2s | ease | active |

### 8.6 响应式断点

```css
@media (max-width: 860px) {
  .app { grid-template-columns: 1fr; }       /* 双栏→单栏 */
  .status-area { flex-direction: column; }    /* 状态栏竖排 */
  .corner-tag { display: none !important; }   /* 隐藏挂角 */
}
```

---

## 9. 定时任务体系

### 9.1 两个独立任务

| 任务名 | 时间 | 执行内容 | 触发条件 |
|--------|------|---------|---------|
| `AI Daily Publisher` | `config.schedule_time` | `run_scheduled.bat` → `python app/run_daily.py` | InteractiveToken（需用户登录） |
| `AI Daily Publisher - Check` | 主任务 + 5 min | `python app/check_daily.py` → MessageBoxW 弹窗 | 同上，独立于主任务 |

### 9.2 触发器文件：`run_scheduled.bat`

```batch
@echo off
cd /d "E:\App Development\AI Daily"
python app/run_daily.py >> app\logs\scheduled.log 2>&1
```

### 9.3 时间联动机制

1. 用户在 UI 修改 time input → 点击「保存」
2. `POST /api/config {"schedule_time": "11:00"}`
3. `set_config("schedule_time", "11:00")` 写入 config.json
4. `scheduler.create_or_update_tasks("11:00")`：
   - `schtasks /change /tn "AI Daily Publisher" /st 11:00`
   - 删除并重建 `AI Daily Publisher - Check`（触发 11:05）
5. 刷新页面 → `GET /api/config` → 读 schtasks XML 真实时间返回

### 9.4 S4U 模式状态

当前任务使用 `InteractiveToken`（需用户登录）。S4U（Run whether user is logged on or not）因 Windows 密码被 `schtasks` 拒绝而无法启用。

---

## 10. AI 改写 Prompt（`app/prompts/rewrite.md`）

### 10.1 角色设定
- 编辑名字：小 AI
- 读者：AI 早期采用者和产品经理
- 语言：简洁、有判断、有温度，中文

### 10.2 今日观察规则
- **定位**：开篇钩子，告诉读者"今天最该知道什么"
- **选题标准**：从当日抓取中选 1-3 条
  - 高价值：影响面广（政策变动、新模型发布或更新、模型重大突破）
  - 高反常：超出预期的黑天鹅、标志性拐点
- **写作公式**：事实 + 为什么重要
  - 第一句：核心事实（谁 + 发生了什么 + 结果）
  - 第二句：直接后果（市场/行业立刻面对什么）
  - 第三句（可选）：点睛（趋势信号或认知刷新）
- **限制**：120 字内，0 个形容词，用动词名词，不解释基础概念

### 10.3 小编短评规则
- **定位**：把一天的信息串成一根线
- **三段式结构**：
  1. 首句（关联今日观察）：呼应不重复
  2. 中句（提炼主线）：指出共同指向的变化
  3. 末句（观点金句）：立场明确
- **头尾联动**：观察提出事实 → 改写展开细节 → 短评给出判断，形成问答闭环
- **信息不重复**：短评不重复观察中出现的具体数据

### 10.4 输出 JSON 格式

```json
{
  "todayObservation": "120字内开篇钩子",
  "items": [
    {
      "title": "原标题（可微调措辞）",
      "rewritten": "改写后内容（不超过 {{MAX_CHARS}} 字）",
      "link": "原链接",
      "source": "原来源"
    }
  ],
  "editorComment": "300字内三段式短评"
}
```

### 10.5 强约束
1. 只能改写输入已有的事实，不能编造
2. 每条 items 必须包含 `title`/`rewritten`/`link`/`source`，`rewritten` 不能为空
3. 改写不是缩写，是"用自己的话重新讲一遍"

---

## 11. 用户流程

### 11.1 手动流程（Web UI）

```
打开 http://localhost:5000
  │
  ├─① 日历
  │   默认显示当月，今天橙色圆点
  │   点击◀ ▶ 切换月份
  │   点击某日 → 日期显示更新，标题自动填入 "AI 行业热点新闻 | YYYY-MM-DD"
  │   标题自动保存到 config.json
  │
  ├─② 点击「⟳ 抓取」
  │   按钮禁用，Timeline 第 1 步 active
  │   SSE 连接 /api/progress
  │   Timeline 逐步推进：抓取✓ → 重写中... → 重写✓ → 排版✓ → 封面✓ → 完成✓
  │   右上角显示 BUSY 挂角标签
  │   完成时正文预览自动加载，发布按钮启用
  │
  ├─③ 预览
  │   点击「正文预览」/「封面预览」tab 切换
  │   可点「📋 复制」复制全文到剪贴板
  │
  ├─④ 设置定时
  │   修改 time input → 点击「保存」
  │   自动更新两个计划任务时间
  │
  └─⑤ 点击「📢 发布」
       POST /api/publish → toast "草稿已创建成功！" / "发布失败：xxx"
```

### 11.2 自动流程（Windows 计划任务）

```
10:00 — AI Daily Publisher（主任务）
  └─ run_scheduled.bat → python app/run_daily.py
      ├─ env.load_env() 加载 .env 凭证
      ├─ 获取当天日期 YYYY-MM-DD
      ├─ run_pipeline()
      │   ├─ fetch_and_parse → 抓取 aihot API + 解析 items
      │   ├─ rewrite_news → Agnes AI 改写（单次调用，timeout 180s）
      │   ├─ build_markdown → 组装文章
      │   ├─ format_article → CJK 排版
      │   └─ generate_cover → 生成封面
      ├─ publish_article() → build_markdown + format + cover + publish_to_wechat
      └─ 输出日志到 app/logs/scheduled.log

10:05 — AI Daily Publisher - Check（独立于主任务）
  └─ python app/check_daily.py
      ├─ scheduler.get_task_info() 查主任务状态
      ├─ 今天有记录 + 结果码 0 → ✅ 弹窗
      ├─ 今天有记录 + 结果码 ≠ 0 → ❌ 弹窗
      └─ 今天无记录 → schtasks /run 重新触发主任务 + ⚠️ 弹窗
```

---

## 12. 配置系统

### 12.1 `.env`（根目录，gitignored）

```env
LLM_BASE_URL=https://apihub.agnes-ai.com/v1
LLM_API_KEY=sk-xxxx
LLM_MODEL=agnes-2.0-flash
WECHAT_APP_ID=wx0000000000000000
WECHAT_APP_SECRET=xxxx
```

### 12.2 `app/data/config.json`

```json
{
  "title": "AI 行业热点新闻 | 2026-06-28",
  "author": "Tommy",
  "max_words": 150,
  "schedule_time": "10:00",
  "data_source": "https://aihot.virxact.com/"
}
```

**`schedule_time` 同步规则**：UI 始终显示 schtasks XML 真实触发时间（`GET /api/config` 查询计划任务），config.json 中的值仅作备份和初始加载。

---

## 13. 错误处理

### 13.1 错误场景表

| 步骤 | 错误场景 | 处理方式 | 异常类型 |
|------|---------|---------|---------|
| 抓取 | HTTP 超时 (>15s) | `RuntimeError("请求超时: {url}")` → pipeline 捕获为 PipelineError | `PipelineError` |
| 抓取 | HTTP 非 200 | `RuntimeError("请求失败: {str(e)}")` → PipelineError | `PipelineError` |
| 改写 | API 调用失败 | 3 次指数退避重试(2s/4s间隔) → 全部失败才 `RuntimeError` → SSE error | `RuntimeError` |
| 改写 | JSON 解析失败 | 自动 fallback 到原始内容截取 | 静默处理 |
| 封面 | 字体文件缺失 | `ImageFont.load_default()` | 静默 fallback |
| 发布 | skill 目录不存在 | 返回 `{"success": False, "error": "发布 skill 不存在"}` | JSON 响应 |
| 发布 | bun 超时 (>120s) | 返回 `{"success": False, "error": "发布超时"}` | JSON 响应 |
| 发布 | 微信 API 错误 | 从 stderr 解析 `Error:` 行 | JSON 响应 |
| 检查 | schtasks 找不到 | `MessageBoxW` 报错 | 弹窗通知 |

### 13.2 SSE 错误流

```
event: stage
data: {"stage":"error","status":"error","message":"API 调用失败: ...","percent":0}
```

前端接到 error 事件后：
1. 关闭 EventSource 连接
2. 找到当前 active 的 Timeline 步骤 → 设置为 fail（红色 ✕ 抖动）
3. 右上角挂角标签变为 FAIL（红底）
4. Status bar 变为 FAILED（红底，shake 动画）
5. Toast 显示错误消息
6. 恢复抓取按钮

---

## 14. 部署指南

### 14.1 首次部署

1. **克隆项目**到目标机器
2. **安装 Python 依赖**：
   ```bash
   pip install flask requests beautifulsoup4 Pillow
   ```
3. **安装 bun**：
   ```powershell
   powershell -c "irm bun.sh/install.ps1 | iex"
   ```
4. **下载 Google Fonts** 放入 `app/fonts/`：
   - [Caveat](https://fonts.google.com/specimen/Caveat)（需要 wght 变体）
   - [ZCOOL KuaiLe](https://fonts.google.com/specimen/ZCOOL+KuaiLe)
   - [Lora](https://fonts.google.com/specimen/Lora)
5. **配置 `.env`**：填入 LLM_API_KEY、WECHAT_APP_ID、WECHAT_APP_SECRET
6. **启动 Web UI**：双击 `run.bat` → 浏览器打开 `http://localhost:5000`
7. **设置定时时间**：在 UI 中修改 → 保存（自动创建两个计划任务）
8. **微信 IP 白名单**：将本机公网 IP 添加到 mp.weixin.qq.com → 开发 → 基本配置

### 14.2 启动方式

**手动启动 Web UI**：
```batch
run.bat
:: 等价于 python -m app.main
:: 访问 http://localhost:5000
```

**计划任务**：在 UI 中设置时间后自动创建，或通过 `scheduler.create_or_update_tasks()` 手动创建。

### 14.3 必需文件清单

```
.env                          # 密钥（gitignored）
app/fonts/Caveat[wght].ttf   # 封面英文字体
app/fonts/ZCOOLKuaiLe-Regular.ttf  # 封面中文字体
app/fonts/Lora[wght].ttf     # UI 衬线字体
app/prompts/rewrite.md       # AI 改写 prompt
app/data/config.json         # 首次运行自动创建
skills/baoyu-post-to-wechat/ # 发布 skill 目录
```

---

## 15. 架构演进记录

| 版本 | 日期 | 主要变更 |
|------|------|---------|
| v0.1 | 2026-06-26 | 初始实现：单文件 Flask + TailwindCSS + daisyUI 深色主题 |
| v1.0 | 2026-06-28 | 完整架构重构：13 个 Python 模块、涂鸦 UI 主题、scheduler 模块、env 分离、统一发布路径 |
| v1.1 | 2026-06-30 | 修复定时任务默认电池禁用 + 睡眠不唤醒；rewriter 加 3 次指数退避重试网络故障；max_tokens 3000→8000 解决 JSON 截断丢失今日观察/小编短评；添加 _try_repair_json 截断容错；timeout (10,180)→(10,60)；run_daily.py 任务前同步标题解决日期不符 |

### v1.0 关键重构决策

| 决策 | 原因 |
|------|------|
| scraper `fetch+parse` 合并为 `fetch_and_parse()` | 两者永远一起调用，伪接缝消除 |
| `scheduler` 模块提取 | main.py 不应直接操作操作系统调度器（schtasks XML/CSV/PowerShell 细节隐藏） |
| `env` 与 `config` 分离 | 测试安全隐患——import 时自动加载凭据 |
| `formatter` 并入 `markdown` | 浅模块（34 行），单独文件导航成本 > 收益 |
| `publish_article()` 统一手动/自动路径 | run_daily.py 和 main.py 曾有不同的 publish 实现，潜在 bug |

---

## 16. 注意事项

1. **封面 Byline 位置**：y=430 而非底部，避免微信草稿预览 UI 裁剪
2. **`schedule_time` 同步**：始终以 schtasks 真实时间为准，config.json 仅作备份
3. **API key 安全**：不在代码/日志/commit 中出现，`.env` 已 gitignored
4. **定时任务模式**：InteractiveToken 要求用户登录状态，注销时不会触发
5. **AI 改写响应时间**：完整 prompt 约需 15-20 秒 API 响应，属正常范围
6. **微信 IP 白名单**：如果本机 IP 变化，需更新微信后台白名单
7. **电池/睡眠坑（已修）**：Windows 默认 `DisallowStartIfOnBatteries=true` + 无 `WakeToRun`，拔电或睡眠时任务静默跳过。`scheduler._fix_task_settings()` 修复为 `DisallowStartIfOnBatteries=false` + `WakeToRun=true`
