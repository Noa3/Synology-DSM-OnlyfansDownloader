"""Worker-only job implementations.

This module is imported by the short-lived worker process, never by the control
service.  Heavy dependencies (requests, curl_cffi, Pillow) appear only in the
functions that need them.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ..common import AppError, Control, EventSink
from . import db as control_db
from .config import Paths, ensure_dirs
from .jobs import normalize_download_options, normalize_preview
from .security import SessionStore, atomic_write

DEFAULT_RULES_SOURCE = 'https://raw.githubusercontent.com/DATAHOARDERS/dynamic-rules/main/onlyfans.json'
PREVIEW_CACHE_FILES = 512
PREVIEW_CACHE_BYTES = 100 * 1024 * 1024


def _setting(paths: Paths, key: str, default: str = '') -> str:
    with control_db.connect(paths.db) as db:
        return control_db.get_setting(db, key, default)


def _load_session(paths: Paths):
    credentials = SessionStore(paths.data).load()
    if credentials is None:
        raise AppError('Es ist keine Sitzung eingerichtet. Bitte zuerst eine Sitzung importieren und testen.')
    return credentials


def _proxy(paths: Paths) -> str:
    from ..http import normalize_proxy
    return normalize_proxy(_setting(paths, 'proxy', ''))


def _rules_source(paths: Paths, payload: dict[str, Any]) -> str:
    return (str(payload.get('rules_source') or '').strip()
            or _setting(paths, 'rules_source', '') or DEFAULT_RULES_SOURCE)


def _client(paths: Paths, control: Control, emit: EventSink, payload: dict[str, Any]):
    from ..api import ApiClient, load_rules
    credentials = _load_session(paths)
    proxy = _proxy(paths)
    rules = load_rules(_rules_source(paths, payload), control,
                       cache_dir=paths.config / 'rules', emit=emit, proxy=proxy)
    return ApiClient(credentials, rules, control, emit=emit, proxy=proxy, retry_floor=180)


def run_test_session(paths: Paths, payload: dict[str, Any], control: Control,
                     emit: EventSink) -> dict[str, Any]:
    emit('phase', 'Sitzung wird geprüft')
    with _client(paths, control, emit, payload) as client:
        user = client.user('me')
    if not isinstance(user, dict):
        raise AppError('Die Sitzungsprüfung lieferte keine gültige Antwort.')
    return {
        'user_id': str(user.get('id', '')),
        'username': str(user.get('username', ''))[:100],
        'message': 'Sitzung wurde vom Konto-Endpunkt akzeptiert.',
    }


def run_subscriptions(paths: Paths, payload: dict[str, Any], control: Control,
                      emit: EventSink) -> dict[str, Any]:
    from ..downloads import parse_profiles
    emit('phase', 'Abonnements werden geladen')
    count = 0
    batch: list[tuple[str, str, str]] = []
    with _client(paths, control, emit, payload) as client:
        with control_db.connect(paths.db) as db:
            # Keep the old list usable if authentication/network fails mid-scan.
            db.execute('CREATE TEMP TABLE incoming_creators(username TEXT PRIMARY KEY, display_name TEXT, '
                       'subscription TEXT, scanned_at TEXT)')
            def store_batch() -> None:
                db.executemany('INSERT OR REPLACE INTO incoming_creators VALUES(?,?,?,?)',
                               [(name, display, status, control_db.now_iso()) for name, display, status in batch])
                db.commit()
                batch.clear()
            for row in client.paginate('/subscriptions/subscribes', 'subscriptions'):
                control.checkpoint()
                if not isinstance(row, dict):
                    continue
                username = str(row.get('username') or '').strip().lower()
                if not username:
                    continue
                try:
                    parsed = parse_profiles(username)
                except AppError:
                    continue
                if not parsed:
                    continue
                name = parsed[0]
                display = str(row.get('name') or name)[:200]
                batch.append((name, display, 'active'))
                count += 1
                if len(batch) >= 100:
                    store_batch()
                    emit('overall', {'done': count, 'total': 0, 'scanning': True})
                if count > 50000:
                    raise AppError('Die Abonnementliste ist unerwartet groß; der Vorgang wurde begrenzt.')
            if batch:
                store_batch()
            control.checkpoint()
            db.execute('DELETE FROM creators')
            db.execute('INSERT INTO creators SELECT * FROM incoming_creators')
            count = db.execute('SELECT COUNT(*) FROM creators').fetchone()[0]
            db.commit()
    return {'creators': count, 'message': f'{count} Abonnements gespeichert.'}


def run_download(paths: Paths, payload: dict[str, Any], control: Control,
                 emit: EventSink) -> dict[str, Any]:
    from ..downloads import Options, run_downloads
    options = normalize_download_options(payload, paths)
    output_dir = Path(options['output_dir'])
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        raise AppError('Der Downloadordner konnte nicht angelegt werden. Prüfe Pfad und Berechtigungen.') from None
    since = None
    if options['since_days']:
        since = datetime.now(timezone.utc) - timedelta(days=options['since_days'])
    types = options['types']
    download_options = Options(
        output_dir=output_dir,
        profiles=list(options['profiles']),
        categories=tuple(options['categories']),
        photos=bool(types['photos']),
        videos=bool(types['videos']),
        audio=bool(types['audio']),
        albums=bool(options['albums']),
        subfolders=bool(options['subfolders']),
        previews=bool(options['previews']),
        since=since,
        dry_run=bool(options['dry_run']),
        all_subscriptions=bool(options['all_subscriptions']),
        skip_profiles=tuple(options['skip_profiles']),
    )
    with _client(paths, control, emit, options) as client:
        summary = run_downloads(client, download_options, control, emit)
    return summary.to_dict()


def _cache_key(path: Path, kind: str) -> str:
    stat = path.stat()
    digest = hashlib.sha256(f'{path.resolve()}|{stat.st_size}|{stat.st_mtime_ns}|{kind}'.encode('utf-8'))
    return digest.hexdigest()


def _prune_preview_cache(paths: Paths) -> None:
    try:
        files = [entry for entry in paths.previews.iterdir() if entry.is_file() and entry.suffix == '.png']
    except OSError:
        return
    total = sum(entry.stat().st_size for entry in files)
    if len(files) <= PREVIEW_CACHE_FILES and total <= PREVIEW_CACHE_BYTES:
        return
    files.sort(key=lambda entry: entry.stat().st_mtime)
    while files and (len(files) > PREVIEW_CACHE_FILES or total > PREVIEW_CACHE_BYTES):
        entry = files.pop(0)
        try:
            total -= entry.stat().st_size
            entry.unlink()
        except OSError:
            pass


def run_preview(paths: Paths, payload: dict[str, Any], control: Control,
                emit: EventSink) -> dict[str, Any]:
    from ..preview import build_preview
    options = normalize_preview(payload, paths)
    source = (Path(options['output_dir']) / options['path']).resolve()
    control.checkpoint()
    emit('phase', 'Vorschau wird erzeugt')
    result = build_preview(source, options['kind'], (320, 240))
    if not result.png:
        return {'name': None, 'url': None, 'message': result.message}
    name = _cache_key(source, options['kind']) + '.png'
    paths.previews.mkdir(parents=True, exist_ok=True)
    atomic_write(paths.previews / name, result.png, 0o600)
    _prune_preview_cache(paths)
    return {'name': name, 'url': f'/api/preview/{name}', 'message': result.message}


def run_job(paths: Paths, kind: str, payload: dict[str, Any], control: Control,
            emit: EventSink) -> dict[str, Any]:
    ensure_dirs(paths)
    if kind == 'test_session':
        return run_test_session(paths, payload, control, emit)
    if kind == 'subscriptions':
        return run_subscriptions(paths, payload, control, emit)
    if kind == 'download':
        return run_download(paths, payload, control, emit)
    if kind == 'preview':
        return run_preview(paths, payload, control, emit)
    if kind in {'offers_scan', 'free_renew'}:
        from .renewals import run_free_renew, run_offers_scan
        return (run_offers_scan if kind == 'offers_scan' else run_free_renew)(paths, payload, control, emit)
    raise AppError('Unbekannter Auftragstyp.')
