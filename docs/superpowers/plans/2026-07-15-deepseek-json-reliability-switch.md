# DeepSeek JSON Reliability Switch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将日报改写服务从 Agnes 切换为 DeepSeek，并在请求层强制关闭思考模式、启用 JSON 输出，保留现有“整天一次生成、失败仅重试一次、内容不完整绝不发布”的核心流程。

**Architecture:** 继续复用现有 OpenAI 兼容适配器。适配器仅在目标地址是 DeepSeek 时附加 DeepSeek 专用请求字段；内容抓取、严格校验、重试、微信草稿发布和 Windows 定时任务均不改动。密钥只写入本机被 Git 忽略的 `.env`。

**Tech Stack:** Python、requests、unittest、DeepSeek OpenAI-compatible Chat Completions API。

---

### Task 1: 用测试锁定 DeepSeek 的请求契约

**Files:**
- Modify: `app/tests/test_runtime.py`

- [ ] **Step 1: 编写会失败的测试**

在 `OpenAiCompatibleLlm` 的测试中模拟一次 DeepSeek 调用，断言请求 JSON 包含：

```python
"thinking": {"type": "disabled"},
"response_format": {"type": "json_object"},
```

同时断言仍保留既有的 `model`、`messages` 和 `max_tokens` 字段。

- [ ] **Step 2: 运行测试，确认当前实现失败**

Run: `app\.venv\Scripts\python.exe -m unittest app/tests/test_runtime.py -q`

Expected: 新增断言失败，因为当前请求尚未携带 DeepSeek 的两个字段。

- [ ] **Step 3: 实现最小改动**

在 `app/src/ai_daily/runtime.py` 组装请求体的位置，仅当 `LLM_BASE_URL` 指向 `https://api.deepseek.com` 时加入上述两个字段。不要改变 Agnes 或其他 OpenAI 兼容服务的请求体。

- [ ] **Step 4: 再次运行测试，确认通过**

Run: `app\.venv\Scripts\python.exe -m unittest app/tests/test_runtime.py -q`

Expected: PASS。

### Task 2: 切换本机运行配置，不让密钥进入版本库

**Files:**
- Modify locally only: `.env` (Git ignored; 不提交)

- [ ] **Step 1: 更新本机 `.env`**

设置以下运行参数：

```text
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-v4-flash
LLM_API_KEY=<用户提供的 DeepSeek 密钥>
```

密钥不能出现在源码、测试、文档、命令输出或 Git 暂存区。

- [ ] **Step 2: 验证忽略规则**

Run: `git check-ignore -q .env`

Expected: 返回成功，证明 `.env` 不会被 Git 跟踪。

- [ ] **Step 3: 验证配置已被加载但不打印密钥**

用 Python 仅输出 `LLM_BASE_URL`、`LLM_MODEL` 和“密钥是否存在”的布尔值。

Expected: 地址为 `https://api.deepseek.com`、模型为 `deepseek-v4-flash`、密钥存在为 `True`。

### Task 3: 完整回归并验证“失败不发布”的边界未被破坏

**Files:**
- Verify: `app/tests/`
- Verify: `app/src/ai_daily/content.py`
- Verify: `app/src/ai_daily/runtime.py`

- [ ] **Step 1: 运行完整测试集**

Run: `app\.venv\Scripts\python.exe -m unittest discover -s app\tests -q`

Expected: 全部通过。

- [ ] **Step 2: 运行静态编译检查**

Run: `app\.venv\Scripts\python.exe -m compileall -q app\src`

Expected: 无错误。

- [ ] **Step 3: 检查改动范围和密钥泄漏**

Run: `git diff --check`，再检查待提交文件中不存在 `.env` 或 `LLM_API_KEY` 的实际值。

Expected: 只有运行时适配器和对应测试会进入提交；没有密钥。

### Task 4: 真实预检与定时任务交付

**Files:**
- Verify: Windows task `\AI Daily Publisher`

- [ ] **Step 1: 做一次不发布的完整日报预检**

运行现有生成链路到严格校验完成为止，不调用微信草稿发布。仅记录抓取条数、返回条数、缺失编号（若有）、耗时和错误类型；不记录正文或密钥。

Expected: 成功时得到完整日报；失败时明确停在校验前，不产生半成品草稿。

- [ ] **Step 2: 确认 Windows 定时任务仍保留既有重试与失败提示逻辑**

检查任务脚本和任务状态，不新建额外轮询或重复任务。

Expected: 仍是“首次 + 自动重试一次”；两次失败后弹出失败原因，成功才推送草稿箱。

- [ ] **Step 3: 提交可公开的代码改动**

Run: `git add app/src/ai_daily/runtime.py app/tests/test_runtime.py && git commit -m "fix: use DeepSeek JSON mode for daily rewrite"`

Expected: 仅提交代码和测试；`.env` 与用户已有未跟踪封面文件不进入提交。
