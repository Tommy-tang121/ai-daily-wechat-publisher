import sys
import tempfile
import unittest
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

    def test_content_limits_a_daily_run_to_ten_items(self):
        source = lambda date: [{"title": str(i), "summary": "S", "source_url": f"https://origin/{i}", "source": "A", "category": "news"} for i in range(11)]
        raw = '{"items":[' + ','.join('{"title":"R","body":"rewritten"}' for _ in range(10)) + ']}'
        article = Content(source, lambda messages: raw).build("2026-07-10", {})
        self.assertEqual(len(article["items"]), 10)

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
