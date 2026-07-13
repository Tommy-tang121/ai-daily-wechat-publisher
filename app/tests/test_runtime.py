import os
import sys
import tempfile
import unittest
import json
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from ai_daily.runtime import OpenAiCompatibleLlm, build_runner, load_environment
from ai_daily.publishing import WeChatPublisher


class RuntimeTests(unittest.TestCase):
    def test_app_env_overrides_legacy_root_env(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env").write_text("VALUE=legacy\n", encoding="utf-8")
            (root / "app").mkdir()
            (root / "app" / ".env").write_text("VALUE=app\n", encoding="utf-8")
            previous = os.environ.pop("VALUE", None)
            self.addCleanup(lambda: previous and os.environ.__setitem__("VALUE", previous))
            load_environment(root / "app")
            self.assertEqual(os.environ["VALUE"], "app")

    def test_llm_connection_error_is_reported_without_being_a_format_error(self):
        import requests
        with patch.dict(os.environ, {"LLM_API_KEY": "test"}), patch("requests.post", side_effect=requests.ConnectionError("closed")), patch("time.sleep"):
            with self.assertRaisesRegex(RuntimeError, "LLM"):
                OpenAiCompatibleLlm()([])

    def test_runtime_runner_has_a_cover_factory_for_ready_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            app_dir = Path(directory) / "app"
            app_dir.mkdir()
            self.assertTrue(callable(build_runner(app_dir, preview_only=True).cover))

    def test_runtime_cleanup_deletes_only_an_existing_cover_in_static_covers(self):
        with tempfile.TemporaryDirectory() as directory:
            app_dir = Path(directory) / "app"
            covers = app_dir / "static" / "covers"
            covers.mkdir(parents=True)
            inside = covers / "inside.png"
            outside = app_dir / "outside.png"
            inside.write_text("inside", encoding="utf-8")
            outside.write_text("outside", encoding="utf-8")

            cleanup = build_runner(app_dir, preview_only=True).cleanup
            cleanup({"cover_path": str(inside)})
            cleanup({"cover_path": str(outside)})
            cleanup({"cover_path": str(covers / "missing.png")})

            self.assertFalse(inside.exists())
            self.assertTrue(outside.exists())

    def test_runtime_history_cleanup_removes_only_the_runtime_cover_for_its_date(self):
        with tempfile.TemporaryDirectory() as directory:
            app_dir = Path(directory) / "app"
            covers = app_dir / "static" / "covers"
            covers.mkdir(parents=True)
            runtime_cover = covers / "2026-07-07.png"
            reference_cover = covers / "2026-07-07-published.png"
            runtime_cover.write_text("runtime", encoding="utf-8")
            reference_cover.write_text("reference", encoding="utf-8")

            build_runner(app_dir, preview_only=True).cleanup_date("2026-07-07")

            self.assertFalse(runtime_cover.exists())
            self.assertTrue(reference_cover.exists())

    def test_formal_runner_uses_the_wechat_publisher_directly(self):
        with tempfile.TemporaryDirectory() as directory:
            app_dir = Path(directory) / "app"
            app_dir.mkdir()

            self.assertIsInstance(build_runner(app_dir).publisher, WeChatPublisher)

    def test_legacy_config_migration_keeps_only_known_non_secret_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            app_dir = Path(directory) / "app"
            (app_dir / "data").mkdir(parents=True)
            (app_dir / "data" / "config.json").write_text(
                json.dumps({"title": "Migrated", "max_words": 200, "LLM_API_KEY": "must-not-persist"}),
                encoding="utf-8",
            )

            values = build_runner(app_dir, preview_only=True).settings()

        self.assertEqual(values["title"], "Migrated")
        self.assertEqual(values["max_words"], 200)
        self.assertNotIn("LLM_API_KEY", values)
