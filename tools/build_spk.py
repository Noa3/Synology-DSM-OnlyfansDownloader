#!/usr/bin/env python3
"""Build a reproducible native Synology DSM 7.2 SPK.

No Synology toolchain is required: the package is pure Python, and all binary
wheels target the DS723+ (r1000) / CPython 3.13 / manylinux2014.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import shutil
import sys
import tarfile
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = 'OnlyFansDL'
VERSION = '2.8.0-5'
ARCH = 'r1000'
DSM_MIN = '7.2-64570'
PORT = '8765'
DEFAULT_EPOCH = int(datetime(2026, 11, 7, tzinfo=timezone.utc).timestamp())
APP_FILES = ['onlyfans-dl.py', 'requirements.txt', 'LICENSE.txt', 'THIRD_PARTY_NOTICES.md']
PACKAGE_DIRS = ['ofdl', 'web', 'wheelhouse']
SCRIPT_FILES = ['preinst', 'preuninst', 'postuninst', 'preupgrade', 'start-stop-status']
EXECUTABLES = {'onlyfans-dl.py', 'start-stop-status', 'preinst', 'postinst',
               'preuninst', 'postuninst', 'preupgrade', 'postupgrade'}
TEXT_SUFFIXES = {'.py', '.sh', '.js', '.css', '.html', '.svg', '.json', '.md',
                 '.txt', '.lock', '.in', '.webmanifest', '.cfg', '.ini'}
TEXT_NAMES = {'VERSION', 'LICENSE', 'LICENSE.txt', 'onlyfans-dl.py', 'config',
              'privilege', 'resource', 'start-stop-status', 'preinst', 'postinst',
              'preuninst', 'postuninst', 'preupgrade', 'postupgrade'}


def is_text_file(path: Path) -> bool:
    return path.suffix.lower() in TEXT_SUFFIXES or path.name in TEXT_NAMES or path.name.startswith('install_uifile')


class BuildError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def md5(path: Path) -> str:
    digest = hashlib.md5()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def read_lock(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or ' --hash=sha256:' not in line:
            continue
        requirement, digest = line.split(' --hash=sha256:', 1)
        name = requirement.split('==', 1)[0].replace('_', '-').lower()
        result[name] = digest
    return result


def verify_wheelhouse(wheelhouse: Path, lock: dict[str, str]) -> None:
    wheels = sorted(wheelhouse.glob('*.whl'))
    if not wheels:
        raise BuildError('wheelhouse is empty; run tools/fetch_wheels.py first')
    actual: dict[str, str] = {}
    for wheel in wheels:
        name = wheel.name.split('-', 1)[0].replace('_', '-').lower()
        actual[name] = sha256(wheel)
    missing = sorted(set(lock) - set(actual))
    if missing:
        raise BuildError('missing wheels for lock entries: ' + ', '.join(missing))
    for name, digest in lock.items():
        if actual[name] != digest:
            raise BuildError(f'hash mismatch for {name}; run tools/fetch_wheels.py')


def add_file(tar: tarfile.TarFile, source: Path, arcname: str, *, epoch: int,
             mode: int | None = None) -> None:
    info = tar.gettarinfo(str(source), arcname)
    info.uid = 0
    info.gid = 0
    info.uname = 'root'
    info.gname = 'root'
    info.mtime = epoch
    if mode is not None:
        info.mode = mode
    elif source.name in EXECUTABLES or source.suffix == '.sh':
        info.mode = 0o755
    else:
        info.mode = 0o644
    if is_text_file(source):
        # Normalize line endings so a Windows checkout with CRLF still builds
        # a DSM-safe package (shell shebangs and JSON stay LF-only).
        data = source.read_bytes().replace(b'\r\n', b'\n').replace(b'\r', b'\n')
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    else:
        with source.open('rb') as stream:
            tar.addfile(info, stream)


def add_dir(tar: tarfile.TarFile, arcname: str, epoch: int, mode: int = 0o755) -> None:
    info = tarfile.TarInfo(arcname.rstrip('/') + '/')
    info.type = tarfile.DIRTYPE
    info.uid = 0
    info.gid = 0
    info.uname = 'root'
    info.gname = 'root'
    info.mtime = epoch
    info.mode = mode
    tar.addfile(info)


def add_tree(tar: tarfile.TarFile, source: Path, arcroot: str, epoch: int,
             *, exclude: set[str] | None = None) -> None:
    exclude = exclude or set()
    files = []
    for path in source.rglob('*'):
        if path.is_dir():
            continue
        if '__pycache__' in path.parts or path.suffix in {'.pyc', '.pyo'}:
            continue
        if path.name in exclude:
            continue
        files.append(path)
    files.sort(key=lambda item: item.relative_to(source).as_posix())
    added_dirs: set[str] = {arcroot}
    for path in files:
        relative = path.relative_to(source)
        parent = Path(arcroot) / relative.parent
        for part in [parent] + list(parent.parents):
            text = part.as_posix()
            if text in {'.', arcroot} or text in added_dirs:
                continue
            if text.startswith(arcroot + '/'):
                add_dir(tar, text, epoch)
                added_dirs.add(text)
        add_file(tar, path, (Path(arcroot) / relative).as_posix(), epoch=epoch)
    if not files:
        add_dir(tar, arcroot, epoch)


def make_package_tgz(staging: Path, output: Path, epoch: int) -> None:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w', format=tarfile.GNU_FORMAT) as tar:
        for child in sorted(staging.iterdir(), key=lambda item: item.name):
            if child.is_dir():
                add_tree(tar, child, child.name, epoch)
            else:
                add_file(tar, child, child.name, epoch=epoch)
    raw = buffer.getvalue()
    with output.open('wb') as stream:
        import gzip
        with gzip.GzipFile(filename='', mode='wb', fileobj=stream, mtime=epoch,
                           compresslevel=9) as gz:
            gz.write(raw)


def info_text(checksum: str) -> str:
    description = ('Native OnlyFans downloader for Synology DSM. Uses a private '
                   'Python 3.13 environment and keeps downloads, the existing '
                   'folder layout and the SQLite manifest.')
    description_ger = ('Nativer OnlyFans-Downloader fuer Synology DSM. Nutzt eine '
                       'private Python-3.13-Umgebung und behaelt Downloads, '
                       'Ordnerstruktur und SQLite-Manifest bei.')
    values = [
        ('package', PACKAGE),
        ('version', VERSION),
        ('description', description),
        ('description_ger', description_ger),
        ('displayname', 'OnlyFans DL'),
        ('arch', ARCH),
        ('os_min_ver', DSM_MIN),
        ('maintainer', 'Noa3'),
        ('maintainer_url', 'https://github.com/Noa3'),
        ('distributor', 'Noa3'),
        ('distributor_url', 'https://github.com/Noa3/Synology-DSM-OnlyfansDownloader'),
        ('support_url', 'https://github.com/Noa3/Synology-DSM-OnlyfansDownloader/issues'),
        ('helpurl', 'https://github.com/Noa3/Synology-DSM-OnlyfansDownloader'),
        ('thirdparty', 'yes'),
        ('adminprotocol', 'http'),
        ('adminport', PORT),
        ('adminurl', '/'),
        ('dsmuidir', 'ui'),
        ('dsmappname', 'com.noa3.onlyfansdl'),
        ('silent_install', 'no'),
        ('silent_upgrade', 'yes'),
        ('reloadui', 'yes'),
        ('install_dep_packages', 'python313>=3.13.11-9'),
        ('changelog', '2.8.0-5: Reload-safe job status, separate scan/file progress, '
                      'automatic DSM/browser language with seven UI languages, opt-in free-page '
                      'renewals and website-only trial review. No automatic shared folders.'),
        ('checksum', checksum),
    ]
    lines = [f'{key}="{value}"' for key, value in values]
    return '\n'.join(lines) + '\n'


def make_spk(output: Path, package_tgz: Path, scripts: Path, conf: Path,
             wizard: Path, icons: Path, license_file: Path,
             epoch: int) -> None:
    checksum = md5(package_tgz)
    with tarfile.open(output, 'w', format=tarfile.GNU_FORMAT) as tar:
        info = info_text(checksum).encode('utf-8')
        info_tar = tarfile.TarInfo('INFO')
        info_tar.size = len(info)
        info_tar.mode = 0o644
        info_tar.uid = info_tar.gid = 0
        info_tar.uname = info_tar.gname = 'root'
        info_tar.mtime = epoch
        tar.addfile(info_tar, io.BytesIO(info))

        add_file(tar, package_tgz, 'package.tgz', epoch=epoch)
        for folder, arcroot in ((scripts, 'scripts'), (conf, 'conf'),
                                (wizard, 'WIZARD_UIFILES')):
            add_tree(tar, folder, arcroot, epoch)
        for icon_name in ('PACKAGE_ICON.PNG', 'PACKAGE_ICON_256.PNG'):
            add_file(tar, icons / icon_name, icon_name, epoch=epoch)
        add_file(tar, license_file, 'LICENSE', epoch=epoch)


def build(dist: Path, wheelhouse: Path, epoch: int) -> Path:
    lock_path = ROOT / 'requirements-dsm.lock'
    if not lock_path.is_file():
        raise BuildError('requirements-dsm.lock is missing; run tools/fetch_wheels.py')
    lock = read_lock(lock_path)
    verify_wheelhouse(wheelhouse, lock)
    for required in APP_FILES:
        if not (ROOT / required).is_file():
            raise BuildError(f'missing {required}')

    work = ROOT / 'build'
    if work.exists():
        shutil.rmtree(work)
    staging = work / 'package'
    staging.mkdir(parents=True)
    for folder in ('ofdl', 'web'):
        add_source = ROOT / folder
        if not add_source.is_dir():
            raise BuildError(f'missing {folder}/')
        shutil.copytree(add_source, staging / folder,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.pyo'))
    for name in APP_FILES:
        shutil.copy2(ROOT / name, staging / name)
    shutil.copytree(wheelhouse, staging / 'wheelhouse',
                    ignore=shutil.ignore_patterns('*.lock', 'SHA256SUMS'))
    for wheel in (staging / 'wheelhouse').glob('*.whl'):
        if wheel.name.lower().split('-', 1)[0] not in {name.replace('-', '_') for name in lock}:
            # Keep only locked wheels; pip's resolver would otherwise see extra files.
            wheel.unlink()
    shutil.copy2(lock_path, staging / 'requirements-dsm.lock')
    shutil.copytree(ROOT / 'spk' / 'ui', staging / 'ui')
    (staging / 'VERSION').write_text(
        f'{PACKAGE} {VERSION}\nPython 3.13 / manylinux2014 x86_64\nBuilt {epoch}\n',
        encoding='utf-8')

    package_tgz = work / 'package.tgz'
    make_package_tgz(staging, package_tgz, epoch)

    scripts = work / 'scripts'
    scripts.mkdir()
    for name in SCRIPT_FILES:
        shutil.copy2(ROOT / 'spk' / 'scripts' / name, scripts / name)
        os.chmod(scripts / name, 0o755)
    install_template = (ROOT / 'spk' / 'scripts' / 'install.sh').read_text(encoding='utf-8')
    for name, action in (('postinst', 'install'), ('postupgrade', 'upgrade')):
        target = scripts / name
        target.write_text(install_template.replace('@ACTION@', action), encoding='utf-8')
        os.chmod(target, 0o755)

    dist.mkdir(parents=True, exist_ok=True)
    output = dist / f'{PACKAGE}-{ARCH}-dsm72_{VERSION}.spk'
    make_spk(output, package_tgz, scripts, ROOT / 'spk' / 'conf',
             ROOT / 'spk' / 'WIZARD_UIFILES',
             ROOT / 'spk', ROOT / 'LICENSE.txt', epoch)
    digest = sha256(output)
    (output.with_suffix('.spk.sha256')).write_text(f'{digest}  {output.name}\n', encoding='ascii')
    print(f'Built {output}')
    print(f'Size  {output.stat().st_size / (1024 * 1024):.2f} MiB')
    print(f'SHA256 {digest}')
    print(f'MD5(package.tgz) {md5(package_tgz)}')
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--dist', type=Path, default=ROOT / 'dist')
    parser.add_argument('--wheelhouse', type=Path, default=ROOT / 'wheelhouse')
    parser.add_argument('--source-date-epoch', type=int,
                        default=int(os.environ.get('SOURCE_DATE_EPOCH', DEFAULT_EPOCH)))
    args = parser.parse_args(argv)
    try:
        build(args.dist, args.wheelhouse, args.source_date_epoch)
    except BuildError as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
