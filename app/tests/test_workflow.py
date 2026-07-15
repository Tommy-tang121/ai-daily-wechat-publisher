import sys
import json
import tempfile
import threading
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from ai_daily.content import Content, ContentError
from ai_daily.daily_run import DailyRun
from ai_daily.storage import InvalidTransition, Store


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    @staticmethod
    def valid_llm(messages):
        count = messages[1]["content"].count("### 条目 ")
        return json.dumps({
            "todayObservation": "今日观察",
            "items": [
                {"title": "R", "rewritten": "rewritten"}
                for _ in range(count)
            ],
            "editorComment": "小编短评",
        })

    def test_content_keeps_source_url_and_rejects_bad_result(self):
        source = lambda date: [{"title": "T", "summary": "S", "source_url": "https://origin/a", "source": "A", "category": "news"}]
        def good(messages):
            return '{"todayObservation":"今日观察","items":[{"title":"R","rewritten":"rewritten","link":"https://wrong"}],"editorComment":"小编短评"}'
        article = Content(source, good).build("2026-07-10", {"max_words": 150})
        self.assertEqual(article["items"][0]["source_url"], "https://origin/a")
        with self.assertRaises(ContentError):
            Content(source, lambda messages: "not json").build("2026-07-10", {})

    def test_content_accepts_legacy_rewritten_json_inside_a_code_block(self):
        source = lambda date: [{"title": "T", "summary": "S", "source_url": "https://origin/a", "source": "A", "category": "news"}]
        raw = '```json\n{"todayObservation":"今日观察","items":[{"title":"R","rewritten":"rewritten"}],"editorComment":"小编短评"}\n```'
        article = Content(source, lambda messages: raw).build("2026-07-10", {})
        self.assertEqual(article["items"][0]["body"], "rewritten")

    def test_content_rewrites_a_25_item_daily_in_one_complete_llm_call(self):
        source = lambda date: [
            {
                "title": f"Source {index}",
                "summary": f"Summary {index}",
                "source_url": f"https://origin/{index}",
                "source": "A",
                "category": "news",
            }
            for index in range(25)
        ]
        calls = []

        def llm(messages):
            calls.append(messages)
            try:
                # Supports the old implementation just long enough for this test to prove it is wrong.
                payload = json.loads(messages[1]["content"])
            except json.JSONDecodeError:
                return json.dumps({
                    "todayObservation": "覆盖全天的观察",
                    "items": [
                        {"title": f"Edited {index}", "rewritten": f"Rewritten {index}"}
                        for index in range(25)
                    ],
                    "editorComment": "覆盖全天的短评",
                })
            if "sources" in payload:
                return json.dumps({
                    "items": [
                        {"title": item["title"], "body": "Rewritten"}
                        for item in payload["sources"]
                    ]
                })
            return '{"opening":"覆盖全天的观察","closing":"覆盖全天的短评"}'

        article = Content(source, llm).build("2026-07-10", {"max_words": 150})

        self.assertEqual(len(calls), 1)
        self.assertEqual(len(article["items"]), 25)
        self.assertEqual(article["opening"], "覆盖全天的观察")
        self.assertEqual(article["closing"], "覆盖全天的短评")
        self.assertEqual(article["items"][24]["source_url"], "https://origin/24")

    def test_content_rejects_a_partial_single_response(self):
        source = lambda date: [
            {"title": str(index), "summary": "S", "source_url": f"https://origin/{index}", "source": "A", "category": "news"}
            for index in range(25)
        ]

        def llm(messages):
            return json.dumps({
                "todayObservation": "今日观察",
                "items": [
                    {"title": str(index), "rewritten": "正文"}
                    for index in range(24)
                ],
                "editorComment": "小编短评",
            })

        with self.assertRaisesRegex(ContentError, "条目不完整"):
            Content(source, llm).build("2026-07-10", {})

    def test_content_retries_one_invalid_full_daily_response_before_failing(self):
        source = lambda date: [
            {"title": str(index), "summary": "S", "source_url": f"https://origin/{index}", "source": "A", "category": "news"}
            for index in range(25)
        ]
        calls = []
        responses = [
            "not json",
            json.dumps({
                "todayObservation": "today observation",
                "items": [{"title": str(index), "rewritten": "rewritten"} for index in range(25)],
                "editorComment": "editor comment",
            }),
        ]

        def llm(messages):
            calls.append(messages)
            return responses.pop(0)

        article = Content(source, llm).build("2026-07-10", {})

        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0][1]["content"], calls[1][1]["content"])
        self.assertEqual(len(article["items"]), 25)

    def test_content_stops_after_two_invalid_full_daily_responses(self):
        source = lambda date: [
            {"title": str(index), "summary": "S", "source_url": f"https://origin/{index}", "source": "A", "category": "news"}
            for index in range(25)
        ]
        calls = []

        def llm(messages):
            calls.append(messages)
            return "not json"

        with self.assertRaisesRegex(ContentError, "已自动重试一次"):
            Content(source, llm).build("2026-07-10", {})

        self.assertEqual(len(calls), 2)

    def test_content_adds_editorial_sections_from_the_same_daily_response(self):
        source = lambda date: [
            {"title": str(index), "summary": "S", "source_url": f"https://origin/{index}", "source": "A", "category": "行业动态"}
            for index in range(11)
        ]
        calls = []

        def llm(messages):
            calls.append(messages)
            self.assertEqual(messages[1]["content"].count("### 条目 "), 11)
            return json.dumps({
                "todayObservation": "覆盖全天的观察",
                "items": [{"title": "R", "rewritten": "正文"} for _ in range(11)],
                "editorComment": "覆盖全天的短评",
            })

        article = Content(source, llm).build("2026-07-10", {})

        self.assertEqual(len(calls), 1)
        self.assertEqual(len(article["items"]), 11)
        self.assertEqual(article["opening"], "覆盖全天的观察")
        self.assertEqual(article["closing"], "覆盖全天的短评")
        self.assertIn("**今日观察**", article["markdown"])
        self.assertIn("**小编短评**", article["markdown"])
        self.assertIn("数据来源：https://aihot.virxact.com/", article["markdown"])

    def test_content_reports_one_complete_daily_rewrite(self):
        source = lambda date: [{"title": str(i), "summary": "S", "source_url": f"https://origin/{i}", "source": "A", "category": "news"} for i in range(11)]
        llm = self.valid_llm
        progress = []
        Content(source, llm).build("2026-07-10", {}, progress=lambda *event: progress.append(event))
        self.assertEqual(progress[0][:2], ("scraping", "progress"))
        self.assertEqual(progress[1][:2], ("scraping", "complete"))
        self.assertEqual(progress[2][:2], ("rewriting", "progress"))
        self.assertIn("全部 11 条", progress[2][2])
        self.assertEqual(progress[3][:2], ("rewriting", "complete"))

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
        self.assertEqual(cleanup_calls, [{"cover_path": "C:/covers/2026-07-10.png"}])
        self.assertEqual(cleanup_calls[0]["cover_path"], "C:/covers/2026-07-10.png")
        self.assertEqual(published.state, "published")
        self.assertEqual(published.media_id, "")
        self.assertIsNone(published.article)
        with self.assertRaises(KeyError):
            runner.get(ready.id)

    def test_ephemeral_daily_lifecycle_keeps_ready_content_then_clears_it_after_publish(self):
        date = "2026-07-10"
        store = Store(Path(self.tmp.name) / "daily.db")
        cover_path = Path(self.tmp.name) / "cover.png"
        publisher_calls = []
        cleanup_calls = []

        def source(_date):
            return [
                {
                    "title": f"Source {index}",
                    "summary": "Summary",
                    "source_url": f"https://origin/{index}",
                    "source": "AIHot",
                    "category": "news",
                }
                for index in range(11)
            ]

        def llm(messages):
            count = messages[1]["content"].count("### 条目 ")
            return json.dumps({
                "todayObservation": "Opening",
                "items": [
                    {"title": f"Edited {index}", "rewritten": "Rewritten"}
                    for index in range(count)
                ],
                "editorComment": "Closing",
            })

        def cover(article, settings):
            cover_path.write_bytes(b"temporary cover")
            return {"cover_path": str(cover_path)}

        def cleanup(article):
            cleanup_calls.append(article["cover_path"])
            Path(article["cover_path"]).unlink()

        def publish(article):
            publishing = store.get(ready.id)
            self.assertEqual(publishing.state, "publishing")
            self.assertIsNone(publishing.article)
            self.assertEqual(publishing.media_id, "")
            self.assertEqual(store.events(ready.id), [])
            self.assertTrue(cover_path.is_file())
            publisher_calls.append(article.copy())
            return "draft-1"

        runner = DailyRun(store, Content(source, llm), publish, cover=cover, cleanup=cleanup)
        ready = runner.prepare(date, {})
        retained = runner.get(ready.id)

        self.assertEqual(retained.state, "ready")
        self.assertEqual(len(retained.article["items"]), 11)
        self.assertTrue(cover_path.is_file())
        self.assertIn("**\u4eca\u65e5\u89c2\u5bdf**", retained.article["markdown"])
        self.assertIn("**\u5c0f\u7f16\u77ed\u8bc4**", retained.article["markdown"])
        self.assertIn("\u6570\u636e\u6765\u6e90\uff1ahttps://aihot.virxact.com/", retained.article["markdown"])
        self.assertGreater(len(runner.events(ready.id)), 0)
        self.assertEqual(publisher_calls, [])

        published = runner.publish(date)

        self.assertEqual(publisher_calls, [retained.article])
        self.assertEqual(cleanup_calls, [str(cover_path)])
        self.assertFalse(cover_path.exists())
        self.assertEqual(published.state, "published")
        self.assertEqual(published.media_id, "")
        self.assertIsNone(published.article)
        with self.assertRaises(KeyError):
            runner.get(ready.id)
        with closing(store._connect()) as db:
            self.assertIsNone(db.execute("SELECT 1 FROM daily_runs WHERE id=?", (ready.id,)).fetchone())
            self.assertIsNone(db.execute("SELECT 1 FROM run_events WHERE run_id=?", (ready.id,)).fetchone())

        fresh = runner.start(date, {}, fresh=True)

        self.assertTrue(fresh.owner)
        self.assertNotEqual(fresh.id, ready.id)
        self.assertEqual(fresh.state, "scraping")

    def test_successful_publish_hides_finalization_content_until_cover_cleanup_recovers(self):
        source = lambda date: [{"title": "T", "summary": "S", "source_url": "https://origin/a", "source": "A", "category": "news"}]
        cleanup_calls = []

        def cleanup(article):
            cleanup_calls.append(article["cover_path"])
            if len(cleanup_calls) == 1:
                raise RuntimeError("cover cleanup unavailable")

        publisher_calls = []
        runner = DailyRun(
            store := Store(Path(self.tmp.name) / "daily.db"),
            Content(source, self.valid_llm),
            lambda article: publisher_calls.append(article.copy()) or "draft-1",
            cover=lambda article, settings: {"cover_path": "C:/covers/2026-07-10.png"},
            cleanup=cleanup,
        )
        ready = runner.prepare("2026-07-10", {})

        published = runner.publish("2026-07-10")

        self.assertEqual(published.state, "finalizing")
        self.assertEqual(published.media_id, "")
        self.assertIsNone(published.article)
        retained = store.get(ready.id)
        self.assertEqual(retained.state, "finalizing")
        self.assertEqual(retained.media_id, "")
        self.assertIsNone(retained.article)
        self.assertEqual(store.events(ready.id), [])

        with self.assertRaises(KeyError):
            runner.get(ready.id)

        self.assertEqual(len(publisher_calls), 1)
        self.assertEqual(len(cleanup_calls), 2)

    def test_finalization_blocks_history_cleanup_after_remote_draft_succeeds(self):
        date = "2026-07-10"
        store = Store(Path(self.tmp.name) / "daily.db")
        source = lambda date: [{"title": "T", "summary": "S", "source_url": "https://origin/a", "source": "A", "category": "news"}]
        deleted = []
        cleanup_started = False

        def cleanup(article):
            nonlocal cleanup_started
            if not cleanup_started:
                cleanup_started = True
                with self.assertRaisesRegex(RuntimeError, "active"):
                    runner.clear_history(deleted.append)

        runner = DailyRun(
            store,
            Content(source, self.valid_llm),
            lambda article: "draft-1",
            cover=lambda article, settings: {"cover_path": "C:/covers/2026-07-10.png"},
            cleanup=cleanup,
        )
        ready = runner.prepare(date, {})

        published = runner.publish(date)

        self.assertEqual(published.state, "published")
        self.assertEqual(published.media_id, "")
        self.assertIsNone(published.article)
        with self.assertRaises(KeyError):
            runner.get(ready.id)
        self.assertEqual(deleted, [])

    def test_recovered_finalization_never_calls_the_publisher_again(self):
        store = Store(Path(self.tmp.name) / "daily.db")
        calls = []
        cleanup = []
        runner = DailyRun(store, Content(lambda date: [{"title": "T", "summary": "S", "source_url": "https://origin/a", "source": "A", "category": "news"}], self.valid_llm), lambda article: calls.append(article) or "new-draft", cleanup=lambda article: cleanup.append(article["markdown"]))
        ready = runner.prepare("2026-07-10", {})
        store.transition(ready.id, "publishing")
        store.mark_finalizing(ready.id, "draft-1")

        recovered = runner.prepare("2026-07-10", {}, retry=True)
        published = runner.publish("2026-07-10")

        self.assertEqual(recovered.state, "finalizing")
        self.assertFalse(recovered.owner)
        self.assertEqual(published.state, "published")
        self.assertEqual(published.media_id, "")
        self.assertEqual(calls, [])
        self.assertEqual(len(cleanup), 0)
        with self.assertRaises(KeyError):
            runner.get(ready.id)

    def test_stale_publishing_stops_as_uncertain_without_republishing(self):
        store = Store(Path(self.tmp.name) / "daily.db")
        publisher_calls = []
        cleanup_calls = []
        run = store.claim("2026-07-10")
        store.transition(run.id, "scraping")
        store.transition(run.id, "rewriting")
        ready = store.save_article(
            run.id,
            {"date": "2026-07-10", "markdown": "article", "items": [], "cover_path": "C:/covers/2026-07-10.png"},
        )
        store.transition(ready.id, "publishing")
        with closing(store._connect()) as db, db:
            db.execute("UPDATE daily_runs SET updated_at=datetime('now', '-31 minutes') WHERE id=?", (ready.id,))
        runner = DailyRun(
            store,
            None,
            lambda article: publisher_calls.append(article) or "new-draft",
            cleanup=lambda article: cleanup_calls.append(article["cover_path"]),
        )

        scheduled = runner.prepare("2026-07-10", {}, retry=True)
        publish_result = runner.publish("2026-07-10")

        self.assertEqual(scheduled.state, "publication_uncertain")
        self.assertEqual(publish_result.state, "publication_uncertain")
        self.assertEqual(publisher_calls, [])
        self.assertEqual(cleanup_calls, ["C:/covers/2026-07-10.png"])
        retained = store.get(ready.id)
        self.assertEqual(retained.state, "publication_uncertain")
        self.assertIsNone(retained.article)
        self.assertEqual(store.events(ready.id), [])

        with self.assertRaisesRegex(RuntimeError, "确认"):
            runner.start("2026-07-10", {}, fresh=True)
        self.assertEqual(store.get(ready.id).state, "publication_uncertain")

        fresh = runner.start("2026-07-10", {}, fresh=True, resolve_uncertain=True)

        self.assertTrue(fresh.owner)
        self.assertEqual(fresh.state, "scraping")
        with self.assertRaises(KeyError):
            store.get(ready.id)

    def test_cleanup_history_refuses_a_publication_uncertain_run(self):
        store = Store(Path(self.tmp.name) / "daily.db")
        run = store.claim("2026-07-10")
        store.transition(run.id, "scraping")
        store.transition(run.id, "rewriting")
        store.save_article(run.id, {"date": "2026-07-10", "markdown": "article", "items": []})
        store.transition(run.id, "publishing")
        store.mark_publication_uncertain(run.id, "发布结果待确认")
        deleted = []

        with self.assertRaisesRegex(RuntimeError, "active"):
            DailyRun(store, None, None).clear_history(deleted.append)

        self.assertEqual(deleted, [])
        self.assertEqual(store.get(run.id).state, "publication_uncertain")

    def test_clear_history_deletes_every_draft_before_removing_local_runs(self):
        store = Store(Path(self.tmp.name) / "daily.db")
        first = self._published_run(store, "2026-07-10", "draft-1", "C:/covers/2026-07-10.png")
        second = self._published_run(store, "2026-07-11", "draft-2", "C:/covers/2026-07-11.png")
        deleted = []
        cleaned = []
        runner = DailyRun(store, None, None, cleanup=lambda article: cleaned.append(article["cover_path"]))

        summary = runner.clear_history(deleted.append)

        self.assertEqual(summary, {"count": 2, "dates": ["2026-07-10", "2026-07-11"]})
        self.assertEqual(deleted, ["draft-1", "draft-2"])
        self.assertEqual(cleaned, ["C:/covers/2026-07-10.png", "C:/covers/2026-07-11.png"])
        with self.assertRaises(KeyError):
            store.get(first.id)
        with self.assertRaises(KeyError):
            store.get(second.id)

    def test_clear_history_resumes_after_a_partial_draft_deletion_failure(self):
        store = Store(Path(self.tmp.name) / "daily.db")
        first = self._published_run(store, "2026-07-10", "draft-1", "C:/covers/2026-07-10.png")
        second = self._published_run(store, "2026-07-11", "draft-2", "C:/covers/2026-07-11.png")
        store.record_event(first.id, "done", "complete", "private progress")
        store.record_event(second.id, "done", "complete", "private progress")
        deleted = []
        cleaned = []
        runner = DailyRun(store, None, None, cleanup=lambda article: cleaned.append(article["cover_path"]))

        def delete_draft(media_id):
            deleted.append(media_id)
            if media_id == "draft-2":
                raise RuntimeError("draft deletion failed")

        with self.assertRaisesRegex(RuntimeError, "draft deletion failed"):
            runner.clear_history(delete_draft)

        self.assertEqual(deleted, ["draft-1", "draft-2"])
        self.assertEqual(store.get(first.id).state, "cleaning")
        self.assertEqual(store.get(first.id).media_id, "")
        self.assertIsNone(store.get(first.id).article)
        self.assertEqual(store.events(first.id), [])
        self.assertEqual(store.pending_cover_cleanup(first.id), {"cover_path": "C:/covers/2026-07-10.png"})
        self.assertEqual(store.get(second.id).state, "cleaning")
        self.assertEqual(store.get(second.id).media_id, "draft-2")
        self.assertIsNone(store.get(second.id).article)
        self.assertEqual(store.events(second.id), [])
        self.assertEqual(store.pending_cover_cleanup(second.id), {"cover_path": "C:/covers/2026-07-11.png"})

        deleted = []
        summary = runner.clear_history(deleted.append)

        self.assertEqual(deleted, ["draft-2"])
        self.assertEqual(summary, {"count": 2, "dates": ["2026-07-10", "2026-07-11"]})
        self.assertEqual(cleaned, ["C:/covers/2026-07-10.png", "C:/covers/2026-07-11.png"])
        with self.assertRaises(KeyError):
            store.get(first.id)
        with self.assertRaises(KeyError):
            store.get(second.id)

    def test_cleanup_history_lease_blocks_a_second_remote_delete(self):
        store = Store(Path(self.tmp.name) / "daily.db")
        self._published_run(store, "2026-07-10", "draft-1")
        runner = DailyRun(store, None, None)
        entered_delete = threading.Event()
        allow_first_delete = threading.Event()
        errors = []
        deleted = []

        def first_delete(media_id):
            entered_delete.set()
            self.assertTrue(allow_first_delete.wait(1))
            deleted.append(("first", media_id))

        def run_first_cleanup():
            try:
                runner.clear_history(first_delete)
            except Exception as exc:
                errors.append(exc)

        first = threading.Thread(target=run_first_cleanup)
        first.start()
        self.assertTrue(entered_delete.wait(1))

        with self.assertRaisesRegex(RuntimeError, "cleanup"):
            runner.clear_history(lambda media_id: deleted.append(("second", media_id)))

        allow_first_delete.set()
        first.join(1)
        self.assertFalse(first.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(deleted, [("first", "draft-1")])

    def test_cleanup_history_reclaims_a_stale_crashed_lease(self):
        store = Store(Path(self.tmp.name) / "daily.db")
        self._published_run(store, "2026-07-10", "draft-1")
        store.begin_cleanup("crashed-owner")
        with closing(store._connect()) as db, db:
            db.execute("UPDATE cleanup_leases SET acquired_at=datetime('now', '-6 minutes')")

        summary = DailyRun(store, None, None).clear_history(lambda media_id: self.assertEqual(media_id, "draft-1"))

        self.assertEqual(summary, {"count": 1, "dates": ["2026-07-10"]})

    def test_clear_history_refuses_while_a_run_is_active(self):
        store = Store(Path(self.tmp.name) / "daily.db")
        active = store.claim("2026-07-10")
        deleted = []

        with self.assertRaisesRegex(RuntimeError, "active"):
            DailyRun(store, None, None).clear_history(deleted.append)

        self.assertEqual(deleted, [])
        self.assertEqual(store.get(active.id).state, "queued")

    def test_clear_history_discards_a_stale_queued_legacy_run_without_publishing(self):
        store = Store(Path(self.tmp.name) / "daily.db")
        stale = store.claim("2026-07-07")
        with closing(store._connect()) as db, db:
            db.execute("UPDATE daily_runs SET updated_at=datetime('now', '-31 minutes') WHERE id=?", (stale.id,))
        publisher_calls = []
        deleted = []
        runner = DailyRun(store, None, lambda article: publisher_calls.append(article))

        summary = runner.clear_history(deleted.append)

        self.assertEqual(summary, {"count": 1, "dates": ["2026-07-07"]})
        self.assertEqual(publisher_calls, [])
        self.assertEqual(deleted, [])
        with self.assertRaises(KeyError):
            store.get(stale.id)

    def test_active_progress_prevents_history_cleanup_and_publisher_calls(self):
        for state in ("scraping", "rewriting"):
            with self.subTest(state=state):
                store = Store(Path(self.tmp.name) / f"{state}.db")
                active = store.claim("2026-07-10")
                store.transition(active.id, "scraping")
                if state == "rewriting":
                    store.transition(active.id, "rewriting")
                with closing(store._connect()) as db, db:
                    db.execute("UPDATE daily_runs SET updated_at=datetime('now', '-31 minutes') WHERE id=?", (active.id,))
                store.record_event(active.id, state, "progress", "Still working")
                publisher_calls = []
                runner = DailyRun(store, None, lambda article: publisher_calls.append(article))

                with self.assertRaisesRegex(RuntimeError, "active"):
                    runner.clear_history(lambda media_id: None)

                self.assertEqual(publisher_calls, [])
                self.assertEqual(store.get(active.id).state, state)

    def test_clear_history_never_takes_an_aged_publishing_run_while_the_publisher_finishes(self):
        store = Store(Path(self.tmp.name) / "daily.db")
        ready = self._ready_run(store, "2026-07-10", "C:/covers/2026-07-10.png")
        started = threading.Event()
        release = threading.Event()
        deleted = []

        def publisher(article):
            started.set()
            self.assertTrue(release.wait(1))
            return "draft-1"

        runner = DailyRun(
            store,
            None,
            publisher,
            cleanup=lambda article: (_ for _ in ()).throw(RuntimeError("cover still locked")),
        )
        result = []
        worker = threading.Thread(target=lambda: result.append(runner.publish(ready.date)))
        worker.start()
        self.assertTrue(started.wait(1))
        with closing(store._connect()) as db, db:
            db.execute("UPDATE daily_runs SET updated_at=datetime('now', '-31 minutes') WHERE id=?", (ready.id,))

        with self.assertRaisesRegex(RuntimeError, "active"):
            runner.clear_history(deleted.append)

        self.assertEqual(deleted, [])
        self.assertEqual(store.get(ready.id).state, "publishing")
        release.set()
        worker.join(1)
        self.assertFalse(worker.is_alive())
        self.assertEqual(result[0].state, "finalizing")
        self.assertEqual(store.get(ready.id).state, "finalizing")

    def test_clear_history_blocks_a_stale_ready_publish_before_remote_publish(self):
        store = Store(Path(self.tmp.name) / "daily.db")
        ready = self._ready_run(store, "2026-07-10")
        self._published_run(store, "2026-07-11", "draft-1")
        remote_publishes = []
        runner = DailyRun(store, None, lambda article: remote_publishes.append(article) or "new-draft")

        def delete_draft(media_id):
            self.assertEqual(media_id, "draft-1")
            with self.assertRaises(InvalidTransition):
                store.transition(ready.id, "publishing")
            with self.assertRaises(InvalidTransition):
                runner.publish(ready.date)

        runner.clear_history(delete_draft)

        self.assertEqual(remote_publishes, [])

    @staticmethod
    def _published_run(store, date, media_id, cover_path=None):
        run = WorkflowTests._ready_run(store, date, cover_path)
        store.transition(run.id, "publishing")
        return store.mark_published(run.id, media_id)

    @staticmethod
    def _ready_run(store, date, cover_path=None):
        run = store.claim(date)
        store.transition(run.id, "scraping")
        store.transition(run.id, "rewriting")
        article = {"date": date, "markdown": "article", "items": []}
        if cover_path:
            article["cover_path"] = cover_path
        return store.save_article(run.id, article)

    def test_publish_error_becomes_uncertain_and_never_retries_the_remote_call(self):
        source = lambda date: [{"title": "T", "summary": "S", "source_url": "https://origin/a", "source": "A", "category": "news"}]
        llm = self.valid_llm
        calls = []

        def publisher(article):
            calls.append(article)
            raise RuntimeError("publisher unavailable")

        runner = DailyRun(Store(Path(self.tmp.name) / "daily.db"), Content(source, llm), publisher)
        ready = runner.prepare("2026-07-10", {})

        uncertain = runner.publish("2026-07-10")
        repeated = runner.publish("2026-07-10")

        self.assertEqual(uncertain.state, "publication_uncertain")
        self.assertEqual(repeated.state, "publication_uncertain")
        self.assertEqual(len(calls), 1)
        self.assertIsNone(uncertain.article)
        self.assertEqual(uncertain.media_id, "")
        self.assertEqual(runner.events(ready.id), [])

    def test_finalization_write_failure_becomes_uncertain_without_republishing(self):
        store = Store(Path(self.tmp.name) / "daily.db")
        ready = self._ready_run(store, "2026-07-10")
        calls = []
        runner = DailyRun(
            store,
            None,
            lambda article: calls.append(article) or "draft-1",
            cleanup=lambda article: None,
        )

        with patch.object(store, "mark_finalizing", side_effect=RuntimeError("receipt write failed")):
            uncertain = runner.publish(ready.date)

        repeated = runner.publish(ready.date)

        self.assertEqual(uncertain.state, "publication_uncertain")
        self.assertEqual(repeated.state, "publication_uncertain")
        self.assertEqual(len(calls), 1)
        self.assertIsNone(uncertain.article)
        self.assertEqual(uncertain.media_id, "")
        self.assertEqual(runner.events(ready.id), [])

    def test_uncertain_write_failure_never_restores_or_republishes_detached_content(self):
        store = Store(Path(self.tmp.name) / "daily.db")
        ready = self._ready_run(store, "2026-07-10")
        store.record_event(ready.id, "done", "complete", "ready")
        calls = []
        runner = DailyRun(
            store,
            None,
            lambda article: calls.append(article) or "draft-1",
            cleanup=lambda article: None,
        )
        persist_uncertain = store.mark_publication_uncertain
        attempts = 0

        def fail_once_then_persist(run_id, error):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError("database unavailable")
            return persist_uncertain(run_id, error)

        with patch.object(store, "mark_finalizing", side_effect=RuntimeError("receipt write failed")), patch.object(
            store, "mark_publication_uncertain", side_effect=fail_once_then_persist
        ):
            first = runner.publish(ready.date)

            self.assertEqual(first.state, "publishing")
            self.assertIsNone(first.article)
            self.assertEqual(first.media_id, "")
            self.assertEqual(runner.events(ready.id), [])
            with closing(store._connect()) as db, db:
                db.execute("UPDATE daily_runs SET updated_at=datetime('now', '-31 minutes') WHERE id=?", (ready.id,))

            recovered = runner.get(ready.id)
            repeated = runner.publish(ready.date)

        self.assertEqual(recovered.state, "publication_uncertain")
        self.assertEqual(repeated.state, "publication_uncertain")
        self.assertEqual(len(calls), 1)
        self.assertIsNone(store.get(ready.id).article)
        self.assertEqual(store.events(ready.id), [])

    def test_uncertain_publish_keeps_only_a_retryable_cover_cleanup_marker(self):
        store = Store(Path(self.tmp.name) / "daily.db")
        run = store.claim("2026-07-10")
        store.transition(run.id, "scraping")
        store.transition(run.id, "rewriting")
        ready = store.save_article(
            run.id,
            {"date": run.date, "markdown": "article", "cover_path": "C:/covers/2026-07-10.png"},
        )
        cleanup_calls = []

        def cleanup(article):
            cleanup_calls.append(article["cover_path"])
            if len(cleanup_calls) == 1:
                raise RuntimeError("cover locked")

        runner = DailyRun(
            store,
            None,
            lambda article: (_ for _ in ()).throw(RuntimeError("publisher timeout")),
            cleanup=cleanup,
        )

        uncertain = runner.publish(ready.date)
        recovered = runner.get(ready.id)

        self.assertEqual(uncertain.state, "publication_uncertain")
        self.assertIsNone(uncertain.article)
        self.assertEqual(cleanup_calls, ["C:/covers/2026-07-10.png", "C:/covers/2026-07-10.png"])
        self.assertEqual(recovered.state, "publication_uncertain")
        self.assertIsNone(store.pending_cover_cleanup(ready.id))

    def test_publish_adds_a_date_title_to_a_legacy_ready_article(self):
        store = Store(Path(self.tmp.name) / "daily.db")
        run = store.claim("2026-07-10")
        store.transition(run.id, "scraping")
        store.transition(run.id, "rewriting")
        store.save_article(run.id, {"date": "2026-07-10", "markdown": "article", "items": []})
        captured = {}

        published = DailyRun(store, None, lambda article: captured.update(article) or "draft-1").publish("2026-07-10")

        self.assertEqual(published.media_id, "")
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

    def test_retry_starts_a_new_queued_run_and_executes_it(self):
        store = Store(Path(self.tmp.name) / "daily.db")
        source = lambda date: [
            {"title": "T", "summary": "S", "source_url": "https://origin/a", "source": "A", "category": "news"}
        ]
        runner = DailyRun(store, Content(source, self.valid_llm), None)

        started = runner.start("2026-07-10", {}, retry=True)
        completed = runner.execute(started.id, "2026-07-10", {})

        self.assertTrue(started.owner)
        self.assertEqual(started.state, "scraping")
        self.assertEqual(completed.state, "ready")

    def test_fresh_generation_reclaims_stale_prepublication_states_and_executes(self):
        source = lambda date: [
            {"title": "T", "summary": "S", "source_url": "https://origin/a", "source": "A", "category": "news"}
        ]
        for state in ("queued", "scraping", "rewriting"):
            with self.subTest(state=state):
                store = Store(Path(self.tmp.name) / f"fresh-{state}.db")
                stale = store.claim("2026-07-10")
                if state in {"scraping", "rewriting"}:
                    store.transition(stale.id, "scraping")
                if state == "rewriting":
                    store.transition(stale.id, "rewriting")
                with closing(store._connect()) as db, db:
                    db.execute("UPDATE daily_runs SET updated_at=datetime('now', '-31 minutes') WHERE id=?", (stale.id,))
                runner = DailyRun(store, Content(source, self.valid_llm), None)

                started = runner.start("2026-07-10", {}, fresh=True)
                completed = runner.execute(started.id, "2026-07-10", {})

                self.assertTrue(started.owner)
                self.assertEqual(started.state, "scraping")
                self.assertEqual(completed.state, "ready")

    def test_fresh_generation_does_not_hijack_an_active_queued_run(self):
        store = Store(Path(self.tmp.name) / "daily.db")
        active = store.claim("2026-07-10")

        waiting = DailyRun(store, None, None).start("2026-07-10", {}, fresh=True)

        self.assertFalse(waiting.owner)
        self.assertEqual(waiting.id, active.id)
        self.assertEqual(waiting.state, "queued")

    def test_prepare_fresh_cleans_the_old_cover_before_replacing_a_ready_run(self):
        store = Store(Path(self.tmp.name) / "daily.db")
        source = lambda date: [{"title": "T", "summary": "S", "source_url": "https://origin/a", "source": "A", "category": "news"}]
        cleaned = []
        runner = DailyRun(
            store,
            Content(source, self.valid_llm),
            None,
            cover=lambda article, settings: {"cover_path": "C:/covers/2026-07-10.png"},
            cleanup=lambda article: cleaned.append(article["cover_path"]),
        )
        old = runner.prepare("2026-07-10", {})

        fresh = runner.prepare("2026-07-10", {}, fresh=True)

        self.assertNotEqual(fresh.id, old.id)
        self.assertEqual(fresh.state, "ready")
        self.assertEqual(cleaned, ["C:/covers/2026-07-10.png"])
        with self.assertRaises(KeyError):
            runner.get(old.id)

    def test_fresh_generation_refuses_to_orphan_a_legacy_published_receipt(self):
        store = Store(Path(self.tmp.name) / "daily.db")
        legacy = self._published_run(store, "2026-07-10", "draft-1")
        runner = DailyRun(store, Content(lambda date: [], self.valid_llm), None)

        with self.assertRaisesRegex(RuntimeError, "cleanup-history"):
            runner.start("2026-07-10", {}, fresh=True)

        retained = store.get(legacy.id)
        self.assertEqual(retained.state, "published")
        self.assertEqual(retained.media_id, "draft-1")

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
