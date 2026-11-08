from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
WHEELHOUSE = ROOT / 'wheelhouse'


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


@unittest.skipUnless(WHEELHOUSE.is_dir() and any(WHEELHOUSE.glob('*.whl')),
                     'wheelhouse not prepared; run tools/fetch_wheels.py')
class PackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tools import build_spk
        cls.build_spk = build_spk
        cls.tmp = tempfile.TemporaryDirectory()
        cls.first = build_spk.build(Path(cls.tmp.name) / 'one', WHEELHOUSE, build_spk.DEFAULT_EPOCH)
        cls.second = build_spk.build(Path(cls.tmp.name) / 'two', WHEELHOUSE, build_spk.DEFAULT_EPOCH)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_build_is_byte_reproducible(self):
        self.assertEqual(sha256(self.first), sha256(self.second))

    def test_info_contract(self):
        with tarfile.open(self.first) as archive:
            info = archive.extractfile('INFO').read().decode('utf-8')
            package = archive.extractfile('package.tgz').read()
        values = {}
        for line in info.splitlines():
            key, _, value = line.partition('=')
            values[key] = value.strip('"')
        self.assertEqual(values['package'], 'OnlyFansDL')
        self.assertEqual(values['version'], '2.8.0-8')
        self.assertEqual(values['arch'], 'r1000')
        self.assertEqual(values['os_min_ver'], '7.2-64570')
        self.assertEqual(values['adminport'], '8765')
        self.assertEqual(values['adminurl'], '/')
        self.assertIn('python313', values['install_dep_packages'])
        self.assertEqual(values['checksum'], hashlib.md5(package).hexdigest())

    def test_package_contents_and_modes(self):
        with tarfile.open(self.first) as archive:
            names = archive.getnames()
            for required in ('scripts/postinst', 'scripts/postupgrade',
                             'scripts/start-stop-status', 'conf/privilege',
                             'conf/resource', 'WIZARD_UIFILES/install_uifile',
                             'PACKAGE_ICON.PNG', 'PACKAGE_ICON_256.PNG', 'LICENSE'):
                self.assertIn(required, names)
            for script in ('scripts/postinst', 'scripts/postupgrade', 'scripts/start-stop-status'):
                self.assertEqual(archive.getmember(script).mode & 0o777, 0o755)
            postinst = archive.extractfile('scripts/postinst').read().decode('utf-8')
            self.assertNotIn('@ACTION@', postinst)
            self.assertIn('ACTION="install"', postinst)
            postupgrade = archive.extractfile('scripts/postupgrade').read().decode('utf-8')
            self.assertIn('ACTION="upgrade"', postupgrade)
            package_data = archive.extractfile('package.tgz').read()
        import io
        with tarfile.open(fileobj=io.BytesIO(package_data), mode='r:gz') as pkg:
            pkg_names = pkg.getnames()
            self.assertIn('ofdl/dsm/service.py', pkg_names)
            self.assertIn('ofdl/dsm/worker.py', pkg_names)
            self.assertIn('web/index.html', pkg_names)
            self.assertIn('web/static/app.js', pkg_names)
            self.assertIn('ui/config', pkg_names)
            self.assertIn('onlyfans-dl.py', pkg_names)
            self.assertIn('requirements-dsm.lock', pkg_names)
            self.assertFalse(any('__pycache__' in name or name.endswith('.pyc') for name in pkg_names))
            self.assertFalse(any('session.json' in name or 'control.sqlite3' in name for name in pkg_names))
            self.assertEqual(sum(name.startswith('wheelhouse/') and name.endswith('.whl')
                                 for name in pkg_names), 11)

    def test_json_metadata(self):
        with tarfile.open(self.first) as archive:
            privilege = json.loads(archive.extractfile('conf/privilege').read().decode('utf-8'))
            resource = json.loads(archive.extractfile('conf/resource').read().decode('utf-8'))
            wizard = json.loads(archive.extractfile('WIZARD_UIFILES/install_uifile').read().decode('utf-8'))
            wizard_ger = json.loads(archive.extractfile('WIZARD_UIFILES/install_uifile_ger').read().decode('utf-8'))
            upgrade = json.loads(archive.extractfile('WIZARD_UIFILES/upgrade_uifile').read().decode('utf-8'))
            upgrade_ger = json.loads(archive.extractfile('WIZARD_UIFILES/upgrade_uifile_ger').read().decode('utf-8'))
            package_data = archive.extractfile('package.tgz').read()
        import io
        with tarfile.open(fileobj=io.BytesIO(package_data), mode='r:gz') as pkg:
            ui_data = pkg.extractfile('ui/config').read().decode('utf-8')
        self.assertEqual(privilege['defaults']['run-as'], 'package')
        self.assertEqual(privilege['username'], 'sc-onlyfansdl')
        self.assertEqual(privilege['groupname'], 'synocommunity')
        self.assertNotIn('join-groupname', privilege)
        self.assertNotIn('ctrl-script', privilege)
        self.assertNotIn('data-share', resource, 'installation must not create or grant shares')
        postinst = (ROOT / 'spk/scripts/install.sh').read_text(encoding='utf-8')
        self.assertNotIn('OFDL_SHARE_ROOT=', postinst)
        self.assertNotIn('--share-root', postinst)
        for document in (wizard, wizard_ger):
            keys = [item.get('subitems', [{}])[0].get('key') for item in document[0]['items']
                    if item.get('type') == 'password']
            self.assertIn('wizard_app_password', keys)
            self.assertIn('wizard_app_password_confirm', keys)
        for document in (upgrade, upgrade_ger):
            # The upgrade wizard must not ask for a password that --if-missing
            # would silently ignore, leaving the first-install hash active.
            self.assertFalse(any(item.get('type') == 'password' for item in document[0]['items']))
        config = json.loads(ui_data)
        app = config['.url']['com.noa3.onlyfansdl']
        self.assertEqual(app['port'], '8765')
        self.assertEqual(app['url'], '/')

    def test_shell_scripts_parse(self):
        candidates = [Path(r'C:\Program Files\Git\bin\bash.exe'),
                      Path(r'C:\Program Files\Git\usr\bin\sh.exe'),
                      shutil.which('bash'), shutil.which('sh')]
        shell = next((str(item) for item in candidates if item and Path(item).is_file()), None)
        if not shell:
            self.skipTest('no POSIX shell available')
        with tarfile.open(self.first) as archive:
            for member in archive.getmembers():
                if member.name.startswith('scripts/') and member.isfile():
                    text = archive.extractfile(member).read().decode('utf-8')
                    completed = subprocess.run([shell, '-n'], input=text,
                                               capture_output=True, text=True)
                    self.assertEqual(completed.returncode, 0,
                                     f'{member.name}: {completed.stderr}')


if __name__ == '__main__':
    unittest.main()
