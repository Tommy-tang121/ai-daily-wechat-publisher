# AI Daily Stability Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the local daily publisher into a recoverable, single-run-per-day workflow while placing every project artifact under `app`, `design`, or `docs`.

**Architecture:** Keep Flask/Jinja/vanilla JavaScript, but make the browser and Windows Task Scheduler callers of a single persisted `DailyRun` module. SQLite owns settings, state, artifacts and publishing receipts; content and WeChat are injected adapters behind small interfaces.

**Tech Stack:** Python 3.14, Flask + Waitress, SQLite WAL, uv, pytest, Bun/TypeScript, vendored `baoyu-post-to-wechat`.

---

## Target file map

```text
app/
  pyproject.toml, uv.lock, .python-version, .env.example
  src/ai_daily/{cli,storage,content,daily_run,publishing,scheduler,settings,logging}.py
  src/ai_daily/adapters/{aihot,llm,wechat,windows_tasks}.py
  src/ai_daily/web/{app.py,templates/index.html,static/*}
  src/ai_daily/assets/{fonts,prompts/rewrite.md}
  tests/test_{storage,content,daily_run,scheduler,web}.py
  vendor/{baoyu-post-to-wechat,baoyu-format-markdown}/
  scripts/{run_web.bat,run_scheduled.bat,setup_vendor.ps1}
  data/                              # ignored runtime database and logs
design/ui-components.html
docs/{PRD,SPEC,plans,README.md,THIRD_PARTY.md}
```

### Task 1: Reclassify files and document ownership

**Files:** move `skills/*` to `app/vendor/*`; move `run*.bat` to `app/scripts/*`; move `requirements.txt` into the new Python project; move the product document to `docs/PRD/`; modify `.gitignore`, `docs/README.md`; create `docs/THIRD_PARTY.md` and `app/.env.example`.

- [ ] Move only tracked project files. Do not move an ignored `.env`, generated covers, logs, or user databases.
- [ ] Write `docs/THIRD_PARTY.md` naming `JimLiu/baoyu-skills`, its pinned vendored version, use (`baoyu-post-to-wechat`), update rule (run Bun tests), and the local temporary-directory cleanup patch if one is needed.
- [ ] Make `.gitignore` exclude `app/.env`, `app/data/*.db`, `app/data/*.log`, virtual environments and `node_modules`; keep tracked reference covers unchanged.
- [ ] Run `git diff --check` and commit `refactor: organize project files`.

### Task 2: Establish a reproducible Python project and test harness

**Files:** create `app/pyproject.toml`, `app/.python-version`, `app/tests/conftest.py`; remove `requirements.txt`; modify batch scripts.

- [ ] Create `pyproject.toml` with `requires-python = ">=3.14,<3.15"`, runtime dependencies `flask`, `waitress`, `requests`, `pillow`, and test dependency `pytest`.
- [ ] Install with `uv lock` and `uv sync --locked`; the scripts must run `uv run ai-daily web` and `uv run ai-daily daily`, never bare `python`.
- [ ] First test must fail because the package is absent:

```python
def test_package_can_be_imported():
    import ai_daily
    assert ai_daily.__name__ == "ai_daily"
```

- [ ] Add the smallest package/entry-point implementation, re-run the single test, then `uv run pytest`.
- [ ] Commit `build: manage Python dependencies with uv`.

### Task 3: Persist settings and daily runs in SQLite

**Files:** create `app/src/ai_daily/storage.py`, `settings.py`, `tests/test_storage.py`; retire `app/config.py` after compatibility import has been replaced.

- [ ] Write the failing tests using a temporary database:

```python
def test_claim_returns_existing_published_run_without_new_publish(tmp_path):
    store = Store(tmp_path / "daily.db")
    first = store.claim("2026-07-10")
    store.mark_published(first.id, "media-1")
    assert store.claim("2026-07-10").id == first.id
    assert store.claim("2026-07-10").media_id == "media-1"

def test_second_claim_of_active_date_is_not_owner(tmp_path):
    store = Store(tmp_path / "daily.db")
    assert store.claim("2026-07-10").owner is True
    assert store.claim("2026-07-10").owner is False
```

- [ ] Implement schema initialization with WAL, a unique date, settings table, event table and transactional state updates. Store only JSON-safe article data and a redacted error summary.
- [ ] Test state transitions and invalid transition rejection, then run the full Python suite.
- [ ] Commit `feat: persist daily runs and settings`.

### Task 4: Build content safely and preserve attribution

**Files:** create `content.py`, `adapters/aihot.py`, `adapters/llm.py`, `assets/prompts/rewrite.md`, `tests/test_content.py`; retire `scraper.py`, `rewriter.py`, `markdown.py`, `pipeline.py` after their behavior is covered.

- [ ] Write failing tests with in-memory source and LLM adapters:

