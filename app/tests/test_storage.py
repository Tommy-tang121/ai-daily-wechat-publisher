import sys
import tempfile
import unittest
from contextlib import closing
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

    def test_failed_run_can_be_explicitly_retried(self):
        run = self.store.claim("2026-07-10")
        self.store.transition(run.id, "failed", "temporary error")
        retried = self.store.retry(run.id)
        self.assertEqual(retried.state, "queued")
        self.assertTrue(retried.owner)

    def test_failed_publish_with_an_article_retries_from_ready_without_regenerating(self):
        run = self.store.claim("2026-07-10")
        self.store.transition(run.id, "scraping")
        self.store.transition(run.id, "rewriting")
        self.store.save_article(run.id, {"markdown": "article"})
        self.store.transition(run.id, "publishing")
        self.store.transition(run.id, "failed", "publisher unavailable")

        retried = self.store.retry(run.id)

        self.assertEqual(retried.state, "ready")
        self.assertFalse(retried.owner)
        self.assertEqual(retried.article, {"markdown": "article"})

    def test_events_are_persisted_in_the_order_they_happened(self):
        run = self.store.claim("2026-07-10")
        self.store.record_event(run.id, "scraping", "progress", "Fetching sources")
        self.store.record_event(run.id, "rewriting", "progress", "Rewriting batch 1 of 3")
        self.assertEqual(
            self.store.events(run.id),
            [
                {"stage": "scraping", "status": "progress", "message": "Fetching sources"},
                {"stage": "rewriting", "status": "progress", "message": "Rewriting batch 1 of 3"},
            ],
        )

    def test_settings_keep_defaults_and_persist_user_changes(self):
        defaults = {"title": "Daily", "max_words": 150}
        self.store.initialize_settings(defaults)
        self.store.update_settings({"title": "Updated", "max_words": 200})
        self.assertEqual(self.store.settings(defaults), {"title": "Updated", "max_words": 200})

    def test_stale_active_run_can_be_safely_reclaimed_for_retry(self):
        run = self.store.claim("2026-07-10")
        self.store.transition(run.id, "scraping")
        with closing(self.store._connect()) as db, db:
            db.execute("UPDATE daily_runs SET updated_at=datetime('now', '-31 minutes') WHERE id=?", (run.id,))

        reclaimed = self.store.reclaim_stale(run.id, minutes=30)

        self.assertTrue(reclaimed.owner)
        self.assertEqual(reclaimed.state, "queued")

    def test_stale_queued_run_can_be_safely_reclaimed_for_retry(self):
        run = self.store.claim("2026-07-10")
        with closing(self.store._connect()) as db, db:
            db.execute("UPDATE daily_runs SET updated_at=datetime('now', '-31 minutes') WHERE id=?", (run.id,))

        reclaimed = self.store.reclaim_stale(run.id, minutes=30)

        self.assertTrue(reclaimed.owner)
        self.assertEqual(reclaimed.state, "queued")
