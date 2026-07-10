import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from ai_daily.runtime import AihotSource


class AihotTests(unittest.TestCase):
    def test_source_uses_browser_user_agent(self):
        class Response:
            def raise_for_status(self): pass
            def json(self): return {"sections": []}
        with patch("requests.get", return_value=Response()) as get:
            AihotSource()("2026-07-10")
        self.assertIn("User-Agent", get.call_args.kwargs["headers"])
