"""Lifecycle, worker isolation and atomic persistence against temporary storage."""
from dataclasses import asdict
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'ElPartsPluginSrc/kicad'))

from ElDBScheme import DBFactory
from ElPartsPluginApi.importers import ImportedComponent, ImportedProject, ImportCancelled, PluginError
from ElPartsPluginApi.importers.manifest import PluginManifest
from ElPartsImport.installer import InstalledPlugin, PluginInstaller, inspect_wheel
from ElPartsImport.manager import PluginManager
from ElPartsImport.protocol import project_from_dict, project_to_dict
from ElPartsImport.repository import ProjectRepository
from ElPartsImport.runner import PluginRunner
from partsdb_kicad import KiCadImporter

SOURCE = ROOT / 'tests/input/SMHome_UniversalRound_ESP32_C3_Mini_v4/SMHome_UniversalRound_ESP32_C3_Mini_v4.kicad_pro'
MANIFEST = json.loads((ROOT / 'ElPartsPluginSrc/kicad/partsdb-plugin.json').read_text())


class RepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.factory = DBFactory(str(Path(self.temp.name) / 'database.sqlite'))
        self.addCleanup(self.factory.disconnect)
        self.conn = self.factory.scheme.db.conn
        self.repo = ProjectRepository(self.conn)
        self.project = KiCadImporter().import_project(SOURCE.as_uri())
        section = self.factory.appendType('Test resistors', None)
        self.part = self.factory.createPart(section, {'part_num': 'Stock sample', 'quantity': 100})
        self.part_id = self.part.id

    def save(self, project_id=None):
        return self.repo.save(self.project, MANIFEST['id'], SOURCE.as_uri(), project_id)

    def match(self, project_id):
        external_id = self.project.components[0].external_id
        component_id = next(row['id'] for row in self.repo.components(project_id)
                            if row['external_id'] == external_id)
        with self.conn:
            self.conn.execute('INSERT INTO PROJECT_COMPONENT_MATCHES(component_id,part_id) VALUES (?,?)',
                              (component_id, self.part_id))
        return component_id

    def test_first_import_and_repeat_preserve_ids_and_matches(self):
        project_id = self.save()
        before = self.repo.components(project_id)
        component_id = self.match(project_id)
        self.assertEqual(len(before), 49)
        self.assertEqual(self.save(project_id), project_id)
        self.assertEqual(self.repo.components(project_id), before)
        self.assertEqual(self.conn.execute('SELECT component_id,part_id,needs_review FROM PROJECT_COMPONENT_MATCHES').fetchone(),
                         (component_id, self.part_id, 0))
        self.assertEqual(self.conn.execute('SELECT needs_reload FROM PROJECTS').fetchone(), (0,))
        self.assertEqual(len(self.repo.changes(self.project, project_id).unchanged), 49)
        self.assertEqual(self.conn.execute('SELECT quantity FROM PARTS WHERE id=?', (self.part_id,)).fetchone(), (100,))

    def test_changed_requirements_keep_match_and_mark_review(self):
        project_id = self.save()
        component_id = self.match(project_id)
        self.project.components[0].properties['Voltage'] = '50 V'
        self.assertEqual(len(self.repo.changes(self.project, project_id).changed), 1)
        self.save(project_id)
        self.assertEqual(self.conn.execute('SELECT component_id,needs_review FROM PROJECT_COMPONENT_MATCHES').fetchone(),
                         (component_id, 1))

    def test_reference_rename_preserves_match_without_review(self):
        project_id = self.save()
        component_id = self.match(project_id)
        self.project.components[0].reference = 'C100'
        self.project.components[0].properties['Reference'] = 'C100'
        self.save(project_id)
        self.assertEqual(self.conn.execute('SELECT component_id,needs_review FROM PROJECT_COMPONENT_MATCHES').fetchone(),
                         (component_id, 0))

    def test_removed_position_deletes_its_match_and_keeps_stock(self):
        project_id = self.save()
        self.match(project_id)
        removed = self.project.components.pop(0)
        self.assertEqual(self.repo.changes(self.project, project_id).removed, (removed.reference,))
        self.save(project_id)
        self.assertEqual(len(self.repo.components(project_id)), 48)
        self.assertEqual(self.conn.execute('SELECT count(*) FROM PROJECT_COMPONENT_MATCHES').fetchone(), (0,))
        self.assertEqual(self.conn.execute('SELECT count(*) FROM PARTS').fetchone(), (1,))

    def test_failed_write_rolls_back_project_and_all_components(self):
        project_id = self.save()
        with self.conn:
            self.conn.execute("CREATE TRIGGER fail_import BEFORE INSERT ON PROJECT_COMPONENTS "
                              "WHEN NEW.reference='ZFAIL' BEGIN SELECT RAISE(ABORT,'test failure'); END")
        before = list(self.conn.iterdump())
        self.project.name = 'Must roll back'
        self.project.components[0].value_raw = 'Changed before failure'
        self.project.components.append(ImportedComponent('new', 'ZFAIL'))
        with self.assertRaises(sqlite3.IntegrityError):
            self.save(project_id)
        self.assertEqual(list(self.conn.iterdump()), before)

    def test_invalid_result_and_plugin_switch_cannot_change_data(self):
        project_id = self.save()
        before = list(self.conn.iterdump())
        with self.assertRaises(PluginError):
            self.repo.save(self.project, 'different.plugin', SOURCE.as_uri(), project_id)
        self.project.components.append(self.project.components[0])
        with self.assertRaises(PluginError):
            self.save(project_id)
        self.assertEqual(list(self.conn.iterdump()), before)

    def test_delete_project_cascades_components_and_legacy_links_only(self):
        project_id = self.save()
        self.match(project_id)
        with self.conn:
            self.conn.execute('INSERT INTO EL_BY_PROJECT(project_id,part_id,quantity) VALUES (?,?,1)',
                              (project_id, self.part_id))
        self.repo.delete(project_id)
        for table in ('PROJECTS', 'PROJECT_COMPONENTS', 'PROJECT_COMPONENT_MATCHES', 'EL_BY_PROJECT'):
            self.assertEqual(self.conn.execute('SELECT count(*) FROM ' + table).fetchone(), (0,))
        self.assertEqual(self.conn.execute('SELECT count(*) FROM PARTS').fetchone(), (1,))


