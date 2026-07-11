import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from ai_daily.publishing import WeChatPublisher, build_wechat_command


class PublishingTests(unittest.TestCase):
    def test_command_keeps_default_citations(self):
        command = build_wechat_command("bun", Path("article.md"), "title", "cover.png", "author")
        self.assertNotIn("--no-cite", command)
        self.assertIn("--theme", command)

    def test_publisher_reuses_the_cover_persisted_with_the_ready_run(self):
        article = {"date": "2026-07-10", "markdown": "article", "cover_path": "C:/covers/2026-07-10.png"}
        completed = SimpleNamespace(returncode=0, stdout='{"success":true,"media_id":"draft-1"}', stderr="")
        with patch("ai_daily.publishing.shutil.which", return_value="bun"), patch("ai_daily.publishing.subprocess.run", return_value=completed) as run:
            self.assertEqual(WeChatPublisher("title")(article), "draft-1")
        command = run.call_args.args[0]
        self.assertEqual(command[command.index("--cover") + 1], article["cover_path"])
        self.assertEqual(run.call_args.kwargs.get("encoding"), "utf-8")

    def test_publisher_uses_the_title_persisted_with_the_article(self):
        article = {"date": "2026-07-10", "title": "AI 行业热点新闻 | 2026-07-10", "markdown": "article", "cover_path": "C:/covers/2026-07-10.png"}
        completed = SimpleNamespace(returncode=0, stdout='{"success":true,"media_id":"draft-1"}', stderr="")
        with patch("ai_daily.publishing.shutil.which", return_value="bun"), patch("ai_daily.publishing.subprocess.run", return_value=completed) as run:
            WeChatPublisher("stale title")(article)

        command = run.call_args.args[0]
        self.assertEqual(command[command.index("--title") + 1], article["title"])

    def test_publisher_reports_the_real_script_error_after_progress_logs(self):
        article = {"date": "2026-07-10", "markdown": "article", "cover_path": "C:/covers/2026-07-10.png"}
        completed = SimpleNamespace(returncode=1, stdout="", stderr=("progress\n" * 100) + "根本原因")
        with patch("ai_daily.publishing.shutil.which", return_value="bun"), patch("ai_daily.publishing.subprocess.run", return_value=completed):
            with self.assertRaisesRegex(RuntimeError, "根本原因"):
                WeChatPublisher("title")(article)
