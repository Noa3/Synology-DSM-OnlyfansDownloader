"""Native Synology DSM integration for the OnlyFans downloader.

This package is intentionally small at import time.  The long-running control
service must not import the download, API, Pillow or curl_cffi modules; those
belong to the short-lived worker process.  See ``docs/ARCHITECTURE.md``.
"""
from __future__ import annotations

SERVICE_VERSION = '2.8.0'
PACKAGE_REVISION = '3'
PACKAGE_VERSION = f'{SERVICE_VERSION}-{PACKAGE_REVISION}'
DEFAULT_PORT = 8765
DEFAULT_SHARE_NAME = 'OnlyFansDL'
DEFAULT_SUBFOLDER = 'OnlyFans'
JOB_KINDS = ('test_session', 'subscriptions', 'download', 'preview')
ACTIVE_STATES = ('queued', 'running', 'paused')
