"""Qt workflow tests use temporary databases and do not open the personal stock."""
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest import mock

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'ElPartsPluginSrc/kicad'))

from PyQt6.QtWidgets import QDialog, QMessageBox, QFileDialog
import zipfile
from ElConfig import ElConfig
from ElData.ElDBScheme import DBFactory
from ElMainWindow import MainWindow
from ElImportPreview import ImportPreview
from ElImportTask import run_import_task
from ElPluginsDialog import PluginsDialog
from ElPluginMgr.installer import InstalledPlugin
from ElPluginMgr.manager import PluginManager
from ElPluginMgr.repository import ProjectRepository
from ElPartsPluginApi import PLUGIN_TYPE_IMPORT, PLUGIN_TYPE_PARTS_ORDER
from ElPartsPluginApi.importers import ImportCancelled
from ElPartsPluginApi.importers.manifest import PluginManifest
from ElTranslations import LanguageManager
from partsdb_kicad import KiCadImporter
from tests.qt_support import application
import json

app = application()
SOURCE = ROOT / 'tests/input/SMHome_UniversalRound_ESP32_C3_Mini_v4/SMHome_UniversalRound_ESP32_C3_Mini_v4.kicad_pro'
MANIFEST = PluginManifest.from_dict(json.loads((ROOT / 'ElPartsPluginSrc/kicad/partsdb-plugin.json').read_text()))


class PluginWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.factory = DBFactory(str(self.path / 'database.sqlite'))
        self.addCleanup(self.factory.disconnect)
        self.config = ElConfig()
        self.config.filename = str(self.path / 'elworks.conf')
        self.config.set_value('language', 'en')
        self.window = MainWindow(self.factory, self.config)
        self.window.setStartupMode(None)
        self.addCleanup(self.window.close)
        self.controller = self.window.projectImports
        self.conn = self.factory.scheme.db.conn
        self.project = KiCadImporter().import_project(SOURCE.as_uri())
        self.plugin = InstalledPlugin(MANIFEST, self.path / 'unused-plugin')
        self.addCleanup(self.window.languageManager.close)

    def test_import_preview_accept_writes_and_displays_all_components(self):
        with mock.patch('ElPluginMgr.ElProjectImports.PluginRunner.run', return_value=self.project), \
                mock.patch.object(ImportPreview, 'exec', return_value=QDialog.DialogCode.Accepted):
            project_id = self.controller.import_source(self.plugin, SOURCE.as_uri())
        self.assertIsNotNone(project_id)
        self.assertEqual(self.window.projWindow.componentsModel.rowCount(), 49)
        self.assertEqual(self.window.projWindow.unmatchedModel.rowCount(), 49)
        self.assertEqual(self.window.projWindow.project.id, project_id)
        before = ProjectRepository(self.conn).components(project_id)
        with mock.patch.object(self.controller.manager, 'get', return_value=self.plugin), \
                mock.patch('ElPluginMgr.ElProjectImports.PluginRunner.run', return_value=self.project), \
                mock.patch.object(ImportPreview, 'exec', return_value=QDialog.DialogCode.Accepted):
            self.window.d_prj_reload_cmd.click()
        self.assertEqual(ProjectRepository(self.conn).components(project_id), before)

    def test_preview_reject_cancel_and_worker_error_keep_database_unchanged(self):
        before = list(self.conn.iterdump())
        with mock.patch('ElPluginMgr.ElProjectImports.PluginRunner.run', return_value=self.project), \
                mock.patch.object(ImportPreview, 'exec', return_value=QDialog.DialogCode.Rejected):
            self.assertIsNone(self.controller.import_source(self.plugin, SOURCE.as_uri()))
        with mock.patch('ElPluginMgr.ElProjectImports.PluginRunner.run', side_effect=ImportCancelled('cancelled')):
            self.assertIsNone(self.controller.import_source(self.plugin, SOURCE.as_uri()))
        with mock.patch('ElPluginMgr.ElProjectImports.PluginRunner.run', side_effect=RuntimeError('failed')), \
                mock.patch.object(QMessageBox, 'critical') as error:
            self.assertIsNone(self.controller.import_source(self.plugin, SOURCE.as_uri()))
            error.assert_called_once()
        self.assertEqual(list(self.conn.iterdump()), before)

    def test_confirmed_match_is_displayed_and_can_be_cleared(self):
        repo = ProjectRepository(self.conn)
        project_id = repo.save(self.project, MANIFEST.id, SOURCE.as_uri())
        section = self.factory.appendType('Test capacitors', None)
        part = self.factory.createPart(section, {'part_num': 'Stock capacitor'})
        component_id = repo.components(project_id)[0]['id']
        repo.set_match(component_id, part.id)
        self.window.projWindow.refresh()
        self.assertEqual(self.window.projWindow.unmatchedModel.rowCount(), 48)
        self.assertEqual(repo.matches(project_id)[component_id]['part_id'], part.id)
        repo.set_match(component_id)
        self.window.projWindow.refresh()
        self.assertEqual(self.window.projWindow.unmatchedModel.rowCount(), 49)
        self.assertEqual(repo.matches(project_id), {})

    def test_confirmed_delete_button_removes_import_and_keeps_stock(self):
        repo = ProjectRepository(self.conn)
        project_id = repo.save(self.project, MANIFEST.id, SOURCE.as_uri())
        self.window.projWindow.refresh()
        with mock.patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Yes):
            self.window.proj_remove_cmd.click()
        self.assertEqual(repo.components(project_id), [])
        self.assertIsNone(self.window.projWindow.project)

    def test_preview_language_changes_preserve_component_rows(self):
        preview = ImportPreview(self.project, ProjectRepository(self.conn).changes(self.project), self.window)
        self.addCleanup(preview.close)
        self.assertEqual(preview.ui.table.rowCount(), 49)
        self.window.languageManager.setLanguage('ru')
        app.processEvents()
        self.assertEqual(preview.windowTitle(), 'Предпросмотр импорта')
        self.assertEqual(preview.ui.table.item(0, 1).text(), 'C1')
        self.assertEqual(preview.ui.table.rowCount(), 49)

    def test_plugins_dialog_has_install_action_and_preserves_plain_metadata(self):
        manager = PluginManager(self.path / 'plugins')
        with mock.patch.object(manager, 'list_plugins', return_value=[self.plugin]), \
                mock.patch.object(manager, 'set_enabled') as enable:
            dialog = PluginsDialog(self.window, manager=manager, conn=self.conn)
            self.addCleanup(dialog.close)
            self.assertTrue(dialog.ui.pl_add_file_cmd.isEnabled())
            self.assertEqual(dialog.ui.pl_name.text(), MANIFEST.name)
            self.assertTrue(dialog.ui.pl_enable.isChecked())
            dialog.ui.pl_enable.click()
            enable.assert_called_once_with(MANIFEST.id, False, self.conn)

    def test_install_from_file_and_remove_use_the_manager(self):
        manager = PluginManager(self.path / 'plugin-storage')
        candidate = InstalledPlugin(MANIFEST, manager.root / '.installs/test-candidate')
        candidate.python.parent.mkdir(parents=True)
        candidate.python.touch()
        (candidate.path / 'runtime').mkdir()
        (candidate.path / 'runtime/worker.py').write_text('')
        wheel = self.path / 'test.whl'
        with zipfile.ZipFile(wheel, 'w') as archive:
            archive.writestr('partsdb-plugin.json', json.dumps(MANIFEST.to_dict()))
        dialog = PluginsDialog(self.window, manager=manager, conn=self.conn)
        self.addCleanup(dialog.close)
        with mock.patch.object(QFileDialog, 'getOpenFileName', return_value=(str(wheel), '')), \
                mock.patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Yes), \
                mock.patch('ElPluginsDialog.PluginInstaller.prepare', return_value=candidate):
            dialog.ui.pl_add_file_cmd.click()
        self.assertEqual(manager.get(MANIFEST.id).manifest, MANIFEST)
        self.assertEqual(dialog.pluginsModel.rowCount(), 1)
        self.assertEqual(dialog.ui.pl_name.text(), MANIFEST.name)
        self.assertIn('Project import', dialog.ui.pl_type.text())
        self.assertEqual(self.conn.execute('SELECT plugin_type FROM PLUGINS').fetchone(), (PLUGIN_TYPE_IMPORT,))
        with mock.patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Yes):
            dialog.ui.pl_delete.click()
        self.assertEqual(manager.list_plugins(), [])
        self.assertFalse(candidate.path.exists())
        self.assertEqual(self.conn.execute('SELECT count(*) FROM PLUGINS').fetchone(), (0,))

    def test_project_import_chooser_filters_other_plugin_types(self):
        other_manifest = PluginManifest.from_dict(dict(MANIFEST.to_dict(),
            id='example.order', plugin_type=PLUGIN_TYPE_PARTS_ORDER, capabilities=[PLUGIN_TYPE_PARTS_ORDER]))
        other = InstalledPlugin(other_manifest, self.path / 'other')
        with mock.patch.object(self.controller.manager, 'list_plugins', return_value=[other, self.plugin]):
            self.assertEqual(self.controller.choose_plugin(), self.plugin)
        before = list(self.conn.iterdump())
        with mock.patch.object(QMessageBox, 'critical') as error:
            self.assertIsNone(self.controller.import_source(other, SOURCE.as_uri()))
            error.assert_called_once()
        self.assertEqual(list(self.conn.iterdump()), before)

    def test_background_work_uses_another_thread(self):
        owner = threading.get_ident()
        worker = run_import_task(self.window, lambda cancel, emit: threading.get_ident())
        self.assertNotEqual(owner, worker)
