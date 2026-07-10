from .storage import InvalidTransition


class DailyRun:
    """The sole workflow interface for browser and scheduled execution."""

    def __init__(self, store, content, publisher):
        self.store, self.content, self.publisher = store, content, publisher

    def get(self, run_id: str):
        return self.store.get(run_id)

    def prepare(self, date: str, settings: dict, retry: bool = False):
        run = self.store.claim(date)
        if retry and run.state == "failed":
            run = self.store.retry(run.id)
        if not run.owner:
            return run
        try:
            self.store.transition(run.id, "scraping")
            self.store.transition(run.id, "rewriting")
            return self.store.save_article(run.id, self.content.build(date, settings))
        except Exception as exc:
            self.store.transition(run.id, "failed", str(exc))
            raise

    def publish(self, date: str):
        run = self.store.claim(date)
        if run.state == "published":
            return run
        if run.state != "ready":
            raise InvalidTransition(f"cannot publish {run.state}")
        self.store.transition(run.id, "publishing")
        try:
            media_id = self.publisher(run.article)
            return self.store.mark_published(run.id, media_id)
        except Exception as exc:
            self.store.transition(run.id, "failed", str(exc))
            raise
