from dataclasses import asdict, is_dataclass
import mimetypes
from pathlib import Path
from threading import Thread

from flask import Flask, abort, jsonify, request


def _payload(run):
    if is_dataclass(run):
        return asdict(run)
    return {
        key: getattr(run, key, None)
        for key in ("id", "state", "media_id", "article", "error", "owner")
    }


def create_app(runner, settings=None, tasks=None):
    app_dir = Path(__file__).resolve().parents[2]
    app = Flask(__name__, static_folder=None)
    settings = settings or {}

    def current_settings():
        return runner.settings() if hasattr(runner, "settings") else settings

    def file_response(directory: Path, filename: str):
        root = directory.resolve()
        target = (root / filename).resolve()
        if not target.is_relative_to(root) or not target.is_file():
            abort(404)
        mimetype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        return app.response_class(target.read_bytes(), mimetype=mimetype)

    @app.get("/")
    def index():
        script_version = (app_dir / "static" / "app.js").stat().st_mtime_ns
        page = (app_dir / "templates" / "index.html").read_text(encoding="utf-8")
        return app.response_class(
            page.replace("/static/app.js", f"/static/app.js?v={script_version}"),
            mimetype="text/html",
        )

    @app.get("/static/<path:filename>")
    def static_files(filename):
        return file_response(app_dir / "static", filename)

    @app.get("/fonts/<path:filename>")
    def fonts(filename):
        return file_response(app_dir / "fonts", filename)

    @app.get("/api/config")
    def read_config():
        return jsonify(current_settings())

    @app.post("/api/config")
    def update_config():
        values = request.get_json(silent=True) or {}
        if not values:
            return jsonify(error="没有可保存的设置"), 400
        if not hasattr(runner, "update_settings"):
            return jsonify(error="当前运行环境不支持保存设置"), 501
        return jsonify(runner.update_settings(values))

    @app.get("/api/schedule")
    def read_schedule():
        if tasks is None:
            return jsonify(error="Windows 计划任务不可用"), 501
        try:
            return jsonify(tasks.status())
        except Exception as exc:
            return jsonify(error=str(exc)), 502

    @app.post("/api/schedule")
    def save_schedule():
        schedule_time = (request.get_json(silent=True) or {}).get("schedule_time")
        if not schedule_time:
            return jsonify(error="请选择定时时间"), 400
        if tasks is None:
            return jsonify(error="Windows 计划任务不可用"), 501
        try:
            result = tasks.install(schedule_time)
            if not hasattr(runner, "update_settings"):
                return jsonify(error="当前运行环境不支持保存设置"), 501
            runner.update_settings({"schedule_time": schedule_time})
            return jsonify(result)
        except Exception as exc:
            return jsonify(error=str(exc)), 409

    @app.post("/api/runs")
    def prepare():
        body = request.get_json(silent=True) or {}
        date = body.get("date")
        if not date:
            return jsonify(error="请选择日期"), 400
        try:
            run_settings = current_settings()
            run = runner.start(
                date,
                run_settings,
                retry=bool(body.get("retry")),
                fresh=True,
                resolve_uncertain=body.get("resolve_uncertain") is True,
            )
        except Exception as exc:
            if "发布结果待确认" in str(exc):
                return jsonify(error=str(exc), state="publication_uncertain"), 409
            return jsonify(error=str(exc)), 502
        if getattr(run, "owner", False):
            Thread(target=runner.execute, args=(run.id, date, run_settings), daemon=True).start()
        return jsonify(_payload(run)), 202

    @app.get("/api/runs/<run_id>")
    def read(run_id):
        try:
            payload = _payload(runner.get(run_id))
            payload["events"] = runner.events(run_id)
            return jsonify(payload)
        except KeyError:
            return jsonify(error="运行记录不存在"), 404

    @app.post("/api/runs/<run_id>/publish")
    def publish(run_id):
        body = request.get_json(silent=True) or {}
        date = body.get("date")
        if not date:
            return jsonify(error="请选择日期"), 400
        try:
            run = runner.get(run_id)
            if run.date != date:
                return jsonify(error="日期与运行记录不一致"), 400
            return jsonify(_payload(runner.publish(date)))
        except KeyError:
            return jsonify(error="运行记录不存在"), 404
        except Exception as exc:
            return jsonify(error=str(exc)), 409

    return app
