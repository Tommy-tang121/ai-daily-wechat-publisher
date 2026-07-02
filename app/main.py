import json
import os
import queue
from threading import Thread
from flask import Flask, render_template, request, Response, jsonify, stream_with_context
from app.env import load_env
load_env()
from app.config import get_config, set_config
from app.pipeline import run_pipeline, PipelineError
from app.markdown import build_markdown
from app.publisher import publish_article
from app import scheduler

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config["CURRENT_ARTICLE"] = None
app.config["CURRENT_DATE"] = None


@app.route("/")
def index():
    return render_template("index.html", config=get_config())


@app.route("/api/fetch", methods=["POST"])
def api_fetch():
    data = request.get_json()
    date_str = data.get("date", "")
    if not date_str:
        return jsonify({"error": "请选择日期"}), 400
    app.config["CURRENT_DATE"] = date_str
    app.config["CURRENT_ARTICLE"] = None
    app.config["CURRENT_MAX_WORDS"] = data.get("max_words", get_config("max_words"))
    return jsonify({"status": "ok"})


@app.route("/api/progress")
def api_progress():
    def generate():
        date_str = app.config.get("CURRENT_DATE")
        max_words = app.config.get("CURRENT_MAX_WORDS", 150)
        if not date_str:
            yield f"event: stage\ndata: {json.dumps({'stage': 'error', 'status': 'error', 'message': '没有选择日期'})}\n\n"
            return

        q = queue.Queue()

        def on_progress(stage, status, message, percent):
            q.put(("stage", {"stage": stage, "status": status, "message": message, "percent": percent}))

        def do_pipeline():
            try:
                result = run_pipeline(date_str, max_words, on_progress=on_progress)
                q.put(("result", result))
            except PipelineError as e:
                q.put(("error", str(e)))
            except Exception as e:
                q.put(("error", str(e)))

        Thread(target=do_pipeline, daemon=True).start()

        while True:
            try:
                typ, payload = q.get(timeout=0.5)
            except queue.Empty:
                continue

            if typ == "stage":
                yield f"event: stage\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                if payload.get("stage") == "done":
                    return
            elif typ == "result":
                app.config["CURRENT_ARTICLE"] = payload
                yield f"event: stage\ndata: {json.dumps({'stage': 'done', 'status': 'complete', 'message': '全部完成', 'percent': 100}, ensure_ascii=False)}\n\n"
                return
            elif typ == "error":
                yield f"event: stage\ndata: {json.dumps({'stage': 'error', 'status': 'error', 'message': payload, 'percent': 0}, ensure_ascii=False)}\n\n"
                return

    return Response(stream_with_context(generate()), mimetype="text/event-stream")


@app.route("/api/preview")
def api_preview():
    article = app.config.get("CURRENT_ARTICLE")
    if not article:
        return jsonify({"error": "还没有文章"}), 400
    return jsonify(article)


@app.route("/api/article-text")
def api_article_text():
    article = app.config.get("CURRENT_ARTICLE")
    date_str = app.config.get("CURRENT_DATE")
    if not article or not date_str:
        return jsonify({"error": "还没有文章"}), 400
    text = build_markdown(article, date_str, get_config("title"), get_config("data_source"))
    return jsonify({"text": text})


@app.route("/api/cover")
def api_cover():
    date_str = app.config.get("CURRENT_DATE")
    if not date_str:
        return jsonify({"error": "没有封面"}), 400
    return jsonify({"url": f"static/covers/{date_str}.png"})


@app.route("/api/publish", methods=["POST"])
def api_publish():
    article = app.config.get("CURRENT_ARTICLE")
    date_str = app.config.get("CURRENT_DATE")
    if not article or not date_str:
        return jsonify({"error": "还没有文章"}), 400
    result = publish_article(date_str, article)
    return jsonify(result)


@app.route("/api/config", methods=["GET", "POST"])
def api_config():
    if request.method == "POST":
        data = request.get_json()
        for key in data:
            set_config(key, data[key])
        if "schedule_time" in data:
            scheduler.create_or_update_tasks(data["schedule_time"])
        return jsonify({"status": "ok"})
    cfg = get_config()
    st = scheduler.get_trigger_time(scheduler.TASK_NAME)
    if st:
        cfg["schedule_time"] = st
    return jsonify(cfg)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
