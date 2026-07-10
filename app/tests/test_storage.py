import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from ai_daily.storage import InvalidTransition, Store


class StoreTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.temp = Path(self._tmp.name) / "daily.db"
        self.store = Store(self.temp)

    def test_active_date_has_one_owner(self):
        self.assertTrue(self.store.claim("2026-07-10").owner)
        self.assertFalse(self.store.claim("2026-07-10").owner)

    def test_published_date_keeps_its_receipt(self):
        run = self.store.claim("2026-07-10")
        self.store.transition(run.id, "scraping")
        self.store.transition(run.id, "rewriting")
        self.store.save_article(run.id, {"markdown": "article"})
        self.store.transition(run.id, "publishing")
        self.store.mark_published(run.id, "media-1")
        repeated = self.store.claim("2026-07-10")
        self.assertEqual(repeated.media_id, "media-1")
        self.assertFalse(repeated.owner)

    def test_invalid_transition_is_rejected(self):
        run = self.store.claim("2026-07-10")
        with self.assertRaises(InvalidTransition):
            self.store.transition(run.id, "published")
