from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

import requests

from ofdl.api import ApiClient, ApiError, Rules
from ofdl.common import AppError, Cancelled, Control
from ofdl.dsm import db
from ofdl.dsm.jobs import normalize_renewal
from ofdl.dsm.locale import dsm_language
from ofdl.dsm.processes import _stat, register_worker, signal_worker
from ofdl.dsm.renewals import run_free_renew, run_offers_scan
from ofdl.dsm.security import SessionStore
from ofdl.dsm.worker import EventWriter
from tests.test_api import AUTH, RULE_DATA, session_for
from tests.test_dsm_service import Harness
from tests.test_offers import FREE_ROW, PAID_ROW, TRIAL_ROW, FakeClient


class ResilienceTests(unittest.TestCase):
    def setUp(self):
        self.h = Harness()

    def tearDown(self):
        self.h.close()

    def test_threaded_progress_releases_write_lock_and_flushes_final_stats(self):
        with db.connect(self.h.paths.db) as conn:
            job = db.create_job(conn, 'download', {})
        writer = EventWriter(self.h.paths, job)
        try:
            thread = threading.Thread(target=lambda: writer.emit('progress', {
                'file': 'example.mp4', 'done': 1, 'total': 10, 'speed': float('inf')}))
            thread.start(); thread.join(timeout=3)
            with db.connect(self.h.paths.db) as conn:
                stats = json.loads(db.get_job(conn, job)['stats'])
                self.assertEqual(stats['current_done'], 1)
                self.assertEqual(stats['current_speed'], 0)
                # Must succeed while writer is idle, not after a 10 s lock timeout.
                conn.execute('PRAGMA busy_timeout=100')
                db.update_job(conn, job, cancel_requested=1)
            writer.emit('stats', {'downloaded': 1})
            writer.emit('stats', {'downloaded': 2})
            writer.flush()
            with db.connect(self.h.paths.db) as conn:
                self.assertEqual(json.loads(db.get_job(conn, job)['stats'])['downloaded'], 2)
        finally:
            writer.close()

    def test_failed_subscription_refresh_preserves_old_creator_list(self):
        from ofdl.dsm.run_jobs import run_subscriptions
        with db.connect(self.h.paths.db) as conn:
            db.upsert_creators(conn, [('oldcreator', 'Old', 'active')])
        client = FakeClient()
        def broken(*args, **kwargs):
            yield {'username': 'newcreator', 'name': 'New'}
            raise AppError('temporary network failure')
        client.paginate = broken
        with patch('ofdl.dsm.run_jobs._client', return_value=nullcontext(client)):
            with self.assertRaises(AppError):
                run_subscriptions(self.h.paths, {}, Control(), lambda *_: None)
        with db.connect(self.h.paths.db) as conn:
            self.assertEqual(db.page_creators(conn)[0]['username'], 'oldcreator')

    def test_nonfinite_old_stats_do_not_break_status_json(self):
        self.h.setup()
        with db.connect(self.h.paths.db) as conn:
            job = db.create_job(conn, 'download', {})
            db.update_job(conn, job, stats='{"current_speed":Infinity,"overall_done":NaN}')
        status, data = self.h.call('GET', '/api/status')
        self.assertEqual(status, 200)
        self.assertIsNone(data['active_job']['stats']['current_speed'])

    def test_recent_events_restore_tail_not_beginning(self):
        self.h.setup()
        with db.connect(self.h.paths.db) as conn:
            job = db.create_job(conn, 'download', {})
            for n in range(250):
                db.add_event(conn, job, 'log', str(n))
            conn.commit()
        status, data = self.h.call('GET', f'/api/jobs/{job}?tail=1')
        self.assertEqual(status, 200)
        self.assertEqual(len(data['events']), 100)
        self.assertEqual(data['events'][-1]['message'], '249')

    def test_status_returns_partial_data_instead_of_500(self):
        self.h.setup()
        with patch.object(self.h.app, 'library', side_effect=RuntimeError('broken manifest')):
            status, data = self.h.call('GET', '/api/status')
        self.assertEqual(status, 200)
        self.assertEqual(data['warnings'][0]['section'], 'library')
        self.assertEqual(data['warnings'][0]['error'], 'RuntimeError')
        self.assertTrue(data['version'])
        self.assertIn('recent_jobs', data)
        self.assertIn('memory', data)
        with patch.object(self.h.app.session_store, 'describe', side_effect=OSError('unreadable')):
            status, data = self.h.call('GET', '/api/status')
        self.assertEqual(status, 200)
        self.assertFalse(data['session']['present'])
        self.assertTrue(any(item['section'] == 'session' for item in data['warnings']))
        with patch.object(self.h.app, 'output_dir', side_effect=RuntimeError('symlink loop')):
            status, data = self.h.call('GET', '/api/status')
        self.assertEqual(status, 200)
        self.assertTrue(any(item['section'] == 'output_dir' for item in data['warnings']))

    def test_storage_check_reports_account_and_probe(self):
        self.h.setup()
        self.h.call('POST', '/api/settings', {'output_dir': str(self.h.output)})
        status, data = self.h.call('POST', '/api/storage/check', {})
        self.assertEqual(status, 200)
        self.assertTrue(data['ok'], data)
        self.assertEqual(data['path'], str(self.h.output.resolve()))
        self.assertTrue(data['target']['is_dir'])
        self.assertTrue(data['write_test']['ok'])
        self.assertTrue(data['disk']['ok'])
        self.assertTrue(data['process'].get('user'))
        self.assertTrue(data['hints'])
        # The probe must not leave a file behind.
        self.assertFalse(any(name.startswith('.ofdl-perm-') for name in
                             (item.name for item in self.h.output.iterdir())))

    def test_library_failure_is_a_warning_not_a_500(self):
        self.h.setup()
        with patch('ofdl.dsm.service.control_db.library_stats', side_effect=PermissionError(13, 'denied', '/volume1/x')):
            status, data = self.h.call('GET', '/api/status')
        self.assertEqual(status, 200)
        self.assertEqual(data['library']['error'], 'PermissionError')
        self.assertEqual(data['library']['detail']['errno'], 13)
        self.assertIn('/volume1/x', data['library']['detail']['filename'])
        self.assertFalse(any(item['section'] == 'library' for item in data['warnings']))

    def test_session_cannot_change_mid_job(self):
        self.h.setup(); self.h.import_fake_session()
        with db.connect(self.h.paths.db) as conn:
            db.create_job(conn, 'download', {})
        self.assertEqual(self.h.import_fake_session()[0], 409)
        self.assertEqual(self.h.call('POST', '/api/session/clear', {})[0], 409)
        self.assertEqual(self.h.call('DELETE', '/api/session')[0], 409)

    def test_spawn_registration_failure_does_not_leave_worker_running(self):
        manager = self.h.app.job_manager
        with patch('ofdl.dsm.service.register_worker', side_effect=OSError('disk full')), \
                patch.object(manager, '_signal', wraps=manager._signal) as stop:
            job = manager.start('test_session', {})
        self.assertEqual(job['status'], 'failed')
        self.assertTrue(stop.called)
        process = stop.call_args.args[0]
        self.assertIsNotNone(process.poll())
        self.assertIsNone(manager.process)

    def test_locale_dsm_config_and_fallback(self):
        config = self.h.root / 'synoinfo.conf'
        config.write_text('language="nld"\n')
        with patch.dict(os.environ, {'OFDL_DSM_LANGUAGE': ''}):
            self.assertEqual(dsm_language(config), 'nl')
        with patch.dict(os.environ, {'OFDL_DSM_LANGUAGE': 'ita'}):
            self.assertEqual(self.h.call('GET', '/api/locale')[1]['language'], 'it')

    def test_renewal_requires_confirmation_and_is_disabled_for_new_account(self):
        self.h.setup(); self.h.import_fake_session()
        self.assertEqual(self.h.call('POST', '/api/jobs', {
            'kind': 'free_renew', 'options': {'profiles': ['freebie']}})[0], 400)
        status, data = self.h.call('POST', '/api/settings', {'free_renewal': {
            'profiles': ['freebie'], 'confirm_free_only': True, 'enabled': True}})
        self.assertEqual(status, 200)
        self.assertTrue(data['free_renewal']['enabled'])
        from ofdl.auth import Credentials
        credentials = Credentials('67890', 'Mozilla/5.0 test', 'test-bc', 'test-sess')
        self.h.call('POST', '/api/session/import', {'text': json.dumps(credentials.to_dict())})
        self.assertFalse(self.h.app.public_settings()['free_renewal']['enabled'])

    def test_free_renew_skips_trials_paid_and_duplicate_daily_attempts(self):
        from ofdl.auth import Credentials
        SessionStore(self.h.paths.data).save(Credentials('12345', 'TestBrowser', 'bc', 'sess'))
        client = FakeClient(profiles={'freebie': FREE_ROW, 'paidpage': PAID_ROW, 'tester': TRIAL_ROW})
        payload = {'account_id': '12345', 'profiles': ['freebie', 'paidpage', 'tester']}
        with patch('ofdl.dsm.run_jobs._client', return_value=nullcontext(client)):
            result = run_free_renew(self.h.paths, payload, Control(), lambda *_: None)
        self.assertEqual(result['subscribed'], 1)
        self.assertEqual(len(client.posts), 1)
        with patch('ofdl.dsm.run_jobs._client', return_value=nullcontext(client)):
            run_free_renew(self.h.paths, payload, Control(), lambda *_: None)
        self.assertEqual(len(client.posts), 1)

    def test_price_change_and_cancellation_never_post(self):
        from ofdl.auth import Credentials
        SessionStore(self.h.paths.data).save(Credentials('12345', 'TestBrowser', 'bc', 'sess'))
        client = FakeClient()
        client.user = unittest.mock.Mock(side_effect=[FREE_ROW, dict(FREE_ROW, subscribePrice=5)])
        with patch('ofdl.dsm.run_jobs._client', return_value=nullcontext(client)):
            result = run_free_renew(self.h.paths, {'account_id': '12345', 'profiles': ['freebie']},
                                    Control(), lambda *_: None)
        self.assertEqual(result['errors'], 1)
        self.assertEqual(client.posts, [])
        stopped = Control(); stopped.stop()
        with patch('ofdl.dsm.run_jobs._client', return_value=nullcontext(client)):
            with self.assertRaises(Cancelled):
                run_free_renew(self.h.paths, {'account_id': '12345', 'profiles': ['freebie']}, stopped, lambda *_: None)

    def test_scan_does_not_claim_or_expose_trial_codes(self):
        from ofdl.auth import Credentials
        SessionStore(self.h.paths.data).save(Credentials('12345', 'TestBrowser', 'bc', 'sess'))
        client = FakeClient(subscriptions={'expired': [FREE_ROW, TRIAL_ROW]})
        with patch('ofdl.dsm.run_jobs._client', return_value=nullcontext(client)):
            result = run_offers_scan(self.h.paths, {}, Control(), lambda *_: None)
        self.assertEqual(result['offers'], 2)
        self.assertEqual(client.posts, [])

    def test_stale_worker_registry_cannot_signal_reused_pid(self):
        path = self.h.paths.pkgvar / 'worker-process.json'
        path.write_text(json.dumps({'pid': 54321, 'start': 'old', 'token': 'owned'}))
        with patch('ofdl.dsm.processes.os.name', 'posix'), \
                patch('ofdl.dsm.processes._stat', return_value=(54321, 'new')), \
                patch('ofdl.dsm.processes.os.killpg', create=True) as kill:
            self.assertFalse(signal_worker(self.h.paths.pkgvar, signal.SIGTERM))
            kill.assert_not_called()


