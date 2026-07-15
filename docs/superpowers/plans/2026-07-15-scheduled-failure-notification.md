# Scheduled Failure Notification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the formal daily task try at most twice, then show one safe Windows failure message when it cannot confirm a WeChat draft.

**Architecture:** The CLI owns the two end-to-end attempts. A normal preparation failure is retried once immediately. A `publication_uncertain` result never re-calls WeChat because the remote draft may already exist; it becomes an immediate notification instead. The task XML removes Task Scheduler's independent retries so it cannot exceed the CLI-owned limit.

**Tech Stack:** Python 3, unittest, Windows Task Scheduler XML, ctypes MessageBoxW.

---

### Task 1: Define and test the two-attempt scheduled workflow

**Files:**
- Modify: `app/tests/test_cli.py`
- Modify: `app/src/ai_daily/cli.py`

- [ ] **Step 1: Write failing tests for three terminal outcomes**

Add a fake runner whose first `prepare` raises `RuntimeError("LLM connection failed")` and whose second returns a `ready` run. Assert two preparation calls, one publish call, and no notification. Add a fake runner that raises the same error twice; assert `ScheduledDailyFailedError` and one `show_scheduled_failure` call containing the safe reason. Add a runner returning `publication_uncertain`; assert no publisher call and one notification instructing the user to check the draft box.

- [ ] **Step 2: Run the new tests red**

Run:

```powershell
& app\.venv\Scripts\python.exe -m unittest app.tests.test_cli.CliTests -v
```

Expected: FAIL because generic two-attempt handling and `ScheduledDailyFailedError` do not yet exist.

- [ ] **Step 3: Implement the minimal CLI boundary**

In `cli.py`, add `ScheduledDailyFailedError`, a `safe_failure_reason(error)` helper, and a `run_scheduled_daily(runner, run_date, settings, preview)` helper. The reason helper collapses whitespace, masks the values of `LLM_API_KEY`, `WECHAT_APP_ID`, and `WECHAT_APP_SECRET` when present, and limits the visible text to 300 characters.

The helper must:
1. Call `runner.prepare(..., retry=True)` at most twice for ordinary pre-publication errors.
2. Call `runner.publish` only for `ready` or `finalizing` runs.
3. Return normally only for `published` or `finalizing`.
4. Stop after `ContentRetryExhaustedError`, because it already used two same-input AI responses.
5. Stop after `publication_uncertain` with the fixed reason `微信发布结果待确认，请检查草稿箱`; do not call WeChat again.
6. Raise `ScheduledDailyFailedError` after the final failure.

Replace the current format-only catch in `main()`. On `ScheduledDailyFailedError`, formal mode calls `show_scheduled_failure(str(error))` once and re-raises so the task result is visible as failed. Preview mode never opens a dialog.

- [ ] **Step 4: Run the focused tests green**

Run:

```powershell
& app\.venv\Scripts\python.exe -m unittest app.tests.test_cli.CliTests -v
```

Expected: PASS for the original CLI checks and the three new boundary tests.

- [ ] **Step 5: Commit**

```powershell
git add app/src/ai_daily/cli.py app/tests/test_cli.py
git commit -m "fix: notify after scheduled daily retries"
```

### Task 2: Remove Task Scheduler's independent retries

**Files:**
- Modify: `app/tests/test_scheduler.py`
- Modify: `app/src/ai_daily/scheduler.py`

- [ ] **Step 1: Write the failing XML assertion**

Replace the existing `RestartOnFailure` interval/count assertions with:

```python
self.assertIsNone(document.find(".//task:RestartOnFailure", namespaces=namespace))
```

- [ ] **Step 2: Run it red**

Run:

```powershell
& app\.venv\Scripts\python.exe -m unittest app.tests.test_scheduler.SchedulerTests.test_task_xml_retries_failures_and_runs_the_quoted_daily_script -v
```

Expected: FAIL because the XML still adds `RestartOnFailure`.

- [ ] **Step 3: Implement only the policy deletion**

Delete the three-line `RestartOnFailure` block from `task_xml`. Keep the 10:00 schedule, `InteractiveToken`, the batch command, and legacy Hook deletion unchanged.

- [ ] **Step 4: Run it green and commit**

Run:

```powershell
& app\.venv\Scripts\python.exe -m unittest app.tests.test_scheduler.SchedulerTests.test_task_xml_retries_failures_and_runs_the_quoted_daily_script -v
git add app/src/ai_daily/scheduler.py app/tests/test_scheduler.py
git commit -m "fix: keep scheduled daily retries bounded"
```

Expected: PASS; XML has no `RestartOnFailure`.

### Task 3: Verify, install, and exercise the real task

**Files:**
- Verify only: `app/tests/`
- Verify only: installed `\AI Daily Publisher` task

- [ ] **Step 1: Run all checks**

```powershell
& app\.venv\Scripts\python.exe -m unittest discover -s app\tests -q
& app\.venv\Scripts\python.exe -m compileall -q app\src
git diff --check
```

Expected: all tests pass, compilation succeeds, and no whitespace errors.

- [ ] **Step 2: Replace the installed task at its existing 10:00 time**

Use `WindowsTasks(...).install("10:00")`. Query its XML afterward and confirm the batch path and `InteractiveToken` remain present while `RestartOnFailure` is absent.

- [ ] **Step 3: Trigger once and monitor**

```powershell
schtasks /Run /TN "\AI Daily Publisher"
```

Poll the task without triggering again. Success is `published` or `finalizing`. If it finally fails, inspect only local run state, stages, and the safe error string; never print article content, keys, tokens, or draft IDs.

- [ ] **Step 4: Verify the final worktree state**

```powershell
git status --short
git log --oneline -3
```

Expected: implementation commits are present; only the user's existing config and cover-image files remain unstaged.
