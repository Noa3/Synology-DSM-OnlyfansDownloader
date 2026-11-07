"""First-install bootstrap used by the SPK postinst script.

The installer wizard passes the web password through stdin so it never appears
in the process list or the package log.  The module is intentionally tiny and
imports only stdlib plus the control database.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import DEFAULT_SHARE_NAME
from . import db as control_db
from .config import resolve_paths
from .security import SecurityError, set_password


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Initialise the OnlyFans DL DSM control database.')
    parser.add_argument('--password-stdin', action='store_true')
    parser.add_argument('--if-missing', action='store_true')
    parser.add_argument('--share-root', default='')
    parser.add_argument('--output-dir', default='')
    parser.add_argument('--data-dir', default='')
    args = parser.parse_args(argv)

    paths = resolve_paths()
    data_dir = Path(args.data_dir).resolve() if args.data_dir else paths.data
    data_dir.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(data_dir, 0o700)
    except OSError:
        pass
    control_db.init_db(data_dir / 'control.sqlite3')

    password = ''
    if args.password_stdin:
        password = sys.stdin.read(1024)
        # The shell sends exactly the password; tolerate a trailing newline from
        # a manual invocation but not arbitrary whitespace inside it.
        password = password.rstrip('\r\n')

    with control_db.connect(data_dir / 'control.sqlite3') as db:
        control_db.set_setting(db, 'share_name', DEFAULT_SHARE_NAME)
        if args.share_root:
            control_db.set_setting(db, 'share_root', str(Path(args.share_root).resolve()))
        if args.output_dir:
            control_db.set_setting(db, 'output_dir', str(Path(args.output_dir).resolve()))
        control_db.set_setting(db, 'bootstrap_version', '1')

    if password:
        try:
            changed = set_password(data_dir, password, only_if_missing=args.if_missing)
        except SecurityError as exc:
            print(f'ERROR: {exc}', file=sys.stderr)
            return 1
        print('PASSWORD_SET' if changed else 'PASSWORD_KEPT')
    else:
        print('NO_PASSWORD')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
