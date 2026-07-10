import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))


class PackageTests(unittest.TestCase):
    def test_package_can_be_imported(self):
        import ai_daily

        self.assertEqual(ai_daily.__name__, "ai_daily")
