"""Native DSM control service.

Only the Python standard library is imported here.  Downloads, API requests,
Pillow and curl_cffi live in the worker subprocess, which exits after each job.
"""
from __future__ import annotations

import argparse
import hmac
import json
import logging
import logging.handlers
import mimetypes
import os
import re
import shlex
import shutil
import signal
import subprocess
import threading
import time
from contextlib import suppress
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

from ..auth import SessionError, parse_session
from ..common import AppError
from . import DEFAULT_PORT, DEFAULT_SHARE_NAME, PACKAGE_VERSION, SERVICE_VERSION
from . import db as control_db
from .config import (Paths, allowed_roots, default_output_dir, directory_is_writable,
                     ensure_dirs, human_bytes, path_is_allowed, resolve_paths,
                     resolve_share_root)
from .jobs import (CATEGORIES, normalize_download_options, normalize_preview,
                    normalize_proxy, normalize_schedule, normalize_schedule_options,
                    public_job, resolve_output_dir, json_safe, normalize_renewal, parse_profiles)
from .locale import dsm_language
from .processes import register_worker, signal_worker
from .security import (LoginLimiter, SecurityError, SessionStore, new_csrf, new_token,
                       redact_proxy, sanitize_text, set_password, verify_password)

LOG = logging.getLogger('ofdl.dsm.service')
SESSION_SECONDS = 12 * 60 * 60
MAX_JSON_BYTES = 256 * 1024
MAX_SESSION_IMPORT_BYTES = 2 * 1024 * 1024
MAX_STATIC_BYTES = 2 * 1024 * 1024
COOKIE_NAME = 'ofdl_session'
STATIC_EXTENSIONS = {'.css', '.js', '.svg', '.png', '.ico', '.webmanifest', '.woff2'}


class HTTPError(Exception):
    def __init__(self, status: int, message: str):
        self.status = int(status)
        self.message = str(message)
        super().__init__(message)


