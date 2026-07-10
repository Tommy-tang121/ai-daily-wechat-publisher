import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from ai_daily.web import create_app


class Run:
    id = "run-1"
    state = "ready"
    media_id = ""
    article = {"markdown": "article"}
    error = ""


class FakeRunner:
    def __init__(self): self.run = Run()
    def prepare(self, date, settings, retry=False): return self.run
    def publish(self, date): self.run.state, self.run.media_id = "published", "draft-1"; return self.run
    def get(self, run_id): return self.run


class FailingRunner:
    def prepare(self, date, settings, retry=False):
        raise RuntimeError("source unavailable")


class WebTests(unittest.TestCase):
    def test_prepare_failure_is_json_not_html(self):
        response = create_app(FailingRunner()).test_client().post("/api/runs", json={"date": "2026-07-10"})
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.get_json()["error"], "source unavailable")

    def test_home_page_is_available(self):
        response = create_app(FakeRunner()).test_client().get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"AI Daily", response.data)

    def test_prepare_and_publish_use_the_same_persisted_run(self):
        client = create_app(FakeRunner()).test_client()
        prepared = client.post("/api/runs", json={"date": "2026-07-10"}).get_json()
        self.assertEqual(prepared["state"], "ready")
        self.assertEqual(client.post("/api/runs/run-1/publish", json={"date": "2026-07-10"}).get_json()["media_id"], "draft-1")
