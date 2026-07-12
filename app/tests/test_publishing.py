import sys
import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from ai_daily.publishing import WeChatPublisher, build_wechat_command


class PublishingTests(unittest.TestCase):
    def test_delete_draft_requests_token_then_deletes_the_draft(self):
        with (
            patch.dict(os.environ, {"WECHAT_APP_ID": "app-id", "WECHAT_APP_SECRET": "app-secret"}, clear=True),
            patch("requests.get") as get,
            patch("requests.post") as post,
        ):
            get.return_value.json.return_value = {"access_token": "access-token"}
            post.return_value.json.return_value = {"errcode": 0}

            WeChatPublisher("title").delete_draft("draft-media-id")

        get.assert_called_once_with(
            "https://api.weixin.qq.com/cgi-bin/token",
            params={"grant_type": "client_credential", "appid": "app-id", "secret": "app-secret"},
            timeout=(15, 30),
        )
        post.assert_called_once_with(
            "https://api.weixin.qq.com/cgi-bin/draft/delete",
            params={"access_token": "access-token"},
            json={"media_id": "draft-media-id"},
            timeout=(15, 30),
        )

    def test_delete_draft_refuses_when_wechat_credentials_are_missing(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "微信"):
                WeChatPublisher("title").delete_draft("draft-media-id")

    def test_delete_draft_reports_a_safe_token_error(self):
        secret = "app-secret"
        with (
            patch.dict(os.environ, {"WECHAT_APP_ID": "app-id", "WECHAT_APP_SECRET": secret}, clear=True),
            patch("requests.get") as get,
        ):
            get.return_value.json.return_value = {"errcode": 40013, "errmsg": f"bad token {secret}"}

            with self.assertRaisesRegex(RuntimeError, "40013") as raised:
                WeChatPublisher("title").delete_draft("draft-media-id")

        self.assertNotIn(secret, str(raised.exception))
        self.assertNotIn("draft-media-id", str(raised.exception))

    def test_delete_draft_reports_a_safe_delete_error(self):
        with (
            patch.dict(os.environ, {"WECHAT_APP_ID": "app-id", "WECHAT_APP_SECRET": "app-secret"}, clear=True),
            patch("requests.get") as get,
            patch("requests.post") as post,
        ):
            get.return_value.json.return_value = {"access_token": "access-token"}
            post.return_value.json.return_value = {"errcode": 45009, "errmsg": "bad draft-media-id"}

            with self.assertRaisesRegex(RuntimeError, "45009") as raised:
                WeChatPublisher("title").delete_draft("draft-media-id")

        self.assertNotIn("draft-media-id", str(raised.exception))

    def test_delete_draft_treats_an_already_absent_draft_as_success(self):
        with (
            patch.dict(os.environ, {"WECHAT_APP_ID": "app-id", "WECHAT_APP_SECRET": "app-secret"}, clear=True),
            patch("requests.get") as get,
            patch("requests.post") as post,
        ):
            get.return_value.json.return_value = {"access_token": "access-token"}
            post.return_value.json.return_value = {"errcode": 40007, "errmsg": "invalid media_id"}

            WeChatPublisher("title").delete_draft("draft-media-id")

    def test_delete_draft_keeps_other_wechat_errors_visible(self):
        with (
            patch.dict(os.environ, {"WECHAT_APP_ID": "app-id", "WECHAT_APP_SECRET": "app-secret"}, clear=True),
            patch("requests.get") as get,
            patch("requests.post") as post,
        ):
            get.return_value.json.return_value = {"access_token": "access-token"}
            post.return_value.json.return_value = {"errcode": 45009, "errmsg": "rate limit"}

            with self.assertRaisesRegex(RuntimeError, "45009"):
                WeChatPublisher("title").delete_draft("draft-media-id")

    def test_command_disables_automatic_link_citations(self):
        command = build_wechat_command("bun", Path("article.md"), "title", "cover.png", "author")
        self.assertIn("--no-cite", command)
        self.assertIn("--theme", command)

    def test_publisher_reuses_the_cover_persisted_with_the_ready_run(self):
        article = {"date": "2026-07-10", "markdown": "article", "cover_path": "C:/covers/2026-07-10.png"}
        completed = SimpleNamespace(returncode=0, stdout='{"success":true,"media_id":"draft-1"}', stderr="")
        with patch("ai_daily.publishing.shutil.which", return_value="bun"), patch("ai_daily.publishing.subprocess.run", return_value=completed) as run:
            self.assertEqual(WeChatPublisher("title")(article), "draft-1")
        command = run.call_args.args[0]
        self.assertEqual(command[command.index("--cover") + 1], article["cover_path"])
        self.assertEqual(run.call_args.kwargs.get("encoding"), "utf-8")

    def test_publisher_uses_the_title_persisted_with_the_article(self):
        article = {"date": "2026-07-10", "title": "AI 行业热点新闻 | 2026-07-10", "markdown": "article", "cover_path": "C:/covers/2026-07-10.png"}
        completed = SimpleNamespace(returncode=0, stdout='{"success":true,"media_id":"draft-1"}', stderr="")
        with patch("ai_daily.publishing.shutil.which", return_value="bun"), patch("ai_daily.publishing.subprocess.run", return_value=completed) as run:
            WeChatPublisher("stale title")(article)

        command = run.call_args.args[0]
        self.assertEqual(command[command.index("--title") + 1], article["title"])

    def test_publisher_reports_the_real_script_error_after_progress_logs(self):
        article = {"date": "2026-07-10", "markdown": "article", "cover_path": "C:/covers/2026-07-10.png"}
        completed = SimpleNamespace(returncode=1, stdout="", stderr=("progress\n" * 100) + "根本原因")
        with patch("ai_daily.publishing.shutil.which", return_value="bun"), patch("ai_daily.publishing.subprocess.run", return_value=completed):
            with self.assertRaisesRegex(RuntimeError, "根本原因"):
                WeChatPublisher("title")(article)
