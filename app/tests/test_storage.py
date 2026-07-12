import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

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

    def test_discard_returns_the_saved_run_and_removes_its_events(self):
        run = self.store.claim("2026-07-10")
        self.store.transition(run.id, "scraping")
        self.store.transition(run.id, "rewriting")
        self.store.save_article(run.id, {"markdown": "article"})
        self.store.record_event(run.id, "done", "complete", "Ready to publish")

        discarded = self.store.discard(run.id)

        self.assertEqual(discarded.id, run.id)
        self.assertEqual(discarded.state, "ready")
        self.assertEqual(discarded.article, {"markdown": "article"})
        with self.assertRaises(KeyError):
            self.store.get(run.id)
        with closing(self.store._connect()) as db:
            self.assertIsNone(db.execute("SELECT 1 FROM daily_runs WHERE id=?", (run.id,)).fetchone())
            self.assertIsNone(db.execute("SELECT 1 FROM run_events WHERE run_id=?", (run.id,)).fetchone())

    def test_claim_fresh_replaces_ready_failed_and_published_runs(self):
        for state in ("ready", "failed", "published"):
            with self.subTest(state=state):
                date = f"2026-07-{11 + len(state)}"
                old = self.store.claim(date)
                self.store.record_event(old.id, "scraping", "progress", "Old run")
                if state == "ready":
                    self.store.transition(old.id, "scraping")
                    self.store.transition(old.id, "rewriting")
                    self.store.save_article(old.id, {"markdown": "article"})
                elif state == "failed":
                    self.store.transition(old.id, "failed", "source unavailable")
                else:
                    self.store.transition(old.id, "scraping")
                    self.store.transition(old.id, "rewriting")
                    self.store.save_article(old.id, {"markdown": "article"})
                    self.store.transition(old.id, "publishing")
                    self.store.mark_published(old.id, "media-1")

                fresh = self.store.claim_fresh(date)

                self.assertTrue(fresh.owner)
                self.assertNotEqual(fresh.id, old.id)
                self.assertEqual(fresh.state, "queued")
                self.assertIsNone(fresh.article)
                with self.assertRaises(KeyError):
                    self.store.get(old.id)
                with closing(self.store._connect()) as db:
                    self.assertIsNone(db.execute("SELECT 1 FROM run_events WHERE run_id=?", (old.id,)).fetchone())

    def test_claim_fresh_keeps_active_runs(self):
        for state in ("queued", "scraping", "rewriting", "publishing"):
            with self.subTest(state=state):
                date = f"2026-07-{20 + len(state)}"
                active = self.store.claim(date)
                if state in {"scraping", "rewriting", "publishing"}:
                    self.store.transition(active.id, "scraping")
                if state in {"rewriting", "publishing"}:
                    self.store.transition(active.id, "rewriting")
                if state == "publishing":
                    self.store.save_article(active.id, {"markdown": "article"})
                    self.store.transition(active.id, "publishing")

                claimed = self.store.claim_fresh(date)

                self.assertFalse(claimed.owner)
                self.assertEqual(claimed.id, active.id)
                self.assertEqual(claimed.state, state)

    def test_claim_fresh_keeps_a_cleaning_run_for_cleanup_retry(self):
        run = self.store.claim("2026-07-29")
        self.store.transition(run.id, "scraping")
        self.store.transition(run.id, "rewriting")
        self.store.save_article(run.id, {"markdown": "article"})
        self.store.begin_cleanup()

        claimed = self.store.claim_fresh("2026-07-29")

        self.assertFalse(claimed.owner)
        self.assertEqual(claimed.id, run.id)
        self.assertEqual(claimed.state, "cleaning")

    def test_invalid_transition_is_rejected(self):
        run = self.store.claim("2026-07-10")
        with self.assertRaises(InvalidTransition):
            self.store.transition(run.id, "published")

    def test_transition_does_not_overwrite_a_cleaning_state_changed_after_its_read(self):
        run = self.store.claim("2026-07-10")
        self.store.transition(run.id, "scraping")
        self.store.transition(run.id, "rewriting")
        self.store.save_article(run.id, {"markdown": "article"})
        original_connect = self.store._connect

        class InterleavingConnection:
            def __init__(self, connection):
                self.connection = connection
                self.changed_state = False

            def __enter__(self):
                self.connection.__enter__()
                return self

            def __exit__(self, *args):
                return self.connection.__exit__(*args)

            def close(self):
                self.connection.close()

            def execute(self, sql, parameters=()):
                if sql.startswith("UPDATE daily_runs SET state=?, error=?") and not self.changed_state:
                    self.changed_state = True
                    with closing(original_connect()) as concurrent, concurrent:
                        concurrent.execute("UPDATE daily_runs SET state='cleaning' WHERE id=?", (run.id,))
                return self.connection.execute(sql, parameters)

        with patch.object(self.store, "_connect", side_effect=lambda: InterleavingConnection(original_connect())):
            with self.assertRaisesRegex(InvalidTransition, "ready -> publishing"):
                self.store.transition(run.id, "publishing")

        self.assertEqual(self.store.get(run.id).state, "cleaning")

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

    def test_list_runs_returns_articles_in_date_order_without_mutating_them(self):
        later = self.store.claim("2026-07-11")
        earlier = self.store.claim("2026-07-10")
        self.store.transition(later.id, "scraping")
        self.store.transition(later.id, "rewriting")
        self.store.save_article(later.id, {"date": "2026-07-11", "markdown": "saved article"})

        runs = self.store.list_runs()

        self.assertEqual([run.date for run in runs], ["2026-07-10", "2026-07-11"])
        self.assertEqual(runs[1].article, {"date": "2026-07-11", "markdown": "saved article"})
        self.assertEqual(self.store.get(earlier.id).state, "queued")
        self.assertEqual(self.store.get(later.id).article, runs[1].article)

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
