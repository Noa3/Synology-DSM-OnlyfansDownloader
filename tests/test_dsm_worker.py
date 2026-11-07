from __future__ import annotations

import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from ofdl.common import AppError, Cancelled, Control
from ofdl.dsm import db
from ofdl.dsm.config import resolve_paths
from ofdl.dsm.run_jobs import run_job, run_preview, run_subscriptions, run_test_session
from ofdl.dsm.worker import EventWriter, JobControl


class WorkerTests(unittest.TestCase):
    def setUp(self):
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
            'OFDL_PARENT_PID': str(os.getppid()),
        }.items():
            self.env[key] = os.environ.get(key)
            os.environ[key] = str(value)
        self.paths = resolve_paths()
        db.init_db(self.paths.db)
        with db.connect(self.paths.db) as conn:
            self.job_id = db.create_job(conn, 'test_session', {})

    def tearDown(self):
        for key, value in self.env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()

    def test_job_control_pause_and_cancel(self):
        control = JobControl(self.paths, self.job_id)
        self.assertFalse(control.paused.is_set())
        with db.connect(self.paths.db) as conn:
            db.update_job(conn, self.job_id, pause_requested=1)
        control._poll()
        self.assertTrue(control.paused.is_set())
        with db.connect(self.paths.db) as conn:
            db.update_job(conn, self.job_id, pause_requested=0)
        control._next_poll = 0
        control._poll()
        self.assertFalse(control.paused.is_set())
        with db.connect(self.paths.db) as conn:
            db.update_job(conn, self.job_id, cancel_requested=1)
        control._next_poll = 0
        control._poll()
        with self.assertRaises(Cancelled):
            control.checkpoint()

    def test_event_writer_is_bounded_and_records_progress(self):
        writer = EventWriter(self.paths, self.job_id)
        writer.emit('log', 'hello')
        writer.emit('phase', 'Download')
        writer.emit('stats', {'downloaded': 2, 'existing': 1})
        writer.emit('overall', {'done': 5, 'total': 10})
        writer.emit('progress', {'file': 'a.jpg', 'done': 100, 'total': 200, 'speed': 10.0})
        writer.emit('media_complete', {'relative': 'a.jpg', 'kind': 'photo', 'size': 123, 'profile': 'alice'})
        writer.flush()
        writer.close()
        with db.connect(self.paths.db) as conn:
            job = db.get_job(conn, self.job_id)
            events = db.list_events(conn, self.job_id, limit=20)
        self.assertEqual(job['progress_done'], 5)
        self.assertEqual(job['progress_total'], 10)
        self.assertIn('downloaded', job['stats'])
        self.assertTrue(any(event['level'] == 'media' for event in events))
        self.assertTrue(any(event['level'] == 'log' for event in events))

    def test_preview_job_writes_cache_file(self):
        image = self.output / 'album' / 'photo.jpg'
        image.parent.mkdir()
        Image.new('RGB', (800, 600), (20, 100, 150)).save(image, quality=85)
        result = run_preview(self.paths, {
            'output_dir': str(self.output), 'path': 'album/photo.jpg', 'kind': 'photo',
        }, Control(), lambda *_: None)
        self.assertTrue(result['url'])
        name = result['url'].rsplit('/', 1)[-1]
        self.assertTrue((self.paths.previews / name).is_file())

    def test_subscriptions_are_stored_in_pages(self):
        class FakeClient:
            def paginate(self, endpoint, category):
                for name in ('Alice', 'bob', 'carol'):
                    yield {'username': name, 'name': name.title()}

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        with patch('ofdl.dsm.run_jobs._client', return_value=FakeClient()):
            result = run_subscriptions(self.paths, {}, Control(), lambda *_: None)
        self.assertEqual(result['creators'], 3)
        with db.connect(self.paths.db) as conn:
            self.assertEqual(db.count_creators(conn), 3)
            self.assertEqual(db.page_creators(conn, query='ali')[0]['username'], 'alice')

    def test_test_session_returns_only_safe_fields(self):
        class FakeClient:
            def user(self, endpoint):
                return {'id': 123, 'username': 'alice', 'email': 'secret@example.com',
                        'session': 'should-not-leak'}

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        with patch('ofdl.dsm.run_jobs._client', return_value=FakeClient()):
            result = run_test_session(self.paths, {}, Control(), lambda *_: None)
        self.assertEqual(result['user_id'], '123')
        self.assertEqual(result['username'], 'alice')
        self.assertNotIn('email', result)
        self.assertNotIn('session', result)

    def test_download_job_maps_options_and_writes_summary(self):
        post = {
            'id': 77,
            'postedAt': '2026-01-02T03:04:05Z',
            'media': [{
                'id': '999',
                'type': 'photo',
                'createdAt': '2026-01-02T03:04:05Z',
                'files': {'full': {'url': 'https://onlyfans.com/media/999.jpg'}},
            }],
        }

        class FakeClient:
            class Auth:
                user_agent = 'Mozilla/5.0 test'

            auth = Auth()

            def user(self, endpoint):
                return {'id': 1, 'username': 'alice'}

            def paginate(self, endpoint, category, since=None):
                if endpoint == '/users/1/posts':
                    yield post

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        def fake_download(downloader, task):
            target = downloader.options.output_dir / task.relative_path(downloader.options)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b'fake image bytes')
            return 'downloaded', len(b'fake image bytes')

        from ofdl.dsm.run_jobs import run_download
        with patch('ofdl.dsm.run_jobs._client', return_value=FakeClient()), \
                patch('ofdl.downloads.Downloader.download', new=fake_download):
            summary = run_download(self.paths, {
                'output_dir': str(self.output),
                'profiles': ['alice'],
                'categories': ['posts'],
                'types': {'photos': True, 'videos': False, 'audio': False},
            }, Control(), lambda *_: None)
        self.assertEqual(summary['downloaded'], 1)
        self.assertEqual(summary['errors'], 0)
        files = list(self.output.rglob('*.jpg'))
        self.assertEqual(len(files), 1)

    def test_unknown_job_type(self):
        with self.assertRaises(AppError):
            run_job(self.paths, 'missing', {}, Control(), lambda *_: None)


if __name__ == '__main__':
    unittest.main()
