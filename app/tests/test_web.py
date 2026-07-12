import sys
import unittest
import warnings
import gc
from pathlib import Path
from threading import Event

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from ai_daily.web import create_app


class Run:
    id = "run-1"
    date = "2026-07-10"
    state = "scraping"
    owner = True
    media_id = ""
    article = {"markdown": "article"}
    error = ""


class FakeRunner:
    def __init__(self):
        self.run = Run()
        self.executed = Event()
        self.values = {"title": "Daily", "max_words": 150}
        self.start_calls = []

    def start(self, date, settings, retry=False, fresh=False, resolve_uncertain=False):
        self.start_calls.append({"date": date, "retry": retry, "fresh": fresh, "resolve_uncertain": resolve_uncertain})
        return self.run

    def execute(self, run_id, date, settings):
        self.executed.set()
        return self.run

    def publish(self, date):
        self.run.state, self.run.media_id, self.run.article = "published", "draft-1", None
        return self.run

    def get(self, run_id):
        return self.run

    def events(self, run_id):
        return [{"stage": "scraping", "status": "progress", "message": "Fetching sources"}]

    def settings(self):
        return self.values.copy()

    def update_settings(self, values):
        self.values.update(values)
        return self.settings()


class FailingRunner:
    def start(self, date, settings, retry=False, fresh=False, resolve_uncertain=False):
        raise RuntimeError("source unavailable")


class ConfirmationRunner(FakeRunner):
    def start(self, date, settings, retry=False, fresh=False, resolve_uncertain=False):
        run = super().start(date, settings, retry, fresh, resolve_uncertain)
        if not resolve_uncertain:
            raise RuntimeError("发布结果待确认：请先在微信草稿箱核对")
        return run


class FakeTasks:
    def __init__(self):
        self.times = []

    def install(self, schedule_time):
        self.times.append(schedule_time)
        return {"installed": True, "task_name": "AI Daily Publisher"}

    def status(self):
        return {"installed": True, "task_name": "AI Daily Publisher"}


