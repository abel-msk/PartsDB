"""Offline wheel installation into a private, disposable Python environment."""
from dataclasses import dataclass
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tempfile
import zipfile

from ElPartsPluginApi.importers import PluginError
from ElPartsPluginApi.importers.manifest import PluginManifest
from .runner import PluginRunner


@dataclass(frozen=True)
class InstalledPlugin:
    manifest: PluginManifest
    path: Path
    enabled: bool = True

    @property
    def python(self):
        return self.path / 'venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')


def inspect_wheel(filename):
    path = Path(filename).resolve()
    if path.suffix != '.whl':
        raise PluginError('Choose a Python wheel (.whl)')
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)):
                raise PluginError('Wheel contains duplicate files')
            for name in names:
                parts = PurePosixPath(name)
                if parts.is_absolute() or '..' in parts.parts or '\\' in name:
                    raise PluginError('Invalid wheel path')
            manifests = [n for n in names if PurePosixPath(n).name == 'partsdb-plugin.json']
            if len(manifests) != 1:
                raise PluginError('Wheel must contain exactly one partsdb-plugin.json')
            if archive.getinfo(manifests[0]).file_size > 65536:
                raise PluginError('Plugin manifest is too large')
            return PluginManifest.from_dict(json.loads(archive.read(manifests[0])))
    except (OSError, zipfile.BadZipFile, ValueError, UnicodeError) as exc:
        raise PluginError(f'Cannot read plugin wheel: {exc}') from exc


def python_executable(configured=None):
    if configured:
        return str(Path(configured).expanduser())
    if not getattr(sys, 'frozen', False):
        return sys.executable
    executable = shutil.which('python3')
    if not executable:
        raise PluginError('Python 3.9+ is required to create plugin environments; install Python or configure plugins.python')
    return executable


class PluginInstaller:
    def __init__(self, root, python=None):
        self.root = Path(root)
        self.python = python_executable(python)

    def prepare(self, wheel):
        manifest = inspect_wheel(wheel)
        installs = self.root / '.installs'
        installs.mkdir(parents=True, exist_ok=True)
        path = Path(tempfile.mkdtemp(prefix=manifest.id + '-', dir=installs))
        try:
            self._command([self.python, '-m', 'venv', str(path / 'venv')], path)
            plugin = InstalledPlugin(manifest, path)
            self._command([str(plugin.python), '-m', 'pip', 'install', '--disable-pip-version-check',
                           '--no-index', '--no-cache-dir', '--only-binary=:all:', '--find-links', str(Path(wheel).resolve().parent),
                           str(Path(wheel).resolve())], path)
            runtime = path / 'runtime'
            runtime.mkdir()
            source = Path(__file__).resolve().parent
            sdk = source.parent / 'ElPartsPluginApi'
            shutil.copytree(sdk, runtime / 'ElPartsPluginApi', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
            (runtime / 'ElPluginMgr').mkdir()
            for name in ('__init__.py', 'protocol.py'):
                shutil.copyfile(source / name, runtime / 'ElPluginMgr' / name)
            shutil.copyfile(source / 'worker.py', runtime / 'worker.py')
            PluginRunner().run(plugin, action='inspect')
            return plugin
        except Exception:
            shutil.rmtree(path, ignore_errors=True)
            raise

    @staticmethod
    def _command(command, path):
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=180)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise PluginError(f'Cannot prepare plugin environment: {exc}') from exc
        if result.returncode:
            raise PluginError('Cannot prepare plugin environment:\n' + (result.stderr or result.stdout)[-6000:])

    def discard(self, plugin):
        path = plugin.path.resolve()
        if path.parent != (self.root / '.installs').resolve():
            raise PluginError('Refusing to remove a directory outside plugin storage')
        shutil.rmtree(path)
