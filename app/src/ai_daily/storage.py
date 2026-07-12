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
    "publishing": {"finalizing", "published", "ready", "failed"},
    "finalizing": set(),
    "publication_uncertain": set(),
    "published": set(),
    "failed": set(),
    "cleaning": set(),
}

ACTIVE_STATES = {"queued", "scraping", "rewriting", "publishing"}
HISTORY_BLOCKING_STATES = ACTIVE_STATES | {"finalizing", "publication_uncertain"}
RECLAIMABLE_STATES = {"queued", "scraping", "rewriting"}
CLEANUP_LEASE_NAME = "history"
CLEANUP_LEASE_MINUTES = 5


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
            db.execute("""CREATE TABLE IF NOT EXISTS run_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
                stage TEXT NOT NULL, status TEXT NOT NULL, message TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(run_id) REFERENCES daily_runs(id))""")
            db.execute("""CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY, value TEXT NOT NULL)""")
            db.execute("""CREATE TABLE IF NOT EXISTS cleanup_leases (
                name TEXT PRIMARY KEY, owner TEXT NOT NULL,
                acquired_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")

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

    def claim_fresh(self, date: str) -> Run:
        """Legacy compatibility only; fresh replacement belongs to DailyRun."""
        return self.claim(date)

    def get(self, run_id: str) -> Run:
        with closing(self._connect()) as db, db:
            row = db.execute("SELECT * FROM daily_runs WHERE id=?", (run_id,)).fetchone()
        if not row:
            raise KeyError(run_id)
        return self._run(row)

    def list_runs(self) -> list[Run]:
        with closing(self._connect()) as db:
            rows = db.execute("SELECT * FROM daily_runs ORDER BY date").fetchall()
        return [self._run(row) for row in rows]

    def begin_cleanup(self, owner: str) -> list[Run]:
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            lease = db.execute(
                "SELECT owner, acquired_at FROM cleanup_leases WHERE name=?",
                (CLEANUP_LEASE_NAME,),
            ).fetchone()
            rows = db.execute("SELECT * FROM daily_runs ORDER BY date").fetchall()
            if lease and db.execute(
                "SELECT datetime('now', ?)", (f"-{CLEANUP_LEASE_MINUTES} minutes",)
            ).fetchone()[0] <= lease["acquired_at"]:
                raise RuntimeError("history cleanup is already active")
            if any(row["state"] in HISTORY_BLOCKING_STATES for row in rows):
                raise RuntimeError("cannot clear history while active runs exist")
            db.execute(
                """INSERT INTO cleanup_leases(name, owner, acquired_at) VALUES (?, ?, CURRENT_TIMESTAMP)
                   ON CONFLICT(name) DO UPDATE SET owner=excluded.owner, acquired_at=CURRENT_TIMESTAMP""",
                (CLEANUP_LEASE_NAME, owner),
            )
            runs = [self._run(row) for row in rows]
            if runs:
                db.execute("UPDATE daily_runs SET state='cleaning', updated_at=CURRENT_TIMESTAMP")
        return runs

    def require_cleanup_lease(self, owner: str) -> None:
        with closing(self._connect()) as db, db:
            updated = db.execute(
                """UPDATE cleanup_leases SET acquired_at=CURRENT_TIMESTAMP
                   WHERE name=? AND owner=? AND acquired_at >= datetime('now', ?)""",
                (CLEANUP_LEASE_NAME, owner, f"-{CLEANUP_LEASE_MINUTES} minutes"),
            )
            if not updated.rowcount:
                raise RuntimeError("history cleanup lease is unavailable")

    def release_cleanup_lease(self, owner: str) -> None:
        with closing(self._connect()) as db, db:
            db.execute(
                "DELETE FROM cleanup_leases WHERE name=? AND owner=?",
                (CLEANUP_LEASE_NAME, owner),
            )

    def clear_media_receipt(self, run_id: str, owner: str) -> None:
        with closing(self._connect()) as db, db:
            updated = db.execute(
                """UPDATE daily_runs SET media_id='', updated_at=CURRENT_TIMESTAMP
                   WHERE id=? AND state='cleaning' AND EXISTS (
                       SELECT 1 FROM cleanup_leases WHERE name=? AND owner=?)""",
                (run_id, CLEANUP_LEASE_NAME, owner),
            )
            if not updated.rowcount:
                raise KeyError(run_id)

    def discard_if_state(self, run_id: str, state: str) -> bool:
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT state FROM daily_runs WHERE id=?", (run_id,)).fetchone()
            if not row or row["state"] != state:
                return False
            db.execute("DELETE FROM run_events WHERE run_id=?", (run_id,))
            db.execute("DELETE FROM daily_runs WHERE id=? AND state=?", (run_id, state))
        return True

    def discard(self, run_id: str) -> Run:
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM daily_runs WHERE id=?", (run_id,)).fetchone()
            if not row:
                raise KeyError(run_id)
            discarded = self._run(row)
            db.execute("DELETE FROM run_events WHERE run_id=?", (run_id,))
            db.execute("DELETE FROM daily_runs WHERE id=?", (run_id,))
            return discarded

    def transition(self, run_id: str, target: str, error: str = "") -> Run:
        with closing(self._connect()) as db, db:
            row = db.execute("SELECT * FROM daily_runs WHERE id=?", (run_id,)).fetchone()
            if not row:
                raise KeyError(run_id)
            if target not in ALLOWED.get(row["state"], set()):
                raise InvalidTransition(f"{row['state']} -> {target}")
            updated = db.execute("UPDATE daily_runs SET state=?, error=?, updated_at=CURRENT_TIMESTAMP WHERE id=? AND state=?",
                                 (target, error[:500], run_id, row["state"]))
            if not updated.rowcount:
                raise InvalidTransition(f"{row['state']} -> {target}")
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

    def mark_finalizing(self, run_id: str, media_id: str) -> Run:
        if not media_id:
            raise ValueError("missing media_id")
        with closing(self._connect()) as db, db:
            row = db.execute("SELECT state FROM daily_runs WHERE id=?", (run_id,)).fetchone()
            if not row or row["state"] != "publishing":
                raise InvalidTransition("only publishing runs can finalize")
            db.execute("UPDATE daily_runs SET state='finalizing', media_id=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                       (media_id, run_id))
        return self.get(run_id)

    def mark_publication_uncertain(self, run_id: str, error: str) -> Run:
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT state FROM daily_runs WHERE id=?", (run_id,)).fetchone()
            if not row or row["state"] != "publishing":
                raise InvalidTransition("only publishing runs can become uncertain")
            db.execute("DELETE FROM run_events WHERE run_id=?", (run_id,))
            db.execute(
                """UPDATE daily_runs
                   SET state='publication_uncertain', article=NULL, media_id='', error=?, updated_at=CURRENT_TIMESTAMP
                   WHERE id=? AND state='publishing'""",
                (error[:500], run_id),
            )
        return self.get(run_id)

    def stale_publishing(self, run_id: str, minutes: int) -> Run | None:
        with closing(self._connect()) as db:
            row = db.execute(
                """SELECT * FROM daily_runs
                   WHERE id=? AND state='publishing' AND updated_at < datetime('now', ?)""",
                (run_id, f"-{minutes} minutes"),
            ).fetchone()
        return self._run(row) if row else None

    def retry(self, run_id: str) -> Run:
        with closing(self._connect()) as db, db:
            row = db.execute("SELECT state, article FROM daily_runs WHERE id=?", (run_id,)).fetchone()
            if not row or row["state"] != "failed":
                raise InvalidTransition("only failed runs can be retried")
            state = "ready" if row["article"] else "queued"
            db.execute("UPDATE daily_runs SET state=?, error='', updated_at=CURRENT_TIMESTAMP WHERE id=?", (state, run_id))
        run = self.get(run_id)
        return Run(run.id, run.date, run.state, state == "queued", run.media_id, run.article, run.error)

    def reclaim_stale(self, run_id: str, minutes: int) -> Run:
        age = f"-{minutes} minutes"
        with closing(self._connect()) as db, db:
            row = db.execute("SELECT * FROM daily_runs WHERE id=?", (run_id,)).fetchone()
            if not row:
                raise KeyError(run_id)
            if row["state"] not in RECLAIMABLE_STATES:
                return self._run(row)
            result = db.execute(
                """UPDATE daily_runs SET state='queued', error='', updated_at=CURRENT_TIMESTAMP
                   WHERE id=? AND updated_at < datetime('now', ?)""",
                (run_id, age),
            )
            if not result.rowcount:
                return self._run(row)
        run = self.get(run_id)
        return Run(run.id, run.date, run.state, True, run.media_id, run.article, run.error)

    def record_event(self, run_id: str, stage: str, status: str, message: str) -> None:
        with closing(self._connect()) as db, db:
            exists = db.execute("SELECT 1 FROM daily_runs WHERE id=?", (run_id,)).fetchone()
            if not exists:
                raise KeyError(run_id)
            db.execute(
                "INSERT INTO run_events(run_id, stage, status, message) VALUES (?, ?, ?, ?)",
                (run_id, stage, status, message[:500]),
            )

    def events(self, run_id: str) -> list[dict]:
        with closing(self._connect()) as db, db:
            rows = db.execute(
                "SELECT stage, status, message FROM run_events WHERE run_id=? ORDER BY id",
                (run_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def initialize_settings(self, defaults: dict) -> None:
        with closing(self._connect()) as db, db:
            for key, value in defaults.items():
                db.execute(
                    "INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)",
                    (key, json.dumps(value, ensure_ascii=False)),
                )

    def settings(self, defaults: dict) -> dict:
        self.initialize_settings(defaults)
        with closing(self._connect()) as db, db:
            rows = db.execute("SELECT key, value FROM settings").fetchall()
        values = defaults.copy()
        values.update({row["key"]: json.loads(row["value"]) for row in rows})
        return values

    def update_settings(self, values: dict) -> None:
        with closing(self._connect()) as db, db:
            for key, value in values.items():
                db.execute(
                    "INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (key, json.dumps(value, ensure_ascii=False)),
                )
