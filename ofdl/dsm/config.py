"""Filesystem layout and small environment helpers for the DSM package.

The values intentionally come from the environment so the same code runs in a
DSM package (``SYNOPKG_PKGDEST`` / ``SYNOPKG_PKGVAR``), in the local test
harness, and in the build container.
"""
from __future__ import annotations

import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from . import DEFAULT_SHARE_NAME


@dataclass(frozen=True)
class Paths:
    pkgdest: Path
    pkgvar: Path
    data: Path
    logs: Path
    previews: Path
    config: Path
    tmp: Path
    home: Path
    web: Path
    wheelhouse: Path
    venv: Path
    share: Path | None

    @property
    def db(self) -> Path:
        return self.data / 'control.sqlite3'

    @property
    def session_file(self) -> Path:
        return self.data / 'session.json'

    @property
    def worker_python(self) -> Path:
        for candidate in (self.venv / 'bin' / 'python', self.venv / 'Scripts' / 'python.exe'):
            if candidate.is_file():
                return candidate
        return Path(sys.executable)


def _repo_root() -> Path:
    # .../ofdl/dsm/config.py -> .../ofdl/dsm -> .../ofdl -> repository root
    return Path(__file__).resolve().parents[2]


def resolve_paths() -> Paths:
    pkgdest = Path(os.environ.get('SYNOPKG_PKGDEST') or _repo_root()).resolve()
    pkgvar = Path(os.environ.get('SYNOPKG_PKGVAR') or (pkgdest / 'var')).resolve()
    data = Path(os.environ.get('OFDL_DATA_DIR') or (pkgvar / 'data')).resolve()
    venv = Path(os.environ.get('OFDL_VENV') or (pkgvar / 'venv')).resolve()
    config = Path(os.environ.get('OFDL_CONFIG_DIR') or (pkgvar / 'config')).resolve()
    share = os.environ.get('OFDL_SHARE_ROOT')
    share_path = Path(share).resolve() if share else None
    return Paths(
        pkgdest=pkgdest,
        pkgvar=pkgvar,
        data=data,
        logs=Path(os.environ.get('OFDL_LOG_DIR') or (pkgvar / 'logs')).resolve(),
        previews=Path(os.environ.get('OFDL_PREVIEW_DIR') or (data / 'previews')).resolve(),
        config=config,
        tmp=Path(os.environ.get('OFDL_TMP_DIR') or (pkgvar / 'tmp')).resolve(),
        home=Path(os.environ.get('OFDL_HOME') or (pkgvar / 'home')).resolve(),
        web=Path(os.environ.get('OFDL_WEB_DIR') or (pkgdest / 'web')).resolve(),
        wheelhouse=Path(os.environ.get('OFDL_WHEELHOUSE') or (pkgdest / 'wheelhouse')).resolve(),
        venv=venv,
        share=share_path,
    )


def ensure_dirs(paths: Paths) -> None:
    for folder in (paths.pkgvar, paths.data, paths.logs, paths.previews,
                   paths.config, paths.tmp, paths.home):
        folder.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(folder, 0o700)
        except OSError:
            pass


def _candidate_share_roots(paths: Paths) -> list[Path]:
    candidates: list[Path] = []
    if paths.share is not None:
        candidates.append(paths.share)
    # Package Center creates this symlink for the data-share resource.
    candidates.append(paths.pkgdest.parent / 'shares' / DEFAULT_SHARE_NAME)
    candidates.append(paths.pkgvar / 'shares' / DEFAULT_SHARE_NAME)
    # Fallback for development and for DSM releases that do not create the link.
    for base in ('/volume1', '/volume2', '/volume3', '/volume4', '/volume5',
                 '/volume6', '/volume7', '/volume8'):
        candidates.append(Path(base) / DEFAULT_SHARE_NAME)
    candidates.append(paths.pkgvar / 'share')
    return candidates


def resolve_share_root(paths: Paths) -> Path | None:
    """Return the first usable download-share root without scanning all volumes."""
    for candidate in _candidate_share_roots(paths):
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved.is_dir():
            return resolved
    return None


def allowed_roots(paths: Paths) -> list[Path]:
    """Directories the folder picker may expose.

    The package is installed for a NAS administrator and protected by its own
    login.  Exposing the volume roots lets the user reuse an existing library
    (for example /volume1/OnlyFans) without an SSH session.  File contents are
    never listed, only directory names.
    """
    roots: list[Path] = []
    share = resolve_share_root(paths)
    if share is not None:
        roots.append(share)
    for base in ('/volume1', '/volume2', '/volume3', '/volume4', '/volume5',
                 '/volume6', '/volume7', '/volume8', '/volumeUSB1', '/volumeUSB2'):
        candidate = Path(base)
        try:
            if candidate.is_dir():
                roots.append(candidate.resolve())
        except OSError:
            continue
    # Local development / tests.  On a real DSM package the private var folder
    # must not appear in the folder picker (it contains the session database).
    is_dsm = bool(os.environ.get('SYNOPKG_PKGDEST') or os.environ.get('SYNOPKG_PKGVAR')
                  or str(paths.pkgdest).startswith('/var/packages/'))
    if not is_dsm:
        for candidate in (paths.pkgvar, paths.share):
            if candidate is not None and candidate.is_dir():
                try:
                    roots.append(candidate.resolve())
                except OSError:
                    pass
    unique: list[Path] = []
    for root in roots:
        if root not in unique:
            unique.append(root)
    return unique


def is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (ValueError, OSError, RuntimeError):
        return False


def path_is_allowed(path: Path, roots: list[Path]) -> bool:
    return any(is_within(path, root) for root in roots)


def directory_is_writable(path: Path) -> bool:
    try:
        if not path.is_dir():
            return False
        with tempfile.NamedTemporaryFile(prefix='.ofdl-write-', dir=path, delete=True):
            pass
        return True
    except OSError:
        return False


def default_output_dir(paths: Paths) -> Path | None:
    share = resolve_share_root(paths)
    return (share / 'OnlyFans') if share is not None else None


def human_bytes(value: int | float | None) -> str:
    try:
        amount = float(value or 0)
    except (TypeError, ValueError):
        return '0 B'
    for unit in ('B', 'KiB', 'MiB', 'GiB', 'TiB'):
        if abs(amount) < 1024 or unit == 'TiB':
            return f'{amount:.1f} {unit}' if unit != 'B' else f'{int(amount)} B'
        amount /= 1024
    return f'{amount:.1f} TiB'
