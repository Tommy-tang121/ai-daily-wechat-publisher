import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from ai_daily import cli
from ai_daily.cli import serve_preview
from ai_daily.scheduler import WindowsTasks


class CliTests(unittest.TestCase):
    def test_preview_uses_flask_fallback_when_waitress_is_unavailable(self):
        seen = []
        serve_preview(object(), lambda app: seen.append(app))
        self.assertEqual(len(seen), 1)

    def test_web_injects_windows_task_helper_with_scheduled_script(self):
        captured = {}

        def create_web(runner, tasks):
            captured["runner"] = runner
            captured["tasks"] = tasks
            return object()

        with (
            patch.object(cli, "build_runner", return_value=object()),
            patch.object(cli, "create_app", side_effect=create_web),
            patch.object(cli, "serve_preview"),
            patch.object(sys, "argv", ["ai_daily", "web", "--preview"]),
        ):
            cli.main()

        self.assertIsInstance(captured["tasks"], WindowsTasks)
        self.assertEqual(captured["tasks"].script.name, "run_scheduled.bat")

    def test_cleanup_history_uses_the_formal_runner_and_prints_only_safe_summary(self):
        built = []
        printed = []

        class Publisher:
            def delete_draft(self, media_id):
                self.deleted = media_id

        class Runner:
            publisher = Publisher()

            def clear_history(self, delete_draft):
                delete_draft("draft-1")
                return {"count": 2, "dates": ["2026-07-10", "2026-07-11"]}

        runner = Runner()
        with (
            patch.object(cli, "build_runner", side_effect=lambda app_dir, preview: built.append(preview) or runner),
            patch.object(sys, "argv", ["ai-daily", "cleanup-history"]),
            patch("builtins.print", side_effect=printed.append),
        ):
            cli.main()

        self.assertEqual(built, [False])
        self.assertEqual(runner.publisher.deleted, "draft-1")
        self.assertIn("2", printed[0])
        self.assertIn("2026-07-10", printed[0])
        self.assertNotIn("draft-1", printed[0])

    def test_cleanup_history_rejects_preview_mode(self):
        with (
            patch.object(cli, "build_runner") as build_runner,
            patch.object(sys, "argv", ["ai-daily", "cleanup-history", "--preview"]),
            self.assertRaisesRegex(RuntimeError, "formal"),
        ):
            cli.main()

        build_runner.assert_not_called()

    def test_cleanup_history_requires_a_draft_deleter(self):
        class Runner:
            publisher = lambda article: "draft-1"

        with (
            patch.object(cli, "build_runner", return_value=Runner()),
            patch.object(sys, "argv", ["ai-daily", "cleanup-history"]),
            self.assertRaisesRegex(RuntimeError, "draft deletion"),
        ):
            cli.main()

    def test_scheduled_daily_command_explicitly_retries_a_failed_date(self):
        captured = {}

        class Runner:
            def settings(self):
                return {"title": "stale title", "max_words": 150}

            def prepare(self, date_value, settings, retry=False):
                captured["retry"] = retry
                captured["settings"] = settings
                return type("Run", (), {"date": date_value})()

        with (
            patch.object(cli, "build_runner", return_value=Runner()),
            patch.object(sys, "argv", ["ai-daily", "daily", "--preview"]),
        ):
            cli.main()

        self.assertTrue(captured["retry"])
        self.assertEqual(captured["settings"].get("title"), f"AI 行业热点新闻 | {date.today().isoformat()}")

    def test_scheduled_daily_does_not_publish_an_uncertain_publication(self):
        class Runner:
            def settings(self):
                return {"title": "stale title", "max_words": 150}

            def prepare(self, date_value, settings, retry=False):
                return type("Run", (), {"date": date_value, "state": "publication_uncertain"})()

            def publish(self, date_value):
                raise AssertionError("uncertain publication must not call publisher")

        with (
            patch.object(cli, "build_runner", return_value=Runner()),
            patch.object(sys, "argv", ["ai-daily", "daily"]),
        ):
            cli.main()

    def test_scheduled_daily_finishes_pending_finalization_cleanup(self):
        class Runner:
            def __init__(self):
                self.publish_calls = []

            def settings(self):
                return {"title": "stale title", "max_words": 150}

            def prepare(self, date_value, settings, retry=False):
                return type("Run", (), {"date": date_value, "state": "finalizing"})()

            def publish(self, date_value):
                self.publish_calls.append(date_value)

        runner = Runner()
        with (
            patch.object(cli, "build_runner", return_value=runner),
            patch.object(sys, "argv", ["ai-daily", "daily"]),
        ):
            cli.main()

        self.assertEqual(len(runner.publish_calls), 1)

    def test_scheduled_daily_reports_a_recent_non_owner_run_for_task_scheduler_retry(self):
        class Runner:
            def settings(self):
                return {"title": "stale title", "max_words": 150}

            def prepare(self, date_value, settings, retry=False):
                return type("Run", (), {"date": date_value, "state": "queued", "owner": False})()

            def publish(self, date_value):
                raise AssertionError("a non-owner run must not be published twice")

        with (
            patch.object(cli, "build_runner", return_value=Runner()),
            patch.object(sys, "argv", ["ai-daily", "daily"]),
            self.assertRaisesRegex(RuntimeError, "already active"),
        ):
            cli.main()
