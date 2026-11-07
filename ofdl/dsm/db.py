"""Bounded SQLite control database.

Everything that can grow (job events, creator lists, job history) lives here
instead of in the control service's memory.  Connections are short-lived in the
service; the worker keeps one connection guarded by a lock.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

SCHEMA_VERSION = 2
ACTIVE_STATES = ('queued', 'running', 'paused')
MAX_EVENT_ROWS_PER_JOB = 3000
MAX_JOBS_KEPT = 100

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    status TEXT NOT NULL,
    payload TEXT NOT NULL DEFAULT '{}',
    result TEXT,
    error TEXT,
    phase TEXT,
    progress_done INTEGER NOT NULL DEFAULT 0,
    progress_total INTEGER NOT NULL DEFAULT 0,
    stats TEXT NOT NULL DEFAULT '{}',
    pid INTEGER,
    exit_code INTEGER,
    pause_requested INTEGER NOT NULL DEFAULT 0,
    cancel_requested INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
);
CREATE INDEX IF NOT EXISTS jobs_status_idx ON jobs(status, id DESC);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL,
    ts TEXT NOT NULL,
    level TEXT NOT NULL,
    message TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS events_job_idx ON events(job_id, id DESC);

CREATE TABLE IF NOT EXISTS creators (
    username TEXT PRIMARY KEY,
    display_name TEXT,
    subscription TEXT,
    scanned_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS creators_name_idx ON creators(username COLLATE NOCASE);

CREATE TABLE IF NOT EXISTS offers (
    account_id TEXT NOT NULL,
    username TEXT NOT NULL,
    kind TEXT NOT NULL,
    status TEXT NOT NULL,
    detail TEXT NOT NULL,
    scanned_at TEXT NOT NULL,
    PRIMARY KEY(account_id, username)
);
CREATE TABLE IF NOT EXISTS renewal_attempts (
    account_id TEXT NOT NULL,
    username TEXT NOT NULL,
    day TEXT NOT NULL,
    status TEXT NOT NULL,
    PRIMARY KEY(account_id, username, day)
);
"""

