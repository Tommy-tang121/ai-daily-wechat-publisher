import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from ai_daily.runtime import load_environment


class RuntimeTests(unittest.TestCase):
    def test_app_env_overrides_legacy_root_env(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env").write_text("VALUE=legacy\n", encoding="utf-8")
            (root / "app").mkdir()
            (root / "app" / ".env").write_text("VALUE=app\n", encoding="utf-8")
            previous = os.environ.pop("VALUE", None)
            self.addCleanup(lambda: previous and os.environ.__setitem__("VALUE", previous))
            load_environment(root / "app")
            self.assertEqual(os.environ["VALUE"], "app")