class RetryTests(unittest.TestCase):
    def client(self, replies):
        session, adapter = session_for(replies)
        control = Control()
        events = []
        client = ApiClient(AUTH, Rules.from_dict(RULE_DATA), control, session=session,
                           interval=0, retry_floor=180, emit=lambda *args: events.append(args))
        self.addCleanup(client.close)
        return client, adapter, control, events

    def test_dsm_reads_wait_three_minutes_and_honor_retry_after(self):
        for headers, expected in [({}, 180), ({'Retry-After': '240'}, 240)]:
            client, adapter, control, events = self.client([(429, {}, headers), (200, {'id': 123}, {})])
            with patch.object(control, 'wait') as wait:
                client.user('me')
            self.assertTrue(any(call.args == (expected,) for call in wait.call_args_list))
            self.assertEqual(len(adapter.requests), 2)
            self.assertTrue(any(kind == 'retry' and value.get('retry_at') for kind, value in events))

    def test_authentication_failure_and_post_are_not_retried(self):
        client, adapter, control, events = self.client([(401, {}, {})])
        with self.assertRaises(ApiError): client.user('me')
        self.assertEqual(len(adapter.requests), 1)
        client, adapter, control, events = self.client([requests.Timeout()])
        with self.assertRaises(AppError): client.post('/users/11/subscribe')
        self.assertEqual(len(adapter.requests), 1)
        self.assertFalse(any(kind == 'retry' for kind, _ in events))

    def test_three_minute_wait_is_cancellable(self):
        client, adapter, control, events = self.client([(503, {}, {})])
        def wait(seconds):
            if seconds >= 180:
                raise Cancelled('test cancellation during backoff')
        with patch.object(control, 'wait', side_effect=wait):
            with self.assertRaises(Cancelled): client.user('me')
        self.assertEqual(len(adapter.requests), 1)


