#!/usr/bin/env python3
"""Optional local browser regression test; requires Playwright + Chromium.

Run: python tools/test_web_ui.py. No real account or NAS is contacted.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> None:
    from playwright.sync_api import expect, sync_playwright
    from ofdl.dsm.config import resolve_paths
    from ofdl.dsm.service import create_server

    with tempfile.TemporaryDirectory(prefix='ofdl-web-') as temp:
        root = Path(temp)
        share = root / 'user-approved-share'
        share.mkdir()
        library = share / 'library'
        library.mkdir()
        with sqlite3.connect(library / '.ofdl.sqlite3') as db:
            db.execute('CREATE TABLE media(size INTEGER)')
            db.execute('INSERT INTO media VALUES (1234)')
        db.close()
        env = {key: str(root / value) for key, value in {
            'OFDL_DATA_DIR': 'data', 'OFDL_LOG_DIR': 'logs',
            'OFDL_CONFIG_DIR': 'config', 'OFDL_TMP_DIR': 'tmp',
            'OFDL_HOME': 'home', 'OFDL_PREVIEW_DIR': 'previews',
            'SYNOPKG_PKGVAR': 'private',
        }.items()}
        env['OFDL_SHARE_ROOT'] = str(share)
        with patch.dict(os.environ, env):
            server, app = create_server(resolve_paths(), '127.0.0.1', 0, start_scheduler=False)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            errors = []
            try:
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(headless=True)
                    page = browser.new_page(viewport={'width': 1440, 'height': 1100}, locale='en-US')
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    page.on('console', lambda message: errors.append(message.text) if message.type == 'error' else None)
                    page.goto(f'http://127.0.0.1:{server.server_address[1]}/')
                    for language, title in [('fr', 'Première configuration'), ('es', 'Configuración inicial'),
                                            ('en', 'First-time setup')]:
                        page.select_option('#language-select', language)
                        expect(page.locator('#auth-title')).to_have_text(title)
                    page.fill('#password', 'local-test-password')
                    page.fill('#confirm', 'local-test-password')
                    page.click('#auth-submit')
                    expect(page.locator('#tab-settings')).to_be_visible()
                    expect(page.locator('#storage-setup')).to_be_visible()
                    assert sorted(item.name for item in share.iterdir()) == ['library']
                    page.fill('#library-dir', str(library))
                    page.click('#save-library')
                    expect(page.locator('#output-dir')).to_have_value(str(library))
                    page.click('[data-tab="library"]')
                    expect(page.locator('#library-output')).to_have_text(str(library))
                    expect(page.locator('#library-files')).to_have_text('1')
                    # A different manifest must replace the cached count immediately.
                    second = share / 'second-library'
                    second.mkdir()
                    page.click('[data-tab="settings"]')
                    page.fill('#library-dir', str(second))
                    page.click('#save-library')
                    expect(page.locator('#output-dir')).to_have_value(str(second))
                    page.click('[data-tab="library"]')
                    expect(page.locator('#library-output')).to_have_text(str(second))
                    expect(page.locator('#library-files')).to_have_text('–')
                    for language, library_text in [('de', 'Bibliothek'), ('fr', 'Bibliothèque'),
                                                    ('es', 'Biblioteca'), ('en', 'Library'), ('de', 'Bibliothek')]:
                        page.select_option('#language-select', language)
                        expect(page.locator('[data-tab="library"]')).to_have_text(library_text)
                        expect(page.locator('#library-output')).to_have_text(str(second))
                        for tab in ('dashboard', 'downloads', 'session', 'library', 'settings'):
                            page.click(f'[data-tab="{tab}"]')
                            expect(page.locator(f'#tab-{tab}')).to_be_visible()
                    page.click('#browse-library')
                    expect(page.locator('#folder-modal')).to_be_visible()
                    page.fill('#new-folder-name', 'explicit-subfolder')
                    page.once('dialog', lambda dialog: dialog.dismiss())
                    page.click('#create-folder')
                    assert not (second / 'explicit-subfolder').exists()
                    page.once('dialog', lambda dialog: dialog.accept())
                    page.click('#create-folder')
                    expect(page.locator('#folder-path')).to_have_text(str(second / 'explicit-subfolder'))
                    page.click('#folder-close')
                    page.click('[data-tab="session"]')
                    capture = root / 'session-import.json'
                    capture.write_text(json.dumps({
                        'user_id': '12345', 'user_agent': 'Mozilla/5.0 synthetic-test',
                        'x_bc': 'test-value', 'sess_cookie': 'fake-session',
                    }), encoding='utf-8')
                    page.set_input_files('#session-file', str(capture))
                    expect(page.locator('#session-text')).to_have_value(capture.read_text(encoding='utf-8'))
                    assert not app.paths.session_file.exists(), 'file selection must not submit credentials'
                    page.click('#import-session')
                    expect(page.locator('#session-user')).to_have_text('12345')
                    expect(page.locator('#session-text')).to_have_value('')
                    page.reload()
                    page.click('[data-tab="downloads"]')
                    expect(page.locator('#output-dir')).to_have_value(str(second))
                    page.click('#logout-button')
                    expect(page.locator('#auth-submit')).to_be_visible()
                    for language, label in [('fr', 'Connexion'), ('es', 'Iniciar sesión'), ('de', 'Anmelden')]:
                        page.select_option('#language-select', language)
                        expect(page.locator('#auth-submit')).to_have_text(label)
                    browser.close()
                assert not errors, errors
                print('PASS: setup/login DE/EN/FR/ES, explicit storage, shared manifest path, '
                      'cache invalidation, folder consent, file import, persistence; no browser errors.')
            finally:
                server.shutdown()
                server.server_close()
                app.close()
                thread.join(timeout=5)


if __name__ == '__main__':
    main()
