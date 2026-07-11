import sys
import tempfile
import threading
import time
import unittest
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from ai_daily.content import Content, ContentError
from ai_daily.daily_run import DailyRun
from ai_daily.storage import Store


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_content_keeps_source_url_and_rejects_bad_result(self):
        source = lambda date: [{"title": "T", "summary": "S", "source_url": "https://origin/a", "source": "A", "category": "news"}]
        good = lambda messages: '{"items":[{"title":"R","body":"rewritten","link":"https://wrong"}]}'
        article = Content(source, good).build("2026-07-10", {"max_words": 150})
        self.assertEqual(article["items"][0]["source_url"], "https://origin/a")
        with self.assertRaises(ContentError):
            Content(source, lambda messages: "not json").build("2026-07-10", {})

    def test_content_accepts_legacy_rewritten_json_inside_a_code_block(self):
        source = lambda date: [{"title": "T", "summary": "S", "source_url": "https://origin/a", "source": "A", "category": "news"}]
        raw = '```json\n{"items":[{"title":"R","rewritten":"rewritten"}]}\n```'
        article = Content(source, lambda messages: raw).build("2026-07-10", {})
        self.assertEqual(article["items"][0]["body"], "rewritten")

    def test_content_rewrites_all_items_in_safe_batches(self):
        source = lambda date: [{"title": str(i), "summary": "S", "source_url": f"https://origin/{i}", "source": "A", "category": "news"} for i in range(25)]
        calls = []
        barrier = threading.Barrier(3)
        def llm(messages):
            batch = __import__("json").loads(messages[1]["content"])["sources"]
            barrier.wait(timeout=1)
            calls.append(len(batch))
            return '{"items":[' + ','.join('{"title":"R","body":"rewritten"}' for _ in batch) + ']}'
        article = Content(source, llm).build("2026-07-10", {})
        self.assertEqual(len(article["items"]), 25)
        self.assertEqual(sorted(calls), [5, 10, 10])

    def test_content_reports_scraping_and_each_finished_rewrite_batch(self):
        source = lambda date: [{"title": str(i), "summary": "S", "source_url": f"https://origin/{i}", "source": "A", "category": "news"} for i in range(11)]
        llm = lambda messages: '{"items":[' + ','.join('{"title":"R","body":"rewritten"}' for _ in __import__("json").loads(messages[1]["content"])["sources"]) + ']}'
        progress = []
        Content(source, llm).build("2026-07-10", {"batch_size": 10}, progress=lambda *event: progress.append(event))
        self.assertEqual(progress[0][:2], ("scraping", "progress"))
        self.assertEqual(progress[1][:2], ("scraping", "complete"))
        self.assertEqual(sum(stage == "rewriting" and status == "progress" for stage, status, _ in progress), 2)

    def test_content_never_opens_more_than_three_llm_requests_at_once(self):
        source = lambda date: [{"title": str(i), "summary": "S", "source_url": f"https://origin/{i}", "source": "A", "category": "news"} for i in range(31)]
        active = 0
        highest = 0
        lock = threading.Lock()

        def llm(messages):
            nonlocal active, highest
            with lock:
                active += 1
                highest = max(highest, active)
            time.sleep(0.05)
            with lock:
                active -= 1
            count = len(__import__("json").loads(messages[1]["content"])["sources"])
            return '{"items":[' + ','.join('{"title":"R","body":"rewritten"}' for _ in range(count)) + ']}'

        Content(source, llm).build("2026-07-09", {"batch_size": 10})
        self.assertLessEqual(highest, 3)

    def test_publish_same_ready_run_calls_adapter_once(self):
        calls = []
        source = lambda date: [{"title": "T", "summary": "S", "source_url": "https://origin/a", "source": "A", "category": "news"}]
        llm = lambda messages: '{"items":[{"title":"R","body":"rewritten"}]}'
        publish = lambda article: calls.append(article) or "draft-1"
        runner = DailyRun(Store(Path(self.tmp.name) / "daily.db"), Content(source, llm), publish)
        runner.prepare("2026-07-10", {})
        self.assertEqual(runner.publish("2026-07-10").media_id, "draft-1")
        self.assertEqual(runner.publish("2026-07-10").media_id, "draft-1")
        self.assertEqual(len(calls), 1)

    def test_get_reads_the_persisted_run(self):
        runner = DailyRun(Store(Path(self.tmp.name) / "daily.db"), None, None)
        run = runner.store.claim("2026-07-10")
        self.assertEqual(runner.get(run.id).date, "2026-07-10")

    def test_prepare_retries_an_explicitly_failed_date(self):
        store = Store(Path(self.tmp.name) / "daily.db")
        old = store.claim("2026-07-10")
        store.transition(old.id, "failed", "source error")
        source = lambda date: [{"title": "T", "summary": "S", "source_url": "https://origin/a", "source": "A", "category": "news"}]
        llm = lambda messages: '{"items":[{"title":"R","body":"rewritten"}]}'
        run = DailyRun(store, Content(source, llm), None).prepare("2026-07-10", {}, retry=True)
        self.assertEqual(run.state, "ready")

    def test_started_run_persists_progress_before_background_execution_finishes(self):
        store = Store(Path(self.tmp.name) / "daily.db")
        source = lambda date: [{"title": "T", "summary": "S", "source_url": "https://origin/a", "source": "A", "category": "news"}]
        llm = lambda messages: '{"items":[{"title":"R","body":"rewritten"}]}'
        runner = DailyRun(store, Content(source, llm), None)
        started = runner.start("2026-07-10", {})
        self.assertTrue(started.owner)
        self.assertEqual(started.state, "scraping")
        finished = runner.execute(started.id, "2026-07-10", {})
        self.assertEqual(finished.state, "ready")
        self.assertEqual(runner.events(started.id)[-1]["stage"], "done")

    def test_ready_run_keeps_the_generated_cover_for_preview_and_publishing(self):
        store = Store(Path(self.tmp.name) / "daily.db")
        source = lambda date: [{"title": "T", "summary": "S", "source_url": "https://origin/a", "source": "A", "category": "news"}]
        llm = lambda messages: '{"items":[{"title":"R","body":"rewritten"}]}'
        cover = lambda article, settings: {"cover_path": "C:/covers/2026-07-10.png", "cover_url": "/static/covers/2026-07-10.png"}
        runner = DailyRun(store, Content(source, llm), None, cover=cover)
        ready = runner.prepare("2026-07-10", {"title": "Daily"})
        self.assertEqual(ready.article["cover_url"], "/static/covers/2026-07-10.png")
        self.assertEqual(runner.events(ready.id)[-2]["stage"], "cover")

    def test_runner_exposes_persisted_settings_to_web_and_scheduled_callers(self):
        store = Store(Path(self.tmp.name) / "daily.db")
        runner = DailyRun(store, None, None, settings={"max_words": 150})
        runner.update_settings({"max_words": 200})
        self.assertEqual(runner.settings()["max_words"], 200)

    def test_retry_reclaims_only_a_stale_active_run(self):
        store = Store(Path(self.tmp.name) / "daily.db")
        old = store.claim("2026-07-10")
        store.transition(old.id, "scraping")
        with closing(store._connect()) as db, db:
            db.execute("UPDATE daily_runs SET updated_at=datetime('now', '-31 minutes') WHERE id=?", (old.id,))
        source = lambda date: [{"title": "T", "summary": "S", "source_url": "https://origin/a", "source": "A", "category": "news"}]
        llm = lambda messages: '{"items":[{"title":"R","body":"rewritten"}]}'

        run = DailyRun(store, Content(source, llm), None).prepare("2026-07-10", {}, retry=True)

        self.assertEqual(run.state, "ready")