@unittest.skipUnless(sys.platform.startswith('linux'), 'real Linux process groups tested in CI, not on Windows')
class LinuxProcessTreeTests(unittest.TestCase):
    def test_cleanup_stops_owned_service_with_missing_pidfile(self):
        root_source = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            env = {**os.environ, 'SYNOPKG_PKGDEST': str(root_source), 'SYNOPKG_PKGVAR': str(root),
                   'OFDL_DATA_DIR': str(root / 'data'), 'OFDL_LOG_DIR': str(root / 'logs'),
                   'OFDL_CONFIG_DIR': str(root / 'config'), 'OFDL_TMP_DIR': str(root / 'tmp'),
                   'OFDL_HOME': str(root / 'home'), 'OFDL_PREVIEW_DIR': str(root / 'previews')}
            process = subprocess.Popen([sys.executable, '-m', 'ofdl.dsm.service', '--host',
                                        '127.0.0.1', '--port', '0', '--no-scheduler'],
                                       cwd=root_source, env=env)
            try:
                deadline = time.monotonic() + 8
                while not (root / 'service.pid').exists() and time.monotonic() < deadline: time.sleep(.05)
                (root / 'service.pid').unlink()
                result = subprocess.run([sys.executable, '-m', 'ofdl.dsm.processes', 'cleanup', '--var', str(root)],
                                        cwd=root_source, env=env, timeout=15, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                process.wait(timeout=5)
            finally:
                if process.poll() is None: process.kill()
                process.wait(timeout=3)

    def test_group_cleanup_stops_worker_and_child_even_after_leader_dies(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            child_file = root / 'child.pid'
            script = ('import subprocess,sys,time,pathlib; '
                      'p=subprocess.Popen([sys.executable,"-c","import time; time.sleep(120)"]); '
                      'pathlib.Path(sys.argv[1]).write_text(str(p.pid)); time.sleep(120)')
            process = subprocess.Popen([sys.executable, '-c', script, str(child_file)],
                                       env={**os.environ, 'OFDL_RUN_TOKEN': 'test-owned-group'}, start_new_session=True)
            try:
                register_worker(root, process.pid, 'test-owned-group')
                deadline = time.monotonic() + 5
                while not child_file.exists() and time.monotonic() < deadline: time.sleep(.02)
                child = int(child_file.read_text())
                process.kill(); process.wait(timeout=3)
                self.assertTrue(signal_worker(root, signal.SIGTERM))
                deadline = time.monotonic() + 3
                while _stat(child) is not None and time.monotonic() < deadline: time.sleep(.02)
                self.assertIsNone(_stat(child))
            finally:
                try: os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError: pass
                process.wait(timeout=3)


if __name__ == '__main__':
    unittest.main()
