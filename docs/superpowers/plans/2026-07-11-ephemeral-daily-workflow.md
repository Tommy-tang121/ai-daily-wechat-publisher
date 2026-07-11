# Ephemeral Daily Workflow Implementation Plan

> For agentic workers: REQUIRED SUB-SKILL: Use executing-plans to implement this plan task-by-task. Steps use checkbox syntax.

**Goal:** Make every completed daily article temporary, allow manual re-generation for any date, and remove the existing WeChat legacy draft plus all local historical runs.

**Architecture:** SQLite remains only for active work and failed publishing retries. A successful WeChat draft creation returns a short response to the browser, then removes the article, event rows and runtime cover. A separate one-time CLI cleanup uses the same WeChat credentials as the current publisher to delete the existing draft before purging the final local receipt.

**Tech Stack:** Python 3.12, unittest, Flask, SQLite, Pillow, requests, existing baoyu-post-to-wechat publisher.

---

### Task 1: Replace completed-run retention with temporary-run storage

Files:
- Modify: app/src/ai_daily/storage.py
- Modify: app/src/ai_daily/daily_run.py
- Modify: app/tests/test_storage.py
- Modify: app/tests/test_workflow.py

- [ ] Step 1: Write failing storage tests

Add a test that creates a run with article and events, calls Store.discard(run.id), then verifies Store.get(run.id) raises KeyError and the run_events rows are gone.

Add a test for Store.claim_fresh(date): after a ready run exists for the date, claim_fresh returns a new owner with a different id and no article. Add a separate assertion that claim_fresh does not replace an active scraping run.

- [ ] Step 2: Run the new tests and verify RED

    py -m uv run --project app python -m unittest tests.test_storage -v

Expected: missing Store.discard and Store.claim_fresh methods.

- [ ] Step 3: Implement atomic Store methods

Add Store.discard(run_id), which starts an immediate transaction, reads and returns the run, deletes its run_events, then deletes the daily_runs row.

Add Store.claim_fresh(date), which starts an immediate transaction. If the same date has state queued, scraping, rewriting or publishing, return that existing run without ownership. Otherwise delete its event rows and run row, insert a new queued row and return it with owner=True.

Keep Store.claim and Store.retry unchanged for scheduler retry behavior.

- [ ] Step 4: Write failing daily-run cleanup tests

Add a test with an injected cleanup callback. After DailyRun.publish succeeds, assert:
- publisher is called once;
- cleanup receives the persisted cover path;
- runner.get(run.id) raises KeyError;
- the returned publish result has state published, media_id draft-1 and article None.

Keep the existing failed-publish test and assert its ready article remains present.

- [ ] Step 5: Implement successful-publish cleanup

Add cleanup=None to DailyRun.__init__. In DailyRun.publish, preserve the current failure behavior. On success:
1. mark the run published to get a valid receipt;
2. call cleanup with the article when supplied;
3. discard the persisted run;
4. return the completed Run with article=None.

Add fresh=False to DailyRun.start and DailyRun.prepare. When fresh=True, use Store.claim_fresh; web manual generation will use this flag while scheduler retries will not.

- [ ] Step 6: Run focused tests and commit

    py -m uv run --project app python -m unittest tests.test_storage tests.test_workflow -v
    git add app/src/ai_daily/storage.py app/src/ai_daily/daily_run.py app/tests/test_storage.py app/tests/test_workflow.py
    git commit -m "feat: clear completed daily runs"

Expected: all storage and workflow tests pass.

### Task 2: Safely remove generated cover files and return a cleared browser result

Files:
- Modify: app/src/ai_daily/runtime.py
- Modify: app/src/ai_daily/web.py
- Modify: app/static/app.js
- Modify: app/tests/test_runtime.py
- Modify: app/tests/test_web.py

- [ ] Step 1: Write failing runtime and browser tests

Add a runtime test that invokes the cleanup callback with a generated cover below app/static/covers and asserts the file is deleted. Add a second assertion that a path outside that folder is not deleted.

Add a web test whose fake publish result is published with article=None. Assert the publish response returns state published and no article.

Add browser-script assertions that a completed draft removes ai-daily-run-id and renders the explicit local-content-cleared status.

- [ ] Step 2: Run the tests and verify RED

    py -m uv run --project app python -m unittest tests.test_runtime tests.test_web -v

Expected: no cleanup callback and no browser handling for a cleared completed run.

- [ ] Step 3: Implement safe cleanup and browser reset

In runtime.py, pass a cleanup callback to DailyRun. Resolve article cover_path and unlink it only when it is a file below app/static/covers. Missing files are ignored. Never delete arbitrary paths.

In web.py, pass fresh=True in the manual POST /api/runs start call.

