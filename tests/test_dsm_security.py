from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from ofdl.auth import Credentials, SessionError
from ofdl.dsm.security import (LoginLimiter, SecurityError, SessionStore, hash_password,
                               redact_proxy, sanitize_text, validate_password,
                               verify_password)


def fake_credentials() -> Credentials:
    return Credentials('12345', 'Mozilla/5.0 test', 'x-bc-value', 'sess-value',
                       {'auth_id': '12345', 'sess': 'sess-value'})


class PasswordTests(unittest.TestCase):
    def test_hash_and_verify(self):
        stored = hash_password('correct horse battery')
        self.assertTrue(verify_password('correct horse battery', stored))
        self.assertFalse(verify_password('wrong password', stored))
        self.assertFalse(verify_password('correct horse battery', 'broken'))
        self.assertNotIn('correct horse battery', stored)

    def test_validation(self):
        for value in ('short', 'x' * 257, 'line\nbreak'):
            with self.assertRaises(SecurityError):
                validate_password(value)
        self.assertEqual(validate_password('1234567890'), '1234567890')


class SessionStoreTests(unittest.TestCase):
    def test_roundtrip_and_clear(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SessionStore(tmp)
            store.save(fake_credentials())
            loaded = store.load()
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.user_id, '12345')
            self.assertEqual(store.describe(), {'present': True, 'user_id': '12345'})
            if os.name == 'posix':
                self.assertEqual(Path(tmp, 'session.json').stat().st_mode & 0o777, 0o600)
            self.assertTrue(store.clear())
            self.assertEqual(store.describe(), {'present': False, 'user_id': None})

    def test_corrupt_file_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, 'session.json')
            path.write_text('{"user_id": "not-a-number"}', encoding='utf-8')
            self.assertIsNone(SessionStore(tmp).load())

    def test_duplicate_cookie_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SessionStore(tmp)
            credentials = Credentials('12345', 'ua', 'bc', 'sess', {'sess': 'different'})
            with self.assertRaises(SessionError):
                store.save(credentials)


class TextTests(unittest.TestCase):
    def test_sanitize(self):
        self.assertEqual(sanitize_text('a\x00b\nc', 10), 'a b c')
        self.assertEqual(len(sanitize_text('x' * 500, 20)), 20)

    def test_redact_proxy(self):
        self.assertEqual(redact_proxy('http://user:pass@nas:8080'), 'http://***@nas:8080')
        self.assertEqual(redact_proxy('socks5h://nas:1080'), 'socks5h://nas:1080')
        self.assertEqual(redact_proxy(''), '')
        self.assertEqual(redact_proxy('not a proxy'), '***')


class LimiterTests(unittest.TestCase):
    def test_lock_after_attempts(self):
        limiter = LoginLimiter(attempts=2, window=60, lock_seconds=60)
        key = '192.0.2.1'
        self.assertTrue(limiter.allow(key))
        limiter.failure(key)
        self.assertTrue(limiter.allow(key))
        limiter.failure(key)
        self.assertFalse(limiter.allow(key))
        limiter.success(key)
        self.assertTrue(limiter.allow(key))


if __name__ == '__main__':
    unittest.main()
