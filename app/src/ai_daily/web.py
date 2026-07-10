from dataclasses import asdict, is_dataclass

from flask import Flask, jsonify, request


def _payload(run):
    if is_dataclass(run):
        return asdict(run)
    return {key: getattr(run, key, None) for key in ("id", "state", "media_id", "article", "error")}


def create_app(runner, settings=None):
    app = Flask(__name__)
    settings = settings or {}

    @app.post("/api/runs")
    def prepare():
        date = (request.get_json(silent=True) or {}).get("date")
        if not date:
            return jsonify(error="请选择日期"), 400
        return jsonify(_payload(runner.prepare(date, settings)))

    @app.get("/api/runs/<run_id>")
    def read(run_id):
        try:
            return jsonify(_payload(runner.get(run_id)))
        except KeyError:
            return jsonify(error="运行记录不存在"), 404

    @app.post("/api/runs/<run_id>/publish")
    def publish(run_id):
        date = (request.get_json(silent=True) or {}).get("date")
        if not date:
            return jsonify(error="请选择日期"), 400
        try:
            return jsonify(_payload(runner.publish(date)))
        except Exception as exc:
            return jsonify(error=str(exc)), 409

    return app
