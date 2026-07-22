import sys
import os
import tempfile
import unittest
from contextlib import closing
from datetime import date
from pathlib import Path
from unittest.mock import patch

import requests

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from ai_daily import cli
from ai_daily.content import ContentRetryExhaustedError
from ai_daily.cli import serve_preview
from ai_daily.daily_run import DailyRun
from ai_daily.scheduler import WindowsTasks
from ai_daily.storage import Store


class CliTests(unittest.TestCase):
    def test_scheduled_failure_reason_masks_configured_secrets(self):
        with patch.dict(os.environ, {"LLM_API_KEY": "private-key"}):
            reason = cli.safe_failure_reason(RuntimeError("LLM failed with private-key"))

        self.assertEqual(reason, "LLM failed with ***")

    def test_scheduled_failure_reason_names_the_current_wechat_whitelist_ip(self):
        reason = cli.safe_failure_reason(
            RuntimeError("Access token error 40164: invalid ip 138.199.22.133, not in whitelist")
        )

        self.assertIn("当前出口 IP：138.199.22.133", reason)
        self.assertIn("微信公众平台", reason)

    def test_scheduled_failure_reason_explains_a_source_dns_failure(self):
        reason = cli.safe_failure_reason(
            requests.ConnectionError(
                "HTTPSConnectionPool(host='aihot.virxact.com', port=443): "
                "NameResolutionError: Failed to resolve 'aihot.virxact.com' "
                "([Errno 11001] getaddrinfo failed)"
            )
        )

        self.assertIn("资讯源域名解析失败", reason)
        self.assertIn("网络、VPN 或 DNS", reason)

    def test_scheduled_daily_keeps_the_saved_uncertain_publication_reason(self):
        class Runner:
            def prepare(self, date_value, settings, retry=False):
                return type(
                    "Run",
                    (),
                    {
                        "date": date_value,
                        "state": "publication_uncertain",
                        "error": "微信 IP 白名单未包含当前出口 IP：138.199.22.133。",
                    },
                )()

        with self.assertRaisesRegex(cli.ScheduledDailyFailedError, "138.199.22.133"):
            cli.run_scheduled_daily(Runner(), "2026-07-17", {}, preview=False)

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
        notifications = []

        class Runner:
            def settings(self):
                return {"title": "stale title", "max_words": 150}

            def prepare(self, date_value, settings, retry=False):
                return type("Run", (), {"date": date_value, "state": "publication_uncertain"})()

            def publish(self, date_value):
                raise AssertionError("uncertain publication must not call publisher")

        with (
            patch.object(cli, "build_runner", return_value=Runner()),
            patch.object(cli, "show_scheduled_failure", side_effect=notifications.append, create=True),
            patch.object(sys, "argv", ["ai-daily", "daily"]),
        ):
            error = None
            try:
                cli.main()
            except Exception as exc:
                error = exc

        self.assertEqual(type(error).__name__, "ScheduledDailyFailedError")
        self.assertEqual(notifications, ["微信发布结果待确认，请检查草稿箱"])

    def test_scheduled_daily_retries_a_connection_failure_once_then_publishes(self):
        class Runner:
            def __init__(self):
                self.prepare_calls = 0
                self.publish_calls = 0

            def settings(self):
                return {"title": "stale title", "max_words": 150}

            def prepare(self, date_value, settings, retry=False):
                self.prepare_calls += 1
                if self.prepare_calls == 1:
                    raise RuntimeError("LLM connection failed")
                return type("Run", (), {"date": date_value, "state": "ready", "owner": True})()

            def publish(self, date_value):
                self.publish_calls += 1
                return type("Run", (), {"date": date_value, "state": "published"})()

        runner = Runner()
        with (
            patch.object(cli, "build_runner", return_value=runner),
            patch.object(sys, "argv", ["ai-daily", "daily"]),
        ):
            error = None
            try:
                cli.main()
            except Exception as exc:
                error = exc

        self.assertIsNone(error)
        self.assertEqual(runner.prepare_calls, 2)
        self.assertEqual(runner.publish_calls, 1)

    def test_scheduled_daily_waits_before_retrying_a_source_connection_failure(self):
        class Runner:
            def __init__(self):
                self.prepare_calls = 0

            def prepare(self, date_value, settings, retry=False):
                self.prepare_calls += 1
                if self.prepare_calls == 1:
                    raise requests.ConnectionError("temporary DNS failure")
                return type("Run", (), {"date": date_value, "state": "published", "owner": True})()

        runner = Runner()
        with patch("time.sleep") as sleep:
            run = cli.run_scheduled_daily(runner, "2026-07-22", {}, preview=False)

        self.assertEqual(run.state, "published")
        sleep.assert_called_once_with(60)

    def test_scheduled_daily_notifies_after_two_connection_failures(self):
        notifications = []

        class Runner:
            def __init__(self):
                self.prepare_calls = 0

            def settings(self):
                return {"title": "stale title", "max_words": 150}

            def prepare(self, date_value, settings, retry=False):
                self.prepare_calls += 1
                raise RuntimeError("LLM connection failed")

        runner = Runner()
        with (
            patch.object(cli, "build_runner", return_value=runner),
            patch.object(cli, "show_scheduled_failure", side_effect=notifications.append),
            patch.object(sys, "argv", ["ai-daily", "daily"]),
        ):
            error = None
            try:
                cli.main()
            except Exception as exc:
                error = exc

        self.assertEqual(type(error).__name__, "ScheduledDailyFailedError")
        self.assertEqual(runner.prepare_calls, 2)
        self.assertEqual(notifications, ["LLM connection failed"])

    def test_scheduled_daily_shows_one_windows_message_after_two_invalid_ai_responses(self):
        notifications = []

        class Runner:
            def settings(self):
                return {"title": "stale title", "max_words": 150}

            def prepare(self, date_value, settings, retry=False):
                raise ContentRetryExhaustedError("LLM 返回格式无效（已自动重试一次）")

        with (
            patch.object(cli, "build_runner", return_value=Runner()),
            patch.object(cli, "show_scheduled_retry_failure", create=True),
            patch.object(cli, "show_scheduled_failure", side_effect=notifications.append, create=True),
            patch.object(sys, "argv", ["ai_daily", "daily"]),
        ):
            error = None
            try:
                cli.main()
            except Exception as exc:
                error = exc

        self.assertEqual(type(error).__name__, "ScheduledDailyFailedError")
        self.assertEqual(len(notifications), 1)
        self.assertIn("LLM 返回格式无效", notifications[0])

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
                return type("Run", (), {"date": date_value, "state": "published"})()

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

    def test_scheduled_daily_rechecks_a_publishing_run_without_republishing_it(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "daily.db")
            run_date = date.today().isoformat()
            run = store.claim(run_date)
            store.transition(run.id, "scraping")
            store.transition(run.id, "rewriting")
            store.save_article(run.id, {"date": run_date, "markdown": "article", "items": []})
            store.begin_publication(run.id)
            publisher_calls = []
            runner = DailyRun(
                store,
                None,
                lambda article: publisher_calls.append(article) or "draft-1",
                settings={"title": "Daily", "max_words": 150},
            )

            with (
                patch.object(cli, "build_runner", return_value=runner),
                patch.object(sys, "argv", ["ai-daily", "daily"]),
                self.assertRaisesRegex(RuntimeError, "already active"),
            ):
                cli.main()

            self.assertEqual(publisher_calls, [])
            self.assertEqual(store.get(run.id).state, "publishing")
            with closing(store._connect()) as db, db:
                db.execute("UPDATE daily_runs SET updated_at=datetime('now', '-31 minutes') WHERE id=?", (run.id,))

            with (
                patch.object(cli, "build_runner", return_value=runner),
                patch.object(cli, "show_scheduled_failure"),
                patch.object(sys, "argv", ["ai-daily", "daily"]),
                self.assertRaisesRegex(RuntimeError, "发布结果待确认"),
            ):
                cli.main()

            self.assertEqual(publisher_calls, [])
            self.assertEqual(store.get(run.id).state, "publication_uncertain")
