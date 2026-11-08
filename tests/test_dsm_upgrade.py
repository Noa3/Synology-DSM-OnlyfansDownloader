from __future__ import annotations

import os
import unittest
from dataclasses import replace
from unittest.mock import patch

from ofdl.dsm import db
from ofdl.dsm import preserve
from ofdl.dsm.bootstrap import main as bootstrap_main
from ofdl.dsm.config import resolve_paths
from ofdl.dsm.security import SessionStore, set_password
from tests.test_dsm_service import Harness


class UpgradePreservationTests(unittest.TestCase):
    def setUp(self):
        self.h = Harness()
        self.h.setup('upgrade-password-123')
        self.assertNotEqual(self.h.call('POST', '/api/settings', {
            'output_dir': str(self.h.output),
            'schedule': {'enabled': True, 'time': '03:30', 'options': {'since_days': 3}},
            'proxy': 'http://192.0.2.10:8080',
        })[0], 400)
        self.assertEqual(self.h.import_fake_session()[0], 200)
        with db.connect(self.h.paths.db) as conn:
            db.set_json(conn, 'free_renewal', {'enabled': True, 'profiles': ['freebie'],
                                               'time': '04:00', 'account_id': '12345'})
        # Keep snapshots inside the test sandbox instead of the repository var/.
        private = self.h.root / 'private'
        private.mkdir(exist_ok=True)
        self.paths = replace(self.h.paths, pkgvar=private)
        self.snapshot = preserve.snapshot(self.paths, 'test-upgrade')
        self.assertIsNotNone(self.snapshot)

    def tearDown(self):
        self.h.close()

    def _state(self):
        with db.connect(self.h.paths.db) as conn:
            return {
                'output_dir': db.get_setting(conn, 'output_dir'),
                'password': db.get_setting(conn, 'password_hash'),
                'library_confirmed': db.get_setting(conn, 'library_confirmed'),
                'proxy': db.get_setting(conn, 'proxy'),
                'schedule': db.get_json(conn, 'schedule', {}),
                'free_renewal': db.get_json(conn, 'free_renewal', {}),
            }

    def test_snapshot_contains_private_state_and_survives_missing_files(self):
        self.assertTrue((self.snapshot / 'control.sqlite3').is_file())
        self.assertTrue((self.snapshot / 'session.json').is_file())
        before = self._state()
        self.assertEqual(before['output_dir'], str(self.h.output.resolve()))
        self.assertTrue(before['password'])
        self.assertTrue(before['library_confirmed'] == '1')
        # Simulate a failed/partial upgrade that lost the private files.
        (self.h.paths.data / 'control.sqlite3').unlink()
        (self.h.paths.data / 'session.json').unlink()
        result = preserve.restore_if_needed(self.paths)
        self.assertIn('control.sqlite3', result['restored'])
        self.assertIn('session.json', result['restored'])
        self.assertEqual(result['errors'], [])
        self.assertEqual(self._state(), before)
        self.assertTrue((self.h.paths.data / 'session.json').is_file())
        if os.name == 'posix':
            self.assertEqual((self.h.paths.data / 'session.json').stat().st_mode & 0o777, 0o600)

    def test_existing_valid_data_is_not_overwritten(self):
        before = self._state()
        replacement = self.h.share / 'replacement'
        replacement.mkdir()
        self.h.call('POST', '/api/settings', {'output_dir': str(replacement)})
        changed = self._state()
        self.assertNotEqual(changed['output_dir'], before['output_dir'])
        result = preserve.restore_if_needed(self.paths)
        self.assertIn('control.sqlite3', result['kept'])
        self.assertEqual(self._state()['output_dir'], str(replacement.resolve()))

    def test_corrupt_database_is_replaced_from_snapshot(self):
        before = self._state()
        with open(self.h.paths.db, 'wb') as stream:
            stream.write(b'not a sqlite database')
        result = preserve.restore_if_needed(self.paths)
        self.assertIn('control.sqlite3', result['restored'])
        self.assertEqual(self._state(), before)

    def test_bootstrap_rerun_keeps_path_password_and_settings(self):
        before = self._state()
        with patch.dict(os.environ, {
            'OFDL_DATA_DIR': str(self.h.paths.data),
            'OFDL_SHARE_ROOT': str(self.h.share),
        }):
            self.assertEqual(bootstrap_main(['--data-dir', str(self.h.paths.data)]), 0)
        self.assertEqual(self._state(), before)

    def test_snapshot_pruning_keeps_a_bounded_number(self):
        for index in range(7):
            target = self.paths.pkgvar / 'backups' / f'2026010{index}-000000-old'
            target.mkdir(parents=True)
        preserve.snapshot(self.paths, 'prune-test')
        backups = [item for item in (self.paths.pkgvar / 'backups').iterdir() if item.is_dir()]
        self.assertLessEqual(len(backups), preserve.KEEP_SNAPSHOTS)


if __name__ == '__main__':
    unittest.main()
