#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Build Luma84 firmware from pinned sources. This script cannot flash a device."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
LOCK = json.loads((ROOT / 'sources.lock.json').read_text())
WORK = ROOT / 'work'
QMK = WORK / 'qmk'


def run(arguments, *, cwd=ROOT, env=None, capture=False):
    return subprocess.run([str(x) for x in arguments], cwd=cwd, env=env,
                          text=True, capture_output=capture, check=True)


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def toolchain(cache):
    if platform.system() != 'Linux' or platform.machine() != 'x86_64':
        raise SystemExit('The pinned compiler package supports Linux x86_64; use --toolchain on other hosts')
    release = LOCK['arm_gcc']
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / release['name']
    if not archive.exists():
        temporary = archive.with_suffix('.partial')
        print('Downloading the pinned ARM compiler...', flush=True)
        with urllib.request.urlopen(release['url'], timeout=120) as response:
            with temporary.open('wb') as output:
                shutil.copyfileobj(response, output, 1024 * 1024)
        if sha256(temporary) != release['sha256']:
            raise RuntimeError('Compiler download failed its SHA-256 check')
        temporary.rename(archive)
    if sha256(archive) != release['sha256']:
        raise RuntimeError('Cached compiler failed its SHA-256 check')
    with tarfile.open(archive) as source:
        roots = {entry.name.split('/')[0] for entry in source.getmembers()}
        if len(roots) != 1:
            raise RuntimeError('Compiler archive has unexpected roots')
        home = WORK / next(iter(roots))
        if not home.exists():
            source.extractall(WORK, filter='data')
    return home


def checkout():
    if not QMK.exists():
        run(['git', 'init', str(QMK)])
        run(['git', 'remote', 'add', 'origin', LOCK['qmk']['url']], cwd=QMK)
        run(['git', 'fetch', '--depth', '1', 'origin', LOCK['qmk']['commit']], cwd=QMK)
        run(['git', 'checkout', '--detach', 'FETCH_HEAD'], cwd=QMK)
    head = run(['git', 'rev-parse', 'HEAD'], cwd=QMK, capture=True).stdout.strip()
    if head != LOCK['qmk']['commit']:
        raise RuntimeError('work/qmk is at another commit; preserve it and choose a fresh work directory')
    paths = list(LOCK['submodules'])
    run(['git', 'submodule', 'update', '--init', '--depth', '1', *paths], cwd=QMK)
    for name, expected in LOCK['submodules'].items():
        actual = run(['git', 'rev-parse', 'HEAD'], cwd=QMK / name, capture=True).stdout.strip()
        if actual != expected:
            raise RuntimeError('Unexpected submodule commit: ' + name)
    for source, destination in [
        (ROOT / 'keyboard', QMK / 'keyboards/epomaker/hc844'),
        (ROOT / 'wireless', QMK / 'keyboards/linker/wireless'),
    ]:
        if destination.exists():
            extra = [p.relative_to(destination) for p in destination.rglob('*')
                     if p.is_file() and not (source / p.relative_to(destination)).exists()]
            if extra:
                raise RuntimeError('Generated source directory has extra files: ' + str(extra))
        shutil.copytree(source, destination, dirs_exist_ok=True)
    patch = ROOT / 'patches/qmk-rgblight-overrides.patch'
    applicable = subprocess.run(['git', 'apply', '--check', str(patch)], cwd=QMK,
                                capture_output=True).returncode == 0
    if applicable:
        run(['git', 'apply', str(patch)], cwd=QMK)
    elif subprocess.run(['git', 'apply', '--reverse', '--check', str(patch)],
                        cwd=QMK, capture_output=True).returncode != 0:
        raise RuntimeError('QMK patch neither applies nor matches the already-applied patch')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--toolchain', type=Path, help='Existing ARM GCC 13.2.1 directory')
    parser.add_argument('--cache-dir', type=Path,
                        default=Path(os.environ.get('XDG_CACHE_HOME', Path.home() / '.cache')) / 'luma84-firmware')
    args = parser.parse_args()
    for executable in ['git', 'make', 'uv']:
        if not shutil.which(executable):
            parser.error(f'{executable} is required; see README.md')
    WORK.mkdir(exist_ok=True)
    compiler_home = args.toolchain.resolve() if args.toolchain else toolchain(args.cache_dir)
    compiler_version = run([compiler_home / 'bin/arm-none-eabi-gcc', '-dumpfullversion'], capture=True).stdout.strip()
    if compiler_version != '13.2.1':
        raise RuntimeError('Expected ARM GCC 13.2.1, got ' + compiler_version)
    checkout()
    python_home = WORK / 'venv'
    if not python_home.exists():
        run(['uv', 'venv', '--python', LOCK['python'], str(python_home)])
    run(['uv', 'pip', 'sync', '--python', str(python_home / 'bin/python'), str(ROOT / 'requirements.lock')])
    environment = os.environ.copy()
    environment['PATH'] = os.pathsep.join([str(python_home / 'bin'), str(compiler_home / 'bin'), environment['PATH']])
    environment['QMK_HOME'] = str(QMK)
    environment['SKIP_GIT'] = 'yes'
    target = 'epomaker/hc844:via'
    run(['make', target, '-j2'], cwd=QMK, env=environment)
    destination = ROOT / 'dist'
    destination.mkdir(exist_ok=True)
    artifacts = {}
    for suffix in ['bin', 'hex', 'elf']:
        name = 'epomaker_hc844_via.' + suffix
        result = destination / name
        shutil.copy2(QMK / '.build' / name, result)
        artifacts[name] = {'bytes': result.stat().st_size, 'sha256': sha256(result)}
    sources = {str(p.relative_to(ROOT)): sha256(p)
               for folder in ['keyboard', 'wireless', 'patches', 'tools']
               for p in (ROOT / folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    report = {'target': target, 'qmk_commit': LOCK['qmk']['commit'],
              'vendor_commit': LOCK['vendor']['commit'],
              'compiler_version': compiler_version, 'artifacts': artifacts,
              'source_sha256': sources,
              'hardware_tested': False, 'flashed': False,
              'note': 'Compiled from the vendor source with documented QMK compatibility changes; not a byte-for-byte factory reproduction.'}
    (destination / 'build.json').write_text(json.dumps(report, indent=2) + '\n')
    print('Compiled firmware and source hashes are in dist/. No device was opened.', flush=True)


if __name__ == '__main__':
    main()
