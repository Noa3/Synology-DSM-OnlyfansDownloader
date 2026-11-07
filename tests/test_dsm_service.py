from __future__ import annotations

import http.cookiejar
import http.client
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from PIL import Image

from ofdl.dsm.config import resolve_paths
from ofdl.dsm.service import Scheduler, create_server
from ofdl.dsm import db
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class Harness:
    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.share = self.root / 'share'
        self.share.mkdir()
        self.output = self.share / 'OnlyFans'
        self.output.mkdir()
        self.env = {}
        for key, value in {
            'OFDL_DATA_DIR': self.root / 'data',
            'OFDL_SHARE_ROOT': self.share,
            'OFDL_LOG_DIR': self.root / 'logs',
            'OFDL_PREVIEW_DIR': self.root / 'data' / 'previews',
            'OFDL_CONFIG_DIR': self.root / 'config',
            'OFDL_TMP_DIR': self.root / 'tmp',
            'OFDL_HOME': self.root / 'home',
        }.items():
            self.env[key] = os.environ.get(key)
            os.environ[key] = str(value)
        self.fake_worker = self.root / 'fake_worker.py'
        self.fake_worker.write_text(
            'import sys, time\n'
            'from ofdl.dsm import db\n'
            'from ofdl.dsm.config import resolve_paths\n'
            'job_id=int(sys.argv[1]); paths=resolve_paths()\n'
            'with db.connect(paths.db) as c:\n'
            '    db.update_job(c, job_id, status="running", pid=__import__("os").getpid())\n'
            '    db.add_event(c, job_id, "phase", "Fake phase")\n'
            '    c.commit()\n'
            'time.sleep(1.0)\n'
            'with db.connect(paths.db) as c:\n'
            '    db.finish_job(c, job_id, "completed", result={"message":"fake done"}, exit_code=0)\n',
            encoding='utf-8')
        self.env['OFDL_WORKER_COMMAND'] = os.environ.get('OFDL_WORKER_COMMAND')
        os.environ['OFDL_WORKER_COMMAND'] = json.dumps([sys.executable, str(self.fake_worker)])
        self.paths = resolve_paths()
        self.server, self.app = create_server(self.paths, '127.0.0.1', 0, start_scheduler=False)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self.csrf = ''

    def url(self, path):
        return f'http://127.0.0.1:{self.port}{path}'

    def call(self, method, path, payload=None, *, csrf=True, opener=None):
        data = json.dumps(payload).encode('utf-8') if payload is not None else None
        headers = {'Content-Type': 'application/json'} if data is not None else {}
        if csrf and self.csrf:
            headers['X-CSRF-Token'] = self.csrf
        request = urllib.request.Request(self.url(path), data=data, method=method, headers=headers)
        try:
            with (opener or self.opener).open(request, timeout=15) as response:
                body = response.read()
                content_type = response.headers.get('Content-Type', '')
                if 'application/json' in content_type:
                    return response.status, json.loads(body.decode('utf-8'))
                return response.status, body.decode('utf-8', errors='replace')
        except urllib.error.HTTPError as exc:
            body = exc.read()
            content_type = exc.headers.get('Content-Type', '')
            if 'application/json' in content_type:
                return exc.code, json.loads(body.decode('utf-8'))
            return exc.code, body.decode('utf-8', errors='replace')

    def setup(self, password='test-password-123'):
        status, data = self.call('POST', '/api/setup',
                                 {'password': password, 'confirm': password}, csrf=False)
        if status == 200:
            self.csrf = data['csrf']
        return status, data

    def login(self, password='test-password-123', opener=None):
        status, data = self.call('POST', '/api/login', {'password': password}, csrf=False,
                                 opener=opener)
        if status == 200 and opener is None:
            self.csrf = data['csrf']
        return status, data

    def import_fake_session(self):
        return self.call('POST', '/api/session/import', {
            'text': json.dumps({'user_id': '12345', 'user_agent': 'Mozilla/5.0 test',
                                'x_bc': 'abc', 'sess_cookie': 'sess-value'}),
        })

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.app.close()
        for key, value in self.env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.h = Harness()

    def tearDown(self):
        self.h.close()

    def test_control_service_import_is_light(self):
        code = (
            'import sys; import ofdl.dsm.service; '
            'bad=[name for name in ("requests","curl_cffi","PIL","ofdl.api","ofdl.downloads") '
            'if name in sys.modules]; '
            'print(bad); raise SystemExit(1 if bad else 0)'
        )
        completed = subprocess.run([sys.executable, '-c', code], cwd=str(ROOT),
                                   capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)

    def test_health_and_setup(self):
        status, data = self.h.call('GET', '/api/health', csrf=False)
        self.assertEqual(status, 200)
        self.assertTrue(data['setup_required'])
        status, data = self.h.call('GET', '/', csrf=False)
        self.assertEqual(status, 200)
        self.assertIn('Ersteinrichtung', data)
        self.assertEqual(self.h.setup()[0], 200)
        self.assertTrue(self.h.paths.db.is_file())
        status, data = self.h.call('GET', '/api/session')
        self.assertEqual(status, 200)
        self.assertTrue(data['authenticated'])
        self.assertFalse(data['session']['present'])

    def test_unauthenticated_api_is_rejected(self):
        self.h.setup()
        anonymous = urllib.request.build_opener()
        with self.assertRaises(urllib.error.HTTPError) as context:
            anonymous.open(self.h.url('/api/status'), timeout=5)
        self.assertEqual(context.exception.code, 401)

    def test_login_cookie_and_csrf(self):
        self.h.setup('test-password-123')
        jar = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        status, data = self.h.login('test-password-123', opener=opener)
        self.assertEqual(status, 200)
        self.assertTrue(any(cookie.name == 'ofdl_session' for cookie in jar))
        cookie = next(cookie for cookie in jar if cookie.name == 'ofdl_session')
        self.assertTrue(cookie.has_nonstandard_attr('HttpOnly') or cookie._rest.get('HttpOnly'))
        # Missing CSRF token on a state-changing request is refused.
        status, _ = self.h.call('POST', '/api/settings', {'output_dir': str(self.h.output)},
                                csrf=False)
        self.assertEqual(status, 403)
        # A foreign Origin is refused even with a valid token.
        request = urllib.request.Request(self.h.url('/api/settings'),
                                         data=json.dumps({'output_dir': str(self.h.output)}).encode(),
                                         method='POST',
                                         headers={'Content-Type': 'application/json',
                                                  'X-CSRF-Token': self.h.csrf,
                                                  'Origin': 'http://evil.example'})
        with self.assertRaises(urllib.error.HTTPError) as context:
            self.h.opener.open(request, timeout=5)
        self.assertEqual(context.exception.code, 403)

    def test_session_import_status_and_clear(self):
        self.h.setup()
        status, data = self.h.import_fake_session()
        self.assertEqual(status, 200)
        self.assertEqual(data['user_id'], '12345')
        self.assertTrue((self.h.paths.data / 'session.json').is_file())
        status, data = self.h.call('GET', '/api/status')
        self.assertEqual(status, 200)
        self.assertTrue(data['session']['present'])
        self.assertEqual(data['session']['user_id'], '12345')
        self.assertFalse(data['session']['verified'])
        status, data = self.h.call('POST', '/api/session/clear', {})
        self.assertEqual(status, 200)
        status, data = self.h.call('GET', '/api/status')
        self.assertFalse(data['session']['present'])

    def test_settings_folders_and_output_validation(self):
        self.h.setup()
        status, data = self.h.call('POST', '/api/settings', {
            'output_dir': str(self.h.output),
            'schedule': {'enabled': True, 'time': '03:30', 'options': {'output_dir': str(self.h.output)}},
            'proxy': 'http://user:pass@192.0.2.1:8080',
        })
        self.assertEqual(status, 200)
        self.assertEqual(data['output_dir'], str(self.h.output))
        self.assertNotIn('user:pass', data['proxy'])
        status, data = self.h.call('GET', '/api/folders')
        self.assertEqual(status, 200)
        self.assertEqual(Path(data['path']), self.h.share.resolve())
        status, data = self.h.call('POST', '/api/folders', {
            'parent': str(self.h.share), 'name': 'Neu',
        })
        self.assertEqual(status, 201)
        self.assertTrue(Path(data['path']).is_dir())
        status, _ = self.h.call('POST', '/api/folders', {
            'parent': str(self.h.root), 'name': 'outside',
        })
        self.assertEqual(status, 403)
        status, _ = self.h.call('POST', '/api/settings', {'output_dir': str(self.h.root / 'nope')})
        self.assertEqual(status, 400)

    def test_job_lifecycle_events_and_single_job(self):
        self.h.setup()
        self.h.import_fake_session()
        status, data = self.h.call('POST', '/api/jobs', {'kind': 'test_session', 'options': {}})
        self.assertEqual(status, 202)
        job_id = data['job']['id']
        status, _ = self.h.call('POST', '/api/jobs', {'kind': 'test_session', 'options': {}})
        self.assertEqual(status, 409)
        for _ in range(40):
            time.sleep(0.1)
            status, data = self.h.call('GET', f'/api/jobs/{job_id}?after=0')
            if data['job']['status'] not in ('queued', 'running', 'paused'):
                break
        self.assertEqual(data['job']['status'], 'completed')
        self.assertEqual(data['job']['result']['message'], 'fake done')
        self.assertTrue(any(event['level'] == 'phase' for event in data['events']))
        for _ in range(20):
            status, data = self.h.call('GET', '/api/status')
            if data['session']['verified']:
                break
            time.sleep(0.05)
        self.assertTrue(data['session']['verified'])

    def test_preview_job(self):
        self.h.setup()
        self.h.call('POST', '/api/settings', {'output_dir': str(self.h.output)})
        previous = os.environ.pop('OFDL_WORKER_COMMAND', None)
        try:
            image = self.h.output / 'photo.jpg'
            Image.new('RGB', (640, 480), (10, 120, 180)).save(image)
            status, data = self.h.call('POST', '/api/preview',
                                       {'path': 'photo.jpg', 'kind': 'photo',
                                        'output_dir': str(self.h.output)})
            self.assertEqual(status, 202)
            job_id = data['job']['id']
            for _ in range(60):
                time.sleep(0.1)
                status, data = self.h.call('GET', f'/api/jobs/{job_id}')
                if data['job']['status'] not in ('queued', 'running', 'paused'):
                    break
            self.assertEqual(data['job']['status'], 'completed')
            url = data['job']['result']['url']
            request = urllib.request.Request(self.h.url(url))
            with self.h.opener.open(request, timeout=5) as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(response.read(4), b'\x89PNG')
        finally:
            if previous is not None:
                os.environ['OFDL_WORKER_COMMAND'] = previous

    def test_static_files_are_not_traversable(self):
        self.h.setup()
        status, body = self.h.call('GET', '/static/app.js')
        self.assertEqual(status, 200)
        self.assertIn('OnlyFans', body)
        status, _ = self.h.call('GET', '/static/../ofdl/dsm/service.py')
        self.assertEqual(status, 404)
        status, _ = self.h.call('GET', '/static/nope.js')
        self.assertEqual(status, 404)

    def test_startup_and_status_do_not_select_or_create_library(self):
        self.h.setup()
        before = set(self.h.share.iterdir())
        for endpoint in ('/api/settings', '/api/status', '/api/library'):
            status, data = self.h.call('GET', endpoint)
            self.assertEqual(status, 200)
            self.assertEqual(data['output_dir'], '')
        self.assertEqual(set(self.h.share.iterdir()), before)
        self.assertIsNone(self.h.app.ensure_output_dir())

    def test_library_path_is_shared_and_cache_changes_immediately(self):
        self.h.setup()
        self.h.import_fake_session()
        self.h.call('GET', '/api/library')  # Populate cache with no library.
        status, _ = self.h.call('POST', '/api/settings', {'output_dir': str(self.h.output)})
        self.assertEqual(status, 200)
        status, data = self.h.call('GET', '/api/status')
        self.assertEqual(data['output_dir'], str(self.h.output))
        self.assertEqual(data['library']['output_dir'], str(self.h.output))
        missing = self.h.share / 'missing'
        status, _ = self.h.call('POST', '/api/settings', {'output_dir': str(missing)})
        self.assertEqual(status, 400)
        self.assertFalse(missing.exists())
        status, _ = self.h.call('POST', '/api/jobs', {
            'kind': 'download', 'options': {'output_dir': str(self.h.share), 'profiles': ['alice']}})
        self.assertEqual(status, 409)
        status, data = self.h.call('POST', '/api/jobs', {
            'kind': 'download', 'options': {'profiles': ['alice']}})
        self.assertEqual(status, 202)
        self.assertEqual(data['job']['request']['output_dir'], str(self.h.output))
        status, _ = self.h.call('POST', '/api/settings', {'output_dir': str(self.h.share)})
        self.assertEqual(status, 409)

    def test_scheduler_uses_current_library_not_old_snapshot(self):
        self.h.setup()
        self.h.import_fake_session()
        self.h.call('POST', '/api/settings', {
            'output_dir': str(self.h.output),
            'schedule': {'enabled': True, 'time': '00:00',
                         'options': {'output_dir': str(self.h.share), 'profiles': ['alice']}},
        })
        with patch.object(self.h.app.job_manager, 'start') as start:
            Scheduler(self.h.app).tick()
        self.assertEqual(start.call_args.args[1]['output_dir'], str(self.h.output))

    def test_bootstrap_never_creates_download_folders(self):
        from ofdl.dsm.bootstrap import main
        fresh = self.h.root / 'bootstrap-share'
        fresh.mkdir()
        main(['--share-root', str(fresh), '--data-dir', str(self.h.root / 'bootstrap-data')])
        self.assertEqual(list(fresh.iterdir()), [])

    def test_legacy_destination_needs_explicit_confirmation(self):
        self.h.setup()
        with db.connect(self.h.paths.db) as conn:
            db.set_setting(conn, 'output_dir', str(self.h.output))
        self.assertIsNone(self.h.app.output_dir())
        status, data = self.h.call('GET', '/api/settings')
        self.assertEqual(data['output_dir'], '')
        self.h.import_fake_session()
        status, _ = self.h.call('POST', '/api/jobs', {
            'kind': 'download', 'options': {'profiles': ['alice']}})
        self.assertEqual(status, 409)
        status, _ = self.h.call('POST', '/api/settings', {'output_dir': str(self.h.output)})
        self.assertEqual(status, 200)
        self.assertEqual(self.h.app.output_dir(), self.h.output.resolve())

    def test_logout_body_cannot_corrupt_next_http_request(self):
        self.h.setup()
        connection = http.client.HTTPConnection('127.0.0.1', self.h.port, timeout=5)
        cookie = '; '.join(f'{item.name}={item.value}' for item in self.h.jar)
        try:
            connection.request('POST', '/api/logout', body='{}', headers={
                'Cookie': cookie, 'X-CSRF-Token': self.h.csrf, 'Content-Type': 'application/json'})
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(response.getheader('Connection'), 'close')
            response.read()
            connection.request('GET', '/login')
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            response.read()
        finally:
            connection.close()

    def test_login_rate_limit(self):
        self.h.setup('test-password-123')
        for _ in range(5):
            status, _ = self.h.call('POST', '/api/login', {'password': 'wrong'}, csrf=False)
            self.assertEqual(status, 401)
        status, _ = self.h.call('POST', '/api/login', {'password': 'wrong'}, csrf=False)
        self.assertEqual(status, 429)


if __name__ == '__main__':
    unittest.main()
