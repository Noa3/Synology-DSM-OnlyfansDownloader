"""Password hashing, session-at-rest storage and small request guards."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from ..auth import Credentials, SessionError
from . import db as control_db

PBKDF2_ITERATIONS = 600_000
PASSWORD_MIN = 10
PASSWORD_MAX = 256
SESSION_MAX_BYTES = 64 * 1024


class SecurityError(ValueError):
    pass


def _b64(value: bytes) -> str:
    return base64.b64encode(value).decode('ascii')


def _unb64(value: str) -> bytes:
    return base64.b64decode(value.encode('ascii'), validate=True)


def validate_password(password: Any) -> str:
    if not isinstance(password, str):
        raise SecurityError('Das Passwort muss Text sein.')
    if len(password) < PASSWORD_MIN:
        raise SecurityError(f'Das Passwort muss mindestens {PASSWORD_MIN} Zeichen lang sein.')
    if len(password) > PASSWORD_MAX:
        raise SecurityError(f'Das Passwort darf höchstens {PASSWORD_MAX} Zeichen lang sein.')
    if any(ord(char) < 32 or ord(char) == 127 for char in password):
        raise SecurityError('Das Passwort darf keine Steuerzeichen enthalten.')
    return password


def hash_password(password: str) -> str:
    password = validate_password(password)
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, PBKDF2_ITERATIONS)
    return f'pbkdf2_sha256${PBKDF2_ITERATIONS}${_b64(salt)}${_b64(digest)}'


def verify_password(password: Any, stored: str | None) -> bool:
    if not isinstance(password, str) or not stored:
        return False
    try:
        algorithm, iterations, salt_text, digest_text = stored.split('$', 3)
        if algorithm != 'pbkdf2_sha256':
            return False
        rounds = int(iterations)
        if rounds < 100_000 or rounds > 2_000_000:
            return False
        salt = _unb64(salt_text)
        expected = _unb64(digest_text)
        actual = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, rounds)
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError, UnicodeError):
        return False


def password_configured(data_dir: Path | str) -> bool:
    try:
        with control_db.connect(Path(data_dir) / 'control.sqlite3') as db:
            return bool(control_db.get_setting(db, 'password_hash', ''))
    except Exception:
        return False


def set_password(data_dir: Path | str, password: str, *, only_if_missing: bool = False) -> bool:
    password_hash = hash_password(password)
    with control_db.connect(Path(data_dir) / 'control.sqlite3') as db:
        if only_if_missing and control_db.get_setting(db, 'password_hash', ''):
            return False
        control_db.set_setting(db, 'password_hash', password_hash)
        return True


def sanitize_text(value: Any, limit: int = 1000) -> str:
    text = str(value if value is not None else '')
    cleaned = ''.join(' ' if (ord(char) < 32 or ord(char) == 127) else char for char in text)
    return cleaned[:limit]


def redact_proxy(value: Any) -> str:
    """Never return proxy credentials to the browser."""
    text = str(value or '').strip()
    if not text:
        return ''
    try:
        from urllib.parse import urlsplit
        parsed = urlsplit(text)
        if not parsed.scheme or not parsed.hostname:
            return '***'
        host = parsed.hostname or ''
        if ':' in host:
            host = f'[{host}]'
        port = f':{parsed.port}' if parsed.port else ''
        auth = '***@' if (parsed.username or parsed.password) else ''
        return f'{parsed.scheme}://{auth}{host}{port}'
    except (ValueError, TypeError):
        return '***'


def atomic_write(path: Path, data: bytes, mode: int = 0o600) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp = tempfile.mkstemp(prefix='.' + path.name, suffix='.tmp', dir=path.parent)
    try:
        try:
            os.fchmod(descriptor, mode)
        except (AttributeError, OSError):
            pass
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
        try:
            os.chmod(path, mode)
        except OSError:
            pass
    finally:
        if os.path.exists(temp):
            try:
                os.unlink(temp)
            except OSError:
                pass


class SessionStore:
    """The imported session lives in one 0600 file, never in settings or logs."""

    def __init__(self, data_dir: Path | str):
        self.path = Path(data_dir) / 'session.json'

    def save(self, credentials: Credentials) -> None:
        credentials = credentials.validate()
        payload = json.dumps(credentials.to_dict(), ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        atomic_write(self.path, payload, 0o600)

    def load(self) -> Credentials | None:
        try:
            if self.path.is_symlink() or not self.path.is_file():
                return None
            if self.path.stat().st_size > SESSION_MAX_BYTES:
                return None
            values = json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(values, dict):
                return None
            return Credentials(
                str(values.get('user_id', '')),
                str(values.get('user_agent', '')),
                str(values.get('x_bc', '')),
                str(values.get('sess_cookie', '')),
                {str(k): str(v) for k, v in (values.get('extra_cookies') or {}).items()},
            ).validate()
        except (OSError, ValueError, TypeError, SessionError, RecursionError):
            return None

    def describe(self) -> dict[str, Any]:
        credentials = self.load()
        if credentials is None:
            return {'present': False, 'user_id': None}
        return {'present': True, 'user_id': credentials.user_id}

    def clear(self) -> bool:
        try:
            if self.path.exists():
                self.path.unlink()
                return True
        except OSError:
            pass
        return False


class LoginLimiter:
    """Small in-memory brute-force guard; no persistent state is needed."""

    def __init__(self, attempts: int = 5, window: float = 300.0, lock_seconds: float = 60.0):
        self.attempts = max(1, int(attempts))
        self.window = max(10.0, float(window))
        self.lock_seconds = max(5.0, float(lock_seconds))
        self._failures: dict[str, list[float]] = {}
        self._locked_until: dict[str, float] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            locked = self._locked_until.get(key, 0.0)
            if locked > now:
                return False
            failures = [stamp for stamp in self._failures.get(key, []) if now - stamp < self.window]
            if failures:
                self._failures[key] = failures
            else:
                self._failures.pop(key, None)
            return len(failures) < self.attempts

    def failure(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            failures = [stamp for stamp in self._failures.get(key, []) if now - stamp < self.window]
            failures.append(now)
            self._failures[key] = failures
            if len(failures) >= self.attempts:
                self._locked_until[key] = now + self.lock_seconds
            if len(self._failures) > 1000:
                # Bound memory even under a spoofed-source flood.
                self._failures.clear()
                self._locked_until.clear()

    def success(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)
            self._locked_until.pop(key, None)


def new_token() -> str:
    return secrets.token_urlsafe(32)


def new_csrf() -> str:
    return secrets.token_urlsafe(24)
