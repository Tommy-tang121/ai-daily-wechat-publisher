# AI 日报公众号发布助手 · 实施计划 v1.0

> ⚠️ **历史基线文档。** 本文件记录 2026-06-26 的原型实现，里面的旧路径、旧 Hook 和旧模块名不代表当前系统。当前产品、架构、计划任务和验收规则以 `docs/README.md`、`docs/PRD/`、`docs/SPEC/` 与 `docs/superpowers/specs/` 为准。

> **状态**：全部已实现并稳定运行
> **实施周期**：2026-06-26 ~ 2026-06-28
> **代码量**：13 个 Python 模块合计 877 行 + 1 个 HTML 模板 170 行 + CSS 1375 行 + JS 296 行
> **完整设计文档**：`docs/AI日报公众号发布助手-产品设计文档.md`
> **UI 组件参考**：`design/ui-reference.html`

---

## 一、项目目标

每日自动抓取 AI 新闻 → AI 重写 → 排版 → 生成封面 → 发布到微信公众号草稿箱。
Web UI 手动操作 + Windows 计划任务自动运行双通道。

## 二、实施里程碑

### Milestone 1：项目骨架

| 任务 | 文件 | 行数 | 验收标准 |
|------|------|------|---------|
| 项目包结构 | `app/__init__.py` | 0 | — |
| 环境加载 | `app/env.py` | 20 | `load_env()` 加载 .env → os.environ |
| 配置管理 | `app/config.py` | 38 | 读写 `app/data/config.json` |
| Flask 入口 | `app/main.py` | 135 | `python -m app.main` 启动，`/` 返回 HTML |

### Milestone 2：抓取 + 改写管线

| 任务 | 文件 | 行数 | 验收标准 |
|------|------|------|---------|
| scraper | `app/scraper.py` | 74 | `fetch_and_parse()` 返回 `[{title, content, source, category}]` |
| rewrite prompt | `app/prompts/rewrite.md` | 68 | 带今日观察/小编短评规则，{{MAX_CHARS}}/{{DAILY_DATA}} 占位符 |
| rewriter | `app/rewriter.py` | 111 | 单次 API 调用，返回结构化 JSON，JSON 解析失败自动 fallback |
| 封面生成 | `app/cover_generator.py` | 148 | 900×500 PNG，渐变背景 + 4px 圆角 INK 边框 + byline y=430 |

### Milestone 3：排版 + 发布

| 任务 | 文件 | 行数 | 验收标准 |
|------|------|------|---------|
| markdown 构建 | `app/markdown.py` | 67 | 输出格式：`**今日观察**` → `**【分类】**` → `**标题**` → 正文 → `来源` → `**小编短评**` → `---` → `数据来源` |
| CJK 排版 | `app/markdown.py` `format_article()` | — | 标点半角→全角，来源行保护，空行去重 |
| 发布 | `app/publisher.py` | 91 | subprocess → bun → wechat-api.ts，解析 stdout JSON |

### Milestone 4：流水线编排

| 任务 | 文件 | 行数 | 验收标准 |
|------|------|------|---------|
| pipeline 深模块 | `app/pipeline.py` | 46 | `run_pipeline()` 单函数编排全流程，进度回调 |
| 定时任务入口 | `app/run_daily.py` | 32 | 调用 pipeline + publish |
| 计划任务管理 | `app/scheduler.py` | 71 | 创建/更新/查询 schtasks，XML/CSV/PowerShell 封装 |
| 运行检查 | `app/check_daily.py` | 38 | 查 schtasks + MessageBoxW 弹窗（✅/❌/⚠️） |

### Milestone 5：Web UI

| 任务 | 文件 | 行数 | 验收标准 |
|------|------|------|---------|
| 模板 | `app/templates/index.html` | 170 | 涂鸦风格布局，双栏 |
| 样式 | `app/static/style.css` | 1375 | 24+ CSS 组件、7 个动画、CSS 变量体系 |
| 前端交互 | `app/static/app.js` | 296 | 日历、SSE、Timeline、预览、复制、发布 |