```python
def test_build_keeps_original_source_url_when_llm_returns_another_url():
    article = Content(FakeSource(), FakeLlm(link="https://wrong.example")).build("2026-07-10", settings)
    assert article.items[0].source_url == "https://origin.example/a"

def test_invalid_llm_json_raises_and_never_returns_source_excerpt():
    with pytest.raises(ContentError, match="格式"):
        Content(FakeSource(), InvalidLlm()).build("2026-07-10", settings)
```

- [ ] Put static instructions in the system prompt and serialized source records only in the user message. Require a complete result matching source-item count; discard LLM-provided links in favor of originals.
- [ ] Generate Markdown with a source link per item; never use a silent raw-text fallback.
- [ ] Commit `feat: make content generation attributable and fail closed`.

### Task 5: Make publishing idempotent and observable

**Files:** create `publishing.py`, `adapters/wechat.py`, `tests/test_daily_run.py`; move the existing publisher to the new adapter path; update the vendored publisher path and remove `--no-cite`.

- [ ] Write failing tests against a fake WeChat adapter:

```python
def test_publish_same_ready_run_twice_calls_wechat_once(tmp_path):
    runner, wechat = make_runner(tmp_path)
    runner.prepare("2026-07-10")
    assert runner.publish("2026-07-10").media_id == "draft-1"
    assert runner.publish("2026-07-10").media_id == "draft-1"
    assert wechat.calls == 1
```

- [ ] Implement `DailyRun.prepare`, `DailyRun.publish`, and `DailyRun.get` as the only workflow interface. Persist `ready` before calling WeChat; persist `published` only after a non-empty draft receipt.
- [ ] Validate that Bun exists before starting it, give it a bounded timeout, clean up the Markdown temp file, preserve citations, and return a typed failure on nonzero exit.
- [ ] Run `uv run pytest` and `bun test` in `app/vendor/baoyu-post-to-wechat/scripts`; commit `feat: prevent duplicate draft publishing`.

### Task 6: Replace unsafe Windows task management with one CLI entry point

**Files:** create `scheduler.py`, `adapters/windows_tasks.py`, `cli.py`, `tests/test_scheduler.py`; replace `run_daily.py`, `check_daily.py`, and old `scheduler.py`.

- [ ] Write failing pure-command tests:

```python
def test_daily_command_quotes_a_path_containing_spaces():
    command = build_task_command(Path(r"E:\App Development\AI Daily\app\scripts\run_scheduled.bat"))
    assert '"E:\\App Development\\AI Daily\\app\\scripts\\run_scheduled.bat"' in command

def test_add_minutes_wraps_midnight():
    assert add_minutes("23:58", 5) == "00:03"
```

- [ ] Implement task creation/update through checked subprocess results, a daily main task only, and inspectable task status. Delete the old check task only after the new task is successfully installed.
- [ ] Let Task Scheduler retry failures; `DailyRun` makes retries safe. Never auto-start an unknown old run from a checker.
- [ ] Commit `fix: make scheduled execution safe and inspectable`.

### Task 7: Reconnect the web UI to persisted runs

**Files:** create `web/app.py`; move templates/static under `web/`; modify `app.js`, `index.html`, `style.css`; create `tests/test_web.py`; remove old `main.py`.

- [ ] Write Flask test-client failures:

```python
def test_preview_is_loaded_from_run_id(client, ready_run):
    response = client.get(f"/api/runs/{ready_run.id}")
    assert response.get_json()["state"] == "ready"

def test_publish_endpoint_reports_ready_not_published_before_adapter_returns(client, ready_run):
    assert client.post(f"/api/runs/{ready_run.id}/publish").get_json()["state"] == "published"
```

- [ ] Replace global article/date variables and per-SSE-worker pipeline threads with a POST that returns `run_id`, polling/SSE that reads stored events, and a publish endpoint for the same run.
- [ ] Render untrusted article values with DOM nodes/`textContent`; remove unused Tailwind/daisyUI files and Google Fonts links; say “文章已生成，尚未发布” until a receipt exists.
- [ ] Serve with Waitress, run tests, then manually open the local page and verify one prepare → preview → publish flow using fake adapters.
- [ ] Commit `feat: make web progress truthful and persistent`.

### Task 8: Migrate legacy configuration, verify, and hand off

**Files:** create migration compatibility in `settings.py`; update `docs/README.md`, `docs/PRD/*`, `docs/SPEC/*`; remove superseded modules after imports are zero.

- [ ] On first database initialization, import only non-secret values from legacy `app/data/config.json`; prefer `app/.env`, then read the old root `.env` only for compatibility. Do not copy, log, or commit either secret file.
- [ ] Write an upgrade guide: install `uv`, run `app/scripts/setup_vendor.ps1`, move `.env` to `app/.env`, start `app/scripts/run_web.bat`, install the scheduled task from the UI/CLI, and manually update the WeChat IP whitelist each day.
- [ ] Run and record: `uv run pytest`, `bun test`, `bun install --frozen-lockfile`, `git diff --check`, `uv pip check`, and a syntax/import smoke test.
- [ ] Verify the tree has no root business files outside `app`, `design`, `docs`; commit `docs: document stable local operation`.

