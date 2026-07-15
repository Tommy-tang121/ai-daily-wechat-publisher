# Original Request Compatibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Restore the original working prompt envelope and remove redundant link/source output without weakening full-daily validation.

**Architecture:** Content keeps locally captured source URLs, source names, and categories. The LLM receives title, summary, and source in the system prompt, then returns only editorial fields. The parser remains strict: only a complete article with all items, today observation, and editor comment can proceed.

**Tech Stack:** Python 3, unittest, OpenAI-compatible chat API.

---

### Task 1: Lock the original message shape with failing tests

**Files:**
- Modify: app/tests/test_workflow.py
- Modify: app/src/ai_daily/content.py

- [ ] **Step 1: Write a failing message-capture test**

Create one source item with source_url set to https://origin/secret-link and an LLM stub that captures messages then returns complete lean JSON:

```python
article = Content(source, llm).build("2026-07-15", {})
self.assertIn("### 条目 1", captured[0]["content"])
self.assertEqual(captured[1]["content"], "请根据以上要求处理今日的 1 条 AI 新闻。")
self.assertNotIn("https://origin/secret-link", captured[0]["content"])
self.assertEqual(article["items"][0]["source_url"], "https://origin/secret-link")
```

- [ ] **Step 2: Run it red**

```powershell
& app\.venv\Scripts\python.exe -m unittest discover -s app\tests -p test_workflow.py -v
```

Expected: the test fails because the current implementation puts the data in the user message and includes the URL.

- [ ] **Step 3: Implement the minimal message change**

Change _daily_input so it emits only date, item number, title, summary, and source. In _rewrite_once, replace the DAILY_DATA marker with _daily_input(date, items), make that completed prompt the system message, and use exactly this user content:

```python
f"请根据以上要求处理今日的 {len(items)} 条 AI 新闻。"
```

Do not change origin mapping after the LLM response; source_url, source, and category remain local.

- [ ] **Step 4: Run the workflow tests green**

```powershell
& app\.venv\Scripts\python.exe -m unittest discover -s app\tests -p test_workflow.py -q
```

Expected: all workflow tests pass and the new test proves URLs stay local.

### Task 2: Remove redundant response fields from the prompt

**Files:**
- Modify: app/prompts/rewrite.md
- Test: app/tests/test_workflow.py

- [ ] **Step 1: Write a failing prompt-contract assertion**

Read the prompt text in a test and assert that the example item contains title and rewritten but does not contain link or source output fields.

- [ ] **Step 2: Run it red**

```powershell
& app\.venv\Scripts\python.exe -m unittest discover -s app\tests -p test_workflow.py -v
```

Expected: the assertion fails because the current JSON example and important rule still require link and source.

- [ ] **Step 3: Make the prompt lean**

Change only the output JSON example and important rule so an item requires title and rewritten. Keep the count-equals-input rule, today observation rule, editor comment rule, word cap, and factual-writing rules.

- [ ] **Step 4: Run the workflow tests green**

```powershell
& app\.venv\Scripts\python.exe -m unittest discover -s app\tests -p test_workflow.py -q
```

Expected: lean JSON is accepted and all existing source attribution tests stay green.

### Task 3: Verify and exercise the unchanged publishing workflow

**Files:**
- Verify only: app/tests
- Verify only: app/src/ai_daily/runtime.py and installed AI Daily Publisher task

- [ ] **Step 1: Run all checks**

```powershell
& app\.venv\Scripts\python.exe -m unittest discover -s app\tests -q
& app\.venv\Scripts\python.exe -m compileall -q app\src
git diff --check
```

Expected: full suite, compilation, and whitespace check pass.

- [ ] **Step 2: Run a no-publish full-day preflight**

Build the current date through a preview-only runner. Report only item count, article-section presence, and validation result; never print article text, keys, model raw response, or WeChat data.

- [ ] **Step 3: Trigger and monitor the installed task**

Run schtasks /Run for AI Daily Publisher once. On success confirm a published/finalizing state. On failure report the safe reason and start root-cause diagnosis without re-triggering.

- [ ] **Step 4: Commit and merge**

```powershell
git add app/src/ai_daily/content.py app/prompts/rewrite.md app/tests/test_workflow.py
git commit -m "fix: restore lean original daily prompt"
```

Fast-forward merge only after the test suite passes; preserve existing user config and cover files.