_JOB_FIELDS = {
    'status', 'result', 'error', 'phase', 'progress_done', 'progress_total',
    'stats', 'pid', 'exit_code', 'pause_requested', 'cancel_requested',
    'started_at', 'finished_at',
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def _configure(db: sqlite3.Connection) -> None:
    # Small, predictable caches: the control service must stay tiny.
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('PRAGMA synchronous=NORMAL')
    db.execute('PRAGMA busy_timeout=10000')
    db.execute('PRAGMA cache_size=-2000')
    db.execute('PRAGMA temp_store=FILE')
    db.execute('PRAGMA foreign_keys=OFF')
    db.execute('PRAGMA mmap_size=0')


def open_db(path: Path | str, *, check_same_thread: bool = True) -> sqlite3.Connection:
    db = sqlite3.connect(str(path), timeout=10, check_same_thread=check_same_thread)
    db.row_factory = sqlite3.Row
    _configure(db)
    return db


@contextmanager
def connect(path: Path | str) -> Iterator[sqlite3.Connection]:
    db = open_db(path)
    try:
        yield db
    finally:
        db.close()


def init_db(path: Path | str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with connect(path) as db:
        db.executescript(SCHEMA)
        db.execute(f'PRAGMA user_version={SCHEMA_VERSION}')
        db.commit()
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _row(value: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(value) if value is not None else None


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

def get_setting(db: sqlite3.Connection, key: str, default: str = '') -> str:
    row = db.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
    return str(row['value']) if row is not None else default


def set_setting(db: sqlite3.Connection, key: str, value: str) -> None:
    db.execute(
        'INSERT INTO settings(key,value,updated_at) VALUES(?,?,?) '
        'ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at',
        (str(key), str(value), now_iso()),
    )
    db.commit()


def get_json(db: sqlite3.Connection, key: str, default: Any) -> Any:
    raw = get_setting(db, key, '')
    if not raw:
        return default
    try:
        value = json.loads(raw)
        return value if isinstance(value, type(default)) else default
    except (ValueError, RecursionError):
        return default


def set_json(db: sqlite3.Connection, key: str, value: Any) -> None:
    set_setting(db, key, json.dumps(value, ensure_ascii=False, separators=(',', ':')))


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------

def create_job(db: sqlite3.Connection, kind: str, payload: dict[str, Any]) -> int:
    cursor = db.execute(
        'INSERT INTO jobs(kind,status,payload,created_at) VALUES(?,?,?,?)',
        (kind, 'queued', json.dumps(payload, ensure_ascii=False, separators=(',', ':')), now_iso()),
    )
    db.commit()
    return int(cursor.lastrowid)


def get_job(db: sqlite3.Connection, job_id: int) -> dict[str, Any] | None:
    return _row(db.execute('SELECT * FROM jobs WHERE id=?', (int(job_id),)).fetchone())


def active_job(db: sqlite3.Connection) -> dict[str, Any] | None:
    marks = ','.join('?' for _ in ACTIVE_STATES)
    return _row(db.execute(
        f'SELECT * FROM jobs WHERE status IN ({marks}) ORDER BY id DESC LIMIT 1',
        ACTIVE_STATES,
    ).fetchone())


def list_jobs(db: sqlite3.Connection, limit: int = 20) -> list[dict[str, Any]]:
    limit = max(1, min(100, int(limit)))
    # Deliberately omit payload: a list endpoint must not load large creator
    # selections or option blobs into the control service's memory.
    rows = db.execute(
        'SELECT id,kind,status,result,error,phase,progress_done,progress_total,'
        'stats,pid,exit_code,pause_requested,cancel_requested,created_at,'
        'started_at,finished_at FROM jobs ORDER BY id DESC LIMIT ?',
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]


def update_job(db: sqlite3.Connection, job_id: int, **fields: Any) -> None:
    names = [name for name in fields if name in _JOB_FIELDS]
    if not names:
        return
    assignments = ', '.join(f'{name}=?' for name in names)
    values = [fields[name] for name in names]
    values.append(int(job_id))
    db.execute(f'UPDATE jobs SET {assignments} WHERE id=?', values)
    db.commit()


def finish_job(db: sqlite3.Connection, job_id: int, status: str, *,
               result: dict[str, Any] | None = None,
               error: str | None = None,
               exit_code: int | None = None) -> None:
    db.execute(
        'UPDATE jobs SET status=?, result=?, error=?, exit_code=?, finished_at=? WHERE id=?',
        (
            status,
            json.dumps(result, ensure_ascii=False, separators=(',', ':')) if result is not None else None,
            error,
            exit_code,
            now_iso(),
            int(job_id),
        ),
    )
    db.commit()


def mark_stale_jobs(db: sqlite3.Connection) -> int:
    marks = ','.join('?' for _ in ACTIVE_STATES)
    cursor = db.execute(
        f'UPDATE jobs SET status=?, error=?, finished_at=? WHERE status IN ({marks})',
        ('failed', 'Der Dienst wurde neu gestartet; der alte Auftrag wurde beendet.', now_iso(), *ACTIVE_STATES),
    )
    db.commit()
    return int(cursor.rowcount or 0)


def prune_jobs(db: sqlite3.Connection, keep: int = MAX_JOBS_KEPT) -> None:
    keep = max(10, int(keep))
    row = db.execute('SELECT id FROM jobs ORDER BY id DESC LIMIT 1 OFFSET ?', (keep - 1,)).fetchone()
    if row is None:
        return
    cutoff = int(row['id'])
    db.execute('DELETE FROM events WHERE job_id < ?', (cutoff,))
    db.execute('DELETE FROM jobs WHERE id < ?', (cutoff,))
    db.commit()


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

def add_event(db: sqlite3.Connection, job_id: int, level: str, message: str) -> int:
    cursor = db.execute(
        'INSERT INTO events(job_id,ts,level,message) VALUES(?,?,?,?)',
        (int(job_id), now_iso(), str(level)[:32], str(message)[:1000]),
    )
    return int(cursor.lastrowid)


def list_events(db: sqlite3.Connection, job_id: int, after: int = 0,
                limit: int = 200) -> list[dict[str, Any]]:
    limit = max(1, min(500, int(limit)))
    rows = db.execute(
        'SELECT id,ts,level,message FROM events WHERE job_id=? AND id>? ORDER BY id ASC LIMIT ?',
        (int(job_id), max(0, int(after)), limit),
    ).fetchall()
    return [dict(row) for row in rows]


def recent_events(db: sqlite3.Connection, job_id: int, limit: int = 100) -> list[dict[str, Any]]:
    limit = max(1, min(200, int(limit)))
    rows = db.execute('SELECT id,ts,level,message FROM events WHERE job_id=? '
                      'ORDER BY id DESC LIMIT ?', (int(job_id), limit)).fetchall()
    return [dict(row) for row in reversed(rows)]


def prune_events(db: sqlite3.Connection, job_id: int,
                 keep: int = MAX_EVENT_ROWS_PER_JOB) -> None:
    keep = max(100, int(keep))
    row = db.execute(
        'SELECT id FROM events WHERE job_id=? ORDER BY id DESC LIMIT 1 OFFSET ?',
        (int(job_id), keep - 1),
    ).fetchone()
    if row is None:
        return
    db.execute('DELETE FROM events WHERE job_id=? AND id < ?', (int(job_id), int(row['id'])))
    db.commit()


# ---------------------------------------------------------------------------
# Creators (subscription list is stored, never held in the control service)
# ---------------------------------------------------------------------------

def clear_creators(db: sqlite3.Connection) -> None:
    db.execute('DELETE FROM creators')
    db.commit()


def upsert_creators(db: sqlite3.Connection, rows: Iterable[tuple[str, str, str]]) -> int:
    stamp = now_iso()
    data = [(username, display, subscription, stamp) for username, display, subscription in rows]
    if not data:
        return 0
    db.executemany(
        'INSERT INTO creators(username,display_name,subscription,scanned_at) VALUES(?,?,?,?) '
        'ON CONFLICT(username) DO UPDATE SET display_name=excluded.display_name, '
        'subscription=excluded.subscription, scanned_at=excluded.scanned_at',
        data,
    )
    db.commit()
    return len(data)


def count_creators(db: sqlite3.Connection, query: str = '') -> int:
    if query:
        row = db.execute(
            'SELECT COUNT(*) AS n FROM creators WHERE username LIKE ? COLLATE NOCASE',
            ('%' + query + '%',),
        ).fetchone()
    else:
        row = db.execute('SELECT COUNT(*) AS n FROM creators').fetchone()
    return int(row['n']) if row is not None else 0


def page_creators(db: sqlite3.Connection, page: int = 1, per_page: int = 50,
                  query: str = '') -> list[dict[str, Any]]:
    page = max(1, int(page))
    per_page = max(1, min(200, int(per_page)))
    offset = (page - 1) * per_page
    if query:
        rows = db.execute(
            'SELECT username,display_name,subscription,scanned_at FROM creators '
            'WHERE username LIKE ? COLLATE NOCASE ORDER BY username COLLATE NOCASE LIMIT ? OFFSET ?',
            ('%' + query + '%', per_page, offset),
        ).fetchall()
    else:
        rows = db.execute(
            'SELECT username,display_name,subscription,scanned_at FROM creators '
            'ORDER BY username COLLATE NOCASE LIMIT ? OFFSET ?',
            (per_page, offset),
        ).fetchall()
    return [dict(row) for row in rows]


# ---------------------------------------------------------------------------
# Library manifest (read-only, cheap aggregate only)
# ---------------------------------------------------------------------------

def library_stats(output_dir: Path | str | None, timeout: float = 2.0) -> dict[str, Any]:
    """Read counts from the existing .ofdl.sqlite3 without scanning the library.

    The manifest is created by the download engine and is intentionally reused.
    A missing manifest is not an error (a fresh folder simply has no history).
    """
    result: dict[str, Any] = {'manifest': False, 'files': 0, 'bytes': 0, 'error': None}
    if not output_dir:
        return result
    path = Path(output_dir) / '.ofdl.sqlite3'
    if not path.is_file():
        return result
    try:
        uri = path.resolve().as_uri() + '?mode=ro'
        db = sqlite3.connect(uri, uri=True, timeout=timeout)
        try:
            row = db.execute('SELECT COUNT(*) AS files, COALESCE(SUM(size),0) AS bytes FROM media').fetchone()
            result.update({'manifest': True, 'files': int(row[0] or 0), 'bytes': int(row[1] or 0)})
        finally:
            db.close()
    except (sqlite3.Error, OSError) as exc:
        result['error'] = type(exc).__name__
    return result
