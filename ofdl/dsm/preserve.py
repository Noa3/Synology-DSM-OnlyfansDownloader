"""Upgrade-safe snapshots of private settings and the imported session.

The package stores the web password, library path, schedule, proxy and other
settings in ``var/data/control.sqlite3`` and the OnlyFans session in
``var/data/session.json``.  DSM upgrades normally keep ``SYNOPKG_PKGVAR``, but a
failed/partial upgrade must never silently start with an empty database.

``preupgrade`` takes a snapshot; ``postupgrade`` restores only when the live
database or session is missing/corrupt.  Existing valid data is never
overwritten.  User media is never copied or touched.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import Paths, resolve_paths

KEEP_SNAPSHOTS = 5
SNAPSHOT_DIR = 'backups'


def _stamp() -> str:
    return datetime.now().strftime('%Y%m%d-%H%M%S')


def _db_ok(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size == 0:
        return False
    try:
        db = sqlite3.connect(str(path), timeout=2)
        try:
            row = db.execute('PRAGMA quick_check').fetchone()
            return bool(row and row[0] == 'ok')
        finally:
            db.close()
    except (sqlite3.Error, OSError):
        return False


def _session_ok(path: Path) -> bool:
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
        return isinstance(value, dict) and bool(value.get('user_id'))
    except (OSError, ValueError, RecursionError):
        return False


def _settings_summary(db_path: Path) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    try:
        db = sqlite3.connect(str(db_path), timeout=2)
        try:
            rows = dict(db.execute('SELECT key,value FROM settings').fetchall())
        finally:
            db.close()
    except (sqlite3.Error, OSError):
        return summary
    summary['has_password'] = bool(rows.get('password_hash'))
    summary['output_dir'] = bool(rows.get('output_dir'))
    summary['library_confirmed'] = rows.get('library_confirmed') == '1'
    summary['has_session_setting'] = bool(rows.get('session_user_id'))
    summary['schedule'] = bool(rows.get('schedule') and rows.get('schedule') != '{}')
    summary['download_defaults'] = bool(rows.get('download_defaults')
                                        and rows.get('download_defaults') != '{}')
    summary['proxy'] = bool(rows.get('proxy'))
    summary['free_renewal'] = bool(rows.get('free_renewal')
                                    and rows.get('free_renewal') != '{}')
    return summary


def _copy_private(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    try:
        os.chmod(target, 0o600)
    except OSError:
        pass


def _backup_db(source: Path, target: Path) -> bool:
    if not source.is_file() or source.stat().st_size == 0:
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        src = sqlite3.connect(str(source), timeout=5)
        try:
            dst = sqlite3.connect(str(target))
            try:
                src.backup(dst)
            finally:
                dst.close()
        finally:
            src.close()
        try:
            os.chmod(target, 0o600)
        except OSError:
            pass
        return target.is_file() and target.stat().st_size > 0
    except (sqlite3.Error, OSError):
        return False


def _prune(paths: Paths) -> None:
    root = paths.pkgvar / SNAPSHOT_DIR
    try:
        snapshots = sorted((item for item in root.iterdir() if item.is_dir()),
                           key=lambda item: item.name, reverse=True)
    except OSError:
        return
    for old in snapshots[KEEP_SNAPSHOTS:]:
        shutil.rmtree(old, ignore_errors=True)


def snapshot(paths: Paths | None = None, reason: str = 'upgrade') -> Path | None:
    """Create a private snapshot; returns its directory or None if empty."""
    paths = paths or resolve_paths()
    db_path = paths.data / 'control.sqlite3'
    session_path = paths.data / 'session.json'
    if not db_path.exists() and not session_path.exists():
        return None
    target = paths.pkgvar / SNAPSHOT_DIR / f'{_stamp()}-{reason}'
    target.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(target, 0o700)
    except OSError:
        pass
    result: dict[str, Any] = {'created_at': datetime.now().astimezone().isoformat(),
                              'reason': reason, 'database': False, 'session': False,
                              'config_files': []}
    if _backup_db(db_path, target / 'control.sqlite3'):
        result['database'] = True
        result['settings'] = _settings_summary(db_path)
    if session_path.is_file() and session_path.stat().st_size <= 2 * 1024 * 1024:
        _copy_private(session_path, target / 'session.json')
        result['session'] = True
    try:
        for item in paths.config.glob('free-*.json'):
            if item.is_file() and item.stat().st_size <= 2 * 1024 * 1024:
                _copy_private(item, target / 'config' / item.name)
                result['config_files'].append(item.name)
    except OSError:
        pass
    try:
        (target / 'metadata.json').write_text(
            json.dumps(result, ensure_ascii=False, indent=1, sort_keys=True) + '\n',
            encoding='utf-8')
        os.chmod(target / 'metadata.json', 0o600)
    except OSError:
        pass
    _prune(paths)
    return target


def latest_snapshot(paths: Paths | None = None) -> Path | None:
    paths = paths or resolve_paths()
    root = paths.pkgvar / SNAPSHOT_DIR
    try:
        candidates = sorted((item for item in root.iterdir() if item.is_dir()),
                            key=lambda item: item.name, reverse=True)
    except OSError:
        return None
    return candidates[0] if candidates else None


def restore_if_needed(paths: Paths | None = None) -> dict[str, Any]:
    """Restore only missing/corrupt private files; never overwrite valid data."""
    paths = paths or resolve_paths()
    result: dict[str, Any] = {'restored': [], 'kept': [], 'snapshot': None, 'errors': []}
    source = latest_snapshot(paths)
    if source is None:
        return result
    result['snapshot'] = str(source)
    db_path = paths.data / 'control.sqlite3'
    session_path = paths.data / 'session.json'
    backup_db = source / 'control.sqlite3'
    backup_session = source / 'session.json'

    paths.data.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(paths.data, 0o700)
    except OSError:
        pass

    if not _db_ok(db_path):
        if _db_ok(backup_db):
            try:
                _copy_private(backup_db, db_path)
                result['restored'].append('control.sqlite3')
            except OSError as exc:
                result['errors'].append(f'database: {type(exc).__name__}')
        elif db_path.exists():
            result['errors'].append('database exists but is corrupt; no valid backup')
    else:
        result['kept'].append('control.sqlite3')

    if not _session_ok(session_path):
        if _session_ok(backup_session):
            try:
                _copy_private(backup_session, session_path)
                result['restored'].append('session.json')
            except OSError as exc:
                result['errors'].append(f'session: {type(exc).__name__}')
    elif session_path.exists():
        result['kept'].append('session.json')

    try:
        for item in (source / 'config').glob('*.json'):
            target = paths.config / item.name
            if not target.exists():
                _copy_private(item, target)
                result['restored'].append(f'config/{item.name}')
    except OSError as exc:
        result['errors'].append(f'config: {type(exc).__name__}')
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='OnlyFans DL upgrade snapshot helper')
    parser.add_argument('action', choices=['snapshot', 'restore', 'status'])
    parser.add_argument('--reason', default='upgrade')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)
    paths = resolve_paths()
    if args.action == 'snapshot':
        target = snapshot(paths, args.reason)
        print(json.dumps({'snapshot': str(target) if target else None}, ensure_ascii=False))
        return 0
    if args.action == 'restore':
        result = restore_if_needed(paths)
        print(json.dumps(result, ensure_ascii=False))
        return 1 if result['errors'] else 0
    result = {'data': str(paths.data), 'snapshot': str(latest_snapshot(paths) or ''),
              'database_ok': _db_ok(paths.data / 'control.sqlite3'),
              'session_ok': _session_ok(paths.data / 'session.json')}
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