class ProtocolTests(unittest.TestCase):
    def test_roundtrip_preserves_all_import_data(self):
        project = KiCadImporter().import_project(SOURCE.as_uri())
        self.assertEqual(project_from_dict(json.loads(json.dumps(project_to_dict(project)))), project)

    def test_invalid_results_are_rejected(self):
        project = ImportedProject('Test', components=[ImportedComponent('id', 'R1')])
        for key, value in [('reference', ''), ('in_bom', 1), ('properties', []),
                           ('nominal', {'value': 'NaN', 'unit': 'F'})]:
            with self.subTest(key=key):
                data = asdict(project)
                data['components'][0][key] = value
                with self.assertRaises(PluginError):
                    project_from_dict(data)
        project.properties['invalid'] = float('nan')
        with self.assertRaises(PluginError):
            project_to_dict(project)


class ManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.manager = PluginManager(self.root / 'plugins')
        self.conn = sqlite3.connect(':memory:')
        self.addCleanup(self.conn.close)
        self.conn.execute('CREATE TABLE PROJECTS(id INTEGER PRIMARY KEY, plugin_id TEXT, needs_reload INTEGER)')
        with self.conn:
            self.conn.execute('INSERT INTO PROJECTS VALUES(1,?,0)', (MANIFEST['id'],))
        self.generation = 0

    def wheel(self, **overrides):
        manifest = dict(MANIFEST, **overrides)
        path = self.root / (manifest['id'] + '-' + str(manifest['version']) + '.whl')
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('partsdb-plugin.json', json.dumps(manifest))
        return path

    def prepare(self, wheel):
        self.generation += 1
        path = self.manager.root / '.installs' / str(self.generation)
        plugin = InstalledPlugin(inspect_wheel(wheel), path)
        plugin.python.parent.mkdir(parents=True)
        plugin.python.symlink_to(Path(sys.executable).resolve())
        (path / 'runtime').mkdir()
        (path / 'runtime/worker.py').write_text('')
        return plugin

    def install(self, **overrides):
        return self.manager.install(self.wheel(**overrides), self.conn, prepare=self.prepare)

    def test_install_update_disable_remove_preserve_projects(self):
        old = self.install()
        self.assertTrue(self.manager.get(MANIFEST['id']).enabled)
        new = self.install(version='0.2.0')
        self.assertFalse(old.path.exists())
        self.assertTrue(new.path.exists())
        self.assertEqual(self.conn.execute('SELECT needs_reload FROM PROJECTS').fetchone(), (1,))
        self.manager.set_enabled(MANIFEST['id'], False)
        with self.assertRaises(PluginError):
            self.manager.get(MANIFEST['id'])
        self.manager.remove(MANIFEST['id'])
        self.assertFalse(new.path.exists())
        self.assertEqual(self.manager.list_plugins(), [])
        self.assertEqual(self.conn.execute('SELECT plugin_id FROM PROJECTS').fetchone(), (MANIFEST['id'],))

    def test_replace_same_system_switches_projects(self):
        old = self.install()
        replacement = self.wheel(id='org.partsdb.alternative')
        new = self.manager.install(replacement, self.conn, replace_id=MANIFEST['id'], prepare=self.prepare)
        self.assertFalse(old.path.exists())
        self.assertEqual(self.conn.execute('SELECT plugin_id,needs_reload FROM PROJECTS').fetchone(),
                         (new.manifest.id, 1))
        with self.assertRaises(PluginError):
            self.manager.install(self.wheel(id='wrong', system_id='other'), self.conn,
                                 replace_id=new.manifest.id, prepare=self.prepare)

    def test_registry_failure_rolls_back_switch_and_keeps_old_install(self):
        old = self.install()
        before = self.manager.registry.read_bytes()
        with mock.patch.object(self.manager, '_write', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.install(version='0.2.0')
        self.assertEqual(self.manager.registry.read_bytes(), before)
        self.assertTrue(old.path.exists())
        self.assertFalse((self.manager.root / '.installs/2').exists())
        self.assertEqual(self.conn.execute('SELECT needs_reload FROM PROJECTS').fetchone(), (0,))

    def test_unsupported_manifest_does_not_execute_or_install(self):
        with self.assertRaises(PluginError):
            self.install(api_version=999)
        self.assertFalse(self.manager.root.exists())
        bad = self.root / 'bad.whl'
        with zipfile.ZipFile(bad, 'w') as archive:
            archive.writestr('../partsdb-plugin.json', json.dumps(MANIFEST))
        with self.assertRaises(PluginError):
            inspect_wheel(bad)


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        runtime = self.path / 'runtime'
        runtime.mkdir()
        shutil.copytree(ROOT / 'ElPartsPluginApi', runtime / 'ElPartsPluginApi', ignore=shutil.ignore_patterns('__pycache__'))
        (runtime / 'ElPartsImport').mkdir()
        for name in ('__init__.py', 'protocol.py'):
            shutil.copyfile(ROOT / 'ElPartsImport' / name, runtime / 'ElPartsImport' / name)
        shutil.copyfile(ROOT / 'ElPartsImport/worker.py', runtime / 'worker.py')
        self.plugin = InstalledPlugin(PluginManifest.from_dict(dict(MANIFEST, entry_point='test_plugin:Importer')), self.path)
        self.plugin.python.parent.mkdir(parents=True)
        self.plugin.python.symlink_to(Path(sys.executable).resolve())

    def code(self, body):
        (self.path / 'runtime/test_plugin.py').write_text('''
from ElPartsPluginApi.importers import ProjectImporter, ImportFormat, ProbeResult, ImportedProject
class Importer(ProjectImporter):
    def get_import_formats(self):
        return [ImportFormat('test', 'Test', ['.test'])]
    def probe(self, source_uri):
        return ProbeResult(True)
    def import_project(self, source_uri):
''' + '\n'.join('        ' + line for line in body.splitlines()) + '\n')

    def test_noisy_stdout_does_not_corrupt_protocol(self):
        self.code("print('debug output')\nreturn ImportedProject('Test')")
        events = []
        result = PluginRunner().run(self.plugin, 'file:///test', on_event=events.append)
        self.assertEqual(result.name, 'Test')
        self.assertTrue(any(e['type'] == 'progress' for e in events))
        self.assertIn('debug output', (self.path / 'plugin.log').read_text())

    def test_failure_and_bad_return_are_reported(self):
        for body in ("raise RuntimeError('read failed')", "return {'invalid': True}",
                     "import os\nos._exit(42)",
                     "import sys\nsys.__stdout__.write('invalid-json\\n')\nsys.__stdout__.flush()\nreturn ImportedProject('Test')"):
            self.code(body)
            with self.assertRaises(PluginError):
                PluginRunner().run(self.plugin)

    def test_timeout_and_cancellation_stop_the_worker(self):
        self.code('import time\ntime.sleep(30)\nreturn ImportedProject("Test")')
        with self.assertRaisesRegex(PluginError, 'timed out'):
            PluginRunner(timeout=0.15).run(self.plugin)
        cancel = threading.Event()
        timer = threading.Timer(0.15, cancel.set)
        timer.start()
        self.addCleanup(timer.cancel)
        with self.assertRaises(ImportCancelled):
            PluginRunner().run(self.plugin, cancel=cancel)


class WheelEndToEndTests(unittest.TestCase):
    def test_wheel_installs_and_imports_without_source_plugin_on_path(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            wheels = path / 'wheels'
            subprocess.run([sys.executable, '-m', 'pip', 'wheel', '--no-deps', '--no-index',
                            '--no-cache-dir', '--no-build-isolation', '--wheel-dir', str(wheels),
                            str(ROOT / 'ElPartsPluginSrc/kicad')], check=True, capture_output=True, text=True, timeout=60)
            manager = PluginManager(path / 'plugins')
            plugin = manager.install(next(wheels.glob('*.whl')))
            result = PluginRunner().run(plugin, SOURCE.as_uri())
            self.assertEqual(len(result.components), 49)
            database = DBFactory(str(path / 'import.sqlite'))
            try:
                repository = ProjectRepository(database.scheme.db.conn)
                project_id = repository.save(result, plugin.manifest.id, SOURCE.as_uri())
                self.assertEqual(len(repository.components(project_id)), 49)
                self.assertEqual(repository.save(result, plugin.manifest.id, SOURCE.as_uri(), project_id), project_id)
            finally:
                database.disconnect()
            self.assertEqual(result, KiCadImporter().import_project(SOURCE.as_uri()))
            self.assertEqual(PluginRunner().run(plugin, action='inspect')[0]['extensions'],
                             ['.kicad_pro', '.kicad_sch'])
