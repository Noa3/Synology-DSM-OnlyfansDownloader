"""Compatibility entry point for scripts that only set the web password."""
from __future__ import annotations

from .bootstrap import main

if __name__ == '__main__':
    raise SystemExit(main(['--password-stdin', '--if-missing']))
