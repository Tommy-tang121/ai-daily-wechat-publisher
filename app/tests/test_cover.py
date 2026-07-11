import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from ai_daily.cover import generate_cover


class CoverTests(unittest.TestCase):
    def test_cover_is_created_at_wechat_size(self):
        with tempfile.TemporaryDirectory() as directory:
            cover = generate_cover(Path(directory), "2026-07-10", "AI 行业热点新闻")
            self.assertTrue(cover.is_file())
            from PIL import Image
            with Image.open(cover) as image:
                self.assertEqual(image.size, (900, 500))

    def test_cover_matches_the_legacy_hand_drawn_reference(self):
        from PIL import Image, ImageChops

        with tempfile.TemporaryDirectory() as directory:
            cover = generate_cover(Path(directory), "2026-07-02", "ignored", "Tommy")
            reference = Path(__file__).parents[1] / "static" / "covers" / "2026-07-02.png"
            with Image.open(cover).convert("RGB") as actual, Image.open(reference).convert("RGB") as expected:
                self.assertIsNone(ImageChops.difference(actual, expected).getbbox())
