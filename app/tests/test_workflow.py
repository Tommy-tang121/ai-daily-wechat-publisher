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
