import sys
import unittest
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

    def test_scheduled_daily_command_explicitly_retries_a_failed_date(self):
        captured = {}

        class Runner:
            def prepare(self, date_value, settings, retry=False):
                captured["retry"] = retry
                return type("Run", (), {"date": date_value})()

        with (
            patch.object(cli, "build_runner", return_value=Runner()),
            patch.object(sys, "argv", ["ai-daily", "daily", "--preview"]),
        ):
            cli.main()

        self.assertTrue(captured["retry"])