In app.js, when a publish response has state published and article is absent:
- clear state.run and state.runId;
- remove ai-daily-run-id;
- clear article and cover preview;
- restore the fetch button;
- show 微信草稿已创建，本地内容已清理;
- do not poll or restore the old run after refresh.

- [ ] Step 4: Run tests and commit

    py -m uv run --project app python -m unittest tests.test_runtime tests.test_web -v
    git add app/src/ai_daily/runtime.py app/src/ai_daily/web.py app/static/app.js app/tests/test_runtime.py app/tests/test_web.py
    git commit -m "feat: clear local content after draft creation"

Expected: all runtime and browser tests pass.

### Task 3: Add a tested WeChat draft deletion adapter and history cleanup command

Files:
- Modify: app/src/ai_daily/publishing.py
- Modify: app/src/ai_daily/cli.py
- Modify: app/src/ai_daily/daily_run.py
- Modify: app/tests/test_publishing.py
- Modify: app/tests/test_cli.py

- [ ] Step 1: Write failing publisher deletion tests

Add tests that patch requests.get and requests.post. With WECHAT_APP_ID and WECHAT_APP_SECRET present, WeChatPublisher.delete_draft(media_id) must:
- request a token from cgi-bin/token;
- send JSON containing only media_id to cgi-bin/draft/delete;
- return on errcode 0;
- raise RuntimeError for missing credentials, token errors or draft delete errors;
- never include either credential in the exception message.

- [ ] Step 2: Run and verify RED

    py -m uv run --project app python -m unittest tests.test_publishing -v

Expected: WeChatPublisher has no delete_draft method.

- [ ] Step 3: Implement the smallest official-API adapter

Add token and draft-delete URL constants to publishing.py. Implement WeChatPublisher.delete_draft using requests.get for the token and requests.post for deletion, both with timeout=(15, 30). Validate access_token and errcode; report only WeChat error text or code, never request URLs or credentials.

Add DailyRun.clear_history(delete_draft) that:
1. refuses when any run is active;
2. reads all saved runs;
3. deletes every WeChat draft receipt through delete_draft before any local row is removed;
4. invokes the runtime cover cleanup and Store.discard for every local run only after all external deletions succeed.

Add command cleanup-history to cli.py. It builds the formal runner, calls clear_history with the publisher delete_draft method, and prints only dates/counts, not media ids or credentials.

- [ ] Step 4: Write and run a failing cleanup-order test

Create a Store with one no-receipt run and one receipt run. Use a fake delete_draft that raises. Assert clear_history raises and no local row was removed. Then use a successful fake and assert all rows are removed.

    py -m uv run --project app python -m unittest tests.test_workflow tests.test_publishing tests.test_cli -v

Expected: cleanup ordering test fails before the clear_history implementation and passes afterward.

- [ ] Step 5: Commit

    git add app/src/ai_daily/publishing.py app/src/ai_daily/cli.py app/src/ai_daily/daily_run.py app/tests/test_publishing.py app/tests/test_cli.py app/tests/test_workflow.py
    git commit -m "feat: add ephemeral history cleanup"

### Task 4: Verify the complete lifecycle and apply the approved one-time cleanup

Files:
- Modify: docs/README.md
- Modify: docs/SPEC/2026-07-10-stability-refactor.md
- Test: app/tests/test_workflow.py

- [ ] Step 1: Add the full lifecycle regression test

Using a temporary database, fake source, fake LLM, temporary cover and fake publisher:
1. prepare an 11-item article and verify the article is available while ready;
2. publish it and verify the publisher receives it;
3. verify the run, events and cover are absent afterward;
4. verify claim_fresh for the same date starts a new owner.

- [ ] Step 2: Run the test and full suite

    py -m uv run --project app python -m unittest discover -s app/tests -v
    py -m uv run --project app python -m compileall -q app/src
    git diff --check

Expected: all tests pass with no compilation or whitespace errors.

- [ ] Step 3: Update operations documentation

Replace archival language in README and the stability specification with the temporary-retention rules. Document that failed draft creation is retained only for retry and that manual historical selection always starts a new generation.

- [ ] Step 4: Verify dry-run preconditions then perform the approved cleanup

Run a read-only count that must show 4 local runs and exactly 1 WeChat draft receipt. Then run:

    py -m uv run --project app ai-daily cleanup-history

Expected: the command deletes the single old WeChat draft first, then removes all four local runs and runtime covers. It must exit nonzero and leave local records intact if WeChat deletion fails.

- [ ] Step 5: Verify the applied cleanup and commit documentation

Run a read-only database check that returns zero daily_runs rows, then request the web home page and verify HTTP 200.

    git add docs/README.md docs/SPEC/2026-07-10-stability-refactor.md app/tests/test_workflow.py
    git commit -m "docs: document ephemeral daily workflow"

