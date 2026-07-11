from dataclasses import replace
import logging

from .storage import InvalidTransition


logger = logging.getLogger("ai_daily")


class DailyRun:
    """The sole workflow interface for browser and scheduled execution."""

    def __init__(self, store, content, publisher, cover=None, settings=None, cleanup=None):
        self.store = store
        self.content = content
        self.publisher = publisher
        self.cover = cover
        self.default_settings = settings or {}
        self.cleanup = cleanup

    def get(self, run_id: str):
        return self.store.get(run_id)

    def events(self, run_id: str):
        return self.store.events(run_id)

    def settings(self) -> dict:
        return self.store.settings(self.default_settings)

    def update_settings(self, values: dict) -> dict:
        self.store.update_settings(values)
        return self.settings()

    def start(self, date: str, settings: dict, retry: bool = False, fresh: bool = False):
        run = self.store.claim_fresh(date) if fresh else self.store.claim(date)
        if not fresh:
            if retry and run.state == "failed":
                run = self.store.retry(run.id)
            elif retry:
                run = self.store.reclaim_stale(run.id, minutes=30)
        if not run.owner:
            return run
        logger.info("run=%s stage=scraping", run.id)
        self.store.record_event(run.id, "scraping", "progress", "开始抓取当日资讯")
        started = self.store.transition(run.id, "scraping")
        return replace(started, owner=True)

    def execute(self, run_id: str, date: str, settings: dict):
        run = self.store.get(run_id)
        if run.date != date:
            raise ValueError("日期与运行记录不一致")
        if run.state != "scraping":
            raise InvalidTransition(f"cannot execute {run.state}")

        def progress(stage: str, status: str, message: str) -> None:
            current = self.store.get(run_id)
            if stage == "scraping" and status == "complete" and current.state == "scraping":
                self.store.transition(run_id, "rewriting")
            self.store.record_event(run_id, stage, status, message)

        try:
            article = self.content.build(date, settings, progress=progress)
            article["title"] = settings.get("title", f"AI 行业热点新闻 | {date}")
            self.store.record_event(run_id, "formatting", "complete", "文章排版完成")
            if self.cover:
                self.store.record_event(run_id, "cover", "progress", "正在生成封面")
                article.update(self.cover(article, settings))
                self.store.record_event(run_id, "cover", "complete", "封面已生成")
            ready = self.store.save_article(run_id, article)
            self.store.record_event(run_id, "done", "complete", "文章已生成，尚未发布")
            logger.info("run=%s stage=ready", run_id)
            return ready
        except Exception as exc:
            current = self.store.get(run_id)
            if current.state in {"scraping", "rewriting"}:
                self.store.transition(run_id, "failed", str(exc))
            self.store.record_event(run_id, "error", "error", str(exc))
            logger.error("run=%s stage=failed error=%s", run_id, type(exc).__name__)
            raise

    def prepare(self, date: str, settings: dict, retry: bool = False, fresh: bool = False):
        run = self.start(date, settings, retry=retry, fresh=fresh)
        if not run.owner:
            return run
        return self.execute(run.id, date, settings)

    def publish(self, date: str):
        run = self.store.claim(date)
        if run.state == "published":
            return run
        if run.state != "ready":
            raise InvalidTransition(f"cannot publish {run.state}")
        self.store.transition(run.id, "publishing")
        logger.info("run=%s stage=publishing", run.id)
        try:
            article = {**run.article, "title": run.article.get("title", f"AI 行业热点新闻 | {run.date}")}
            media_id = self.publisher(article)
            published = self.store.mark_published(run.id, media_id)
        except Exception as exc:
            self.store.transition(run.id, "ready", str(exc))
            self.store.record_event(run.id, "error", "error", str(exc))
            logger.error("run=%s stage=failed error=%s", run.id, type(exc).__name__)
            raise
        if self.cleanup:
            try:
                self.cleanup(article)
            except Exception as exc:
                logger.warning("run=%s stage=cleanup_failed error=%s", run.id, type(exc).__name__)
        try:
            self.store.discard(run.id)
        except KeyError as exc:
            if exc.args != (run.id,):
                raise
        logger.info("run=%s stage=published", run.id)
        return replace(published, article=None)
