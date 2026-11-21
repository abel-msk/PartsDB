"""Candidate matching and project rendering use disposable catalogs and configured references."""
import tempfile
import unittest
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMainWindow

from ElConstants import (MATCHING_CANDIDATES_ROLE, MATCHING_LABEL_ROLE, MATCHING_STATUS_ROLE,
                         PROJECT_MATCHED_COLOR, PROJECT_UNMATCHED_COLOR)
from ElData.ElDBScheme import DBFactory
from ElParts import Ui_MainWindow
from ElPartsMatching import PartsMatching
from ElPluginMgr.repository import ProjectRepository
from ElPartsPluginApi.importers import ImportedComponent, ImportedProject
from ElProjWindow import ProjWindow
from tests.qt_support import application

app = application()


class MatchingTestWindow(QMainWindow, Ui_MainWindow):
    """Provide generated project widgets for candidate rendering tests.

    @attr prj_parts_all [QTableView] Main project component table from the generated form.
    """


class PartsMatchingTests(unittest.TestCase):
    """Verify literal/SI matching, scope, aliases, mounting and hidden catalog references.

    @attr root [Path] Temporary directory containing the disposable catalog.
    @attr factory [DBFactory] Active test catalog, closed before temporary files are removed.
    @attr conn [sqlite3.Connection] Borrowed test handle used only for fixture arrangement.
    """

    def setUp(self):
        """Create isolated SI/basic-type references and an empty catalog.

        @return [None] Register cleanup of the connection and temporary directory.
        """
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.factory = DBFactory(str(self.root / 'catalog.sqlite'))
        self.addCleanup(self.factory.disconnect)
        self.conn = self.factory.scheme.db.conn

    def section(self, name, basic_type_id, parent=None):
        """Create a catalog section with a selected basic type.

        @param name [str] Display name unrelated to the matching algorithm.
        @param basic_type_id [int] Existing reference ID.
        @param parent [Type, None] Optional parent section.
        @return [Type] Persisted temporary catalog section.
        """
        return self.factory.appendType(name, parent, basic_type_id)

    def part(self, section, **values):
        """Create a stock card without requiring a model for passive parts.

        @param section [Type] Temporary catalog section.
        @param values [dict] Raw stock columns; explicit part_num is supplied when absent.
        @return [Part] Persisted test stock card.
        """
        return self.factory.createPart(section, dict(part_num='', **values) if 'part_num' not in values else values)

    def keys(self, section, fields):
        """Set exact visible matching columns in a given order.

        @param section [Type] Section whose local headers are configured.
        @param fields [list[str]] Stock field names ordered for candidate labels.
        @return [None] Persist key flags, visibility and order for all relevant fields.
        """
        headers = section.refreshHeaders()
        for field in ('part_num', 'device_code', 'value', 'units', 'description', 'package'):
            header = headers[field]
            header['is_key'] = field in fields
            header['hidden'] = False
            if field in fields:
                header['position'] = fields.index(field)
            header.save()

    def candidates(self, kind, value, footprint='Capacitor_SMD:C_0805'):
        """Run a fresh read-only matching pass.

        @param kind [str] Imported category.
        @param value [str] Raw Value text; nominal/model fields are deliberately unused.
        @param footprint [str] Imported footprint text.
        @return [list[CatalogMatch]] Candidate catalog references and display keys.
        """
        return PartsMatching(self.factory).findCandidates({'kind': kind, 'value': value, 'footprint': footprint})

    def test_si_value_units_and_equivalent_prefixes(self):
        """Keep equal quantities and reject equal raw numbers with other dimensions/prefixes.

        @return [None] Assert split value/unit keys and scaled SI comparisons.
        """
        section = self.section('Arbitrary section title', 2)
        expected = self.part(section, value=100, units='нФ', package='0805')
        equivalent = self.part(section, value='0.1uF', units='', package='SMD')
        self.part(section, value=100, units='мкФ', package='SMD')
        self.part(section, value=100, units='V', package='SMD')
        found = self.candidates('capacitor', '100nF')
        self.assertEqual([item.part_id for item in found], [expected.id, equivalent.id])
        self.assertEqual(found[0].matched_fields, ('value',))
        self.assertEqual(found[0].key_text, '100.0')
        self.assertEqual([item.part_id for item in self.candidates('capacitor', '0,1µF')],
                         [expected.id, equivalent.id])

    def test_kind_and_descendants_are_used_instead_of_section_name(self):
        """Include recursive descendants, even with another basic type; exclude unrelated roots.

        @return [None] Check recursive type scoping and duplicate-free candidate ordering.
        """
        root = self.section('Not named capacitor', 2)
        child = self.section('Child with generic kind', 1, root)
        grandchild = self.section('Deep subtree', 1, child)
        unrelated = self.section('Capacitor by display name only', 1)
        self.keys(grandchild, ['value'])
        expected = self.part(grandchild, value='100nF')
        self.keys(unrelated, ['value'])
        self.part(unrelated, value='100nF')
        self.assertEqual([item.part_id for item in self.candidates('capacitor', '100nF')], [expected.id])
        self.assertEqual(self.candidates('unknown', '100nF'), [])

    def test_literal_value_uses_any_visible_key_and_returns_first_matching_key(self):
        """Search key values exactly and show the first matching field, not an unrelated part number.

        @return [None] Verify case-insensitive model equality, ordering and prefix nonmatches.
        """
        section = self.section('Power ICs', 6)
        self.keys(section, ['device_code', 'part_num'])
        expected = self.part(section, part_num='Different model', device_code='AMS1117-3.3', package='SOT-223')
        self.part(section, part_num='AMS1117-3.3-extra')
        self.part(section, part_num='Other', description='AMS1117-3.3')
        before = list(self.conn.iterdump())
        found = self.candidates('ic', 'ams1117-3.3', 'Package_SOT:SOT223')
        self.assertEqual([item.part_id for item in found], [expected.id])
        self.assertEqual((found[0].key_text, found[0].matched_fields), ('AMS1117-3.3', ('device_code',)))
        self.assertEqual(list(self.conn.iterdump()), before)

    def test_hidden_keys_and_units_do_not_supply_matching_values(self):
        """Exclude hidden junk from both numeric and unit stages.

        @return [None] Check hidden value keys and hidden unit metadata.
        """
        section = self.section('Capacitors', 2)
        self.part(section, value=100, units='nF', device_code='100nF')
        self.keys(section, ['value', 'device_code'])
        header = section.refreshHeaders()['device_code']
        header['hidden'] = True
        header.save()
        unit_header = section.refreshHeaders()['units']
        unit_header['hidden'] = True
        unit_header.save()
        self.assertEqual(self.candidates('capacitor', '100nF'), [])

    def test_si_marker_can_be_a_separate_key(self):
        """Use a standalone unit key independently of a numeric key.

        @return [None] Match a component when its unit is stored in another selected key.
        """
        section = self.section('Capacitors', 2)
        self.keys(section, ['value', 'device_code'])
        expected = self.part(section, value=100, device_code='nF')
        self.assertEqual([item.part_id for item in self.candidates('capacitor', '100nF')], [expected.id])

    def test_unit_comparison_uses_uppercase_and_preserves_all_multiplier_candidates(self):
        """Treat unit spellings without case while retaining every colliding interpretation.

        @return [None] Match Russian kilo/mega forms and keep ambiguous milli/mega candidates explicit.
        """
        section = self.section('Resistors', 3)
        milli = self.part(section, value=1, units='mR')
        mega = self.part(section, value=1, units='M')
        kilo = self.part(section, value=1, units='кОм')
        for source in ('1mΩ', '1MΩ'):
            with self.subTest(source=source):
                self.assertEqual([item.part_id for item in self.candidates('resistor', source)], [milli.id, mega.id])
        self.assertEqual([item.part_id for item in self.candidates('resistor', '1M')], [milli.id, mega.id])
        for source in ('1k', '1K', '1кОм', '1КОМ', '1000R'):
            with self.subTest(source=source):
                self.assertEqual([item.part_id for item in self.candidates('resistor', source)], [kilo.id])

    def test_russian_resistor_suffixes_match_split_value_and_unit_keys(self):
        """Reproduce the configured catalog: value and units are keys, part_num is hidden.

        @return [None] Match resistor Value forms across case and normalized Russian ohm suffixes.
        """
        section = self.section('Резистор', 3)
        self.keys(section, ['value', 'units'])
        hidden = section.refreshHeaders()['part_num']
        hidden['hidden'] = True
        hidden.save()
        self.part(section, value=1, units='кОм', package='SMD_0603')
        self.part(section, value=4.7, units='кОм', package='SMD_0603')
        self.part(section, value=10, units='кОм', package='')
        self.part(section, value=1, units='мОм', package='SMD_0603')
        for source, expected in [('1K', '1.0'), ('4.7K', '4.7'), ('10k', '10.0'), ('1M', '1.0')]:
            with self.subTest(source=source):
                found = self.candidates('resistor', source, 'Resistor_SMD:R_0805')
                self.assertEqual(len(found), 1)
                self.assertEqual(found[0].key_text, expected)

    def test_custom_units_and_basic_type_aliases_are_loaded_from_references(self):
        """Honor edited SI spellings, multipliers and a custom imported kind alias.

        @return [None] Resolve the alias to its canonical sections and use reference conversions.
        """
        section = self.section('Resistors', 3)
        expected = self.part(section, value=2, units='rk')
        with self.conn:
            base_id = self.conn.execute("SELECT id FROM SI_UNITS WHERE name='Ohm'").fetchone()[0]
            self.conn.execute("INSERT INTO SI_UNITS(name,name_ru,marker,marker_ru,multiply,base_unit_id) VALUES (?,?,?,?,?,?)",
                              ('Custom ohm', 'Тестовый ом', 'rk', 'рк', 500, base_id))
            self.conn.execute("INSERT INTO BASIC_TYPES(id,name,designator,alias_of_id) VALUES (?,?,?,?)",
                              (100, 'Custom resistor', 'CR', 3))
        self.assertEqual([item.part_id for item in self.candidates('custom_resistor', '1kR')], [expected.id])

    def test_mounting_filters_both_branches_and_defaults_populated_strings_to_smd(self):
        """Apply the clarified SMD default, explicit THT markers and the blank-package exception.

        @return [None] Check mounting rules with SI and literal component values.
        """
        for kind, basic_type_id, value, fields in [('capacitor', 2, '100nF', ['value']),
                                                 ('ic', 6, 'CHIP', ['part_num'])]:
            with self.subTest(kind=kind):
                section = self.section(kind, basic_type_id)
                kwargs = {fields[0]: value}
                smd = self.part(section, **kwargs, package='SMD 0805')
                default_smd = self.part(section, **kwargs, package='SOT-23')
                tht = self.part(section, **kwargs, package='ТНТ DIP-8')
                blank = self.part(section, **kwargs, package='')
                self.assertEqual([item.part_id for item in self.candidates(kind, value, 'UnmarkedFootprint')],
                                 [smd.id, default_smd.id, blank.id])
                self.assertEqual([item.part_id for item in self.candidates(kind, value, 'Device_THT:Thing')],
                                 [tht.id, blank.id])
                self.assertEqual(len(self.candidates(kind, value, '')), 4)

    def test_bare_decimal_value_matches_without_using_normalized_nominal_or_model(self):
        """Use source Value text and numeric equality only when there is no recognized SI suffix.

        @return [None] Match comma decimals and ignore conflicting normalized/model hints.
        """
        section = self.section('Resistors', 3)
        expected = self.part(section, value=.3)
        component = {'kind': 'resistor', 'value_raw': '0,3', 'model': 'Other',
                     'nominal_value': '999', 'nominal_unit': 'V', 'footprint': ''}
        self.assertEqual([item.part_id for item in PartsMatching(self.factory).findCandidates(component)], [expected.id])

    def test_project_model_displays_key_text_and_retains_all_candidate_ids_without_confirming(self):
        """Show the first candidate key, keep hidden IDs and preserve explicit match semantics.

        @return [None] Verify both table roles, unmatched state and ID-free displayed text.
        """
        section = self.section('Capacitors', 2)
        first = self.part(section, value=100, units='nF', package='0805')
        second = self.part(section, value=100, units='nF', package='SMD')
        repo = ProjectRepository(self.factory.scheme)
        project_id = repo.save(ImportedProject('Matching project', components=[
            ImportedComponent('c1', 'C1', kind='capacitor', value_raw='100nF', footprint='Capacitor_SMD:C')]),
            'test.importer', 'file:///tmp/project.kicad_pro')
        window = MatchingTestWindow()
        window.setupUi(window)
        self.addCleanup(window.close)
        controller = ProjWindow(self.factory, window)
        model = controller.componentsModel
        self.assertEqual(model.item(0, 7).text(), 'YES')
        self.assertEqual(model.item(0, 7).data(MATCHING_LABEL_ROLE), '100.0')
        self.assertEqual(model.item(0, 0).data(MATCHING_CANDIDATES_ROLE), (first.id, second.id))
        component_id = model.item(0, 0).data(Qt.ItemDataRole.UserRole)
        self.assertIsNotNone(component_id)
        self.assertEqual(controller.unmatchedModel.rowCount(), 0)
        self.assertEqual(repo.matches(project_id), {})
        repo.set_match(component_id, second.id)
        controller.refresh()
        self.assertEqual(model.item(0, 7).text(), 'YES')
        self.assertEqual(model.item(0, 7).data(MATCHING_LABEL_ROLE), '100.0')
        self.assertEqual(controller.unmatchedModel.rowCount(), 0)

    def test_status_buttons_filter_missing_rows_and_emit_component_identity(self):
        """Render candidate/confirmed YES and missing NO buttons with stable click identities.

        @return [None] Verify colors, filtering and clicks without modifying saved matches.
        """
        section = self.section('Resistors', 3)
        stock = self.part(section, value=1, units='kR')
        repo = ProjectRepository(self.factory.scheme)
        project_id = repo.save(ImportedProject('Buttons', components=[
            ImportedComponent('a', 'R1', kind='resistor', value_raw='1K'),
            ImportedComponent('b', 'R2', kind='resistor', value_raw='missing'),
            ImportedComponent('c', 'R3', kind='resistor', value_raw='manual')]),
            'test.importer', 'file:///tmp/buttons.kicad_pro')
        identities = {row['reference']: row['id'] for row in repo.components(project_id)}
        repo.set_match(identities['R3'], stock.id)
        window = MatchingTestWindow()
        window.setupUi(window)
        self.addCleanup(window.close)
        controller = ProjWindow(self.factory, window)
        requested = []
        controller.matchingRequested.connect(requested.append)
        self.assertEqual(controller.componentsModel.rowCount(), 3)
        self.assertEqual(controller.unmatchedModel.rowCount(), 1)
        self.assertEqual(controller.unmatchedModel.item(0, 0).text(), 'R2')
        before = list(self.conn.iterdump())
        for row in range(controller.componentsModel.rowCount()):
            model = controller.componentsModel
            reference = model.item(row, 0).text()
            found = reference != 'R2'
            index = model.index(row, 7)
            button = window.prj_parts_all.indexWidget(index)
            self.assertEqual(button.text(), 'YES' if found else 'NO')
            self.assertEqual(index.data(MATCHING_STATUS_ROLE), found)
            self.assertIn(PROJECT_MATCHED_COLOR if found else PROJECT_UNMATCHED_COLOR, button.styleSheet())
            button.click()
            self.assertEqual(requested[-1], identities[reference])
        index = controller.unmatchedModel.index(0, 7)
        missing_button = window.no_matched_tbl.indexWidget(index)
        self.assertEqual(missing_button.text(), 'NO')
        self.assertIn(PROJECT_UNMATCHED_COLOR, missing_button.styleSheet())
        missing_button.click()
        self.assertEqual(requested[-1], identities['R2'])
        controller.retranslate()
        self.assertIs(window.no_matched_tbl.indexWidget(index), missing_button)
        self.assertEqual(missing_button.text(), 'NO')
        self.assertEqual(list(self.conn.iterdump()), before)
        controller.onProjectSelected(None)
        self.assertEqual(controller.componentsModel.rowCount(), 0)
        self.assertEqual(controller.unmatchedModel.rowCount(), 0)
