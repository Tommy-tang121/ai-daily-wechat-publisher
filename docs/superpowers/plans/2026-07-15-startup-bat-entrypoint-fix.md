# Startup BAT Entrypoint Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复双击根目录启动 BAT 后网页服务不启动的问题。

**Architecture:** 根目录 BAT 保持现有的“检测 5000 端口、必要时后台启动、成功后打开浏览器”流程。只将 Python 的模块入口从不可运行的包替换为已存在的 `ai_daily.cli` 命令行模块。

**Tech Stack:** Windows Batch、Python unittest、Python module execution。

---

### Task 1: 用回归测试锁定启动入口

**Files:**
- Modify: `app/tests/test_runtime.py`
- Modify: `启动 AI Daily.bat`

- [ ] **Step 1: 编写会失败的测试**

在 `RuntimeTests` 中加入：

```python
def test_root_launch_script_uses_the_cli_module_entrypoint(self):
    script = (Path(__file__).parents[2] / "启动 AI Daily.bat").read_text(encoding="utf-8")

    self.assertIn('"%PYTHON%" -m ai_daily.cli web', script)
```

- [ ] **Step 2: 运行测试，确认当前实现失败**

Run: `app\.venv\Scripts\python.exe -m unittest app/tests/test_runtime.py -q`

Expected: 新增测试失败，因为脚本当前包含 `-m ai_daily web`，没有 `-m ai_daily.cli web`。

- [ ] **Step 3: 实施最小修复**

将 `启动 AI Daily.bat` 中的启动行替换为：

```bat
start "AI Daily Server" /min "%PYTHON%" -m ai_daily.cli web
```

不改变端口检查、等待、浏览器打开或任何其他 BAT 行。

- [ ] **Step 4: 运行测试，确认通过**

Run: `app\.venv\Scripts\python.exe -m unittest app/tests/test_runtime.py -q`

Expected: PASS。

- [ ] **Step 5: 验证完整测试和实际 BAT 启动**

Run: `app\.venv\Scripts\python.exe -m unittest discover -s app\tests -q`

Expected: 全部通过。

随后执行根目录 `启动 AI Daily.bat`，并访问 `http://127.0.0.1:5000/`。

Expected: BAT 退出成功，本地网页返回 HTTP 200；若服务器已在运行，则只打开网页而不重复启动。

- [ ] **Step 6: 提交最小改动**

Run:

```powershell
git add -- "启动 AI Daily.bat" "app/tests/test_runtime.py"
git commit -m "fix: start web server from launch BAT"
```

Expected: 仅提交 BAT 和测试；不提交 `.env`、配置或封面文件。
