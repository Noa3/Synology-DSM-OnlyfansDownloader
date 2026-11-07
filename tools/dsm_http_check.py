#!/usr/bin/env python3
"""Small HTTP smoke test for the DSM control service.

Example on the NAS (password is read from stdin so it is not in the shell history):
    printf '%s' 'your-password' | python3 tools/dsm_http_check.py --password-stdin --open-ui
"""
from __future__ import annotations

import argparse
import http.cookiejar
import json
import os
import sys
import urllib.error
import urllib.request


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', default='http://127.0.0.1:8765')
    parser.add_argument('--password-stdin', action='store_true')
    parser.add_argument('--open-ui', action='store_true',
                        help='also fetch the HTML/CSS/JS files a browser would load')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)

    password = os.environ.get('OFDL_WEB_PASSWORD', '')
    if args.password_stdin:
        password = sys.stdin.read().rstrip('\r\n')
    if not password:
        print('ERROR: provide the web password via stdin or OFDL_WEB_PASSWORD', file=sys.stderr)
        return 2

    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    base = args.base.rstrip('/')
    csrf = ''
    result: dict[str, object] = {'base': base, 'checks': {}, 'ok': True}

    def call(method: str, path: str, payload: dict | None = None, *,
             auth: bool = True, csrf_needed: bool = True):
        nonlocal csrf
        data = json.dumps(payload).encode('utf-8') if payload is not None else None
        headers = {'Content-Type': 'application/json'} if data is not None else {}
        if auth and csrf and csrf_needed:
            headers['X-CSRF-Token'] = csrf
        request = urllib.request.Request(base + path, data=data, method=method, headers=headers)
        try:
            with opener.open(request, timeout=20) as response:
                body = response.read()
                content_type = response.headers.get('Content-Type', '')
                if 'application/json' in content_type:
                    return response.status, json.loads(body.decode('utf-8'))
                return response.status, body
        except urllib.error.HTTPError as exc:
            body = exc.read()
            try:
                parsed = json.loads(body.decode('utf-8'))
            except (ValueError, UnicodeError):
                parsed = body.decode('utf-8', errors='replace')
            return exc.code, parsed

    status, health = call('GET', '/api/health', auth=False)
    result['checks']['health'] = {'status': status, 'setup_required': health.get('setup_required') if isinstance(health, dict) else None}
    if status != 200:
        result['ok'] = False
        print(json.dumps(result, indent=2) if args.json else result)
        return 1

    status, login = call('POST', '/api/login', {'password': password}, auth=False)
    result['checks']['login'] = {'status': status}
    if status != 200:
        result['ok'] = False
        print(json.dumps(result, indent=2) if args.json else result)
        return 1
    csrf = login.get('csrf', '')

    status, session = call('GET', '/api/session')
    result['checks']['session'] = {'status': status, 'present': session.get('session', {}).get('present')}
    status, app_status = call('GET', '/api/status')
    result['checks']['status'] = {
        'status': status,
        'version': app_status.get('version'),
        'output_dir': app_status.get('output_dir'),
        'session_present': app_status.get('session', {}).get('present'),
        'active_job': bool(app_status.get('active_job')),
        'memory': app_status.get('memory'),
    }
    status, settings = call('GET', '/api/settings')
    result['checks']['settings'] = {'status': status, 'schedule': settings.get('schedule')}
    status, folders = call('GET', '/api/folders')
    result['checks']['folders'] = {'status': status, 'path': folders.get('path'),
                                   'items': len(folders.get('items') or [])}
    status, creators = call('GET', '/api/creators?page=1&per_page=5')
    result['checks']['creators'] = {'status': status, 'total': creators.get('total')}
    status, jobs = call('GET', '/api/jobs')
    result['checks']['jobs'] = {'status': status, 'count': len(jobs.get('jobs') or [])}

    if args.open_ui:
        for path in ('/', '/static/style.css', '/static/app.js', '/manifest.webmanifest'):
            request = urllib.request.Request(base + path)
            try:
                with opener.open(request, timeout=20) as response:
                    body = response.read()
                    result['checks']['ui:' + path] = {
                        'status': response.status,
                        'bytes': len(body),
                        'content_type': response.headers.get('Content-Type', ''),
                    }
            except urllib.error.HTTPError as exc:
                result['checks']['ui:' + path] = {'status': exc.code, 'bytes': 0}
                result['ok'] = False

    for check in result['checks'].values():
        if isinstance(check, dict) and check.get('status', 200) >= 400:
            result['ok'] = False
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        for name, check in result['checks'].items():
            print(f'{name}: {check}')
        print('OK' if result['ok'] else 'FAILED')
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
