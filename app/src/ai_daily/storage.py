import json
import sqlite3
import uuid
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path


class InvalidTransition(ValueError):
    pass


@dataclass(frozen=True)
class Run:
    id: str
    date: str
    state: str
    owner: bool
    media_id: str = ""
    article: dict | None = None
    error: str = ""


ALLOWED = {
    "queued": {"scraping", "failed"},
    "scraping": {"rewriting", "failed"},
    "rewriting": {"ready", "failed"},
    "ready": {"publishing", "failed"},
    "publishing": {"published", "failed"},
    "published": set(),
    "failed": set(),
}


class Store:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as db, db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("""CREATE TABLE IF NOT EXISTS daily_runs (
                id TEXT PRIMARY KEY, date TEXT UNIQUE NOT NULL, state TEXT NOT NULL,
                article TEXT, media_id TEXT NOT NULL DEFAULT '', error TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    @staticmethod
    def _run(row, owner=False):
        return Run(row["id"], row["date"], row["state"], owner, row["media_id"],
                   json.loads(row["article"]) if row["article"] else None, row["error"])

    def claim(self, date: str) -> Run:
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM daily_runs WHERE date=?", (date,)).fetchone()
            if row:
                return self._run(row)
            run_id = uuid.uuid4().hex
            db.execute("INSERT INTO daily_runs(id, date, state) VALUES (?, ?, 'queued')", (run_id, date))
            row = db.execute("SELECT * FROM daily_runs WHERE id=?", (run_id,)).fetchone()
            return self._run(row, owner=True)

    def get(self, run_id: str) -> Run:
        with closing(self._connect()) as db, db:
            row = db.execute("SELECT * FROM daily_runs WHERE id=?", (run_id,)).fetchone()
        if not row:
            raise KeyError(run_id)
        return self._run(row)

    def transition(self, run_id: str, target: str, error: str = "") -> Run:
        with closing(self._connect()) as db, db:
            row = db.execute("SELECT * FROM daily_runs WHERE id=?", (run_id,)).fetchone()
            if not row:
                raise KeyError(run_id)
            if target not in ALLOWED.get(row["state"], set()):
                raise InvalidTransition(f"{row['state']} -> {target}")
            db.execute("UPDATE daily_runs SET state=?, error=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                       (target, error[:500], run_id))
        return self.get(run_id)

    def save_article(self, run_id: str, article: dict) -> Run:
        encoded = json.dumps(article, ensure_ascii=False)
        with closing(self._connect()) as db, db:
            row = db.execute("SELECT state FROM daily_runs WHERE id=?", (run_id,)).fetchone()
            if not row:
                raise KeyError(run_id)
            if row["state"] != "rewriting":
                raise InvalidTransition(f"{row['state']} -> ready")
            db.execute("UPDATE daily_runs SET article=?, state='ready', updated_at=CURRENT_TIMESTAMP WHERE id=?",
                       (encoded, run_id))
        return self.get(run_id)

    def mark_published(self, run_id: str, media_id: str) -> Run:
        if not media_id:
            raise ValueError("missing media_id")
        with closing(self._connect()) as db, db:
            row = db.execute("SELECT state FROM daily_runs WHERE id=?", (run_id,)).fetchone()
            if not row or row["state"] != "publishing":
                raise InvalidTransition("only publishing runs can be published")
            db.execute("UPDATE daily_runs SET state='published', media_id=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                       (media_id, run_id))
        return self.get(run_id)
