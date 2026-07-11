import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))


class PublisherPathTests(unittest.TestCase):
    def test_vendored_wechat_script_path_exists(self):
        from ai_daily.publishing import VENDOR_SCRIPTS

        self.assertTrue(Path(VENDOR_SCRIPTS).is_dir())
