import json
import sqlite3
import threading
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

STATES = (
    "fetching",
    "checking",
    "awaiting_track",
    "awaiting_confirm",
    "queued",
    "waiting_model",
    "decoding",
    "separating",
    "encoding",
    "done",
    "failed",
    "canceled",
    "interrupted",
)
RUNNING = {"fetching", "checking", "decoding", "separating", "encoding"}
FINISHED = {"done", "failed", "canceled", "interrupted"}
STOPPED = {"failed", "canceled", "interrupted"}
# Jobs that count toward the queue limit and cancel at once.
WAITING = {"fetching", "checking", "queued", "waiting_model", "awaiting_track", "awaiting_confirm"}

TRANSITIONS: dict[str, set[str]] = {
    "fetching": {"checking", "failed", "canceled", "interrupted"},
    "checking": {
        "queued",
        "awaiting_track",
        "awaiting_confirm",
        "failed",
        "canceled",
        "interrupted",
    },
    "awaiting_track": {"queued", "awaiting_confirm", "canceled"},
    "awaiting_confirm": {"queued", "canceled"},
    # Download only skips straight to encoding.
    "queued": {"waiting_model", "decoding", "encoding", "awaiting_confirm", "canceled"},
    "waiting_model": {"queued", "awaiting_confirm", "canceled"},
    "decoding": {"separating", "failed", "canceled", "interrupted"},
    "separating": {"encoding", "failed", "canceled", "interrupted"},
    "encoding": {"done", "failed", "canceled", "interrupted"},
    "done": set(),
    "failed": {"fetching", "queued", "awaiting_track", "awaiting_confirm"},
    "canceled": {"fetching", "queued", "awaiting_track", "awaiting_confirm"},
    "interrupted": {"fetching", "queued", "awaiting_track", "awaiting_confirm"},
}

