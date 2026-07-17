import argparse
from pathlib import Path

from .content import ContentRetryExhaustedError
from .daily_run import PublicationUncertainError, safe_failure_reason
from .runtime import build_runner
from .scheduler import WindowsTasks
from .web import create_app
from .logging import configure_logging


def serve_preview(app, flask_runner, waitress_runner=None):
    if waitress_runner is None:
        flask_runner(app)
    else:
        waitress_runner(app)


class ScheduledDailyFailedError(RuntimeError):
    pass


class DailyRunActiveError(RuntimeError):
    pass


def show_scheduled_failure(reason: str):
    import ctypes

    ctypes.windll.user32.MessageBoxW(
        0,
        f"❌ 日报两次处理均未成功\n\n未确认微信草稿已创建。\n原因：{reason}",
        "AI Daily · 定时任务失败",
        0x10 | 0x1000,
    )


def run_scheduled_daily(runner, run_date: str, settings: dict, preview: bool):
    last_error = None
    for _ in range(2):
        try:
            run = runner.prepare(run_date, settings, retry=True)
            state = getattr(run, "state", "")
            if not getattr(run, "owner", False) and state in {"queued", "scraping", "rewriting", "publishing"}:
                raise DailyRunActiveError("daily run is already active")
            if preview:
                return run
            if state in {"ready", "finalizing"}:
                run = runner.publish(run.date)
                state = getattr(run, "state", "")
            if state in {"published", "finalizing"}:
                return run
            if state == "publication_uncertain":
                reason = getattr(run, "error", "") or "微信发布结果待确认，请检查草稿箱"
                raise PublicationUncertainError(reason)
            raise RuntimeError(f"daily run did not publish: {state or 'unknown'}")
        except (ContentRetryExhaustedError, PublicationUncertainError) as exc:
            last_error = exc
            break
        except DailyRunActiveError:
            raise
        except Exception as exc:
            last_error = exc
    raise ScheduledDailyFailedError(safe_failure_reason(last_error))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("web", "daily", "cleanup-history"))
    parser.add_argument("--preview", action="store_true")
    args = parser.parse_args()
    app_dir = Path(__file__).parents[2]
    configure_logging(app_dir / "data" / "ai_daily.log")
    if args.command == "cleanup-history":
        if args.preview:
            raise RuntimeError("cleanup-history requires formal mode")
        runner = build_runner(app_dir, False)
        delete_draft = getattr(runner.publisher, "delete_draft", None)
        if not callable(delete_draft):
            raise RuntimeError("cleanup-history requires draft deletion support")
        summary = runner.clear_history(delete_draft)
        print(f"清理完成：{summary['count']} 条记录，日期：{', '.join(summary['dates'])}")
        return
    runner = build_runner(app_dir, args.preview)
    if args.command == "daily":
        from datetime import date
        run_date = date.today().isoformat()
        settings = runner.settings()
        settings["title"] = f"AI 行业热点新闻 | {run_date}"
        try:
            run_scheduled_daily(runner, run_date, settings, args.preview)
        except ScheduledDailyFailedError as exc:
            if not args.preview:
                show_scheduled_failure(str(exc))
            raise
        return
    web = create_app(runner, tasks=WindowsTasks(app_dir / "scripts" / "run_scheduled.bat"))
    try:
        from waitress import serve
        serve_preview(web, None, lambda app: serve(app, host="127.0.0.1", port=5000))
    except ModuleNotFoundError:
        if not args.preview:
            raise RuntimeError("缺少 waitress；请先完成 uv sync 后再启动正式 Web")
        serve_preview(web, lambda app: app.run(host="127.0.0.1", port=5000, debug=False))


if __name__ == "__main__":
    main()
