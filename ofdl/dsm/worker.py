"""Short-lived job worker.

The control service starts one of these per job and waits for it to exit.  The
worker owns the API session, the SQLite manifest access and all heavy imports.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
import traceback
from typing import Any

from ..auth import SessionError
from ..common import AppError, Cancelled, Control
from . import db as control_db
from .config import Paths, ensure_dirs, resolve_paths
from .run_jobs import run_job
from .security import sanitize_text

MAX_RESULT_BYTES = 256 * 1024


class JobControl(Control):
    """Cooperative pause/cancel that also notices a dead control service."""

    def __init__(self, paths: Paths, job_id: int):
        super().__init__()
        self.paths = paths
        self.job_id = int(job_id)
        self.parent_pid = int(os.environ.get('OFDL_PARENT_PID') or os.getppid())
        self._next_poll = 0.0

    def _poll(self) -> None:
        now = time.monotonic()
        if now < self._next_poll:
            return
        self._next_poll = now + 0.5
        # The parent-PID watchdog is a POSIX safety net. Windows reports an
        # unreliable parent for detached children, so it stays disabled there.
        if os.name == 'posix' and os.getppid() != self.parent_pid:
            self.stop()
            return
        try:
            with control_db.connect(self.paths.db) as db:
                row = db.execute(
                    'SELECT pause_requested,cancel_requested FROM jobs WHERE id=?',
                    (self.job_id,),
                ).fetchone()
            if row is None:
                self.stop()
            elif row['cancel_requested']:
                self.stop()
            elif row['pause_requested']:
                self.paused.set()
            else:
                self.paused.clear()
        except Exception:
            # A temporarily locked database must not kill a running download.
            pass

    def checkpoint(self) -> None:
        while True:
            self._poll()
            if self.stopped.is_set():
                raise Cancelled('Abgebrochen. Abgeschlossene Dateien bleiben erhalten; partielle Dateien können fortgesetzt werden.')
            if not self.paused.is_set():
                return
            self.stopped.wait(0.1)


class EventWriter:
    """Small, throttled writer for progress and bounded recent events."""

    def __init__(self, paths: Paths, job_id: int):
        self.paths = paths
        self.job_id = int(job_id)
        self.db = control_db.open_db(paths.db)
        self.lock = threading.RLock()
        self.event_count = 0
        self.last_commit = 0.0
        self.last_overall = 0.0
        self.last_progress = 0.0
        self.last_stats = 0.0
        self.stats: dict[str, Any] = {}
        self.closed = False
        try:
            row = control_db.get_job(self.db, self.job_id)
            if row:
                self.stats = json.loads(row.get('stats') or '{}') or {}
        except Exception:
            self.stats = {}

    def _commit(self, force: bool = False) -> None:
        now = time.monotonic()
        if force or now - self.last_commit >= 0.5:
            try:
                self.db.commit()
            except Exception:
                pass
            self.last_commit = now

    def _update(self, **fields: Any) -> None:
        names = [name for name in fields if name in control_db._JOB_FIELDS]
        if not names:
            return
        assignments = ', '.join(f'{name}=?' for name in names)
        values = [fields[name] for name in names]
        values.append(self.job_id)
        try:
            self.db.execute(f'UPDATE jobs SET {assignments} WHERE id=?', values)
            self._commit()
        except Exception:
            pass

    def _event(self, level: str, message: str) -> None:
        try:
            control_db.add_event(self.db, self.job_id, level, message)
            self.event_count += 1
            if self.event_count % 100 == 0:
                control_db.prune_events(self.db, self.job_id)
            self._commit()
        except Exception:
            pass

    def emit(self, kind: str, value: Any) -> None:
        with self.lock:
            if self.closed:
                return
            try:
                self._emit(kind, value)
            except Exception as exc:  # never let a display update kill a job
                print(f'event writer: {type(exc).__name__}', file=sys.stderr, flush=True)

    def _emit(self, kind: str, value: Any) -> None:
        if kind == 'log':
            self._event('log', sanitize_text(value, 1000))
        elif kind == 'phase':
            text = sanitize_text(value, 300)
            self._update(phase=text)
            self._event('phase', text)
        elif kind == 'stats':
            if isinstance(value, dict):
                self.stats.update(value)
                now = time.monotonic()
                if now - self.last_stats >= 0.5:
                    self.last_stats = now
                    self._update(stats=json.dumps(self.stats, ensure_ascii=False, separators=(',', ':')))
        elif kind == 'overall':
            if isinstance(value, dict):
                done = int(value.get('done') or 0)
                total = int(value.get('total') or 0)
                if total:
                    self.stats['overall_total'] = total
                self.stats['overall_done'] = done
                self.stats['scanning'] = bool(value.get('scanning'))
                now = time.monotonic()
                if now - self.last_overall >= 0.5 or done == total:
                    self.last_overall = now
                    self._update(progress_done=done, progress_total=total,
                                 stats=json.dumps(self.stats, ensure_ascii=False, separators=(',', ':')))
        elif kind == 'progress':
            if isinstance(value, dict):
                now = time.monotonic()
                if now - self.last_progress >= 0.8:
                    self.last_progress = now
                    self.stats['current_file'] = sanitize_text(value.get('file'), 300)
                    self.stats['current_done'] = int(value.get('done') or 0)
                    self.stats['current_total'] = int(value.get('total') or 0)
                    self.stats['current_speed'] = float(value.get('speed') or 0)
                    self._update(stats=json.dumps(self.stats, ensure_ascii=False, separators=(',', ':')))
        elif kind == 'media_complete':
            if isinstance(value, dict):
                compact = {
                    'relative': sanitize_text(value.get('relative'), 500),
                    'kind': sanitize_text(value.get('kind'), 20),
                    'size': int(value.get('size') or 0),
                    'profile': sanitize_text(value.get('profile'), 100),
                }
                self._event('media', json.dumps(compact, ensure_ascii=False, separators=(',', ':')))
        elif kind == 'pipeline':
            if isinstance(value, dict) and value.get('stage'):
                self._update(phase=sanitize_text(value.get('stage'), 100))
        elif kind in {'result', 'error', 'cancelled', 'done'}:
            # The worker main handles these; keep them out of the event table.
            return
        else:
            self._event('log', sanitize_text(value, 500))

    def flush(self) -> None:
        with self.lock:
            try:
                self._commit(force=True)
            except Exception:
                pass

    def close(self) -> None:
        with self.lock:
            self.flush()
            self.closed = True
            try:
                self.db.close()
            except Exception:
                pass


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print('usage: python -m ofdl.dsm.worker JOB_ID', file=sys.stderr)
        return 2
    try:
        job_id = int(args[0])
    except ValueError:
        print('invalid job id', file=sys.stderr)
        return 2

    try:
        os.umask(0o077)
    except (AttributeError, OSError):
        pass
    paths = resolve_paths()
    ensure_dirs(paths)
    control_db.init_db(paths.db)

    with control_db.connect(paths.db) as db:
        job = control_db.get_job(db, job_id)
    if job is None:
        print('job not found', file=sys.stderr)
        return 2
    if job['status'] not in control_db.ACTIVE_STATES:
        return 0
    if job.get('cancel_requested'):
        with control_db.connect(paths.db) as db:
            control_db.finish_job(db, job_id, 'cancelled', error='Vor dem Start abgebrochen.', exit_code=130)
        return 130

    with control_db.connect(paths.db) as db:
        control_db.update_job(db, job_id, status='running', pid=os.getpid(),
                              started_at=control_db.now_iso())
    try:
        payload = json.loads(job.get('payload') or '{}')
        if not isinstance(payload, dict):
            raise AppError('Ungültige Auftragsdaten.')
    except (ValueError, TypeError, AppError) as exc:
        with control_db.connect(paths.db) as db:
            control_db.finish_job(db, job_id, 'failed', error=sanitize_text(exc), exit_code=1)
        return 1

    control = JobControl(paths, job_id)
    writer = EventWriter(paths, job_id)
    exit_code = 0
    try:
        result = run_job(paths, str(job['kind']), payload, control, writer.emit)
        encoded = json.dumps(result, ensure_ascii=False, separators=(',', ':'))
        if len(encoded.encode('utf-8')) > MAX_RESULT_BYTES:
            result = {'message': 'Ergebnis wurde wegen seiner Größe gekürzt.'}
        writer.flush()
        with control_db.connect(paths.db) as db:
            control_db.finish_job(db, job_id, 'completed', result=result, exit_code=0)
    except Cancelled as exc:
        exit_code = 130
        writer.flush()
        with control_db.connect(paths.db) as db:
            control_db.finish_job(db, job_id, 'cancelled', error=sanitize_text(str(exc)), exit_code=exit_code)
    except (AppError, SessionError) as exc:
        exit_code = 1
        writer.flush()
        with control_db.connect(paths.db) as db:
            control_db.finish_job(db, job_id, 'failed', error=sanitize_text(str(exc)), exit_code=exit_code)
    except Exception as exc:
        exit_code = 1
        traceback.print_exc(file=sys.stderr)
        writer.flush()
        with control_db.connect(paths.db) as db:
            control_db.finish_job(db, job_id, 'failed',
                                  error=f'Auftrag fehlgeschlagen ({type(exc).__name__}). Details stehen im Auftragsprotokoll.',
                                  exit_code=exit_code)
    finally:
        writer.flush()
        writer.close()
        control.stop()
        with control_db.connect(paths.db) as db:
            control_db.prune_events(db, job_id)
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