class WebTests(unittest.TestCase):
    def test_prepare_failure_is_json_not_html(self):
        response = create_app(FailingRunner()).test_client().post("/api/runs", json={"date": "2026-07-10"})
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.get_json()["error"], "source unavailable")

    def test_home_page_uses_original_editorial_shell_without_remote_fonts(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", ResourceWarning)
            response = create_app(FakeRunner()).test_client().get("/")
            status_code = response.status_code
            page = response.data
            del response
            gc.collect()
        self.assertEqual(status_code, 200)
        self.assertIn(b"AI Daily", page)
        self.assertIn(b'<aside class="controls"', page)
        self.assertNotIn(b"fonts.googleapis.com", page)
        self.assertFalse(any(item.category is ResourceWarning for item in caught))

    def test_home_page_versions_the_browser_script(self):
        page = create_app(FakeRunner()).test_client().get("/").data

        self.assertIn(b'/static/app.js?v=', page)

    def test_prepare_starts_a_background_run_and_returns_its_persisted_id(self):
        runner = FakeRunner()
        response = create_app(runner).test_client().post("/api/runs", json={"date": "2026-07-10"})
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.get_json()["id"], "run-1")
        self.assertEqual(response.get_json()["state"], "scraping")
        self.assertTrue(runner.start_calls[0]["fresh"])
        self.assertTrue(runner.executed.wait(1))

    def test_prepare_requires_explicit_confirmation_before_replacing_an_uncertain_publication(self):
        runner = ConfirmationRunner()
        client = create_app(runner).test_client()

        rejected = client.post("/api/runs", json={"date": "2026-07-10"})

        self.assertEqual(rejected.status_code, 409)
        self.assertEqual(rejected.get_json()["state"], "publication_uncertain")
        self.assertIn("发布结果待确认", rejected.get_json()["error"])
        self.assertFalse(runner.executed.is_set())

        text_flag = client.post("/api/runs", json={"date": "2026-07-10", "resolve_uncertain": "false"})

        self.assertEqual(text_flag.status_code, 409)
        self.assertFalse(runner.start_calls[-1]["resolve_uncertain"])

        confirmed = client.post("/api/runs", json={"date": "2026-07-10", "resolve_uncertain": True})

        self.assertEqual(confirmed.status_code, 202)
        self.assertTrue(runner.start_calls[-1]["resolve_uncertain"])
        self.assertTrue(runner.executed.wait(1))

    def test_read_returns_persisted_events_for_the_same_run(self):
        response = create_app(FakeRunner()).test_client().get("/api/runs/run-1")
        self.assertEqual(response.get_json()["events"][0]["stage"], "scraping")

    def test_settings_api_reads_and_saves_the_same_runner_settings(self):
        client = create_app(FakeRunner()).test_client()
        self.assertEqual(client.get("/api/config").get_json()["max_words"], 150)
        self.assertEqual(client.post("/api/config", json={"max_words": 200}).get_json()["max_words"], 200)

    def test_schedule_api_installs_task_before_persisting_schedule_time(self):
        runner = FakeRunner()
        tasks = FakeTasks()
        client = create_app(runner, tasks=tasks).test_client()

        response = client.post("/api/schedule", json={"schedule_time": "09:30"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(tasks.times, ["09:30"])
        self.assertEqual(runner.values["schedule_time"], "09:30")
        self.assertTrue(response.get_json()["installed"])

    def test_schedule_api_returns_json_when_task_helper_is_unavailable(self):
        response = create_app(FakeRunner()).test_client().post("/api/schedule", json={"schedule_time": "09:30"})

        self.assertEqual(response.status_code, 501)
        self.assertIn("Windows", response.get_json()["error"])

    def test_browser_uses_schedule_endpoint_for_time_save(self):
        script = create_app(FakeRunner()).test_client().get("/static/app.js").data

        self.assertIn(b'requestJson("/api/schedule"', script)

    def test_browser_warns_when_a_same_named_schedule_task_needs_updating(self):
        script = create_app(FakeRunner()).test_client().get("/static/app.js").data

        self.assertIn(b"loadScheduleStatus", script)
        self.assertIn(b"configured === false", script)

    def test_browser_syncs_the_calendar_to_the_restored_run_date(self):
        script = create_app(FakeRunner()).test_client().get("/static/app.js").data

        self.assertIn(b"state.selectedDate = run.date;", script)
        self.assertIn(b"renderCalendar(restored.getFullYear(), restored.getMonth());", script)

    def test_browser_script_uses_persisted_runs_instead_of_legacy_pipeline_endpoints(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", ResourceWarning)
            response = create_app(FakeRunner()).test_client().get("/static/app.js")
            script = response.data
            del response
            gc.collect()
        self.assertIn(b"/api/runs", script)
        self.assertNotIn(b"/api/fetch", script)
        self.assertIn(b"textContent", script)
        self.assertIn(b"localStorage", script)
        self.assertFalse(any(item.category is ResourceWarning for item in caught))

    def test_publish_uses_the_same_persisted_run(self):
        client = create_app(FakeRunner()).test_client()
        response = client.post("/api/runs/run-1/publish", json={"date": "2026-07-10"})
        payload = response.get_json()
        self.assertEqual(payload["state"], "published")
        self.assertEqual(payload["media_id"], "draft-1")
        self.assertIsNone(payload["article"])

    def test_browser_clears_local_content_after_a_published_empty_response(self):
        script = create_app(FakeRunner()).test_client().get("/static/app.js").data

        self.assertIn(b'run.state === "published" && !run.article', script)
        self.assertIn(b'stopPolling();\n      state.run = null;', script)
        self.assertIn(b'localStorage.removeItem("ai-daily-run-id");', script)
        self.assertIn(b'renderArticle(null);', script)
        self.assertIn(b'renderCover(null);', script)
        self.assertIn(b'$("btnFetch").disabled = false;', script)
        self.assertIn("微信草稿已创建，本地内容已清理".encode(), script)

    def test_browser_restore_drops_a_deleted_run_and_returns_to_idle(self):
        script = create_app(FakeRunner()).test_client().get("/static/app.js").data

        self.assertIn(b"error.status = response.status;", script)
        self.assertIn(b"async function restoreRun() {", script)
        self.assertIn(b"if (error.status === 404)", script)
        self.assertIn(b'state.runId = "";', script)
        self.assertIn(b'localStorage.removeItem("ai-daily-run-id");', script)
        self.assertIn(b'setStatus("idle",', script)

    def test_browser_marks_uncertain_publication_and_requests_confirmation(self):
        script = create_app(FakeRunner()).test_client().get("/static/app.js").data

        self.assertIn(b'run.state === "publication_uncertain"', script)
        self.assertIn("发布结果待确认".encode(), script)
        self.assertIn(b"window.confirm(", script)
        self.assertIn(b"resolve_uncertain: resolveUncertain", script)
