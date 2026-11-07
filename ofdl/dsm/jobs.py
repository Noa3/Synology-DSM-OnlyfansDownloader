"""Job payload validation that deliberately avoids importing the download stack.

The control service imports only this module for validation.  ``requests``,
``curl_cffi`` and Pillow are imported later, inside the worker process, so an
idle NAS keeps a small resident set.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from ..common import AppError
from . import DEFAULT_SHARE_NAME
from .config import Paths, allowed_roots, default_output_dir, directory_is_writable, path_is_allowed

CATEGORIES = ('posts', 'archived', 'stories', 'messages', 'purchased')
PROFILE_RE = re.compile(r'[a-z0-9_][a-z0-9_.-]{0,79}')
PROXY_SCHEMES = {'http', 'https', 'socks5', 'socks5h'}
MAX_PROFILES = 5000
MAX_OPTION_BYTES = 256 * 1024


def _bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {'1', 'true', 'yes', 'on'}
    return default


def parse_profiles(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        text = ' '.join(str(item) for item in value)
    else:
        text = str(value)
    result: list[str] = []
    for token in re.split(r'[\s,;]+', text.strip()):
        if not token:
            continue
        if token.lower().startswith(('http://', 'https://')):
            try:
                url = urlsplit(token)
                if (url.scheme != 'https' or url.hostname not in {'onlyfans.com', 'www.onlyfans.com'}
                        or url.username or url.password or url.port not in (None, 443)):
                    raise ValueError
                token = unquote(url.path.strip('/'))
            except ValueError:
                raise AppError('Profil-URLs müssen HTTPS-OnlyFans-Profil-URLs sein.') from None
        token = token.lstrip('@').lower()
        if not PROFILE_RE.fullmatch(token) or token in {'.', '..'}:
            raise AppError('Creator-Namen dürfen nur Buchstaben, Zahlen, Punkt, Bindestrich und Unterstrich enthalten.')
        if token not in result:
            result.append(token)
        if len(result) > MAX_PROFILES:
            raise AppError(f'Höchstens {MAX_PROFILES} Creator pro Auftrag.')
    return result


def normalize_proxy(value: Any) -> str:
    text = str(value or '').strip()
    if not text:
        return ''
    if len(text) > 512 or any(ord(char) < 33 or ord(char) == 127 for char in text):
        raise AppError('Die Proxy-URL enthält Leerzeichen oder unzulässige Zeichen.')
    try:
        parsed = urlsplit(text)
        port = parsed.port
    except ValueError:
        raise AppError('Die Proxy-URL ist ungültig.') from None
    if parsed.scheme.lower() not in PROXY_SCHEMES:
        raise AppError('Erlaubt sind http://, https://, socks5:// und socks5h://.')
    if (not parsed.hostname or parsed.query or parsed.fragment
            or parsed.path not in {'', '/'}):
        raise AppError('Die Proxy-URL muss die Form schema://host:port haben.')
    if port is not None and not 1 <= port <= 65535:
        raise AppError('Der Proxy-Port muss zwischen 1 und 65535 liegen.')
    return text


def _safe_time(value: Any) -> str:
    text = str(value or '').strip()
    if not re.fullmatch(r'(?:[01][0-9]|2[0-3]):[0-5][0-9]', text):
        raise AppError('Die geplante Uhrzeit muss im Format HH:MM angegeben werden.')
    return text


def resolve_output_dir(value: Any, paths: Paths, *, require_writable: bool = True) -> Path:
    text = str(value or '').strip()
    if not text:
        fallback = default_output_dir(paths)
        if fallback is None:
            raise AppError('Der Downloadordner ist noch nicht eingerichtet. Bitte einen Ordner auswählen.')
        text = str(fallback)
    if not Path(text).is_absolute():
        raise AppError('Der Downloadordner muss ein absoluter Pfad sein.')
    path = Path(text).expanduser()
    try:
        path = path.resolve()
    except OSError:
        raise AppError('Der Downloadordner konnte nicht aufgelöst werden.') from None
    roots = allowed_roots(paths)
    if not path_is_allowed(path, roots):
        raise AppError('Der Downloadordner muss auf einem freigegebenen Volume oder im Paketordner liegen.')
    if path.exists():
        if not path.is_dir():
            raise AppError('Der gewählte Pfad ist kein Ordner.')
        if require_writable and not directory_is_writable(path):
            raise AppError('Der Downloadordner ist nicht beschreibbar. Prüfe die Freigabeberechtigung.')
    else:
        raise AppError('Der Downloadordner existiert nicht. Bitte einen vorhandenen Ordner wählen oder ausdrücklich anlegen.')
    return path


def _categories(value: Any) -> tuple[str, ...]:
    if value is None:
        return CATEGORIES
    if not isinstance(value, (list, tuple)):
        raise AppError('Die Inhaltskategorien müssen als Liste übergeben werden.')
    selected = tuple(str(item) for item in value)
    if not selected or any(item not in CATEGORIES for item in selected):
        raise AppError('Mindestens eine gültige Inhaltskategorie auswählen.')
    return selected


def _types(value: Any) -> dict[str, bool]:
    if value is None:
        return {'photos': True, 'videos': True, 'audio': True}
    if not isinstance(value, dict):
        raise AppError('Die Dateitypen müssen als Objekt übergeben werden.')
    result = {
        'photos': _bool(value.get('photos'), True),
        'videos': _bool(value.get('videos'), True),
        'audio': _bool(value.get('audio'), True),
    }
    if not any(result.values()):
        raise AppError('Mindestens einen Dateityp auswählen (Fotos, Videos oder Audio).')
    return result


def normalize_download_options(value: Any, paths: Paths) -> dict[str, Any]:
    """Return the small, JSON-serialisable payload stored for a worker job."""
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise AppError('Die Download-Einstellungen sind ungültig.')
    raw = json.dumps(value, ensure_ascii=False)
    if len(raw.encode('utf-8')) > MAX_OPTION_BYTES:
        raise AppError('Die Download-Einstellungen sind zu groß.')

    all_subscriptions = _bool(value.get('all_subscriptions'), False)
    profiles = parse_profiles(value.get('profiles'))
    if not all_subscriptions and not profiles:
        raise AppError('Mindestens einen Creator auswählen oder „Alle Abonnements“ aktivieren.')

    since_days = value.get('since_days', 0)
    try:
        since_days = int(since_days or 0)
    except (TypeError, ValueError):
        raise AppError('Der Zeitraum muss eine ganze Zahl in Tagen sein.') from None
    if not 0 <= since_days <= 36500:
        raise AppError('Der Zeitraum muss zwischen 0 und 36500 Tagen liegen.')

    return {
        'output_dir': str(resolve_output_dir(value.get('output_dir'), paths)),
        'profiles': profiles,
        'all_subscriptions': all_subscriptions,
        'skip_profiles': parse_profiles(value.get('skip_profiles')),
        'categories': list(_categories(value.get('categories'))),
        'types': _types(value.get('types')),
        'albums': _bool(value.get('albums'), True),
        'subfolders': _bool(value.get('subfolders'), True),
        'previews': _bool(value.get('previews'), False),
        'dry_run': _bool(value.get('dry_run'), False),
        'since_days': since_days,
        'rules_source': str(value.get('rules_source') or '').strip()[:2048],
    }


def normalize_schedule(value: Any) -> dict[str, Any]:
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise AppError('Die Zeitplanung ist ungültig.')
    return {
        'enabled': _bool(value.get('enabled'), False),
        'time': _safe_time(value.get('time', '03:30')),
        'options': normalize_schedule_options(value.get('options')),
    }


def normalize_schedule_options(value: Any) -> dict[str, Any]:
    """Schedule defaults are validated only when the job starts.

    They may legitimately lack a creator list if the user later chooses
    "all subscriptions"; the scheduler therefore stores a compact snapshot and
    the worker validates it through ``normalize_download_options``.
    """
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise AppError('Die gespeicherten Zeitplan-Einstellungen sind ungültig.')
    allowed = {
        'output_dir', 'profiles', 'all_subscriptions', 'skip_profiles', 'categories',
        'types', 'albums', 'subfolders', 'previews', 'dry_run', 'since_days',
        'rules_source',
    }
    compact: dict[str, Any] = {}
    for key in allowed:
        if key in value:
            compact[key] = value[key]
    raw = json.dumps(compact, ensure_ascii=False)
    if len(raw.encode('utf-8')) > MAX_OPTION_BYTES:
        raise AppError('Die gespeicherten Zeitplan-Einstellungen sind zu groß.')
    return compact


def normalize_preview(value: Any, paths: Paths) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise AppError('Die Vorschau-Anfrage ist ungültig.')
    output_dir = resolve_output_dir(value.get('output_dir'), paths, require_writable=False)
    relative = str(value.get('path') or '').strip()
    if not relative or len(relative) > 1024:
        raise AppError('Der Vorschau-Pfad fehlt.')
    candidate = (output_dir / relative).resolve()
    try:
        candidate.relative_to(output_dir)
    except (ValueError, OSError, RuntimeError):
        raise AppError('Der Vorschau-Pfad liegt außerhalb des Downloadordners.') from None
    if not candidate.is_file():
        raise AppError('Die Datei für die Vorschau existiert nicht.')
    if candidate.stat().st_size > 2 * 1024 * 1024 * 1024:
        raise AppError('Die Datei ist für eine Vorschau zu groß.')
    kind = str(value.get('kind') or 'photo')
    if kind not in {'photo', 'gif', 'video', 'audio'}:
        kind = 'photo'
    return {'output_dir': str(output_dir), 'path': relative, 'kind': kind}


def public_payload(kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Strip credential-bearing and huge fields before sending a job to the UI."""
    if kind == 'download':
        return {
            'output_dir': payload.get('output_dir'),
            'creator_count': len(payload.get('profiles') or []),
            'all_subscriptions': bool(payload.get('all_subscriptions')),
            'categories': payload.get('categories') or [],
            'types': payload.get('types') or {},
            'since_days': payload.get('since_days', 0),
            'dry_run': bool(payload.get('dry_run')),
            'previews': bool(payload.get('previews')),
        }
    if kind == 'preview':
        return {'path': payload.get('path'), 'kind': payload.get('kind')}
    return {}


