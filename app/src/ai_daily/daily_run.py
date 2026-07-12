from dataclasses import replace
import logging
import uuid

from .storage import InvalidTransition


logger = logging.getLogger("ai_daily")


class PublicationUncertainError(RuntimeError):
    pass


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
        run = self.store.get(run_id)
        if run.state == "finalizing":
            finished = self._finish_finalization(run)
            if finished.state == "finalizing":
                return finished
            raise KeyError(run_id)
        return self._recover_stale_publication(run)

    def events(self, run_id: str):
        return self.store.events(run_id)

    def settings(self) -> dict:
        return self.store.settings(self.default_settings)

    def update_settings(self, values: dict) -> dict:
        self.store.update_settings(values)
        return self.settings()

    def clear_history(self, delete_draft):
        owner = uuid.uuid4().hex
        runs = self.store.begin_cleanup(owner)
        try:
            for run in runs:
                if run.media_id:
                    self.store.require_cleanup_lease(owner)
                    delete_draft(run.media_id)
                    self.store.clear_media_receipt(run.id, owner)

            for run in runs:
                self.store.require_cleanup_lease(owner)
                if not self._finish_pending_cover_cleanup(run, "history_cover_cleanup_failed"):
                    raise RuntimeError("history cover cleanup failed")
                if not self.store.discard_if_state(run.id, "cleaning"):
                    raise RuntimeError("history cleanup record changed")
        finally:
            self.store.release_cleanup_lease(owner)
        return {"count": len(runs), "dates": [run.date for run in runs]}

    @staticmethod
    def _published_response(run):
        return replace(run, state="published", owner=False, media_id="", article=None, error="")

    def _finish_pending_cover_cleanup(self, run, stage: str) -> bool:
        article = self.store.pending_cover_cleanup(run.id)
        if not article:
            return True
        if not self.cleanup:
            return False
        try:
            self.cleanup(article)
        except Exception as exc:
            logger.warning("run=%s stage=%s error=%s", run.id, stage, type(exc).__name__)
            return False
        self.store.clear_pending_cover_cleanup(run.id)
        return True

    def _finish_finalization(self, run):
        if run.state != "finalizing":
            raise InvalidTransition(f"cannot finalize {run.state}")
        if not self._finish_pending_cover_cleanup(run, "finalization_cleanup_failed"):
            return run
        self.store.discard_if_state(run.id, "finalizing")
        return self._published_response(run)

    def _finish_uncertain_cleanup(self, run):
        self._finish_pending_cover_cleanup(run, "uncertain_cleanup_failed")
        return self.store.get(run.id)

    def _mark_publication_uncertain(self, run, error: str):
        try:
            uncertain = self.store.mark_publication_uncertain(run.id, error)
        except InvalidTransition:
            return self.store.get(run.id)
        except Exception as exc:
            logger.warning("run=%s stage=uncertain_write_failed error=%s", run.id, type(exc).__name__)
            return self.store.get(run.id)
        return self._finish_uncertain_cleanup(uncertain)

    def _recover_stale_publication(self, run):
        """Stop a possibly-completed remote publish without ever retrying it."""
        if run.state == "publication_uncertain":
            return self._finish_uncertain_cleanup(run)
        if run.state != "publishing" or not self.store.stale_publishing(run.id, minutes=30):
            return run
        return self._mark_publication_uncertain(
            run,
            "发布结果待确认：请先在微信草稿箱核对后再重新生成",
        )

    def _claim_fresh(self, date: str, resolve_uncertain: bool = False):
        while True:
            run = self.store.claim(date)
            if run.owner:
                return run
            run = self._recover_stale_publication(run)
            if run.state == "finalizing":
                completed = self._finish_finalization(run)
                try:
                    self.store.get(run.id)
                except KeyError:
                    continue
                return completed
            if run.state == "published":
                raise RuntimeError("legacy published runs require cleanup-history before fresh generation")
            if run.state == "publication_uncertain":
                if not resolve_uncertain:
                    raise PublicationUncertainError("发布结果待确认：请先在微信草稿箱核对后再重新生成")
                if self.store.pending_cover_cleanup(run.id):
                    raise PublicationUncertainError("发布结果待确认：本地封面清理未完成，请稍后再试")
                self.store.discard_if_state(run.id, "publication_uncertain")
                continue
            if run.state not in {"ready", "failed"}:
                return run
            if self.cleanup and run.article:
                self.cleanup(run.article)
            self.store.discard_if_state(run.id, run.state)
            continue

    def start(
        self,
        date: str,
        settings: dict,
        retry: bool = False,
        fresh: bool = False,
        resolve_uncertain: bool = False,
    ):
        run = self._claim_fresh(date, resolve_uncertain) if fresh else self.store.claim(date)
        if not fresh:
            if retry:
                run = self._recover_stale_publication(run)
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
        if run.state == "finalizing":
            return self._finish_finalization(run)
        if run.state == "publication_uncertain":
            return self._finish_uncertain_cleanup(run)
        if run.state != "ready":
            raise InvalidTransition(f"cannot publish {run.state}")
        publishing, article = self.store.begin_publication(run.id)
        logger.info("run=%s stage=publishing", run.id)
        try:
            article = {**article, "title": article.get("title", f"AI 行业热点新闻 | {run.date}")}
            media_id = self.publisher(article)
        except Exception as exc:
            logger.warning("run=%s stage=publication_uncertain error=%s", run.id, type(exc).__name__)
            return self._mark_publication_uncertain(
                publishing,
                "发布结果待确认：请先在微信草稿箱核对后再重新生成",
            )
        try:
            published = self.store.mark_finalizing(run.id, media_id)
        except Exception as exc:
            logger.error("run=%s stage=receipt_persist_failed error=%s", run.id, type(exc).__name__)
            return self._mark_publication_uncertain(
                publishing,
                "发布结果待确认：请先在微信草稿箱核对后再重新生成",
            )
        published = self._finish_finalization(published)
        logger.info("run=%s stage=published", run.id)
        return published
