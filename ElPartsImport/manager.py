"""Declarative registry and validated, reversible plugin lifecycle changes."""
from contextlib import nullcontext
import json
from pathlib import Path
import tempfile
import os

from ElPartsPluginApi.importers import PluginError
from ElPartsPluginApi.importers.manifest import PluginManifest
from .installer import InstalledPlugin, PluginInstaller, inspect_wheel
from .protocol import json_text


class PluginManager:
    def __init__(self, root=None, python=None):
        self.root = Path(root or Path.home() / '.elworks/plugins').expanduser().resolve()
        self.registry = self.root / 'plugins.json'
        self.python = python

    def _records(self):
        if not self.registry.exists():
            return {}
        try:
            data = json.loads(self.registry.read_text(encoding='utf-8'))
            if not isinstance(data, dict) or data.get('version') != 1 or not isinstance(data.get('plugins'), dict):
                raise ValueError('Unknown plugin registry format')
            return data['plugins']
        except (OSError, ValueError) as exc:
            raise PluginError(f'Cannot read plugin registry: {exc}') from exc

    def _write(self, records):
        self.root.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix='.plugins-', suffix='.json', dir=self.root)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                stream.write(json_text({'version': 1, 'plugins': records}))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.registry)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def list_plugins(self):
        plugins = []
        for plugin_id, record in self._records().items():
            try:
                manifest = PluginManifest.from_dict(record['manifest'])
                path = (self.root / record['path']).resolve()
                if manifest.id != plugin_id or path.parent != (self.root / '.installs').resolve():
                    raise PluginError('Invalid plugin installation path or ID')
                if type(record['enabled']) is not bool:
                    raise PluginError('Invalid plugin enabled state')
                plugin = InstalledPlugin(manifest, path, record['enabled'])
                if not plugin.python.is_file() or not (path / 'runtime/worker.py').is_file():
                    raise PluginError(f'Plugin installation is incomplete: {plugin_id}')
                plugins.append(plugin)
            except (KeyError, TypeError) as exc:
                raise PluginError('Invalid plugin registry record') from exc
        return sorted(plugins, key=lambda p: p.manifest.name.casefold())

    def get(self, plugin_id, require_enabled=True):
        plugin = next((p for p in self.list_plugins() if p.manifest.id == plugin_id), None)
        if plugin is None:
            raise PluginError(f'Plugin is not installed: {plugin_id}')
        if require_enabled and not plugin.enabled:
            raise PluginError(f'Plugin is disabled: {plugin_id}')
        return plugin

    def metadata(self):
        return {p.manifest.id: dict(p.manifest.to_dict(), type=p.manifest.system_name)
                for p in self.list_plugins()}

    @staticmethod
    def inspect(filename):
        return inspect_wheel(filename)

    @staticmethod
    def _connection(conn):
        if conn is not None and conn.in_transaction:
            raise PluginError('Finish the current database transaction before changing plugins')
        return conn if conn is not None else nullcontext()

    def install(self, filename, conn=None, replace_id=None, prepare=None):
        """Validate candidate before registry/DB switch; preserve old install on failure."""
        old_records = self._records()
        manifest = inspect_wheel(filename)
        old_id = replace_id or manifest.id
        old_plugin = self.get(old_id, require_enabled=False) if old_id in old_records else None
        if replace_id and old_plugin is None:
            raise PluginError('Replacement plugin is not installed')
        if old_plugin and old_plugin.manifest.system_id != manifest.system_id:
            raise PluginError('Replacement must support the same external system')
        if replace_id and replace_id != manifest.id and manifest.id in old_records:
            raise PluginError('Replacement ID is already installed')
        installer = PluginInstaller(self.root, self.python)
        candidate = (prepare or installer.prepare)(filename)
        if candidate.manifest != manifest:
            installer.discard(candidate)
            raise PluginError('Wheel manifest changed during installation')
        updated = dict(old_records)
        updated.pop(old_id, None)
        enabled = old_plugin.enabled if old_plugin else True
        updated[manifest.id] = {'manifest': manifest.to_dict(),
                                'path': str(candidate.path.relative_to(self.root)), 'enabled': enabled}
        registry_written = False
        try:
            with self._connection(conn):
                if old_plugin and conn is not None:
                    conn.execute('UPDATE PROJECTS SET plugin_id=?, needs_reload=1 WHERE plugin_id=?',
                                 (manifest.id, old_id))
                self._write(updated)
                registry_written = True
        except Exception:
            if registry_written:
                self._write(old_records)
            installer.discard(candidate)
            raise
        if old_plugin:
            # Registry and project switch succeeded. A failed cleanup leaves only an unused generation.
            try:
                installer.discard(old_plugin)
            except OSError:
                pass
        return self.get(manifest.id, require_enabled=False)

    def set_enabled(self, plugin_id, enabled):
        self.get(plugin_id, require_enabled=False)
        records = self._records()
        records[plugin_id] = dict(records[plugin_id], enabled=bool(enabled))
        self._write(records)

    def remove(self, plugin_id):
        plugin = self.get(plugin_id, require_enabled=False)
        records = self._records()
        records.pop(plugin_id)
        self._write(records)
        # Projects intentionally retain their plugin_id and last imported data.
        try:
            PluginInstaller(self.root, self.python).discard(plugin)
        except OSError:
            pass

    def logs(self, plugin_id):
        plugin = self.get(plugin_id, require_enabled=False)
        path = plugin.path / 'plugin.log'
        return path.read_text(encoding='utf-8', errors='replace')[-1024 * 1024:] if path.exists() else ''
