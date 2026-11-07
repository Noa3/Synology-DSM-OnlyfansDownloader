#!/usr/bin/env python3
"""Measure PSS and RSS of the OnlyFans DL service and its worker on DSM.

Run this on the NAS with any Python 3 (including the SynoCommunity interpreter).
It reads /proc directly, so it does not depend on the app's virtual environment.

Examples:
    python3 tools/measure_dsm.py snapshot
    python3 tools/measure_dsm.py sample --seconds 30 --interval 2
    python3 tools/measure_dsm.py sample --seconds 60 --interval 1 --json
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROLES = {
    'ofdl.dsm.service': 'service',
    'ofdl.dsm.worker': 'worker',
}


def proc_cmdline(pid: int) -> str:
    try:
        raw = Path(f'/proc/{pid}/cmdline').read_bytes()
    except OSError:
        return ''
    return ' '.join(part.decode('utf-8', 'replace') for part in raw.split(b'\0') if part)


def process_role(pid: int) -> str | None:
    cmdline = proc_cmdline(pid)
    for needle, role in ROLES.items():
        if needle in cmdline:
            return role
    return None


def read_memory(pid: int) -> dict[str, int]:
    result = {'pss_kb': 0, 'rss_kb': 0, 'private_kb': 0, 'swap_kb': 0}
    try:
        with open(f'/proc/{pid}/smaps_rollup', 'r', encoding='ascii', errors='ignore') as stream:
            for line in stream:
                key, _, value = line.partition(':')
                if key == 'Pss':
                    result['pss_kb'] = int(value.split()[0])
                elif key == 'Rss':
                    result['rss_kb'] = int(value.split()[0])
                elif key in {'Private_Clean', 'Private_Dirty'}:
                    result['private_kb'] += int(value.split()[0])
                elif key == 'Swap':
                    result['swap_kb'] = int(value.split()[0])
        if result['rss_kb']:
            return result
    except (OSError, ValueError, IndexError):
        pass
    try:
        with open(f'/proc/{pid}/status', 'r', encoding='ascii', errors='ignore') as stream:
            for line in stream:
                if line.startswith('VmRSS:'):
                    result['rss_kb'] = int(line.split()[1])
                    break
    except (OSError, ValueError, IndexError):
        pass
    return result


def snapshot() -> dict[str, Any]:
    processes = []
    totals = {'pss_kb': 0, 'rss_kb': 0, 'private_kb': 0, 'swap_kb': 0, 'count': 0}
    try:
        entries = os.listdir('/proc')
    except OSError:
        entries = []
    for entry in entries:
        if not entry.isdigit():
            continue
        pid = int(entry)
        role = process_role(pid)
        if role is None:
            continue
        memory = read_memory(pid)
        memory.update({'pid': pid, 'role': role})
        processes.append(memory)
        for key in ('pss_kb', 'rss_kb', 'private_kb', 'swap_kb'):
            totals[key] += memory[key]
        totals['count'] += 1
    processes.sort(key=lambda item: (item['role'], item['pid']))
    try:
        load = Path('/proc/loadavg').read_text(encoding='ascii').split()[:3]
    except OSError:
        load = []
    return {
        'timestamp': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'host': os.uname().nodename if hasattr(os, 'uname') else '',
        'loadavg': load,
        'processes': processes,
        'totals': totals,
    }


def friendly(values: dict[str, Any]) -> str:
    lines = [
        f"{values['timestamp']}  load={' '.join(values['loadavg']) or '?'}",
        f"processes={values['totals']['count']}  "
        f"PSS={values['totals']['pss_kb'] / 1024:.1f} MiB  "
        f"RSS={values['totals']['rss_kb'] / 1024:.1f} MiB  "
        f"private={values['totals']['private_kb'] / 1024:.1f} MiB  "
        f"swap={values['totals']['swap_kb'] / 1024:.1f} MiB",
    ]
    for process in values['processes']:
        lines.append(
            f"  {process['role']:<8} pid={process['pid']:<7} "
            f"PSS={process['pss_kb'] / 1024:.1f} MiB  "
            f"RSS={process['rss_kb'] / 1024:.1f} MiB  "
            f"private={process['private_kb'] / 1024:.1f} MiB"
        )
    return '\n'.join(lines)


def sample(seconds: float, interval: float) -> dict[str, Any]:
    samples = []
    deadline = time.monotonic() + max(0.1, seconds)
    while True:
        samples.append(snapshot())
        if time.monotonic() >= deadline:
            break
        time.sleep(max(0.05, interval))
    total_pss = [item['totals']['pss_kb'] for item in samples]
    total_rss = [item['totals']['rss_kb'] for item in samples]
    return {
        'seconds': seconds,
        'interval': interval,
        'samples': samples,
        'summary': {
            'pss_kb': {
                'min': min(total_pss), 'max': max(total_pss),
                'avg': round(statistics.fmean(total_pss), 1),
            },
            'rss_kb': {
                'min': min(total_rss), 'max': max(total_rss),
                'avg': round(statistics.fmean(total_rss), 1),
            },
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument('--json', action='store_true')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('snapshot', parents=[common])
    sample_parser = sub.add_parser('sample', parents=[common])
    sample_parser.add_argument('--seconds', type=float, default=30.0)
    sample_parser.add_argument('--interval', type=float, default=2.0)
    args = parser.parse_args(argv)

    if args.command == 'snapshot':
        result = snapshot()
        print(json.dumps(result, indent=2) if args.json else friendly(result))
        return 0
    result = sample(args.seconds, args.interval)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        for item in result['samples']:
            print(friendly(item))
            print()
        summary = result['summary']
        print(f"PSS min/max/avg: {summary['pss_kb']['min'] / 1024:.1f} / "
              f"{summary['pss_kb']['max'] / 1024:.1f} / {summary['pss_kb']['avg'] / 1024:.1f} MiB")
        print(f"RSS min/max/avg: {summary['rss_kb']['min'] / 1024:.1f} / "
              f"{summary['rss_kb']['max'] / 1024:.1f} / {summary['rss_kb']['avg'] / 1024:.1f} MiB")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
