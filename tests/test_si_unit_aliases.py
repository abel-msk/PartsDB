"""Editable SI aliases, migration atomicity and matching are verified on temporary catalogs."""
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from ElConstants import UNIT_ALIAS_COLUMN, MATCHING_LABEL_ROLE
from ElData import ElDBScheme as database
from ElData.ElDBDataUnits import UnitsDataStore
from ElPartsMatching import PartsMatching
from ElUnitsDialog import UnitsDialog
from tests.qt_support import application

app = application()


class SiUnitAliasesTests(unittest.TestCase):
    """Verify persisted alternate unit spellings without touching the personal inventory.

    @attr factory [DBFactory] Disposable catalog factory.
    @attr store [UnitsDataStore] Public reference access for units and aliases.
    @attr conn [sqlite3.Connection] Test-only borrowed handle for migration assertions.
    """

    def setUp(self):
        """Create a fresh current-version catalog and register its cleanup.

        @return [None] Prepare temporary reference data and a test connection.
        """
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.factory = database.DBFactory(str(Path(folder.name) / 'catalog.sqlite'))
        self.addCleanup(self.factory.disconnect)
        self.store = UnitsDataStore(self.factory.scheme)
        self.conn = self.factory.scheme.db.conn

    def test_standard_resistance_aliases_are_persisted_and_linked(self):
        """Keep alternate spellings in the reference table rather than matcher constants.

        @return [None] Verify aliases point to existing units with the expected factors.
        """
        units = {row[1]: row for row in self.store.units()}
        aliases = self.store.aliases()
        self.assertIn('кОм', aliases[units['Kiloohm'][0]])
        self.assertIn('kR', aliases[units['Kiloohm'][0]])
        self.assertIn('Ω', aliases[units['Ohm'][0]])
        self.assertIn('МОм', aliases[units['Megaohm'][0]])
        self.assertEqual(units['Kiloohm'][5], 1000)
        self.assertEqual(units['Megaohm'][5], 1000000)
        self.assertEqual(self.conn.execute('SELECT marker FROM SI_UNIT_ALIASES WHERE unit_id=? AND marker=?',
                                          (units['Kiloohm'][0], 'кОм')).fetchone(), ('кОм',))

    def test_alias_changes_control_matching_and_are_not_recreated(self):
        """Removing a saved alias disables it; adding a custom alias immediately enables it.

        @return [None] Verify uppercased comparisons, multiplier reuse and no hidden hardcoded fallback.
        """
        units = self.store.units()
        kilo_id = next(row[0] for row in units if row[1] == 'Kiloohm')
        section = self.factory.appendType('Resistors', None, 3)
        card = self.factory.createPart(section, {'value': 1000, 'units': 'R', 'part_num': ''})
        aliases = dict(self.store.aliases())
        aliases[kilo_id] = ['customK']
        self.store.save(units, self.store.basicTypes(), aliases)
        matcher = PartsMatching(self.factory)
        self.assertEqual(matcher.findCandidates({'kind': 'resistor', 'value': '1кОм'}), [])
        found = matcher.findCandidates({'kind': 'resistor', 'value': '1CUSTOMK'})
        self.assertEqual([match.part_id for match in found], [card.id])
        before = list(self.conn.iterdump())
        self.factory.scheme.migrate()
        self.assertEqual(list(self.conn.iterdump()), before)
        updated = [(*row[:5], 2000, row[6]) if row[0] == kilo_id else row for row in units]
        self.store.save(updated, self.store.basicTypes())
        self.assertEqual(PartsMatching(self.factory).findCandidates({'kind': 'resistor', 'value': '1customK'}), [])

    def test_pending_unit_alias_and_deletion_resolve_the_owner_id(self):
        """Persist aliases for a new unit and cascade them when that unit is removed.

        @return [None] Verify temporary ID resolution and lifecycle without duplicate multiplier fields.
        """
        units = self.store.units()
        base_id = next(row[0] for row in units if row[1] == 'Ohm')
        pending = (-1, 'Customohm', 'Своя единица', 'zR', 'зОм', 250, base_id)
        self.store.save(units + [pending], self.store.basicTypes(), {-1: ['customR', ' customR ']})
        unit_id = next(row[0] for row in self.store.units() if row[1] == 'Customohm')
        self.assertEqual(self.store.aliases()[unit_id], ('customR',))
        self.store.save(units, self.store.basicTypes())
        self.assertNotIn(unit_id, self.store.aliases())

    def test_invalid_alias_data_cannot_change_reference_rows(self):
        """Reject aliases for missing owners and malformed spelling lists before any writes.

        @return [None] Assert the entire catalog dump remains unchanged after rejected saves.
        """
        units = self.store.units()
        before = list(self.conn.iterdump())
        for aliases in ({99999: ['x']}, {units[0][0]: ['']}, {units[0][0]: 'not a list'}):
            with self.subTest(aliases=aliases), self.assertRaises(ValueError):
                self.store.save(units, self.store.basicTypes(), aliases)
        self.assertEqual(list(self.conn.iterdump()), before)

    def test_dialog_edits_aliases_and_cancel_preserves_the_saved_list(self):
        """Edit spellings through the SI table while keeping database IDs hidden.

        @return [None] Verify cancel discards edits and Save commits comma/semicolon-separated aliases.
        """
        before = self.store.aliases()
        dialog = UnitsDialog(self.factory.scheme)
        self.addCleanup(dialog.close)
        self.assertTrue(dialog.ui.si_units_tbl.isColumnHidden(0))
        target_row = next(row for row in range(dialog.unitsModel.rowCount())
                          if dialog.unitsModel.item(row, 1).text() == 'Kiloohm')
        dialog.unitsModel.item(target_row, UNIT_ALIAS_COLUMN).setText('кОм, KOhms; customK')
        dialog.reject()
        self.assertEqual(self.store.aliases(), before)
        dialog = UnitsDialog(self.factory.scheme)
        self.addCleanup(dialog.close)
        dialog.unitsModel.item(target_row, UNIT_ALIAS_COLUMN).setText('кОм, KOhms; customK')
        dialog.accept()
        unit_id = next(row[0] for row in self.store.units() if row[1] == 'Kiloohm')
        self.assertEqual(set(self.store.aliases()[unit_id]), {'кОм', 'KOhms', 'customK'})

    def test_reference_save_refreshes_project_candidates_immediately(self):
        """Refresh displayed matches after editing a unit alias in the main window.

        @return [None] A previously unknown unit starts matching without reimporting the project.
        """
        from PyQt6.QtWidgets import QDialog, QMessageBox
        from ElConfig import ElConfig
        from ElMainWindow import MainWindow
        from ElPluginMgr.repository import ProjectRepository
        from ElPartsPluginApi.importers import ImportedComponent, ImportedProject
        section = self.factory.appendType('Resistors', None, 3)
        self.factory.createPart(section, {'value': 1, 'units': 'myKilo', 'part_num': ''})
        ProjectRepository(self.factory.scheme).save(
            ImportedProject('Aliases project', components=[ImportedComponent('r1', 'R1', kind='resistor', value_raw='1K')]),
            'test.importer', 'file:///tmp/test.kicad_pro')
        config = ElConfig()
        config.filename = str(Path(self.factory.db_file).with_suffix('.conf'))
        config.set_value('language', 'en')
        window = MainWindow(self.factory, config)
        self.addCleanup(window.close)
        self.addCleanup(window.languageManager.close)
        self.assertEqual(window.projWindow.componentsModel.item(0, 7).text(), 'NO')
        self.assertEqual(window.projWindow.unmatchedModel.rowCount(), 1)

        def save_alias(dialog):
            """Simulate confirming an edited alias through the real dialog save path.

            @param dialog [UnitsDialog] Reference editor opened by MainWindow.onUnits.
            @return [QDialog.DialogCode] Accepted after saving the pending alias text.
            """
            row = next(i for i in range(dialog.unitsModel.rowCount())
                       if dialog.unitsModel.item(i, 1).text() == 'Kiloohm')
            item = dialog.unitsModel.item(row, UNIT_ALIAS_COLUMN)
            item.setText(item.text() + ', myKilo')
            dialog.accept()
            return QDialog.DialogCode.Accepted

        with mock.patch.object(UnitsDialog, 'exec', save_alias), mock.patch.object(QMessageBox, 'critical') as error:
            window.onUnits()
            error.assert_not_called()
        window.d_proj_link_cmd.click()
        for _ in range(20):
            app.processEvents()
        self.addCleanup(window.projWindow.matchingLog.close)
        self.assertEqual(window.projWindow.componentsModel.item(0, 7).text(), 'YES')
        self.assertEqual(window.projWindow.componentsModel.item(0, 7).data(MATCHING_LABEL_ROLE), '1.0')
        self.assertEqual(window.projWindow.unmatchedModel.rowCount(), 0)

    def test_v11_migration_rolls_back_table_seed_and_version_then_preserves_existing_units(self):
        """Upgrade v10 atomically without overwriting unit edits or restoring removed aliases later.

        @return [None] Verify failure rollback, successful seed and repeatable no-op migration.
        """
        units = self.store.units()
        with self.conn:
            self.conn.execute('DROP TABLE SI_UNIT_ALIASES')
            self.conn.execute("UPDATE ENVIRONMENT SET value='10' WHERE name='db_version'")
        before = list(self.conn.iterdump())
        create_aliases = database._createSiUnitAliases

        def fail_after_seed(conn):
            """Inject a failure after the alias DDL and inserts.

            @param conn [SQLiteConnector] Driver connected to the disposable database.
            @return [None] Raise the requested simulated failure.
            """
            create_aliases(conn)
            raise RuntimeError('Injected SI alias failure')

        with mock.patch.object(database, '_createSiUnitAliases', side_effect=fail_after_seed):
            with self.assertRaisesRegex(RuntimeError, 'Injected SI alias'):
                self.factory.scheme.migrate()
        self.assertEqual(list(self.conn.iterdump()), before)
        self.factory.scheme.migrate()
        self.assertEqual(self.factory.scheme.getDBVersion(), database.DB_VERSION)
        self.assertEqual(self.store.units(), units)
        self.assertTrue(self.store.aliases())
        before = list(self.conn.iterdump())
        self.factory.scheme.migrate()
        self.assertEqual(list(self.conn.iterdump()), before)
