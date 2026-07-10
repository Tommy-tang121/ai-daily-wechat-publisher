import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))


class LegacyPublisherPathTests(unittest.TestCase):
    def test_vendored_wechat_script_path_exists(self):
        from app.publisher import SCRIPTS_DIR

        self.assertTrue(Path(SCRIPTS_DIR).is_dir())
