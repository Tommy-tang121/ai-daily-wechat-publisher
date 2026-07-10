import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from ai_daily.cli import serve_preview


class CliTests(unittest.TestCase):
    def test_preview_uses_flask_fallback_when_waitress_is_unavailable(self):
        seen = []
        serve_preview(object(), lambda app: seen.append(app))
        self.assertEqual(len(seen), 1)
