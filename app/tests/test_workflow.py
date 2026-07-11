import sys
import json
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

    @staticmethod
    def valid_llm(messages):
        payload = json.loads(messages[1]["content"])
        if "sources" in payload:
            items = ",".join('{"title":"R","body":"rewritten"}' for _ in payload["sources"])
            return '{"items":[' + items + ']}'
        return '{"opening":"今日观察","closing":"小编短评"}'

    def test_content_keeps_source_url_and_rejects_bad_result(self):
        source = lambda date: [{"title": "T", "summary": "S", "source_url": "https://origin/a", "source": "A", "category": "news"}]
        def good(messages):
            payload = json.loads(messages[1]["content"])
            if "sources" in payload:
                return '{"items":[{"title":"R","body":"rewritten","link":"https://wrong"}]}'
            return '{"opening":"今日观察","closing":"小编短评"}'
        article = Content(source, good).build("2026-07-10", {"max_words": 150})
        self.assertEqual(article["items"][0]["source_url"], "https://origin/a")
        with self.assertRaises(ContentError):
            Content(source, lambda messages: "not json").build("2026-07-10", {})

    def test_content_accepts_legacy_rewritten_json_inside_a_code_block(self):
        source = lambda date: [{"title": "T", "summary": "S", "source_url": "https://origin/a", "source": "A", "category": "news"}]
        raw = '```json\n{"items":[{"title":"R","rewritten":"rewritten"}]}\n```'
        article = Content(source, lambda messages: raw if "sources" in json.loads(messages[1]["content"]) else '{"opening":"今日观察","closing":"小编短评"}').build("2026-07-10", {})
        self.assertEqual(article["items"][0]["body"], "rewritten")

    def test_content_rewrites_all_items_in_safe_batches(self):
        source = lambda date: [{"title": str(i), "summary": "S", "source_url": f"https://origin/{i}", "source": "A", "category": "news"} for i in range(25)]
        calls = []
        barrier = threading.Barrier(3)
        def llm(messages):
            payload = json.loads(messages[1]["content"])
            if "items" in payload:
                return '{"opening":"今日观察","closing":"小编短评"}'
            batch = payload["sources"]
            barrier.wait(timeout=1)
            calls.append(len(batch))
            return '{"items":[' + ','.join('{"title":"R","body":"rewritten"}' for _ in batch) + ']}'
        article = Content(source, llm).build("2026-07-10", {})
        self.assertEqual(len(article["items"]), 25)
        self.assertEqual(sorted(calls), [5, 10, 10])

    def test_content_adds_editorial_sections_after_all_batches_finish(self):
        source = lambda date: [
            {"title": str(index), "summary": "S", "source_url": f"https://origin/{index}", "source": "A", "category": "行业动态"}
            for index in range(11)
        ]

        def llm(messages):
            payload = json.loads(messages[1]["content"])
            if "sources" in payload:
                items = ",".join('{"title":"R","body":"正文"}' for _ in payload["sources"])
                return '{"items":[' + items + ']}'
            self.assertEqual(len(payload["items"]), 11)
            return '{"opening":"覆盖全天的观察","closing":"覆盖全天的短评"}'

        article = Content(source, llm).build("2026-07-10", {"batch_size": 10})

        self.assertEqual(len(article["items"]), 11)
        self.assertEqual(article["opening"], "覆盖全天的观察")
        self.assertEqual(article["closing"], "覆盖全天的短评")
        self.assertIn("**今日观察**", article["markdown"])
        self.assertIn("**小编短评**", article["markdown"])
        self.assertIn("数据来源：https://aihot.virxact.com/", article["markdown"])

    def test_content_reports_scraping_and_each_finished_rewrite_batch(self):
        source = lambda date: [{"title": str(i), "summary": "S", "source_url": f"https://origin/{i}", "source": "A", "category": "news"} for i in range(11)]
        llm = self.valid_llm
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
            payload = json.loads(messages[1]["content"])
            if "items" in payload:
                return '{"opening":"今日观察","closing":"小编短评"}'
            count = len(payload["sources"])
            return '{"items":[' + ','.join('{"title":"R","body":"rewritten"}' for _ in range(count)) + ']}'

        Content(source, llm).build("2026-07-09", {"batch_size": 10})
        self.assertLessEqual(highest, 3)

    def test_successful_publish_cleans_up_the_persisted_article(self):
        publisher_calls = []
        cleanup_calls = []
        source = lambda date: [{"title": "T", "summary": "S", "source_url": "https://origin/a", "source": "A", "category": "news"}]
        llm = self.valid_llm
        publish = lambda article: publisher_calls.append(article.copy()) or "draft-1"
        cleanup = lambda article: cleanup_calls.append(article.copy())
        cover = lambda article, settings: {"cover_path": "C:/covers/2026-07-10.png"}
        runner = DailyRun(Store(Path(self.tmp.name) / "daily.db"), Content(source, llm), publish, cover=cover, cleanup=cleanup)
        ready = runner.prepare("2026-07-10", {})

        published = runner.publish("2026-07-10")

        self.assertEqual(len(publisher_calls), 1)
        self.assertEqual(cleanup_calls, publisher_calls)
        self.assertEqual(cleanup_calls[0]["cover_path"], "C:/covers/2026-07-10.png")
        self.assertEqual(published.state, "published")
        self.assertEqual(published.media_id, "draft-1")
        self.assertIsNone(published.article)
        with self.assertRaises(KeyError):
            runner.get(ready.id)

    def test_publish_error_keeps_the_generated_article_ready_for_a_safe_retry(self):
        source = lambda date: [{"title": "T", "summary": "S", "source_url": "https://origin/a", "source": "A", "category": "news"}]
        llm = self.valid_llm
        runner = DailyRun(Store(Path(self.tmp.name) / "daily.db"), Content(source, llm), lambda article: (_ for _ in ()).throw(RuntimeError("publisher unavailable")))
        ready = runner.prepare("2026-07-10", {})

        with self.assertRaisesRegex(RuntimeError, "publisher unavailable"):
            runner.publish("2026-07-10")

        retriable = runner.get(ready.id)
        self.assertEqual(retriable.state, "ready")
        self.assertEqual(retriable.article["items"][0]["title"], "R")

    def test_publish_adds_a_date_title_to_a_legacy_ready_article(self):
        store = Store(Path(self.tmp.name) / "daily.db")
        run = store.claim("2026-07-10")
        store.transition(run.id, "scraping")
        store.transition(run.id, "rewriting")
        store.save_article(run.id, {"date": "2026-07-10", "markdown": "article", "items": []})
        captured = {}

        published = DailyRun(store, None, lambda article: captured.update(article) or "draft-1").publish("2026-07-10")

        self.assertEqual(published.media_id, "draft-1")
        self.assertEqual(captured.get("title"), "AI 行业热点新闻 | 2026-07-10")

    def test_get_reads_the_persisted_run(self):
        runner = DailyRun(Store(Path(self.tmp.name) / "daily.db"), None, None)
        run = runner.store.claim("2026-07-10")
        self.assertEqual(runner.get(run.id).date, "2026-07-10")

    def test_prepare_retries_an_explicitly_failed_date(self):
        store = Store(Path(self.tmp.name) / "daily.db")
        old = store.claim("2026-07-10")
        store.transition(old.id, "failed", "source error")
        source = lambda date: [{"title": "T", "summary": "S", "source_url": "https://origin/a", "source": "A", "category": "news"}]
        llm = self.valid_llm
        run = DailyRun(store, Content(source, llm), None).prepare("2026-07-10", {}, retry=True)
        self.assertEqual(run.state, "ready")

    def test_prepare_fresh_replaces_a_ready_run(self):
        store = Store(Path(self.tmp.name) / "daily.db")
        source = lambda date: [{"title": "T", "summary": "S", "source_url": "https://origin/a", "source": "A", "category": "news"}]
        runner = DailyRun(store, Content(source, self.valid_llm), None)
        old = runner.prepare("2026-07-10", {})

        fresh = runner.prepare("2026-07-10", {}, fresh=True)

        self.assertNotEqual(fresh.id, old.id)
        self.assertEqual(fresh.state, "ready")
        with self.assertRaises(KeyError):
            runner.get(old.id)

    def test_started_run_persists_progress_before_background_execution_finishes(self):
        store = Store(Path(self.tmp.name) / "daily.db")
        source = lambda date: [{"title": "T", "summary": "S", "source_url": "https://origin/a", "source": "A", "category": "news"}]
        llm = self.valid_llm
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
        llm = self.valid_llm
        cover = lambda article, settings: {"cover_path": "C:/covers/2026-07-10.png", "cover_url": "/static/covers/2026-07-10.png"}
        runner = DailyRun(store, Content(source, llm), None, cover=cover)
        ready = runner.prepare("2026-07-10", {"title": "Daily"})
        self.assertEqual(ready.article["cover_url"], "/static/covers/2026-07-10.png")
        self.assertEqual(runner.events(ready.id)[-2]["stage"], "cover")

    def test_ready_run_persists_the_title_for_the_publisher(self):
        source = lambda date: [{"title": "T", "summary": "S", "source_url": "https://origin/a", "source": "A", "category": "news"}]
        llm = self.valid_llm
        ready = DailyRun(Store(Path(self.tmp.name) / "daily.db"), Content(source, llm), None).prepare(
            "2026-07-10", {"title": "AI 行业热点新闻 | 2026-07-10"}
        )

        self.assertEqual(ready.article.get("title"), "AI 行业热点新闻 | 2026-07-10")

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
        llm = self.valid_llm

        run = DailyRun(store, Content(source, llm), None).prepare("2026-07-10", {}, retry=True)

        self.assertEqual(run.state, "ready")