def _json_dump(value: Any) -> bytes:
    return json.dumps(json_safe(value), ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')


def _parse_cookies(value: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for part in (value or '').split(';'):
        if '=' not in part:
            continue
        name, token = part.strip().split('=', 1)
        if name:
            result[name] = token
    return result


def _proc_memory(pid: int | None) -> dict[str, int]:
    """PSS/RSS from procfs; zeros on platforms without it (e.g. Windows tests)."""
    result = {'pss_kb': 0, 'rss_kb': 0}
    if not pid:
        return result
    try:
        with open(f'/proc/{int(pid)}/smaps_rollup', 'r', encoding='ascii', errors='ignore') as stream:
            for line in stream:
                if line.startswith('Pss:'):
                    result['pss_kb'] = int(line.split()[1])
                elif line.startswith('Rss:'):
                    result['rss_kb'] = int(line.split()[1])
        if result['rss_kb']:
            return result
    except (OSError, ValueError):
        pass
    try:
        with open(f'/proc/{int(pid)}/status', 'r', encoding='ascii', errors='ignore') as stream:
            for line in stream:
                if line.startswith('VmRSS:'):
                    result['rss_kb'] = int(line.split()[1])
                    break
    except (OSError, ValueError):
        pass
    return result


class JobManager:
    def __init__(self, paths: Paths):
        self.paths = paths
        self.lock = threading.RLock()
        self.process: subprocess.Popen[bytes] | None = None
        self.job_id: int | None = None
        self._threads: list[threading.Thread] = []
        self.stopping = False

    def _active(self) -> dict[str, Any] | None:
        with control_db.connect(self.paths.db) as db:
            return control_db.active_job(db)

    def _worker_command(self) -> list[str]:
        override = os.environ.get('OFDL_WORKER_COMMAND', '').strip()
        if override:
            if override.startswith('['):
                value = json.loads(override)
                if isinstance(value, list) and all(isinstance(item, str) for item in value):
                    return value
                raise RuntimeError('OFDL_WORKER_COMMAND must be a JSON string array or a shell command.')
            parts = shlex.split(override, posix=(os.name != 'nt'))
            if os.name == 'nt':
                parts = [part[1:-1] if len(part) >= 2 and part[0] == part[-1] == '"' else part
                         for part in parts]
            return parts
        python = self.paths.worker_python
        return [str(python), '-m', 'ofdl.dsm.worker']

    def _worker_env(self) -> dict[str, str]:
        env = {
            'PATH': os.environ.get('PATH', '/usr/local/bin:/usr/bin:/bin'),
            'LANG': os.environ.get('LANG', 'C'),
            'LC_ALL': os.environ.get('LC_ALL', ''),
            'TZ': os.environ.get('TZ', ''),
            'PYTHONPATH': str(self.paths.pkgdest),
            'PYTHONUNBUFFERED': '1',
            'PYTHONDONTWRITEBYTECODE': '1',
            'HOME': str(self.paths.home),
            'TMPDIR': str(self.paths.tmp),
            'XDG_CONFIG_HOME': str(self.paths.config),
            'SYNOPKG_PKGDEST': str(self.paths.pkgdest),
            'SYNOPKG_PKGVAR': str(self.paths.pkgvar),
            'OFDL_DATA_DIR': str(self.paths.data),
            'OFDL_CONFIG_DIR': str(self.paths.config),
            'OFDL_LOG_DIR': str(self.paths.logs),
            'OFDL_PREVIEW_DIR': str(self.paths.previews),
            'OFDL_TMP_DIR': str(self.paths.tmp),
            'OFDL_HOME': str(self.paths.home),
            'OFDL_VENV': str(self.paths.venv),
            'OFDL_PARENT_PID': str(os.getpid()),
        }
        share = self.paths.share or resolve_share_root(self.paths)
        if share is not None:
            env['OFDL_SHARE_ROOT'] = str(share)
        return {key: value for key, value in env.items() if value}

    def start(self, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            if self.stopping:
                raise HTTPError(503, 'Das Paket wird gestoppt. Keine neuen Aufträge.')
            if self.process is not None:
                raise HTTPError(409, 'Der vorherige Worker wird noch beendet. Bitte kurz warten.')
            active = self._active()
            if active is not None:
                raise HTTPError(409, f'Es läuft bereits ein Auftrag (ID {active["id"]}).')
            with control_db.connect(self.paths.db) as db:
                job_id = control_db.create_job(db, kind, payload)
            log_path = self.paths.logs / f'job-{job_id}.log'
            log_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.chmod(log_path, 0o600)
            except OSError:
                pass
            command = self._worker_command() + [str(job_id)]
            env = self._worker_env()
            token = new_token()
            env['OFDL_RUN_TOKEN'] = token
            popen_kwargs: dict[str, Any] = {
                'cwd': str(self.paths.pkgdest),
                'env': env,
                'stdin': subprocess.DEVNULL,
                'stdout': subprocess.DEVNULL,
                'close_fds': True,
            }
            if os.name == 'posix':
                popen_kwargs['start_new_session'] = True
            process = None
            try:
                with open(log_path, 'ab', buffering=0) as log_stream:
                    popen_kwargs['stderr'] = log_stream
                    process = subprocess.Popen(command, **popen_kwargs)
                register_worker(self.paths.pkgvar, process.pid, token)
                with control_db.connect(self.paths.db) as db:
                    control_db.update_job(db, job_id, status='running', pid=process.pid,
                                          started_at=control_db.now_iso(),
                                          error=None)
                    job = control_db.get_job(db, job_id)
            except Exception as exc:
                # Registration/DB can fail after spawn (e.g. full disk). Never
                # leave an untracked worker running behind a "failed" job.
                if process is not None:
                    self._signal(process, signal.SIGTERM)
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        self._signal(process, getattr(signal, 'SIGKILL', 9))
                        with suppress(subprocess.TimeoutExpired):
                            process.wait(timeout=2)
                with control_db.connect(self.paths.db) as db:
                    control_db.update_job(db, job_id, status='failed',
                                          error=f'Worker konnte nicht gestartet werden ({type(exc).__name__}).',
                                          finished_at=control_db.now_iso())
                    job = control_db.get_job(db, job_id)
                LOG.exception('worker start failed')
                return public_job(job or {'kind': kind, 'status': 'failed', 'payload': '{}'})
            self.process = process
            self.job_id = job_id
            thread = threading.Thread(target=self._monitor, args=(process, job_id),
                                      name=f'ofdl-job-{job_id}', daemon=True)
            thread.start()
            self._threads = [item for item in self._threads if item.is_alive()]
            self._threads.append(thread)
            return public_job(job or {'kind': kind, 'status': 'queued', 'payload': '{}'})

    def _monitor(self, process: subprocess.Popen[bytes], job_id: int) -> None:
        returncode = process.wait()
        with self.lock:
            self._finish_process(process, job_id, returncode)

    def _finish_process(self, process: subprocess.Popen[bytes], job_id: int, returncode: int) -> None:
        # Keep completion metadata and session verification serialized with new
        # jobs/session imports; an old session test must not verify a new import.
        with self.lock:
            if self.process is process:
                # Clean descendants even when the worker leader exited first.
                if signal_worker(self.paths.pkgvar, signal.SIGTERM, process.pid):
                    time.sleep(0.3)
                    signal_worker(self.paths.pkgvar, getattr(signal, 'SIGKILL', 9), process.pid)
                self.process = None
                self.job_id = None
        try:
            with control_db.connect(self.paths.db) as db:
                row = control_db.get_job(db, job_id)
                if row is not None and row['status'] in control_db.ACTIVE_STATES:
                    cancelled = bool(row.get('cancel_requested'))
                    control_db.finish_job(
                        db, job_id,
                        'cancelled' if cancelled else 'failed',
                        error=('Auftrag wurde abgebrochen.' if cancelled else
                               f'Der Arbeitsprozess wurde unerwartet beendet (Code {returncode}). Details stehen im Auftragsprotokoll.'),
                        exit_code=returncode,
                    )
                if row is not None and row.get('kind') == 'test_session':
                    final = control_db.get_job(db, job_id)
                    if final is not None:
                        control_db.set_setting(
                            db, 'session_verified',
                            '1' if final['status'] == 'completed' else '0')
                control_db.prune_events(db, job_id)
                control_db.prune_jobs(db)
        except Exception:
            LOG.exception('worker monitor failed')

    def cancel(self, job_id: int) -> dict[str, Any]:
        with self.lock:
            with control_db.connect(self.paths.db) as db:
                row = control_db.get_job(db, job_id)
                if row is None:
                    raise HTTPError(404, 'Auftrag nicht gefunden.')
                if row['status'] not in control_db.ACTIVE_STATES:
                    raise HTTPError(409, 'Der Auftrag ist bereits beendet.')
                control_db.update_job(db, job_id, cancel_requested=1, pause_requested=0)
            process = self.process if self.job_id == job_id else None
            if process is not None:
                thread = threading.Thread(target=self._terminate_later, args=(process, job_id),
                                          name=f'ofdl-cancel-{job_id}', daemon=True)
                thread.start()
            return {'ok': True}

    def _terminate_later(self, process: subprocess.Popen[bytes], job_id: int) -> None:
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline:
            if process.poll() is not None:
                return
            time.sleep(0.2)
        self._signal(process, signal.SIGTERM)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._signal(process, getattr(signal, 'SIGKILL', 9))

    def _signal(self, process: subprocess.Popen[bytes], sig: int) -> None:
        if signal_worker(self.paths.pkgvar, sig, process.pid):
            return
        if process.poll() is None:
            with suppress(Exception):
                if os.name == 'posix' and os.getpgid(process.pid) == process.pid:
                    os.killpg(process.pid, sig)
                elif sig == signal.SIGTERM:
                    process.terminate()
                else:
                    process.kill()

    def pause(self, job_id: int, paused: bool) -> dict[str, Any]:
        with self.lock:
            with control_db.connect(self.paths.db) as db:
                row = control_db.get_job(db, job_id)
                if row is None:
                    raise HTTPError(404, 'Auftrag nicht gefunden.')
                if row['status'] not in control_db.ACTIVE_STATES:
                    raise HTTPError(409, 'Der Auftrag ist bereits beendet.')
                control_db.update_job(db, job_id, pause_requested=1 if paused else 0)
            return {'ok': True}

    def shutdown(self) -> None:
        self.stopping = True
        active = None
        with suppress(Exception):
            active = self._active()
        if active is not None:
            with suppress(Exception):
                self.cancel(int(active['id']))
        deadline = time.monotonic() + 6.0
        while time.monotonic() < deadline:
            with self.lock:
                process = self.process
            if process is None or process.poll() is not None:
                break
            time.sleep(0.2)
        with self.lock:
            process = self.process
        if process is not None and process.poll() is None:
            self._signal(process, signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._signal(process, getattr(signal, 'SIGKILL', 9))
                with suppress(subprocess.TimeoutExpired):
                    process.wait(timeout=2)


class Scheduler(threading.Thread):
    def __init__(self, state: 'AppState'):
        super().__init__(name='ofdl-scheduler', daemon=True)
        self.state = state
        self.stop_event = threading.Event()

    def stop(self) -> None:
        self.stop_event.set()

    def run(self) -> None:
        while not self.stop_event.wait(20.0):
            try:
                self.tick()
            except Exception:
                LOG.exception('scheduler tick failed')

    def tick(self) -> None:
        with self.state.job_manager.lock:
            self._tick()
            self._tick_renewals()

    def _tick_renewals(self) -> None:
        with control_db.connect(self.state.paths.db) as db:
            settings = control_db.get_json(db, 'free_renewal', {})
            last = control_db.get_setting(db, 'free_renewal_last_run', '')
        if not settings.get('enabled') or self.state.job_manager._active():
            return
        credentials = self.state.session_store.load()
        if credentials is None or settings.get('account_id') != credentials.user_id:
            return
        now = datetime.now()
        today = now.date().isoformat()
        if last == today or now.strftime('%H:%M') < str(settings.get('time', '04:00')):
            return
        payload = {**normalize_renewal(settings, require_confirmation=False), 'account_id': credentials.user_id}
        self.state.job_manager.start('free_renew', payload)
        with control_db.connect(self.state.paths.db) as db:
            control_db.set_setting(db, 'free_renewal_last_run', today)

    def _tick(self) -> None:
        paths = self.state.paths
        with control_db.connect(paths.db) as db:
            schedule = control_db.get_json(db, 'schedule', {})
            last_run = control_db.get_setting(db, 'schedule_last_run', '')
            defaults = control_db.get_json(db, 'download_defaults', {})
        if not isinstance(schedule, dict) or not schedule.get('enabled'):
            return
        try:
            hour, minute = [int(part) for part in str(schedule.get('time', '03:30')).split(':', 1)]
        except (ValueError, TypeError):
            return
        now = datetime.now()
        scheduled = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if now < scheduled:
            return
        today = now.date().isoformat()
        if last_run == today:
            return
        if self.state.session_store.load() is None:
            LOG.info('schedule skipped: no session')
            return
        active = self.state.job_manager._active()
        if active is not None:
            return
        options = dict(schedule.get('options') or defaults)
        output = self.state.output_dir()
        if output is None:
            return
        # Saved schedules from older revisions may contain a stale destination.
        options['output_dir'] = str(output)
        try:
            payload = normalize_download_options(options, paths)
            self.state.job_manager.start('download', payload)
        except (AppError, HTTPError, SecurityError) as exc:
            LOG.warning('schedule skipped: %s', sanitize_text(exc))
            with control_db.connect(paths.db) as db:
                control_db.set_setting(db, 'schedule_last_run', today)
            return
        with control_db.connect(paths.db) as db:
            control_db.set_setting(db, 'schedule_last_run', today)
        LOG.info('scheduled download started')


class AppState:
    def __init__(self, paths: Paths, *, start_scheduler: bool = True):
        self.paths = paths
        ensure_dirs(paths)
        control_db.init_db(paths.db)
        with control_db.connect(paths.db) as db:
            control_db.mark_stale_jobs(db)
            control_db.prune_jobs(db)
        self.started = time.monotonic()
        self.sessions: dict[str, dict[str, Any]] = {}
        self.sessions_lock = threading.RLock()
        self.limiter = LoginLimiter()
        self.session_store = SessionStore(paths.data)
        self.job_manager = JobManager(paths)
        self._library_cache: tuple[float, dict[str, Any]] | None = None
        self.scheduler = Scheduler(self) if start_scheduler else None
        if self.scheduler is not None:
            self.scheduler.start()

    # -- paths / settings -------------------------------------------------
    def ensure_output_dir(self) -> Path | None:
        """Compatibility entry point; never create or select a library implicitly."""
        return self.output_dir()

    @staticmethod
    def apply_share_permissions(path: Path) -> None:
        """Keep newly created folders writable for the package account.

        DSM share ACLs and the administrator account remain in control.  The
        service deliberately does not chown to an admin group; DSM 7 blocks
        third-party packages from requesting administrator membership.
        """
        if os.name != 'posix':
            return
        with suppress(OSError):
            os.chmod(path, 0o770)

    def output_dir(self) -> Path | None:
        with control_db.connect(self.paths.db) as db:
            if control_db.get_setting(db, 'library_confirmed', '') != '1':
                return None
            configured = control_db.get_setting(db, 'output_dir', '')
        if not configured:
            return None
        try:
            return Path(configured).resolve()
        except OSError:
            return None

    def password_configured(self) -> bool:
        with control_db.connect(self.paths.db) as db:
            return bool(control_db.get_setting(db, 'password_hash', ''))

    def public_settings(self) -> dict[str, Any]:
        with control_db.connect(self.paths.db) as db:
            schedule = control_db.get_json(db, 'schedule', {'enabled': False, 'time': '03:30', 'options': {}})
            defaults = control_db.get_json(db, 'download_defaults', {})
            proxy = control_db.get_setting(db, 'proxy', '')
            rules_source = control_db.get_setting(db, 'rules_source', '')
            last_run = control_db.get_setting(db, 'schedule_last_run', '')
            confirmed = control_db.get_setting(db, 'library_confirmed', '') == '1'
            output_dir = control_db.get_setting(db, 'output_dir', '') if confirmed else ''
            renewal = control_db.get_json(db, 'free_renewal', {'enabled': False, 'profiles': [], 'time': '04:00'})
        share = resolve_share_root(self.paths)
        share_default = default_output_dir(self.paths)
        return {
            'output_dir': output_dir or (str(share_default) if share_default else ''),
            'share': {
                'name': share.name if share else DEFAULT_SHARE_NAME,
                'root': str(share) if share else '',
                'default_output': str(share_default) if share_default else '',
            },
            'schedule': schedule if isinstance(schedule, dict) else {'enabled': False, 'time': '03:30', 'options': {}},
            'schedule_last_run': last_run,
            'download_defaults': defaults if isinstance(defaults, dict) else {},
            'proxy': redact_proxy(proxy),
            'proxy_set': bool(proxy),
            'rules_source': rules_source,
            'version': SERVICE_VERSION,
            'package_version': PACKAGE_VERSION,
            'categories': list(CATEGORIES),
            'free_renewal': renewal,
        }

    # -- sessions ---------------------------------------------------------
    def create_session(self) -> tuple[str, str]:
        token = new_token()
        csrf = new_csrf()
        expiry = time.time() + SESSION_SECONDS
        with self.sessions_lock:
            self._prune_sessions()
            self.sessions[token] = {'expires': expiry, 'csrf': csrf}
        return token, csrf

    def get_session(self, token: str | None) -> dict[str, Any] | None:
        if not token:
            return None
        with self.sessions_lock:
            entry = self.sessions.get(token)
            if entry is None:
                return None
            if entry['expires'] < time.time():
                self.sessions.pop(token, None)
                return None
            return dict(entry)

    def drop_session(self, token: str | None) -> None:
        if not token:
            return
        with self.sessions_lock:
            self.sessions.pop(token, None)

    def drop_other_sessions(self, keep: str | None) -> None:
        with self.sessions_lock:
            for token in list(self.sessions):
                if token != keep:
                    self.sessions.pop(token, None)

    def _prune_sessions(self) -> None:
        now = time.time()
        for token in [key for key, value in self.sessions.items() if value['expires'] < now]:
            self.sessions.pop(token, None)

    # -- library / folders ------------------------------------------------
    def library(self) -> dict[str, Any]:
        output = self.output_dir()
        now = time.monotonic()
        if (self._library_cache and now - self._library_cache[0] < 5.0
                and self._library_cache[1].get('output_dir') == (str(output) if output else '')):
            return self._library_cache[1]
        stats = control_db.library_stats(output)
        stats['output_dir'] = str(output) if output else ''
        stats['writable'] = bool(output and directory_is_writable(output))
        self._library_cache = (now, stats)
        return stats

    def list_folders(self, requested: str | None) -> dict[str, Any]:
        roots = allowed_roots(self.paths)
        if not roots:
            raise HTTPError(409, 'Kein freigegebenes Volume gefunden.')
        root = resolve_share_root(self.paths) or roots[0]
        if requested:
            try:
                current = Path(requested).expanduser().resolve()
            except OSError:
                raise HTTPError(400, 'Der Ordnerpfad ist ungültig.') from None
        else:
            current = root
        if not path_is_allowed(current, roots):
            raise HTTPError(403, 'Der Ordner liegt außerhalb der freigegebenen Volumes.')
        if not current.is_dir():
            raise HTTPError(400, 'Der Pfad ist kein Ordner.')
        items: list[dict[str, str]] = []
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    if len(items) >= 500:
                        break
                    try:
                        if entry.is_dir(follow_symlinks=False) and not entry.name.startswith('@'):
                            items.append({'name': entry.name, 'path': str(current / entry.name)})
                    except OSError:
                        continue
        except OSError:
            raise HTTPError(403, 'Der Ordner kann nicht gelesen werden.') from None
        items.sort(key=lambda item: item['name'].casefold())
        parent = None
        if current != root and current.parent != current and path_is_allowed(current.parent, roots):
            parent = str(current.parent)
        return {
            'path': str(current),
            'parent': parent,
            'root': str(root),
            'roots': [str(item) for item in roots],
            # Browsing must not create even a temporary write-probe file.
            'writable': os.access(current, os.W_OK),
            'items': items,
        }

    def create_folder(self, parent: Any, name: Any) -> str:
        roots = allowed_roots(self.paths)
        try:
            base = Path(str(parent or '')).expanduser().resolve()
        except OSError:
            raise HTTPError(400, 'Der übergeordnete Ordner ist ungültig.') from None
        if not path_is_allowed(base, roots):
            raise HTTPError(403, 'Der Ordner liegt außerhalb der freigegebenen Volumes.')
        if not base.is_dir():
            raise HTTPError(400, 'Der übergeordnete Ordner existiert nicht.')
        clean = str(name or '').strip()
        if (not clean or len(clean) > 100 or clean in {'.', '..'}
                or any(char in clean for char in '/\\\x00') or clean.startswith('.')):
            raise HTTPError(400, 'Der Ordnername ist ungültig.')
        target = base / clean
        try:
            target.mkdir(mode=0o770)
            self.apply_share_permissions(target)
        except FileExistsError:
            raise HTTPError(409, 'Der Ordner existiert bereits.') from None
        except OSError:
            raise HTTPError(403, 'Der Ordner konnte nicht erstellt werden.') from None
        return str(target)

    def preview_file(self, name: str) -> Path:
        if not re.fullmatch(r'[a-f0-9]{64}\.png', name):
            raise HTTPError(404, 'Vorschau nicht gefunden.')
        path = self.paths.previews / name
        if not path.is_file() or path.is_symlink():
            raise HTTPError(404, 'Vorschau nicht gefunden.')
        return path

    # -- lifecycle --------------------------------------------------------
    def close(self) -> None:
        self.job_manager.stopping = True
        if self.scheduler is not None:
            self.scheduler.stop()
            self.scheduler.join(timeout=2)
        self.job_manager.shutdown()


class BoundedThreadingHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 32

    def __init__(self, server_address, handler_class, state: AppState):
        self.state = state
        self._slots = threading.BoundedSemaphore(8)
        super().__init__(server_address, handler_class)

    def process_request(self, request, client_address):
        if not self._slots.acquire(blocking=False):
            with suppress(Exception):
                request.sendall(b'HTTP/1.1 503 Service Unavailable\r\nConnection: close\r\nContent-Length: 0\r\n\r\n')
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._slots.release()


class RequestHandler(BaseHTTPRequestHandler):
    server_version = 'OnlyFansDL'
    sys_version = ''
    protocol_version = 'HTTP/1.1'
    state: AppState

    # -- plumbing ---------------------------------------------------------
    def setup(self) -> None:
        super().setup()
        try:
            self.connection.settimeout(30)
        except OSError:
            pass

    def log_message(self, format: str, *args: Any) -> None:
        # Do not log query strings or cookies.
        path = unquote(urlsplit(self.path).path)
        LOG.info('%s %s %s', self.client_address[0], self.command, path[:300])

    def _common_headers(self) -> None:
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'SAMEORIGIN')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Permissions-Policy', 'geolocation=(), microphone=(), camera=()')
        self.send_header('Content-Security-Policy',
                         "default-src 'self'; img-src 'self' data:; style-src 'self'; "
                         "script-src 'self'; connect-src 'self'; frame-ancestors 'self'; "
                         "base-uri 'none'; form-action 'self'")

    def _send(self, status: int, content_type: str, body: bytes, *,
              cache: str = 'no-store', extra: dict[str, str] | None = None) -> None:
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', cache)
        if self.close_connection:
            self.send_header('Connection', 'close')
        self._common_headers()
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != 'HEAD' and body:
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

    def send_json(self, status: int, payload: Any, *, extra: dict[str, str] | None = None) -> None:
        self._send(status, 'application/json; charset=utf-8', _json_dump(payload), extra=extra)

    def send_text(self, status: int, text: str) -> None:
        self._send(status, 'text/plain; charset=utf-8', text.encode('utf-8'))

    def send_file(self, path: Path, *, content_type: str | None = None,
                  cache: str = 'no-store') -> None:
        try:
            size = path.stat().st_size
            if size > MAX_STATIC_BYTES:
                raise HTTPError(413, 'Datei ist zu groß.')
            stream = path.open('rb')
        except OSError:
            raise HTTPError(404, 'Datei nicht gefunden.') from None
        with stream:
            self.send_response(200)
            self.send_header('Content-Type', content_type or mimetypes.guess_type(str(path))[0] or 'application/octet-stream')
            self.send_header('Content-Length', str(size))
            self.send_header('Cache-Control', cache)
            self._common_headers()
            self.end_headers()
            if self.command == 'HEAD':
                return
            try:
                shutil.copyfileobj(stream, self.wfile, length=64 * 1024)
            except (BrokenPipeError, ConnectionResetError):
                pass

    def _read_body(self, maximum: int) -> bytes:
        length_text = self.headers.get('Content-Length')
        if not length_text:
            raise HTTPError(411, 'Content-Length fehlt.')
        try:
            length = int(length_text)
        except ValueError:
            raise HTTPError(400, 'Content-Length ist ungültig.') from None
        if length < 0 or length > maximum:
            self.close_connection = True
            raise HTTPError(413, 'Anfrage ist zu groß.')
        chunks: list[bytes] = []
        remaining = length
        while remaining > 0:
            chunk = self.rfile.read(min(64 * 1024, remaining))
            if not chunk:
                raise HTTPError(400, 'Anfrage wurde unvollständig übertragen.')
            chunks.append(chunk)
            remaining -= len(chunk)
        return b''.join(chunks)

    def read_json(self, maximum: int = MAX_JSON_BYTES) -> dict[str, Any]:
        body = self._read_body(maximum)
        if not body.strip():
            return {}
        try:
            value = json.loads(body.decode('utf-8'))
        except (UnicodeError, ValueError, RecursionError):
            raise HTTPError(400, 'JSON ist ungültig.') from None
        if not isinstance(value, dict):
            raise HTTPError(400, 'Es wird ein JSON-Objekt erwartet.')
        return value

    # -- auth -------------------------------------------------------------
    def _session_token(self) -> str | None:
        cookies = _parse_cookies(self.headers.get('Cookie', ''))
        return cookies.get(COOKIE_NAME)

    def _session(self) -> tuple[str, dict[str, Any]] | None:
        token = self._session_token()
        entry = self.state.get_session(token)
        if entry is None or token is None:
            return None
        return token, entry

    def require_auth(self) -> tuple[str, dict[str, Any]]:
        session = self._session()
        if session is None:
            raise HTTPError(401, 'Anmeldung erforderlich.')
        return session

    def _same_origin(self) -> bool:
        host = (self.headers.get('Host') or '').lower()
        for header in ('Origin', 'Referer'):
            value = self.headers.get(header)
            if not value:
                continue
            try:
                parsed = urlsplit(value)
            except ValueError:
                return False
            return parsed.netloc.lower() == host
        return True

    def require_csrf(self, session: dict[str, Any]) -> None:
        token = self.headers.get('X-CSRF-Token', '')
        if not token or not hmac.compare_digest(token, str(session.get('csrf', ''))):
            raise HTTPError(403, 'CSRF-Token ungültig. Seite neu laden.')
        if not self._same_origin():
            raise HTTPError(403, 'Ungültiger Ursprung.')

    def _set_cookie(self, token: str) -> None:
        secure = (os.environ.get('OFDL_COOKIE_SECURE') == '1'
                  or (self.headers.get('X-Forwarded-Proto', '').lower() == 'https'))
        suffix = '; Secure' if secure else ''
        self._cookie = (f'{COOKIE_NAME}={token}; HttpOnly; SameSite=Strict; Path=/; '
                        f'Max-Age={SESSION_SECONDS}{suffix}')

    def _clear_cookie(self) -> None:
        self._cookie = f'{COOKIE_NAME}=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0'

    def _extra_headers(self) -> dict[str, str]:
        cookie = getattr(self, '_cookie', None)
        return {'Set-Cookie': cookie} if cookie else {}

    # -- request dispatch -------------------------------------------------
    def do_GET(self) -> None:
        self._handle('GET')

    def do_HEAD(self) -> None:
        self._handle('HEAD')

    def do_POST(self) -> None:
        self._handle('POST')

    def do_DELETE(self) -> None:
        self._handle('DELETE')

    def _handle(self, method: str) -> None:
        self._cookie: str | None = None
        # Some actions (logout, pause/cancel) intentionally need no body. Never
        # reuse their connection with an unread body as the next HTTP request.
        if method not in {'GET', 'HEAD'}:
            self.close_connection = True
        try:
            parsed = urlsplit(self.path)
            path = unquote(parsed.path)
            if '\x00' in path:
                raise HTTPError(400, 'Ungültiger Pfad.')
            query = parse_qs(parsed.query, keep_blank_values=True)
            if method == 'GET' or method == 'HEAD':
                self._route_get(path, query)
            elif method == 'POST':
                self._route_post(path, query)
            elif method == 'DELETE':
                self._route_delete(path, query)
            else:
                raise HTTPError(405, 'Methode nicht erlaubt.')
        except HTTPError as exc:
            self.close_connection = True
            extra = self._extra_headers()
            self.send_json(exc.status, {'error': exc.message,
                                        'setup_required': not self.state.password_configured()},
                           extra=extra)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            self.close_connection = True
            LOG.exception('request failed')
            with suppress(BrokenPipeError, ConnectionResetError):
                self.send_json(500, {'error': 'Interner Fehler. Details stehen im Dienstprotokoll.'})

    # -- GET --------------------------------------------------------------
    def _route_get(self, path: str, query: dict[str, list[str]]) -> None:
        if path == '/api/locale':
            self.send_json(200, {'language': dsm_language(), 'source': 'dsm-system'})
            return
        if path == '/api/health':
            self.send_json(200, {
                'ok': True,
                'version': SERVICE_VERSION,
                'package_version': PACKAGE_VERSION,
                'setup_required': not self.state.password_configured(),
            })
            return
        if path == '/api/session':
            session = self._session()
            if session is None:
                raise HTTPError(401, 'Anmeldung erforderlich.')
            token, entry = session
            with control_db.connect(self.state.paths.db) as db:
                verified = control_db.get_setting(db, 'session_verified', '0') == '1'
            self.send_json(200, {
                'authenticated': True,
                'csrf': entry['csrf'],
                'session': {**self.state.session_store.describe(), 'verified': verified},
                'version': SERVICE_VERSION,
            })
            return
        if path == '/api/status':
            self.require_auth()
            self.send_json(200, self._status())
            return
        if path == '/api/jobs':
            self.require_auth()
            with control_db.connect(self.state.paths.db) as db:
                rows = control_db.list_jobs(db, 20)
            self.send_json(200, {'jobs': [public_job(row) for row in rows]})
            return
        if path.startswith('/api/jobs/'):
            self.require_auth()
            segments = [part for part in path.split('/') if part]
            if len(segments) < 3:
                raise HTTPError(404, 'Auftrag nicht gefunden.')
            try:
                job_id = int(segments[2])
            except ValueError:
                raise HTTPError(404, 'Auftrag nicht gefunden.') from None
            try:
                after = int((query.get('after') or ['0'])[0] or 0)
            except ValueError:
                raise HTTPError(400, 'Ungültiger Ereignis-Zähler.') from None
            with control_db.connect(self.state.paths.db) as db:
                row = control_db.get_job(db, job_id)
                if row is None:
                    raise HTTPError(404, 'Auftrag nicht gefunden.')
                events = (control_db.recent_events(db, job_id) if (query.get('tail') or [''])[0] == '1'
                          else control_db.list_events(db, job_id, after=after, limit=200))
            self.send_json(200, {
                'job': public_job(row),
                'events': events,
                'next_after': events[-1]['id'] if events else after,
            })
            return
        if path == '/api/settings':
            self.require_auth()
            self.send_json(200, self.state.public_settings())
            return
        if path == '/api/offers':
            self.require_auth()
            credentials = self.state.session_store.load()
            account = credentials.user_id if credentials else ''
            try:
                page = max(1, int((query.get('page') or ['1'])[0]))
            except ValueError:
                raise HTTPError(400, 'Ungültige Seitennummer.') from None
            with control_db.connect(self.state.paths.db) as db:
                total = db.execute('SELECT COUNT(*) FROM offers WHERE account_id=?', (account,)).fetchone()[0]
                rows = db.execute('SELECT username,kind,status,detail,scanned_at FROM offers WHERE account_id=? '
                                  'ORDER BY username LIMIT 50 OFFSET ?', (account, (page - 1) * 50)).fetchall()
            self.send_json(200, {'items': [dict(row) for row in rows], 'page': page,
                                 'pages': max(1, (total + 49) // 50), 'total': total})
            return
        if path == '/api/folders':
            self.require_auth()
            requested = (query.get('path') or [''])[0] or None
            self.send_json(200, self.state.list_folders(requested))
            return
        if path == '/api/creators':
            self.require_auth()
            try:
                page = max(1, int((query.get('page') or ['1'])[0] or 1))
                per_page = max(1, min(100, int((query.get('per_page') or ['50'])[0] or 50)))
            except ValueError:
                raise HTTPError(400, 'Ungültige Seitennummer.') from None
            search = str((query.get('q') or [''])[0])[:100]
            with control_db.connect(self.state.paths.db) as db:
                total = control_db.count_creators(db, search)
                rows = control_db.page_creators(db, page, per_page, search)
            pages = max(1, (total + per_page - 1) // per_page)
            self.send_json(200, {'items': rows, 'page': page, 'pages': pages,
                                 'total': total, 'per_page': per_page})
            return
        if path == '/api/library':
            self.require_auth()
            self.send_json(200, self.state.library())
            return
        if path.startswith('/api/preview/'):
            self.require_auth()
            name = path.rsplit('/', 1)[-1]
            self.send_file(self.state.preview_file(name), content_type='image/png',
                           cache='private, max-age=86400')
            return
        if path in {'/', '/app'}:
            if self._session() is None:
                self._send_static('login.html' if self.state.password_configured() else 'setup.html')
            else:
                self._send_static('index.html')
            return
        if path == '/login':
            if self._session() is not None:
                self._send_redirect('/')
            else:
                self._send_static('login.html' if self.state.password_configured() else 'setup.html')
            return
        if path == '/setup':
            if self.state.password_configured():
                self._send_redirect('/login')
            else:
                self._send_static('setup.html')
            return
        if path.startswith('/static/'):
            relative = path[len('/static/'):]
            if '/' in relative or '\\' in relative:
                raise HTTPError(404, 'Datei nicht gefunden.')
            candidate = self.state.paths.web / 'static' / relative
            try:
                candidate = candidate.resolve()
                candidate.relative_to((self.state.paths.web / 'static').resolve())
            except (OSError, ValueError):
                raise HTTPError(404, 'Datei nicht gefunden.') from None
            if candidate.suffix.lower() not in STATIC_EXTENSIONS or not candidate.is_file():
                raise HTTPError(404, 'Datei nicht gefunden.')
            cache = 'public, max-age=300' if candidate.suffix.lower() in {'.css', '.js', '.svg'} else 'private, max-age=3600'
            self.send_file(candidate, cache=cache)
            return
        if path == '/favicon.ico':
            self.send_file(self.state.paths.web / 'static' / 'favicon.svg',
                           content_type='image/svg+xml', cache='public, max-age=86400')
            return
        if path == '/manifest.webmanifest':
            self.send_file(self.state.paths.web / 'static' / 'manifest.webmanifest',
                           content_type='application/manifest+json', cache='public, max-age=3600')
            return
        raise HTTPError(404, 'Nicht gefunden.')

    def _send_static(self, name: str) -> None:
        candidate = (self.state.paths.web / name).resolve()
        try:
            candidate.relative_to(self.state.paths.web.resolve())
        except ValueError:
            raise HTTPError(404, 'Datei nicht gefunden.') from None
        if not candidate.is_file():
            raise HTTPError(500, 'Oberflächendatei fehlt. Bitte Paket neu installieren.')
        self.send_file(candidate, content_type='text/html; charset=utf-8', cache='no-store')

    def _send_redirect(self, location: str) -> None:
        self._send(302, 'text/plain; charset=utf-8', b'', cache='no-store',
                   extra={'Location': location})

    def _status(self) -> dict[str, Any]:
        with control_db.connect(self.state.paths.db) as db:
            active = control_db.active_job(db)
            recent = control_db.list_jobs(db, 5)
            schedule = control_db.get_json(db, 'schedule', {'enabled': False, 'time': '03:30', 'options': {}})
            last_run = control_db.get_setting(db, 'schedule_last_run', '')
            verified = control_db.get_setting(db, 'session_verified', '0') == '1'
        output = self.state.output_dir()
        disk = None
        if output is not None and output.is_dir():
            try:
                usage = shutil.disk_usage(output)
                disk = {'total': usage.total, 'used': usage.used, 'free': usage.free,
                        'total_text': human_bytes(usage.total), 'free_text': human_bytes(usage.free)}
            except OSError:
                disk = None
        worker_memory = _proc_memory(int(active['pid']) if active and active.get('pid') else None)
        self_memory = _proc_memory(os.getpid())
        session = self.state.session_store.describe()
        session['verified'] = verified
        share = resolve_share_root(self.state.paths)
        share_default = default_output_dir(self.state.paths)
        return {
            'version': SERVICE_VERSION,
            'package_version': PACKAGE_VERSION,
            'uptime_seconds': int(time.monotonic() - self.state.started),
            'setup_required': not self.state.password_configured(),
            'session': session,
            'active_job': public_job(active) if active else None,
            'recent_jobs': [public_job(row) for row in recent],
            'schedule': schedule,
            'schedule_last_run': last_run,
            'nas_time': datetime.now().astimezone().isoformat(),
            'output_dir': str(output) if output else '',
            'share': {
                'name': share.name if share else DEFAULT_SHARE_NAME,
                'root': str(share) if share else '',
                'default_output': str(share_default) if share_default else '',
            },
            'disk': disk,
            'library': self.state.library(),
            'memory': {'service_pid': os.getpid(), **self_memory, 'worker': worker_memory},
        }

    # -- POST -------------------------------------------------------------
    def _route_post(self, path: str, query: dict[str, list[str]]) -> None:
        if path in {'/api/session/import', '/api/session/clear'}:
            session = self.require_auth()
            self.require_csrf(session[1])
            with self.state.job_manager.lock:
                if self.state.job_manager._active():
                    raise HTTPError(409, 'Sitzung während eines Auftrags nicht ändern. Erst Auftrag beenden.')
                self._route_post_unlocked(path, query)
            return
        self._route_post_unlocked(path, query)

    def _route_post_unlocked(self, path: str, query: dict[str, list[str]]) -> None:
        if path == '/api/login':
            self._login()
            return
        if path == '/api/setup':
            self._setup()
            return
        if path == '/api/logout':
            session = self.require_auth()
            self.require_csrf(session[1])
            self.state.drop_session(session[0])
            self._clear_cookie()
            self.send_json(200, {'ok': True}, extra=self._extra_headers())
            return
        if path == '/api/password':
            session = self.require_auth()
            self.require_csrf(session[1])
            body = self.read_json()
            self._change_password(session[0], session[1], body)
            return
        if path == '/api/session/import':
            session = self.require_auth()
            self.require_csrf(session[1])
            body = self.read_json(maximum=MAX_SESSION_IMPORT_BYTES)
            text = body.get('text')
            if not isinstance(text, str) or not text.strip():
                raise HTTPError(400, 'Bitte eine Sitzung einfügen.')
            try:
                credentials = parse_session(text)
            except SessionError as exc:
                raise HTTPError(400, self._safe_session_error(exc)) from None
            self.state.session_store.save(credentials)
            with control_db.connect(self.state.paths.db) as db:
                previous_account = control_db.get_setting(db, 'session_user_id', '')
                if previous_account != credentials.user_id:
                    control_db.set_json(db, 'free_renewal', {'enabled': False, 'profiles': [], 'time': '04:00'})
                    db.execute('DELETE FROM offers')
                    db.commit()
                control_db.set_setting(db, 'session_user_id', credentials.user_id)
                control_db.set_setting(db, 'session_verified', '0')
            self.send_json(200, {'ok': True, 'user_id': credentials.user_id})
            return
        if path == '/api/session/clear':
            session = self.require_auth()
            self.require_csrf(session[1])
            self.state.session_store.clear()
            if self.state.paths.session_file.exists():
                raise HTTPError(500, 'Sitzung konnte nicht gelöscht werden. Berechtigungen prüfen.')
            with control_db.connect(self.state.paths.db) as db:
                control_db.set_setting(db, 'session_user_id', '')
                control_db.set_setting(db, 'session_verified', '0')
            self.send_json(200, {'ok': True})
            return
        if path == '/api/settings':
            session = self.require_auth()
            self.require_csrf(session[1])
            body = self.read_json()
            with self.state.job_manager.lock:
                self._update_settings(body)
            self.send_json(200, self.state.public_settings())
            return
        if path == '/api/jobs':
            session = self.require_auth()
            self.require_csrf(session[1])
            self._start_job()
            return
        if path == '/api/preview':
            session = self.require_auth()
            self.require_csrf(session[1])
            body = self.read_json()
            self._start_job(kind_override='preview', options_override=body)
            return
        if path.startswith('/api/jobs/'):
            session = self.require_auth()
            self.require_csrf(session[1])
            segments = [part for part in path.split('/') if part]
            if len(segments) != 4:
                raise HTTPError(404, 'Auftrag nicht gefunden.')
            try:
                job_id = int(segments[2])
            except ValueError:
                raise HTTPError(404, 'Auftrag nicht gefunden.') from None
            action = segments[3]
            if action == 'cancel':
                self.send_json(202, self.state.job_manager.cancel(job_id))
            elif action in {'pause', 'resume'}:
                self.send_json(200, self.state.job_manager.pause(job_id, action == 'pause'))
            else:
                raise HTTPError(404, 'Aktion nicht gefunden.')
            return
        if path == '/api/folders':
            session = self.require_auth()
            self.require_csrf(session[1])
            body = self.read_json()
            target = self.state.create_folder(body.get('parent'), body.get('name'))
            self.send_json(201, {'path': target})
            return
        if path == '/api/creators/clear':
            session = self.require_auth()
            self.require_csrf(session[1])
            with control_db.connect(self.state.paths.db) as db:
                control_db.clear_creators(db)
            self.send_json(200, {'ok': True})
            return
        raise HTTPError(404, 'Nicht gefunden.')

    def _route_delete(self, path: str, query: dict[str, list[str]]) -> None:
        if path == '/api/session':
            session = self.require_auth()
            self.require_csrf(session[1])
            with self.state.job_manager.lock:
                if self.state.job_manager._active():
                    raise HTTPError(409, 'Sitzung während eines Auftrags nicht ändern. Erst Auftrag beenden.')
                self.state.session_store.clear()
                if self.state.paths.session_file.exists():
                    raise HTTPError(500, 'Sitzung konnte nicht gelöscht werden. Berechtigungen prüfen.')
            with control_db.connect(self.state.paths.db) as db:
                control_db.set_setting(db, 'session_user_id', '')
                control_db.set_setting(db, 'session_verified', '0')
            self.send_json(200, {'ok': True})
            return
        raise HTTPError(404, 'Nicht gefunden.')

    def _safe_session_error(self, exc: Exception) -> str:
        # SessionError messages contain no supplied secret values by contract.
        return sanitize_text(str(exc), 1000)

    def _login(self) -> None:
        body = self.read_json()
        password = body.get('password')
        if not isinstance(password, str):
            raise HTTPError(400, 'Passwort fehlt.')
        client = self.client_address[0]
        if not self.state.limiter.allow(client):
            raise HTTPError(429, 'Zu viele fehlgeschlagene Anmeldungen. Bitte eine Minute warten.')
        with control_db.connect(self.state.paths.db) as db:
            stored = control_db.get_setting(db, 'password_hash', '')
        if not stored:
            raise HTTPError(409, 'Es ist noch kein Passwort eingerichtet.')
        if not verify_password(password, stored):
            self.state.limiter.failure(client)
            raise HTTPError(401, 'Passwort falsch.')
        self.state.limiter.success(client)
        token, csrf = self.state.create_session()
        self._set_cookie(token)
        self.send_json(200, {'ok': True, 'csrf': csrf}, extra=self._extra_headers())

    def _setup(self) -> None:
        if self.state.password_configured():
            raise HTTPError(409, 'Das Passwort ist bereits eingerichtet.')
        body = self.read_json()
        password = body.get('password')
        confirm = body.get('confirm')
        if not isinstance(password, str) or password != confirm:
            raise HTTPError(400, 'Die Passwörter stimmen nicht überein.')
        try:
            set_password(self.state.paths.data, password)
        except SecurityError as exc:
            raise HTTPError(400, str(exc)) from None
        token, csrf = self.state.create_session()
        self._set_cookie(token)
        self.send_json(200, {'ok': True, 'csrf': csrf}, extra=self._extra_headers())

    def _change_password(self, token: str, session: dict[str, Any], body: dict[str, Any]) -> None:
        current = body.get('current')
        new = body.get('new')
        confirm = body.get('confirm')
        with control_db.connect(self.state.paths.db) as db:
            stored = control_db.get_setting(db, 'password_hash', '')
        if not verify_password(current, stored):
            raise HTTPError(403, 'Das aktuelle Passwort ist falsch.')
        if not isinstance(new, str) or new != confirm:
            raise HTTPError(400, 'Die neuen Passwörter stimmen nicht überein.')
        try:
            set_password(self.state.paths.data, new)
        except SecurityError as exc:
            raise HTTPError(400, str(exc)) from None
        self.state.drop_other_sessions(token)
        self.send_json(200, {'ok': True})

    def _update_settings(self, body: dict[str, Any]) -> None:
        paths = self.state.paths
        pending: dict[str, Any] = {}
        if 'output_dir' in body:
            try:
                pending['output_dir'] = str(resolve_output_dir(body.get('output_dir'), paths))
            except AppError as exc:
                raise HTTPError(400, str(exc)) from None
            pending['library_confirmed'] = '1'
            with self.state.job_manager.lock:
                if (self.state.job_manager._active() is not None
                        and pending['output_dir'] != str(self.state.output_dir() or '')):
                    raise HTTPError(409, 'Der Bibliothekspfad kann während eines Auftrags nicht geändert werden.')
        if 'schedule' in body:
            try:
                pending['schedule'] = normalize_schedule(body.get('schedule'))
            except AppError as exc:
                raise HTTPError(400, str(exc)) from None
        if 'proxy' in body:
            try:
                pending['proxy'] = normalize_proxy(body.get('proxy'))
            except AppError as exc:
                raise HTTPError(400, str(exc)) from None
        if 'rules_source' in body:
            source = str(body.get('rules_source') or '').strip()
            if source and not (source.startswith('https://') or source.startswith('/')):
                raise HTTPError(400, 'Die Regelquelle muss eine HTTPS-URL oder ein lokaler Pfad sein.')
            pending['rules_source'] = source[:2048]
        if 'download_defaults' in body:
            try:
                pending['download_defaults'] = normalize_schedule_options(body.get('download_defaults'))
            except AppError as exc:
                raise HTTPError(400, str(exc)) from None
        if 'free_renewal' in body:
            value = body['free_renewal']
            if isinstance(value, dict) and value.get('enabled') is False:
                pending['free_renewal'] = {'enabled': False, 'profiles': [], 'time': '04:00'}
            else:
                try:
                    renewal = normalize_renewal(value)
                except AppError as exc:
                    raise HTTPError(400, str(exc)) from None
                credentials = self.state.session_store.load()
                if credentials is None:
                    raise HTTPError(409, 'Bitte zuerst eine Sitzung importieren.')
                pending['free_renewal'] = {**renewal, 'account_id': credentials.user_id}

        with control_db.connect(paths.db) as db:
            for key, value in pending.items():
                if key in {'schedule', 'download_defaults', 'free_renewal'}:
                    control_db.set_json(db, key, value)
                else:
                    control_db.set_setting(db, key, str(value))
        self.state._library_cache = None

    def _start_job(self, kind_override: str | None = None, options_override: Any = None) -> None:
        with self.state.job_manager.lock:
            self._start_job_locked(kind_override, options_override)

    def _start_job_locked(self, kind_override: str | None = None, options_override: Any = None) -> None:
        paths = self.state.paths
        body = self.read_json() if kind_override is None else {}
        kind = kind_override or str(body.get('kind') or '')
        if kind not in {'test_session', 'subscriptions', 'download', 'preview', 'offers_scan', 'free_renew'}:
            raise HTTPError(400, 'Unbekannter Auftragstyp.')
        options = options_override if options_override is not None else (body.get('options') or {})
        if not isinstance(options, dict):
            raise HTTPError(400, 'Die Auftragsoptionen sind ungültig.')
        if kind in {'download', 'preview'}:
            configured = self.state.output_dir()
            if configured is None:
                raise HTTPError(409, 'Bitte zuerst den Bibliothekspfad in den Einstellungen speichern.')
            requested = options.get('output_dir')
            if requested and Path(str(requested)).resolve() != configured:
                raise HTTPError(409, 'Der Auftrag muss den gespeicherten Bibliothekspfad verwenden.')
            options = {**options, 'output_dir': str(configured)}
        if kind != 'preview' and self.state.session_store.load() is None:
            raise HTTPError(409, 'Es ist keine Sitzung eingerichtet. Bitte zuerst eine Sitzung importieren.')
        payload: dict[str, Any]
        if kind == 'download':
            try:
                payload = normalize_download_options(options, paths)
            except AppError as exc:
                raise HTTPError(400, str(exc)) from None
            if not payload.get('dry_run'):
                with control_db.connect(paths.db) as db:
                    control_db.set_json(db, 'download_defaults', payload)
        elif kind == 'preview':
            try:
                payload = normalize_preview(options, paths)
            except AppError as exc:
                raise HTTPError(400, str(exc)) from None
        elif kind == 'offers_scan':
            try:
                profiles = parse_profiles(options.get('profiles'))
                if len(profiles) > 200:
                    raise AppError('Maximal 200 zusätzliche Profile.')
                payload = {'profiles': profiles}
            except AppError as exc:
                raise HTTPError(400, str(exc)) from None
        elif kind == 'free_renew':
            try:
                payload = normalize_renewal(options)
            except AppError as exc:
                raise HTTPError(400, str(exc)) from None
            payload['account_id'] = self.state.session_store.load().user_id
        else:
            payload = {'rules_source': str(options.get('rules_source') or '')[:2048]}
        try:
            job = self.state.job_manager.start(kind, payload)
        except AppError as exc:
            raise HTTPError(400, str(exc)) from None
        self.send_json(202, {'job': job})


def create_server(paths: Paths, host: str = '127.0.0.1', port: int = 0,
                  *, start_scheduler: bool = True) -> tuple[BoundedThreadingHTTPServer, AppState]:
    state = AppState(paths, start_scheduler=start_scheduler)
    handler = type('BoundRequestHandler', (RequestHandler,), {'state': state})
    server = BoundedThreadingHTTPServer((host, port), handler, state)
    return server, state


def _configure_logging(paths: Paths) -> None:
    paths.logs.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        paths.logs / 'service.log', maxBytes=2 * 1024 * 1024, backupCount=3, encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()
    root.addHandler(handler)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='OnlyFans DL DSM control service')
    parser.add_argument('--host', default=os.environ.get('OFDL_BIND', '0.0.0.0'))
    parser.add_argument('--port', type=int, default=int(os.environ.get('OFDL_PORT', DEFAULT_PORT)))
    parser.add_argument('--no-scheduler', action='store_true')
    parser.add_argument('--foreground', action='store_true')
    args = parser.parse_args(argv)

    try:
        os.umask(0o077)
    except (AttributeError, OSError):
        pass
    paths = resolve_paths()
    ensure_dirs(paths)
    _configure_logging(paths)
    if args.foreground:
        stream = logging.StreamHandler()
        stream.setFormatter(logging.Formatter('%(levelname)s %(message)s'))
        logging.getLogger().addHandler(stream)
    try:
        server, state = create_server(paths, args.host, args.port,
                                      start_scheduler=not args.no_scheduler)
    except OSError as exc:
        LOG.error('cannot bind %s:%s (%s)', args.host, args.port, type(exc).__name__)
        return 1
    pid_file = paths.pkgvar / 'service.pid'
    try:
        pid_file.write_text(str(os.getpid()), encoding='ascii')
        os.chmod(pid_file, 0o600)
    except OSError:
        pass
    stop_event = threading.Event()

    def stop(_signum, _frame):
        stop_event.set()

    for name in ('SIGTERM', 'SIGINT'):
        with suppress(AttributeError):
            signal.signal(getattr(signal, name), stop)
    LOG.info('service %s started on %s:%s (pid %s)', PACKAGE_VERSION,
             args.host, server.server_address[1], os.getpid())
    serving = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.5},
                               name='ofdl-http', daemon=True)
    serving.start()
    try:
        stop_event.wait()
    finally:
        LOG.info('service stopping')
        with suppress(Exception):
            server.shutdown()
        with suppress(Exception):
            serving.join(timeout=5)
        with suppress(Exception):
            server.server_close()
        state.close()
        with suppress(OSError):
            pid_file.unlink()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
