"""Reference editor, v8 migration and detached project application launch checks."""
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt6.QtCore import QProcess, QUrl
from PyQt6.QtWidgets import QMainWindow, QMessageBox
from ElConstants import SI_PREFIXES, SI_BASE_UNITS
from ElData import ElDBScheme as db
from ElData.ElDBDataUnits import UnitsDataStore
from ElData.ElDBDataPlagins import PluginDataStore
from ElParts import Ui_MainWindow
from ElPluginsDialog import PluginsDialog
from ElProjWindow import ProjWindow
from ElUnitsDialog import UnitsDialog
from tests.qt_support import application

app = application()


class TestWindow(QMainWindow, Ui_MainWindow):
    """Provide main window widgets for application-launch tests without a production database.

    @attr d_prj_open_cmd [QPushButton] Project application launch button from the generated form."""


class UnitsAndLaunchTests(unittest.TestCase):
    """Verify reference editing, plugin launch settings and version 8 migration in isolation.

    @attr root [Path] Temporary test directory.
    @attr factory [DBFactory] Factory connected to the disposable database.
    @attr scheme [DBScheme] Active temporary database scheme.
    @attr conn [sqlite3.Connection] Test-only handle for fixtures and assertions.
    @attr store [UnitsDataStore] Reference data access layer under test."""

    def setUp(self):
        """Create a disposable database and reference store, registering cleanup.

        @return [None] No value is returned."""
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.factory = db.DBFactory(str(self.root / 'test.sqlite'))
        self.addCleanup(self.factory.disconnect)
        self.scheme = self.factory.scheme
        self.conn = self.scheme.db.conn
        self.store = UnitsDataStore(self.scheme)

    def seedPlugin(self, plugin_id='one'):
        """Insert minimal valid plugin metadata in the temporary database.

        @param plugin_id [str] Unique plugin card ID; defaults to one.
        @return [dict] Metadata record used by subsequent synchronization checks."""
        record = dict(id=plugin_id, plugin_type='project_import', name=plugin_id, version='1',
                      api_version=1, system_id='test', system_name='Test', description='',
                      author='', enabled=1, manifest_json='{}')
        with self.conn:
            self.scheme.storePluginMetadata(record)
        return record

    def test_seed_and_multiplier_validation(self):
        """Verify seeded base conversions and reject invalid or nonfinite multipliers.

        @return [None] No value is returned."""
        units = self.store.units()
        self.assertEqual(len(units), len(SI_PREFIXES) * len(SI_BASE_UNITS))
        by_name = {row[1]: row for row in units}
        self.assertEqual(by_name['Kiloohm'][2:6], ('Килоом', 'k', 'к', 1000))
        self.assertEqual(by_name['Microhenry'][3:6], ('uH', 'мкГ', 1e-6))
        self.assertEqual(by_name['Nanofarad'][3:6], ('nF', 'нФ', 1e-9))
        for value in ('nan', 'inf', '0', '-1', 'bad'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.store.save([(*units[0][:5], value, units[0][6]), *units[1:]], self.store.basicTypes())
        self.assertEqual(self.store.units(), units)

    def test_reference_crud_and_rollback_for_referenced_type(self):
        """Verify reference CRUD and atomic rollback when a referenced type cannot be deleted.

        @return [None] No value is returned."""
        types = self.store.basicTypes()
        ohm_id = next(row[0] for row in self.store.units() if row[1] == 'Ohm')
        self.store.save(self.store.units() + [(None, 'Custom', 'Своя', 'x', 'х', 2, ohm_id)],
                        types + [(None, 'Custom component', 'XYZ', None, None)])
        custom_unit = self.store.units()[-1]
        custom_type = self.store.basicTypes()[-1]
        self.factory.appendType('Uses custom type', None, custom_type[0])
        before = list(self.conn.iterdump())
        with self.assertRaises(ValueError):
            self.store.save(self.store.units()[:-1], types)
        self.assertEqual(list(self.conn.iterdump()), before)
        self.store.save([(*row[:5], 3, row[6]) if row[0] == custom_unit[0] else row
                         for row in self.store.units()], self.store.basicTypes())
        self.assertEqual(self.store.units()[-1][5], 3)
        self.store.save(self.store.units()[:-1], self.store.basicTypes())
        self.assertNotIn(custom_unit[0], [row[0] for row in self.store.units()])

    def test_dialog_cancel_save_and_delete_confirmation(self):
        """Verify affirmative deletion confirmation, Cancel rollback and saved reference edits.

        @return [None] No value is returned."""
        before = list(self.conn.iterdump())
        dialog = UnitsDialog(self.scheme)
        dialog.ui.si_units_tbl.selectRow(0)
        count = dialog.unitsModel.rowCount()
        with mock.patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.No):
            dialog.deleteUnit()
        self.assertEqual(dialog.unitsModel.rowCount(), count)
        with mock.patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Yes):
            dialog.deleteUnit()
        self.assertEqual(dialog.unitsModel.rowCount(), count - 1)
        dialog.reject()
        self.assertEqual(list(self.conn.iterdump()), before)
        dialog = UnitsDialog(self.scheme)
        dialog.unitsModel.item(0, 2).setText('Изменено')
        with mock.patch.object(QMessageBox, 'critical') as error:
            dialog.accept()
        self.assertFalse(error.called, error.call_args)
        self.assertEqual(self.store.units()[0][2], 'Изменено')
        dialog.deleteLater()

    def test_plugin_fields_survive_metadata_sync_and_dialog_switch(self):
        """Verify plugin drafts survive selection, language refresh and metadata synchronization.

        @return [None] No value is returned."""
        first = self.seedPlugin()
        second = self.seedPlugin('two')
        dialog = PluginsDialog(manager=SimpleNamespace(sync=lambda conn: None), conn=self.scheme)
        dialog.ui.app_path_input.setText('/Applications/My Tool.app')
        dialog.ui.app_params_input.setText('--project "{file}"')
        dialog.ui.pl_list.setCurrentIndex(dialog.pluginsModel.index(1, 0))
        dialog.ui.app_path_input.setText('/tmp/second')
        dialog.retranslate()
        self.assertEqual(dialog.ui.app_path_input.text(), '/tmp/second')
        dialog.ui.pl_list.setCurrentIndex(dialog.pluginsModel.index(0, 0))
        self.assertEqual(dialog.ui.app_path_input.text(), '/Applications/My Tool.app')
        with mock.patch('ElPluginsDialog.QFileDialog.getOpenFileName', return_value=('/tmp/chosen app', '')):
            dialog.ui.get_path_cmd.click()
        dialog.reject()  # Window close saves application settings too.
        saved = PluginDataStore(self.scheme).application('one')
        self.assertEqual((saved.app_path, saved.app_params), ('/tmp/chosen app', '--project "{file}"'))
        first['version'] = '2'
        with self.conn:
            self.scheme.syncPluginMetadata([first, second])
        self.assertEqual(PluginDataStore(self.scheme).application('one').app_path, '/tmp/chosen app')
        dialog.deleteLater()

    def test_detached_launch_preserves_spaces_and_handles_failure(self):
        """Verify detached launch arguments, macOS bundles and reported launch failures.

        @return [None] No value is returned."""
        self.seedPlugin()
        PluginDataStore(self.scheme).saveApplications({'one': ('/tmp/My executable', '--flag "{file}" --name "two words"')})
        window = TestWindow()
        window.setupUi(window)
        self.addCleanup(window.close)
        controller = ProjWindow(self.factory, window)
        filename = str(self.root / 'space and "quotes"' / 'board.kicad_pro')
        project = SimpleNamespace(plugin_id='one', source_uri=QUrl.fromLocalFile(filename).toString())
        controller.project = project
        with mock.patch.object(QProcess, 'startDetached', return_value=(True, 123)) as launch:
            controller.onOpenProject()
        launch.assert_called_once_with('/tmp/My executable', ['--flag', filename, '--name', 'two words'])
        with mock.patch.object(QProcess, 'startDetached', return_value=(False, 0)), \
                mock.patch.object(QMessageBox, 'critical') as error:
            controller.onOpenProject()
        error.assert_called_once()
        bundle = self.root / 'My Tool.app'
        bundle.mkdir()
        PluginDataStore(self.scheme).saveApplications({'one': (str(bundle), '"{file}"')})
        with mock.patch('ElProjWindow.sys.platform', 'darwin'), \
                mock.patch.object(QProcess, 'startDetached', return_value=(True, 124)) as launch:
            controller.onOpenProject()
        launch.assert_called_once_with('/usr/bin/open', ['-a', str(bundle), '--args', filename])

    def test_migration_is_atomic_repeatable_and_preserves_plugin(self):
        """Verify version 8 DDL rollback, repeatable migration and retained plugin metadata.

        @return [None] No value is returned."""
        self.seedPlugin()
        with self.conn:
            self.conn.execute('DROP TABLE SI_UNITS')
            self.conn.execute('ALTER TABLE PLUGINS DROP COLUMN app_path')
            self.conn.execute('ALTER TABLE PLUGINS DROP COLUMN app_params')
            self.conn.execute("UPDATE ENVIRONMENT SET value='7' WHERE name='db_version'")
        before = list(self.conn.iterdump())
        with mock.patch.object(db, '_createPluginApplications', side_effect=RuntimeError('failure')):
            with self.assertRaises(RuntimeError):
                self.scheme.migrate()
        self.assertEqual(list(self.conn.iterdump()), before)
        self.scheme.migrate()
        self.assertEqual(self.scheme.getDBVersion(), db.DB_VERSION)
        self.assertEqual(PluginDataStore(self.scheme).application('one').app_path, '')
        before = list(self.conn.iterdump())
        self.scheme.migrate()
        self.assertEqual(list(self.conn.iterdump()), before)


    def test_base_links_and_pending_reference_choices(self):
        """Persist references to new base units and expose only base units in selectors.

        @return [None] Verify temporary IDs resolve and existing default type links are present.
        """
        units = self.store.units()
        by_name = {row[1]: row for row in units}
        self.assertEqual(by_name['Microhenry'][6], by_name['Henry'][0])
        self.assertEqual(by_name['Kiloohm'][6], by_name['Ohm'][0])
        self.assertIsNone(by_name['Henry'][6])
        types = {row[0]: row for row in self.store.basicTypes()}
        self.assertEqual(types[2][4], by_name['Farad'][0])
        self.assertEqual(types[3][4], by_name['Ohm'][0])
        self.assertEqual(types[7][4], by_name['Henry'][0])
        self.assertIsNone(types[4][4])
        pending = [(-1, 'Custombase', 'Базовая', 'X', 'Х', 1, None),
                   (-2, 'Custommilli', 'Миллибазовая', 'mX', 'мХ', 0.001, -1)]
        self.store.save(units + pending, list(types.values()) + [(None, 'Custom type', 'X', None, -1)])
        saved = {row[1]: row for row in self.store.units()}
        self.assertGreater(saved['Custombase'][0], 0)
        self.assertEqual(saved['Custommilli'][6], saved['Custombase'][0])
        self.assertEqual(self.store.basicTypes()[-1][4], saved['Custombase'][0])
        dialog = UnitsDialog(self.scheme)
        choices = dialog.baseUnits()
        self.assertIn(saved['Custombase'][0], choices)
        self.assertNotIn(saved['Custommilli'][0], choices)
        delegate = dialog.ui.b_types_tbl.itemDelegateForColumn(4)
        index = dialog.typesModel.index(0, 4)
        editor = delegate.createEditor(dialog, None, index)
        self.assertIsNone(editor.itemData(0))
        dialog.reject()
        dialog.deleteLater()

    def test_invalid_links_and_referenced_base_deletion_are_rejected(self):
        """Reject dangling references, multiplier chains and deletion of referenced units.

        @return [None] Verify failures preserve the complete reference data.
        """
        units = self.store.units()
        types = self.store.basicTypes()
        by_name = {row[1]: row for row in units}
        before = list(self.conn.iterdump())
        for target in (None, 999999, by_name['Microhenry'][0]):
            changed = [(*row[:6], target) if row[1] == 'Nanofarad' else row for row in units]
            with self.subTest(target=target), self.assertRaises(ValueError):
                self.store.save(changed, types)
        with self.assertRaises(ValueError):
            self.store.save([row for row in units if row[1] != 'Ohm'], types)
        with self.assertRaises(ValueError):
            self.store.save(units, [(*row[:4], by_name['Kiloohm'][0]) if row[0] == 4 else row for row in types])
        self.assertEqual(list(self.conn.iterdump()), before)
        # A whole family can be removed once type links are explicitly cleared.
        ohm_id = by_name['Ohm'][0]
        self.store.save([row for row in units if row[0] != ohm_id and row[6] != ohm_id],
                        [(*row[:4], None) if row[4] == ohm_id else row for row in types])
        self.assertNotIn(ohm_id, [row[0] for row in self.store.units()])

    def test_v9_migration_links_known_units_and_rolls_back_ddl(self):
        """Upgrade a version 8 reference database while preserving custom rows and edits.

        @return [None] Verify atomic DDL rollback and repeatable initialization of known links.
        """
        with self.conn:
            self.conn.execute('ALTER TABLE BASIC_TYPES DROP COLUMN base_unit_id')
            self.conn.execute('ALTER TABLE SI_UNITS DROP COLUMN base_unit_id')
            self.conn.execute("INSERT INTO SI_UNITS(name,name_ru,marker,marker_ru,multiply) VALUES('Custom', 'Своя', 'X', 'Х', 2)")
            self.conn.execute("UPDATE ENVIRONMENT SET value='8' WHERE name='db_version'")
        before = list(self.conn.iterdump())
        original = db._createUnitLinks
        def fail_after_ddl(conn):
            """Inject failure after adding link columns.

            @param conn [SQLiteConnector] Connector for the temporary migration database.
            @return [None] Raise a deliberate migration failure.
            """
            original(conn)
            raise RuntimeError('Injected migration failure')
        with mock.patch.object(db, '_createUnitLinks', side_effect=fail_after_ddl):
            with self.assertRaises(RuntimeError):
                self.scheme.migrate()
        self.assertEqual(list(self.conn.iterdump()), before)
        self.scheme.migrate()
        by_name = {row[1]: row for row in self.store.units()}
        self.assertEqual(by_name['Kiloohm'][6], by_name['Ohm'][0])
        self.assertIsNone(by_name['Custom'][6])
        before = list(self.conn.iterdump())
        self.scheme.migrate()
        self.assertEqual(list(self.conn.iterdump()), before)

    def test_alias_roundtrip_and_invalid_targets(self):
        """Resolve pending alias IDs and reject chains, self-links and removed targets.

        @return [None] Verify valid links persist and invalid edits roll back both tables.
        """
        types = self.store.basicTypes()
        self.store.save(self.store.units(), types + [
            (-2, 'Alias target', 'X', None, None, None),
            (-1, 'Alias name', 'X', None, None, -2)])
        saved = {row[1]: row for row in self.store.basicTypes()}
        target_id = saved['Alias target'][0]
        alias_id = saved['Alias name'][0]
        self.assertEqual(saved['Alias name'][5], target_id)
        before = list(self.conn.iterdump())
        for bad_id in (alias_id, 999999):
            changed = [(*row[:5], bad_id) if row[0] == alias_id else row
                       for row in self.store.basicTypes()]
            with self.subTest(bad_id=bad_id), self.assertRaises(ValueError):
                self.store.save(self.store.units(), changed)
        with self.assertRaises(ValueError):
            self.store.save(self.store.units(), [(*row[:5], alias_id) if row[0] == target_id else row
                                                for row in self.store.basicTypes()])
        with self.assertRaises(ValueError):
            self.store.save(self.store.units(), [row for row in self.store.basicTypes() if row[0] != target_id])
        self.assertEqual(list(self.conn.iterdump()), before)
        self.store.save(self.store.units(), [(*row[:5], None) if row[0] == alias_id else row
                                            for row in self.store.basicTypes()])
        self.assertIsNone(self.store.basicTypes()[-1][5])

    def test_alias_selector_pending_rows_cancel_and_save(self):
        """Filter alias choices using pending rows and persist the selected temporary ID.

        @return [None] Verify labels follow renames, cancellation discards edits and Save resolves IDs.
        """
        from ElConstants import UNIT_REFERENCE_ROLE
        from PyQt6.QtCore import Qt
        dialog = UnitsDialog(self.scheme)
        initial = list(self.conn.iterdump())
        dialog.appendRow(dialog.typesModel, (None, 'Pending target', 'X', None, None, None))
        dialog.appendRow(dialog.typesModel, (None, 'Pending alias', 'X', None, None, None))
        target_row = dialog.typesModel.rowCount() - 2
        alias_row = target_row + 1
        target_id = dialog.typesModel.item(target_row, 0).data(Qt.ItemDataRole.UserRole)
        alias_id = dialog.typesModel.item(alias_row, 0).data(Qt.ItemDataRole.UserRole)
        delegate = dialog.ui.b_types_tbl.itemDelegateForColumn(5)
        index = dialog.typesModel.index(alias_row, 5)
        editor = delegate.createEditor(dialog, None, index)
        self.assertGreaterEqual(editor.findData(target_id), 0)
        self.assertEqual(editor.findData(alias_id), -1)
        editor.setCurrentIndex(editor.findData(target_id))
        delegate.setModelData(editor, dialog.typesModel, index)
        self.assertEqual(index.data(UNIT_REFERENCE_ROLE), target_id)
        dialog.typesModel.item(target_row, 1).setText('Renamed target')
        self.assertEqual(index.data(), 'Renamed target')
        self.assertNotIn(alias_id, dialog.basicTypes())
        dialog.retranslate()
        self.assertEqual(index.data(UNIT_REFERENCE_ROLE), target_id)
        dialog.reject()
        self.assertEqual(list(self.conn.iterdump()), initial)
        with mock.patch.object(QMessageBox, 'critical') as error:
            dialog.accept()
        self.assertFalse(error.called, error.call_args)
        types = {row[1]: row for row in self.store.basicTypes()}
        self.assertEqual(types['Pending alias'][5], types['Renamed target'][0])
        dialog.deleteLater()

    def test_v10_alias_migration_is_atomic_and_preserves_rows(self):
        """Upgrade v9 with an empty alias column and roll back a failure after DDL.

        @return [None] Verify preserved data, current version and repeatable migration.
        """
        types = [row[:5] for row in self.store.basicTypes()]
        with self.conn:
            self.conn.execute('ALTER TABLE BASIC_TYPES DROP COLUMN alias_of_id')
            self.conn.execute("UPDATE ENVIRONMENT SET value='9' WHERE name='db_version'")
        before = list(self.conn.iterdump())
        original = db._createBasicTypeAliases

        def fail_after_ddl(conn):
            """Inject failure after the alias column is created.

            @param conn [SQLiteConnector] Disposable test database connector.
            @return [None] Raise a deliberate migration failure.
            """
            original(conn)
            raise RuntimeError('Injected alias migration failure')

        with mock.patch.object(db, '_createBasicTypeAliases', side_effect=fail_after_ddl):
            with self.assertRaises(RuntimeError):
                self.scheme.migrate()
        self.assertEqual(list(self.conn.iterdump()), before)
        self.scheme.migrate()
        self.assertEqual(self.scheme.getDBVersion(), db.DB_VERSION)
        self.assertEqual(self.store.basicTypes(), [(*row, None) for row in types])
        before = list(self.conn.iterdump())
        self.scheme.migrate()
        self.assertEqual(list(self.conn.iterdump()), before)