### Milestone 6：端到端验证

| 任务 | 验收标准 |
|------|---------|
| 手动流水线 | Web UI 选日期→抓取→预览→发布，Timeline 逐步推进 |
| 定时任务 | `schtasks /run` 触发成功，`app/logs/scheduled.log` 有 media_id 记录 |
| 检查弹窗 | 主任务执行后 5 分钟弹出 ✅ 通知 |

## 三、文件创建顺序（依赖关系）

```
 1. app/__init__.py          (空)
 2. app/env.py               (无依赖)
 3. app/config.py            (无依赖)
 4. app/scraper.py           (requests)
 5. app/prompts/rewrite.md   (prompt 文本)
 6. app/rewriter.py          (app/env.py, app/prompts/rewrite.md)
 7. app/markdown.py          (re)
 8. app/cover_generator.py   (Pillow, app/fonts/)
 9. app/pipeline.py          (app/scraper, app/rewriter, app/markdown, app/cover_generator, app/config)
10. app/scheduler.py         (subprocess, csv)
11. app/publisher.py         (app/markdown, app/config, app/cover_generator)
12. app/run_daily.py         (app/env, app/pipeline, app/publisher, app/config)
13. app/check_daily.py       (app/scheduler)
14. app/main.py              (以上全部 + Flask)
15. app/templates/index.html (Jinja2)
16. app/static/style.css     (CSS 变量体系 → 组件 → 动画 → 响应式)
17. app/static/app.js        (state → calendar → fetch/SSE → Timeline → preview → publish)
```

## 四、模块依赖图

```
                    ┌──────────────┐
                    │   env.py     │  → main.py, run_daily.py (显式加载)
                    └──────────────┘

                    ┌──────────────┐
                    │  config.py   │  → main.py, pipeline.py, publisher.py, run_daily.py
                    └──────────────┘

                    ┌──────────────┐
                    │  scraper.py  │  → pipeline.py
                    └──────────────┘

                    ┌──────────────┐
                    │  rewriter.py │  → pipeline.py
                    └──────────────┘

                    ┌──────────────┐
                    │  markdown.py │  → pipeline.py, publisher.py
                    └──────────────┘

                    ┌──────────────┐
                    │cover_gen.py  │  → pipeline.py, publisher.py
                    └──────────────┘

                    ┌──────────────┐
                    │ scheduler.py │  → main.py, check_daily.py
                    └──────────────┘

                    ┌──────────────┐
                    │ publisher.py │  → main.py (publish_article), run_daily.py
                    │              │  → skills/baoyu-post-to-wechat/scripts/ (bun)
                    └──────────────┘

                    ┌──────────────┐
                    │ pipeline.py  │  → main.py (SSE), run_daily.py (定时)
                    └──────────────┘

main.py: 8 Flask routes → GET /, POST /api/fetch, GET /api/progress (SSE),
         GET /api/preview, GET /api/article-text, GET /api/cover,
         POST /api/publish, GET|POST /api/config
```

## 五、已知问题与后续计划

### 遗留问题

- [ ] **S4U 模式不可用**：Windows 密码 `tsy123` 被 schtasks 拒绝，任务在用户注销时不触发
- [ ] **封面 byline 裁剪**：已在 y=430 修复，待通过微信正式发布验证
- [ ] **CJK 自动间距**：`autocorrect-node` 未安装，`--spacing` 无效果
- [x] **检查任务自动重触**：10:05 检测到主任务未触发，自动 `schtasks /run`
- [ ] **LLM 超时自动重试**：Agnes API 超时无重试机制
- [ ] **IP 白名单**：本机 IP 变化时需手动更新微信后台

### 优化方向

| 方向 | 描述 | 优先级 |
|------|------|--------|
| SSH 隧道转发 | 固定 IP 转发解决白名单问题 | 低 |
| 多条改写并行 | pipeline 中按分类并行调用 LLM | 低 |
| 封面模板切换 | 多套封面布局 | 低 |
| 正文编辑器 | 预览可编辑 | 低 |
