# Title Date Consistency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure a daily article title and its cover always use the same selected daily date.

**Architecture:** `DailyRun` owns title normalization and final title construction because it owns the article date. The runtime cover factory consumes that final article title. This keeps the database setting as a date-free base title and prevents a historic date from entering a new article.

**Tech Stack:** Python 3.14, unittest, SQLite settings store.

---

### Task 1: Add a failing regression test

**Files:**

- Modify: `app/tests/test_workflow.py`
- Modify: `app/tests/test_runtime.py`

- [ ] **Step 1: Add the workflow test to `WorkflowTests`**

```python
def test_daily_title_strips_stale_setting_date_and_uses_run_date(self):
    store = Store(Path(self.tmp.name) / "daily.db")
    source = lambda date: [{"title": "T", "summary": "S", "source_url": "https://origin/a", "source": "A", "category": "news"}]
    runner = DailyRun(store, Content(source, self.valid_llm), None, settings={"title": "AI 行业热点新闻"})
    runner.update_settings({"title": "AI 行业热点新闻 | 2026-07-13"})

    ready = runner.prepare("2026-07-16", runner.settings())

    self.assertEqual(runner.settings()["title"], "AI 行业热点新闻")
    self.assertEqual(ready.article["title"], "AI 行业热点新闻 | 2026-07-16")
```

- [ ] **Step 2: Add the cover factory test to `RuntimeTests`**

```python
def test_runtime_cover_factory_uses_final_article_title(self):
    with tempfile.TemporaryDirectory() as directory:
        app_dir = Path(directory) / "app"
        app_dir.mkdir()
        with patch("ai_daily.runtime.generate_cover", return_value=app_dir / "static" / "runtime-covers" / "2026-07-16.png") as generate:
            build_runner(app_dir, preview_only=True).cover(
                {"date": "2026-07-16", "title": "AI 行业热点新闻 | 2026-07-16"},
                {"title": "AI 行业热点新闻 | 2026-07-13"},
            )

    self.assertEqual(generate.call_args.args[2], "AI 行业热点新闻 | 2026-07-16")
```

- [ ] **Step 3: Run both tests and confirm RED**

Run: `python -m unittest tests.test_workflow.WorkflowTests.test_daily_title_strips_stale_setting_date_and_uses_run_date tests.test_runtime.RuntimeTests.test_runtime_cover_factory_uses_final_article_title -q`

Expected: both tests fail because the old setting date is retained and the old cover factory reads the setting title.

### Task 2: Normalize the title at the workflow boundary

**Files:**

- Modify: `app/src/ai_daily/daily_run.py`
- Test: `app/tests/test_workflow.py`

- [ ] **Step 1: Add date stripping and final title helpers**

```python
def base_title(title: str) -> str:
    return re.sub(r"\\s*\\|\\s*\\d{4}-\\d{2}-\\d{2}\\s*$", "", title).strip()

def daily_title(title: str, run_date: str) -> str:
    return f"{base_title(title) or 'AI 行业热点新闻'} | {run_date}"
```

- [ ] **Step 2: Normalize stored settings before returning them and before saving updates**

```python
def settings(self) -> dict:
    values = self.store.settings(self.default_settings)
    title = base_title(values.get("title", ""))
    if title != values.get("title", ""):
        self.store.update_settings({"title": title})
        values["title"] = title
    return values

def update_settings(self, values: dict) -> dict:
    values = {**values}
    if "title" in values:
        values["title"] = base_title(values["title"])
    self.store.update_settings(values)
    return self.settings()
```

- [ ] **Step 3: Replace article title assignment with the final title helper**

```python
article["title"] = daily_title(settings.get("title", ""), date)
```

- [ ] **Step 4: Run the workflow test and confirm GREEN**

Run: `python -m unittest tests.test_workflow.WorkflowTests.test_daily_title_strips_stale_setting_date_and_uses_run_date -q`

Expected: PASS.

### Task 3: Give the cover factory the final title

**Files:**

- Modify: `app/src/ai_daily/runtime.py`
- Test: `app/tests/test_runtime.py`

- [ ] **Step 1: Select the article title before the settings fallback**

```python
title = article.get("title") or values.get("title", settings["title"])
path = generate_cover(
    app_dir / "static" / "runtime-covers",
    article["date"],
    title,
    values.get("author", settings["author"]),
)
```

- [ ] **Step 2: Run the runtime test and confirm GREEN**

Run: `python -m unittest tests.test_runtime.RuntimeTests.test_runtime_cover_factory_uses_final_article_title -q`

Expected: PASS.

### Task 4: Verify and correct the current draft

**Files:**

- No repository file changes.

- [ ] **Step 1: Run the complete test suite**

Run: `python -m unittest discover -s tests -q`

Expected: all tests pass.

- [ ] **Step 2: Restart the local web process and verify the local page responds**

Run: `启动 AI Daily.bat`

Expected: `http://127.0.0.1:5000/` responds with HTTP 200.

- [ ] **Step 3: Delete only the current incorrect WeChat draft, generate 2026-07-16 again, and publish once**

Expected: the new WeChat draft title and cover both show 2026-07-16.

- [ ] **Step 4: Commit the source, tests, and docs**

```bash
git add app/src/ai_daily/daily_run.py app/src/ai_daily/runtime.py app/tests/test_workflow.py app/tests/test_runtime.py docs/superpowers/specs/2026-07-16-title-date-consistency-design.md docs/superpowers/plans/2026-07-16-title-date-consistency.md
git commit -m "fix: keep daily title and cover date aligned"
```