JSON_FIELDS = ("options", "probe", "result", "link")
# None for a format means "the same kind as the input".
DEFAULT_SETTINGS: dict[str, Any] = {
    "preset": "best",
    "device": "auto",
    "audio_format": None,
    "video_format": None,
}
FIELDS = (
    "name",
    "kind",
    "state",
    "stage",
    "progress",
    "eta",
    "options",
    "probe",
    "result",
    "error",
    "retryable",
    "link",
)

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    created REAL NOT NULL,
    name TEXT NOT NULL,
    kind TEXT,
    state TEXT NOT NULL CHECK (state IN ({", ".join(f"'{s}'" for s in STATES)})),
    stage TEXT,
    progress REAL NOT NULL DEFAULT 0,
    eta REAL,
    options TEXT NOT NULL DEFAULT '{{}}',
    probe TEXT,
    result TEXT,
    error TEXT,
    retryable INTEGER NOT NULL DEFAULT 1,
    link TEXT
)
"""
# The columns a first-release table has, copied across when it is rebuilt.
OLD_COLUMNS = (
    "id, created, name, kind, state, stage, progress, eta, options, probe, result, error, retryable"
)

Job = dict[str, Any]
Listener = Callable[[str, Job], None]


class TransitionError(Exception):
    pass


class Store:
    """The jobs table. Every state change goes through transition(), which checks the from-state.

    One connection is shared by the request threads and the runner, so every use holds the lock.
    """

    def __init__(self, path: Path) -> None:
        self.db = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self._migrate()
        self.db.execute(SCHEMA)
        self.db.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        self.lock = threading.RLock()
        self.listeners: list[Listener] = []

    def _migrate(self) -> None:
        """A table from the first release has neither the fetching state nor the link column,
        and SQLite cannot change a CHECK in place, so the table is rebuilt once."""
        row = self.db.execute("SELECT sql FROM sqlite_master WHERE name = 'jobs'").fetchone()
        if row is None or "'fetching'" in row[0]:
            return
        self.db.executescript(
            f"BEGIN; ALTER TABLE jobs RENAME TO jobs_old; {SCHEMA}; "  # noqa: S608
            f"INSERT INTO jobs ({OLD_COLUMNS}) SELECT {OLD_COLUMNS} FROM jobs_old; "
            "DROP TABLE jobs_old; COMMIT;"
        )

    def close(self) -> None:
        with self.lock:
            self.db.close()

    def subscribe(self, listener: Listener) -> Callable[[], None]:
        self.listeners.append(listener)
        return lambda: self.listeners.remove(listener)

    def _emit(self, event: str, job: Job) -> None:
        """Called with the lock held, so every listener sees changes in the order they happened."""
        for listener in list(self.listeners):
            listener(event, job)

    @staticmethod
    def _row(row: sqlite3.Row) -> Job:
        job = dict(row)
        for key in JSON_FIELDS:
            job[key] = json.loads(job[key]) if job[key] is not None else None
        job["retryable"] = bool(job["retryable"])
        return job

    def create(
        self,
        name: str,
        options: dict[str, Any],
        state: str = "checking",
        link: dict[str, Any] | None = None,
    ) -> Job:
        job_id = str(uuid.uuid4())
        with self.lock:
            self.db.execute(
                "INSERT INTO jobs (id, created, name, state, options, link) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    job_id,
                    time.time(),
                    name,
                    state,
                    json.dumps(options),
                    None if link is None else json.dumps(link),
                ),
            )
            job = self.get(job_id)
            self._emit("job", job)
        return job

    def get(self, job_id: str) -> Job:
        with self.lock:
            row = self.db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(job_id)
        return self._row(row)

    def list(self) -> list[Job]:
        with self.lock:
            rows = self.db.execute("SELECT * FROM jobs ORDER BY created, rowid").fetchall()
        return [self._row(r) for r in rows]

    def _write(self, job_id: str, fields: dict[str, Any]) -> None:
        unknown = set(fields) - set(FIELDS)
        if unknown:
            raise ValueError(f"unknown fields: {unknown}")
        values = [
            json.dumps(v) if k in JSON_FIELDS and v is not None else v for k, v in fields.items()
        ]
        sets = ", ".join(f"{k} = ?" for k in fields)
        self.db.execute(f"UPDATE jobs SET {sets} WHERE id = ?", (*values, job_id))  # noqa: S608

    def update(self, job_id: str, **fields: Any) -> Job:
        """Changes anything but the state."""
        if "state" in fields:
            raise ValueError("use transition() to change state")
        with self.lock:
            self._write(job_id, fields)
            job = self.get(job_id)
            self._emit("job", job)
        return job

    def transition(self, job_id: str, to: str, **fields: Any) -> Job:
        with self.lock:
            current = self.get(job_id)["state"]
            if to not in TRANSITIONS[current]:
                raise TransitionError(f"{current} -> {to}")
            self._write(job_id, {**fields, "state": to})
            job = self.get(job_id)
            self._emit("job", job)
        return job

    def delete(self, job_id: str) -> None:
        with self.lock:
            job = self.get(job_id)
            self.db.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
            self._emit("deleted", job)

    def next_queued(self) -> Job | None:
        with self.lock:
            row = self.db.execute(
                "SELECT * FROM jobs WHERE state = 'queued' ORDER BY created, rowid LIMIT 1"
            ).fetchone()
        return self._row(row) if row else None

    def settings(self) -> dict[str, Any]:
        """Saved choices merged over the defaults."""
        with self.lock:
            rows = self.db.execute("SELECT key, value FROM settings").fetchall()
        return {**DEFAULT_SETTINGS, **{r["key"]: json.loads(r["value"]) for r in rows}}

    def save_settings(self, values: dict[str, Any]) -> None:
        with self.lock:
            self.db.executemany(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                [(k, json.dumps(v)) for k, v in values.items()],
            )

    def count(self, *states: str) -> int:
        marks = ", ".join("?" for _ in states)
        sql = f"SELECT COUNT(*) FROM jobs WHERE state IN ({marks})"  # noqa: S608
        with self.lock:
            return int(self.db.execute(sql, states).fetchone()[0])
