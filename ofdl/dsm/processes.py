"""Linux process-group cleanup, scoped by a private worker identity record."""
from __future__ import annotations

import argparse
import json
import os
import signal
import time
from pathlib import Path

from .security import atomic_write


def _stat(pid: int) -> tuple[int, str] | None:
    try:
        fields = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
        if fields[0] == 'Z':
            return None
        return int(fields[2]), fields[19]  # process group and kernel start ticks
    except (OSError, ValueError, IndexError):
        return None


def register_worker(pkgvar: Path, pid: int, token: str) -> None:
    if os.name != 'posix':
        return
    stat = _stat(pid)
    if stat is None or stat[0] != pid:
        return
    atomic_write(pkgvar / 'worker-process.json', json.dumps({
        'pid': pid, 'start': stat[1], 'token': token,
    }).encode(), 0o600)


def signal_worker(pkgvar: Path, sig: int, expected_pid: int | None = None) -> bool:
    if os.name != 'posix':
        return False
    try:
        record = json.loads((pkgvar / 'worker-process.json').read_text())
        pid = int(record['pid'])
        if pid <= 1 or (expected_pid is not None and expected_pid != pid):
            return False
        stat = _stat(pid)
        if stat is not None:
            if stat != (pid, str(record['start'])):
                return False  # stale PID file must never target a reused PID
        else:
            # The leader can have exited while ffmpeg/other descendants remain.
            # Verify a surviving member inherited the per-job random token.
            marker = f'OFDL_RUN_TOKEN={record["token"]}'.encode()
            found = False
            for path in Path('/proc').iterdir():
                if not path.name.isdigit():
                    continue
                member = _stat(int(path.name))
                if member and member[0] == pid:
                    try:
                        found = marker in (path / 'environ').read_bytes().split(b'\0')
                    except OSError:
                        continue
                    if found:
                        break
            if not found:
                return False
        os.killpg(pid, sig)
        return True
    except (OSError, ValueError, KeyError, TypeError):
        return False


def service_running(pkgvar: Path, pid: int) -> bool:
    if pid <= 1:
        return False
    try:
        command = Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')
        env = Path(f'/proc/{pid}/environ').read_bytes().split(b'\0')
        return (b'ofdl.dsm.service' in command
                and f'SYNOPKG_PKGVAR={pkgvar}'.encode() in env)
    except OSError:
        return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['cleanup', 'service-running'])
    parser.add_argument('--var', type=Path, required=True)
    parser.add_argument('--pid', type=int, default=0)
    args = parser.parse_args()
    if args.action == 'service-running':
        return 0 if service_running(args.var, args.pid) else 1
    # Recover a missing/stale service PID file using exact command + package
    # environment identity, never a process-name wildcard.
    services = [int(path.name) for path in Path('/proc').iterdir()
                if path.name.isdigit() and service_running(args.var, int(path.name))]
    for pid in services:
        if service_running(args.var, pid):
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
    deadline = time.monotonic() + 6
    while any(service_running(args.var, pid) for pid in services) and time.monotonic() < deadline:
        time.sleep(.1)
    for pid in services:
        if service_running(args.var, pid):
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    if signal_worker(args.var, signal.SIGTERM):
        time.sleep(2)
    signal_worker(args.var, signal.SIGKILL)
    time.sleep(0.2)
    return 1 if (signal_worker(args.var, 0) or any(service_running(args.var, pid) for pid in services)) else 0


if __name__ == '__main__':
    raise SystemExit(main())
