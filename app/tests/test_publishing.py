import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from ai_daily.publishing import build_wechat_command


class PublishingTests(unittest.TestCase):
    def test_command_keeps_default_citations(self):
        command = build_wechat_command("bun", Path("article.md"), "标题", "cover.png", "作者")
        self.assertNotIn("--no-cite", command)
        self.assertIn("--theme", command)
