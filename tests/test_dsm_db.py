from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from ofdl.dsm import db
from ofdl.dsm.jobs import public_job


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'control.sqlite3'
        db.init_db(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_settings_and_json(self):
        with db.connect(self.path) as conn:
            self.assertEqual(db.get_setting(conn, 'missing', 'fallback'), 'fallback')
            db.set_setting(conn, 'name', 'value')
            self.assertEqual(db.get_setting(conn, 'name'), 'value')
            db.set_json(conn, 'schedule', {'enabled': True, 'time': '03:30'})
            self.assertEqual(db.get_json(conn, 'schedule', {}), {'enabled': True, 'time': '03:30'})
            db.set_setting(conn, 'schedule', 'not-json')
            self.assertEqual(db.get_json(conn, 'schedule', {'fallback': True}), {'fallback': True})

    def test_job_lifecycle_and_events(self):
        with db.connect(self.path) as conn:
            job_id = db.create_job(conn, 'download', {'output_dir': '/volume1/OnlyFans'})
            row = db.get_job(conn, job_id)
            self.assertEqual(row['status'], 'queued')
            self.assertEqual(db.active_job(conn)['id'], job_id)
            db.update_job(conn, job_id, status='running', progress_done=3, progress_total=10,
                          phase='Download', stats='{"downloaded":2}')
            db.add_event(conn, job_id, 'log', 'hello')
            db.add_event(conn, job_id, 'media', '{"relative":"a.jpg"}')
            conn.commit()
            events = db.list_events(conn, job_id)
            self.assertEqual([event['level'] for event in events], ['log', 'media'])
            self.assertEqual(db.list_events(conn, job_id, after=events[0]['id'])[0]['level'], 'media')
            db.finish_job(conn, job_id, 'completed', result={'downloaded': 2}, exit_code=0)
            row = db.get_job(conn, job_id)
            self.assertEqual(row['status'], 'completed')
            self.assertIsNone(db.active_job(conn))
            self.assertEqual(json.loads(row['result']), {'downloaded': 2})

    def test_stale_jobs_are_failed(self):
        with db.connect(self.path) as conn:
            job_id = db.create_job(conn, 'download', {})
            db.update_job(conn, job_id, status='running')
            self.assertEqual(db.mark_stale_jobs(conn), 1)
            row = db.get_job(conn, job_id)
            self.assertEqual(row['status'], 'failed')
            self.assertIn('neu gestartet', row['error'])

    def test_event_and_job_pruning(self):
        with db.connect(self.path) as conn:
            for _ in range(2):
                job_id = db.create_job(conn, 'download', {})
                for index in range(120):
                    db.add_event(conn, job_id, 'log', str(index))
                conn.commit()
            db.prune_events(conn, job_id, keep=100)
            self.assertEqual(len(db.list_events(conn, job_id, limit=500)), 100)
            db.prune_jobs(conn, keep=10)
            self.assertEqual(len(db.list_jobs(conn, 100)), 2)

    def test_creators_are_paged_and_searchable(self):
        with db.connect(self.path) as conn:
            db.upsert_creators(conn, [('alice', 'Alice', 'active'), ('bob', 'Bob', 'active')])
            self.assertEqual(db.count_creators(conn), 2)
            self.assertEqual(db.count_creators(conn, 'ali'), 1)
            self.assertEqual(db.page_creators(conn, page=1, per_page=1)[0]['username'], 'alice')
            self.assertEqual(db.page_creators(conn, query='bob')[0]['display_name'], 'Bob')
            db.clear_creators(conn)
            self.assertEqual(db.count_creators(conn), 0)

    def test_library_stats_reads_existing_manifest(self):
        library = Path(self.tmp.name) / 'library'
        library.mkdir()
        manifest = sqlite3.connect(library / '.ofdl.sqlite3')
        manifest.execute('CREATE TABLE media (identity TEXT PRIMARY KEY, path TEXT, size INTEGER, completed_at TEXT)')
        manifest.executemany('INSERT INTO media VALUES (?,?,?,?)',
                             [('1', 'a.jpg', 100, '2026-01-01'), ('2', 'b.jpg', 200, '2026-01-01')])
        manifest.commit()
        manifest.close()
        stats = db.library_stats(library)
        self.assertTrue(stats['manifest'])
        self.assertEqual(stats['files'], 2)
        self.assertEqual(stats['bytes'], 300)
        self.assertFalse(db.library_stats(library / 'missing')['manifest'])

    def test_public_job_hides_proxy_and_large_lists(self):
        row = {
            'id': 4, 'kind': 'download', 'status': 'running', 'phase': 'Download',
            'payload': json.dumps({'output_dir': '/volume1/x', 'profiles': ['a'] * 500,
                                   'proxy': 'http://user:pass@host:8080', 'all_subscriptions': False}),
            'result': None, 'error': '', 'progress_done': 1, 'progress_total': 2,
            'stats': '{"downloaded":1}', 'pid': 1, 'exit_code': None,
            'pause_requested': 0, 'cancel_requested': 0,
            'created_at': 'now', 'started_at': 'now', 'finished_at': None,
        }
        public = public_job(row)
        self.assertNotIn('proxy', public['request'])
        self.assertEqual(public['request']['creator_count'], 500)
        self.assertEqual(public['stats']['downloaded'], 1)


if __name__ == '__main__':
    unittest.main()
