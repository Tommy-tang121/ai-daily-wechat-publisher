import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from ai_daily.article_format import build_markdown


class ArticleFormatTests(unittest.TestCase):
    def test_build_markdown_restores_legacy_section_order(self):
        markdown = build_markdown(
            "观察,重要!",
            [
                {"category": "行业动态", "title": "标题 A", "body": "正文 A", "source": "来源 A"},
                {"category": "产品发布", "title": "标题 B", "body": "正文 B", "source": "来源 B"},
            ],
            "短评?有判断!",
            "https://aihot.virxact.com/",
        )

        self.assertIn("**今日观察**\n\n观察，重要！", markdown)
        self.assertIn("**【行业动态】**\n\n**标题 A**\n\n正文 A\n\n来源：来源 A", markdown)
        self.assertIn("**【产品发布】**", markdown)
        self.assertIn("**小编短评**\n\n短评？有判断！", markdown)
        self.assertTrue(markdown.endswith("数据来源：https://aihot.virxact.com/"))