def public_job(row: dict[str, Any], *, include_payload: bool = True) -> dict[str, Any]:
    try:
        payload = json.loads(row.get('payload') or '{}')
    except (ValueError, TypeError):
        payload = {}
    try:
        result = json.loads(row.get('result') or 'null') if row.get('result') else None
    except (ValueError, TypeError):
        result = None
    try:
        stats = json.loads(row.get('stats') or '{}')
    except (ValueError, TypeError):
        stats = {}
    job = {
        'id': row.get('id'),
        'kind': row.get('kind'),
        'status': row.get('status'),
        'phase': row.get('phase') or '',
        'progress_done': int(row.get('progress_done') or 0),
        'progress_total': int(row.get('progress_total') or 0),
        'stats': stats if isinstance(stats, dict) else {},
        'pid': row.get('pid'),
        'exit_code': row.get('exit_code'),
        'error': row.get('error') or '',
        'created_at': row.get('created_at'),
        'started_at': row.get('started_at'),
        'finished_at': row.get('finished_at'),
        'pause_requested': bool(row.get('pause_requested')),
        'cancel_requested': bool(row.get('cancel_requested')),
        'result': result if isinstance(result, dict) else None,
    }
    if include_payload:
        job['request'] = public_payload(str(row.get('kind') or ''), payload if isinstance(payload, dict) else {})
    return job


def default_download_options(paths: Paths) -> dict[str, Any]:
    fallback = default_output_dir(paths)
    return {
        'output_dir': str(fallback) if fallback else '',
        'profiles': [],
        'all_subscriptions': True,
        'skip_profiles': [],
        'categories': list(CATEGORIES),
        'types': {'photos': True, 'videos': True, 'audio': True},
        'albums': True,
        'subfolders': True,
        'previews': False,
        'dry_run': False,
        'since_days': 0,
        'rules_source': '',
    }


def share_label(paths: Paths) -> str:
    share = paths.share
    if share is not None and str(share).endswith(DEFAULT_SHARE_NAME):
        return DEFAULT_SHARE_NAME
    return DEFAULT_SHARE_NAME
