from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from ofdl.common import AppError
from ofdl.dsm.config import resolve_paths
from ofdl.dsm.jobs import (normalize_download_options, normalize_preview, normalize_proxy,
                           normalize_schedule, parse_profiles)


class JobValidationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.share = self.root / 'share'
        self.share.mkdir()
        (self.share / 'OnlyFans').mkdir()
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
        self.paths = resolve_paths()

    def tearDown(self):
        for key, value in self.env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()

    def options(self, **overrides):
        base = {
            'output_dir': str(self.share / 'OnlyFans'),
            'profiles': ['alice', 'https://onlyfans.com/bob'],
            'categories': ['posts', 'messages'],
            'types': {'photos': True, 'videos': False, 'audio': False},
            'since_days': 7,
        }
        base.update(overrides)
        return normalize_download_options(base, self.paths)

    def test_valid_options(self):
        options = self.options()
        self.assertEqual(options['profiles'], ['alice', 'bob'])
        self.assertEqual(options['categories'], ['posts', 'messages'])
        self.assertEqual(options['since_days'], 7)
        self.assertFalse(options['types']['videos'])

    def test_all_subscriptions_does_not_require_profiles(self):
        options = self.options(profiles=[], all_subscriptions=True)
        self.assertTrue(options['all_subscriptions'])
        self.assertEqual(options['profiles'], [])

    def test_rejections(self):
        with self.assertRaises(AppError):
            self.options(profiles=[])
        with self.assertRaises(AppError):
            self.options(categories=['unknown'])
        with self.assertRaises(AppError):
            self.options(types={'photos': False, 'videos': False, 'audio': False})
        with self.assertRaises(AppError):
            self.options(since_days=-1)
        with self.assertRaises(AppError):
            normalize_download_options({'output_dir': 'relative/path'}, self.paths)

    def test_output_outside_allowed_roots_is_rejected(self):
        with self.assertRaises(AppError):
            self.options(output_dir=str(self.root / 'elsewhere'))

    def test_preview_path_must_stay_inside_output(self):
        media = self.share / 'OnlyFans' / 'photo.jpg'
        media.write_bytes(b'not an image')
        result = normalize_preview({'output_dir': str(self.share / 'OnlyFans'),
                                    'path': 'photo.jpg', 'kind': 'photo'}, self.paths)
        self.assertEqual(result['path'], 'photo.jpg')
        with self.assertRaises(AppError):
            normalize_preview({'output_dir': str(self.share / 'OnlyFans'),
                               'path': '../outside.jpg', 'kind': 'photo'}, self.paths)
        with self.assertRaises(AppError):
            normalize_preview({'output_dir': str(self.share / 'OnlyFans'),
                               'path': 'missing.jpg', 'kind': 'photo'}, self.paths)

    def test_profile_parsing(self):
        self.assertEqual(parse_profiles('@Alice, bob  https://onlyfans.com/Carol'), ['alice', 'bob', 'carol'])
        with self.assertRaises(AppError):
            parse_profiles('https://example.com/user')
        with self.assertRaises(AppError):
            parse_profiles('../escape')

    def test_proxy_validation(self):
        self.assertEqual(normalize_proxy('http://192.0.2.1:8080'), 'http://192.0.2.1:8080')
        self.assertEqual(normalize_proxy('socks5h://user:pass@nas:1080'), 'socks5h://user:pass@nas:1080')
        self.assertEqual(normalize_proxy(''), '')
        for value in ('ftp://nas:21', 'http://nas:8080/path', 'http://nas:99999', 'http://na s:8080'):
            with self.assertRaises(AppError):
                normalize_proxy(value)

    def test_schedule(self):
        schedule = normalize_schedule({'enabled': True, 'time': '03:30', 'options': {'since_days': 2}})
        self.assertTrue(schedule['enabled'])
        self.assertEqual(schedule['time'], '03:30')
        self.assertEqual(schedule['options']['since_days'], 2)
        with self.assertRaises(AppError):
            normalize_schedule({'enabled': True, 'time': '25:00'})


if __name__ == '__main__':
    unittest.main()
