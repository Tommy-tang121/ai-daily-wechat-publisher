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

    def test_claim_fresh_never_discards_existing_runs(self):
        for state in ("ready", "failed", "published"):
            with self.subTest(state=state):
                date = f"2026-07-{11 + len(state)}"
                old = self.store.claim(date)
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
                # This test protects claim_fresh only. Insert a pre-existing
                # legacy event directly because terminal states now reject
                # late worker events by design.
                with closing(self.store._connect()) as db, db:
                    db.execute(
                        "INSERT INTO run_events(run_id, stage, status, message) VALUES (?, ?, ?, ?)",
                        (old.id, "scraping", "progress", "Old run"),
                    )

                fresh = self.store.claim_fresh(date)

                self.assertFalse(fresh.owner)
                self.assertEqual(fresh.id, old.id)
                self.assertEqual(fresh.state, state)
                self.assertEqual(fresh.media_id, "media-1" if state == "published" else "")
                self.assertEqual(fresh.article, {"markdown": "article"} if state in {"ready", "published"} else None)
                with closing(self.store._connect()) as db:
                    self.assertIsNotNone(db.execute("SELECT 1 FROM run_events WHERE run_id=?", (old.id,)).fetchone())

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
        self.store.begin_cleanup("test-owner")

        claimed = self.store.claim_fresh("2026-07-29")

        self.assertFalse(claimed.owner)
        self.assertEqual(claimed.id, run.id)
        self.assertEqual(claimed.state, "cleaning")

    def test_begin_cleanup_strips_content_events_and_moves_cover_to_private_metadata(self):
        run = self.store.claim("2026-07-10")
        self.store.transition(run.id, "scraping")
        self.store.transition(run.id, "rewriting")
        self.store.save_article(
            run.id,
            {"markdown": "private article", "cover_path": "C:/covers/2026-07-10.png"},
        )
        self.store.record_event(run.id, "done", "complete", "private progress")
        self.store.transition(run.id, "publishing")
        self.store.mark_published(run.id, "draft-1")

        runs = self.store.begin_cleanup("cleanup-owner")

        self.assertEqual(runs[0].state, "cleaning")
        self.assertIsNone(runs[0].article)
        self.assertEqual(runs[0].media_id, "draft-1")
        retained = self.store.get(run.id)
        self.assertEqual(retained.state, "cleaning")
        self.assertIsNone(retained.article)
        self.assertEqual(retained.media_id, "draft-1")
        self.assertEqual(self.store.events(run.id), [])
        self.assertEqual(self.store.pending_cover_cleanup(run.id), {"cover_path": "C:/covers/2026-07-10.png"})

    def test_begin_cleanup_blocks_recent_active_states(self):
        for state in ("queued", "scraping", "rewriting", "publishing"):
            with self.subTest(state=state):
                store = Store(Path(self._tmp.name) / f"{state}.db")
                run = store.claim("2026-07-10")
                if state in {"scraping", "rewriting", "publishing"}:
                    store.transition(run.id, "scraping")
                if state in {"rewriting", "publishing"}:
                    store.transition(run.id, "rewriting")
                if state == "publishing":
                    store.save_article(run.id, {"markdown": "article"})
                    store.begin_publication(run.id)

                with self.assertRaisesRegex(RuntimeError, "active"):
                    store.begin_cleanup("cleanup-owner")

                self.assertEqual(store.get(run.id).state, state)

    def test_begin_cleanup_converges_stale_active_states_without_retaining_content(self):
        for state in ("queued", "scraping", "rewriting", "publishing"):
            with self.subTest(state=state):
                store = Store(Path(self._tmp.name) / f"stale-{state}.db")
                run = store.claim("2026-07-10")
                if state in {"scraping", "rewriting", "publishing"}:
                    store.transition(run.id, "scraping")
                if state in {"rewriting", "publishing"}:
                    store.transition(run.id, "rewriting")
                if state == "publishing":
                    store.save_article(run.id, {"markdown": "article", "cover_path": "C:/covers/2026-07-10.png"})
                    store.begin_publication(run.id)
                else:
                    store.record_event(run.id, "scraping", "progress", "legacy progress")
                with closing(store._connect()) as db, db:
                    db.execute("UPDATE daily_runs SET updated_at=datetime('now', '-31 minutes') WHERE id=?", (run.id,))

                runs = store.begin_cleanup("cleanup-owner")

                self.assertEqual(runs[0].state, "cleaning")
                self.assertIsNone(runs[0].article)
                self.assertEqual(store.get(run.id).state, "cleaning")
                self.assertIsNone(store.get(run.id).article)
                self.assertEqual(store.events(run.id), [])

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

    def test_retry_cannot_replace_a_cleanup_state_changed_after_its_read(self):
        run = self.store.claim("2026-07-10")
        self.store.transition(run.id, "failed", "temporary error")
        original_connect = self.store._connect
        concurrent_store = Store(self.temp)

        class InterleavingConnection:
            def __init__(self, connection):
                self.connection = connection
                self.started_cleanup = False

            def __enter__(self):
                self.connection.__enter__()
                return self

            def __exit__(self, *args):
                return self.connection.__exit__(*args)

            def close(self):
                self.connection.close()

            def execute(self, sql, parameters=()):
                if sql.startswith("UPDATE daily_runs SET state=?, error='', updated_at=") and not self.started_cleanup:
                    self.started_cleanup = True
                    concurrent_store.begin_cleanup("cleanup-owner")
                return self.connection.execute(sql, parameters)

        with patch.object(self.store, "_connect", side_effect=lambda: InterleavingConnection(original_connect())):
            retried = self.store.retry(run.id)

        self.assertEqual(retried.state, "cleaning")
        self.assertFalse(retried.owner)
        self.assertEqual(self.store.get(run.id).state, "cleaning")

    def test_events_are_persisted_in_the_order_they_happened(self):
        run = self.store.claim("2026-07-10")
        self.store.transition(run.id, "scraping")
        self.store.record_event(run.id, "scraping", "progress", "Fetching sources")
        self.store.transition(run.id, "rewriting")
        self.store.record_event(run.id, "rewriting", "progress", "Rewriting batch 1 of 3")
        self.assertEqual(
            self.store.events(run.id),
            [
                {"stage": "scraping", "status": "progress", "message": "Fetching sources"},
                {"stage": "rewriting", "status": "progress", "message": "Rewriting batch 1 of 3"},
            ],
        )

    def test_active_event_refreshes_stale_timeout_for_safe_reclaim(self):
        run = self.store.claim("2026-07-10")
        self.store.transition(run.id, "scraping")
        with closing(self.store._connect()) as db, db:
            db.execute("UPDATE daily_runs SET updated_at=datetime('now', '-31 minutes') WHERE id=?", (run.id,))

        recorded = self.store.record_event(run.id, "scraping", "progress", "Still fetching")
        reclaimed = self.store.reclaim_stale(run.id, minutes=30)

        self.assertTrue(recorded)
        self.assertEqual(reclaimed.state, "scraping")
        self.assertFalse(reclaimed.owner)

    def test_queued_event_cannot_renew_an_unstarted_run(self):
        run = self.store.claim("2026-07-10")
        with closing(self.store._connect()) as db, db:
            db.execute("UPDATE daily_runs SET updated_at=datetime('now', '-31 minutes') WHERE id=?", (run.id,))

        recorded = self.store.record_event(run.id, "scraping", "progress", "late worker event")
        reclaimed = self.store.reclaim_stale(run.id, minutes=30)

        self.assertFalse(recorded)
        self.assertEqual(self.store.events(run.id), [])
        self.assertTrue(reclaimed.owner)

    def test_record_event_ignores_a_cleaning_run(self):
        run = self.store.claim("2026-07-10")
        self.store.transition(run.id, "failed", "source unavailable")
        self.store.begin_cleanup("cleanup-owner")

        recorded = self.store.record_event(run.id, "error", "error", "late worker event")

        self.assertFalse(recorded)
        self.assertEqual(self.store.events(run.id), [])

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

    def test_stale_publishing_run_is_not_requeued(self):
        run = self.store.claim("2026-07-10")
        self.store.transition(run.id, "scraping")
        self.store.transition(run.id, "rewriting")
        self.store.save_article(run.id, {"markdown": "article"})
        self.store.transition(run.id, "publishing")
        with closing(self.store._connect()) as db, db:
            db.execute("UPDATE daily_runs SET updated_at=datetime('now', '-31 minutes') WHERE id=?", (run.id,))

        reclaimed = self.store.reclaim_stale(run.id, minutes=30)

        self.assertFalse(reclaimed.owner)
        self.assertEqual(reclaimed.state, "publishing")

    def test_publishing_run_cannot_be_returned_to_a_retryable_state(self):
        run = self.store.claim("2026-07-10")
        self.store.transition(run.id, "scraping")
        self.store.transition(run.id, "rewriting")
        self.store.save_article(run.id, {"markdown": "article"})
        publishing, _ = self.store.begin_publication(run.id)

        with self.assertRaisesRegex(InvalidTransition, "publishing -> ready"):
            self.store.transition(publishing.id, "ready")
        with self.assertRaisesRegex(InvalidTransition, "publishing -> failed"):
            self.store.transition(publishing.id, "failed", "publisher unavailable")

        retained = self.store.get(publishing.id)
        self.assertEqual(retained.state, "publishing")
        self.assertIsNone(retained.article)

    def test_publication_uncertain_discards_article_receipt_and_events(self):
        run = self.store.claim("2026-07-10")
        self.store.transition(run.id, "scraping")
        self.store.transition(run.id, "rewriting")
        self.store.save_article(run.id, {"markdown": "article", "cover_path": "C:/covers/2026-07-10.png"})
        self.store.record_event(run.id, "done", "complete", "ready")
        self.store.transition(run.id, "publishing")

        uncertain = self.store.mark_publication_uncertain(run.id, "发布结果待确认")

        self.assertEqual(uncertain.state, "publication_uncertain")
        self.assertEqual(uncertain.error, "发布结果待确认")
        self.assertEqual(uncertain.media_id, "")
        self.assertIsNone(uncertain.article)
        self.assertEqual(self.store.events(run.id), [])
