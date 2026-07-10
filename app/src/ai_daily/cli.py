import argparse
from pathlib import Path

from .runtime import build_runner
from .web import create_app


def serve_preview(app, flask_runner, waitress_runner=None):
    if waitress_runner is None:
        flask_runner(app)
    else:
        waitress_runner(app)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("web", "daily"))
    parser.add_argument("--preview", action="store_true")
    args = parser.parse_args()
    app_dir = Path(__file__).parents[2]
    runner = build_runner(app_dir, args.preview)
    if args.command == "daily":
        from datetime import date
        run = runner.prepare(date.today().isoformat(), {})
        if not args.preview:
            runner.publish(run.date)
        return
    web = create_app(runner)
    try:
        from waitress import serve
        serve_preview(web, None, lambda app: serve(app, host="127.0.0.1", port=5000))
    except ModuleNotFoundError:
        if not args.preview:
            raise RuntimeError("缺少 waitress；请先完成 uv sync 后再启动正式 Web")
        serve_preview(web, lambda app: app.run(host="127.0.0.1", port=5000, debug=False))


if __name__ == "__main__":
    main()
