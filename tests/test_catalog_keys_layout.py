"""Catalog v7 migration, key inputs, shared rendering and project width behavior."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QDialogButtonBox, QTableView, QTreeView, QStyleOptionViewItem, QListWidget
from PyQt6.QtGui import QStandardItemModel

from ElConfig import ElConfig
from ElConstants import PROJECT_TABLE_FIELDS, SUBTITLE_ROLE
from ElData.ElDBScheme import DBFactory, ELEMENT_FLD_NAMES
from ElData import ElDBDataParts, ElDBDataProj
from ElCatalogDialogs import PartValuesDialog, SectionDialog
from ElHdrEditDialog import HeaderEditDialog
from ElPartsTable import PartsTableModel, TableView
from ElProjectTableLayout import ProjectTableLayout
from ElTwoLineDelegate import TwoLineDelegate
from ElTypesTree import TypesTree
from tests.qt_support import application

app = application()


def events():
    for _ in range(5):
        app.processEvents()


class CatalogKeysTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = str(Path(self.temp.name) / 'catalog.sqlite')
        self.factory = DBFactory(self.path)
        self.addCleanup(lambda: self.factory.disconnect())

    def test_reference_inheritance_persistence_and_defaults(self):
        rows = ElDBDataParts.basicTypes(self.factory)
        self.assertIn((2, 'Capacitor', 'C', None), rows)
        root = self.factory.appendType('Any name', None, 2)
        child = self.factory.appendType('Ceramic', root)
        self.assertEqual(child.basic_type_id, 2)
        self.assertEqual([h['field_name'] for h in ElDBDataParts.keyHeaders(child)], ['value'])
        other = self.factory.appendType('Other', None)
        self.assertEqual(other.basic_type_id, 1)
        self.assertEqual([h['field_name'] for h in ElDBDataParts.keyHeaders(other)], ['part_num'])
        ElDBDataParts.setBasicType(child, 4)
        self.factory.disconnect()
        self.factory = DBFactory(self.path)
        self.assertEqual(self.factory.getTypeByID(child.recId).basic_type_id, 4)

    def test_multi_key_editor_save_and_new_part_without_part_number(self):
        section = self.factory.appendType('Resistors', None, 3)
        dialog = HeaderEditDialog(None, self.factory)
        self.addCleanup(dialog.close)
        dialog.loadData(section.recId)
        model = dialog.tableModel
        key_col = model.columnsList.index('is_key')
        package_row = model.rowsList.index('package')
        model.setData(model.index(package_row, key_col), Qt.CheckState.Checked, Qt.ItemDataRole.CheckStateRole)
        title_col = model.columnsList.index('display')
        model.setData(model.index(package_row, title_col), 'Корпус детали', Qt.ItemDataRole.EditRole)
        self.assertTrue(dialog.onSave())
        keys = ElDBDataParts.keyHeaders(section)
        self.assertEqual([h['field_name'] for h in keys], ['value', 'package'])
        entry = PartValuesDialog(None, keys)
        self.addCleanup(entry.close)
        ok = entry.buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.assertFalse(ok.isEnabled())
        entry.editors['value'].setText('1000')
        self.assertFalse(ok.isEnabled())
        entry.editors['package'].setText('0603')
        self.assertTrue(ok.isEnabled())
        self.assertEqual(entry.labels['package'].text(), 'Корпус детали')
        part = ElDBDataParts.createPart(self.factory, section, entry.values())
        self.assertEqual(part['value'], 1000)
        self.assertEqual(part['package'], '0603')
        self.assertEqual(part['part_num'], '')
        table = PartsTableModel(self.factory, section)
        for field in ('value', 'package', 'part_num'):
            font = table.headerData(ELEMENT_FLD_NAMES.index(field) - 2, Qt.Orientation.Horizontal,
                                    Qt.ItemDataRole.FontRole).value()
            self.assertEqual(font.bold(), field != 'part_num')

    def test_add_row_collects_all_configured_keys(self):
        section = self.factory.appendType('Capacitors', None, 2)
        view, docs = QTableView(), QListWidget()
        table = TableView(self.factory, view, docs)
        table.loadData(section)
        def fill(dialog):
            dialog.editors['value'].setText('47')
            return dialog.DialogCode.Accepted
        with mock.patch.object(PartValuesDialog, 'exec', fill):
            table.addRow()
        self.assertEqual(table.tableModel.rowCount(), 1)
        self.assertEqual(table.tableModel.parts[0]['value'], 47)

    def test_added_part_keeps_sort_and_selects_visible_new_row(self):
        section = self.factory.appendType('Resistors', None, 3)
        for value in range(40):
            self.factory.createPart(section, {'value': value})
        value_column = ELEMENT_FLD_NAMES.index('value') - 2
        for order, nominal in ((Qt.SortOrder.AscendingOrder, '-1'),
                               (Qt.SortOrder.DescendingOrder, '99'),
                               (Qt.SortOrder.DescendingOrder, '20')):
            with self.subTest(order=order, nominal=nominal):
                view, docs = QTableView(), QListWidget()
                table = TableView(self.factory, view, docs)
                table.loadData(section)
                view.resize(500, 200)
                view.show()
                view.sortByColumn(value_column, order)
                events()
                previous = list(table.tableModel.parts.partsAr)
                descending = previous[0]['value'] > previous[-1]['value']
                previous_ids = {part.id for part in previous}
                # Even in multiple-selection mode the new part becomes the sole selection.
                view.setSelectionMode(view.SelectionMode.MultiSelection)
                view.selectRow(0)
                view.selectRow(1)
                def fill(dialog):
                    dialog.editors['value'].setText(nominal)
                    return dialog.DialogCode.Accepted
                with mock.patch.object(PartValuesDialog, 'exec', fill):
                    table.addRow()
                events()
                parts = table.tableModel.parts.partsAr
                self.assertEqual([part['value'] for part in parts],
                                 sorted([part['value'] for part in previous] + [float(nominal)],
                                        reverse=descending))
                selected = view.selectionModel().selectedRows()
                self.assertEqual(len(selected), 1)
                new_part = view.currentIndex().data(Qt.ItemDataRole.UserRole)
                self.assertNotIn(new_part.id, previous_ids)
                self.assertEqual(selected[0].data(Qt.ItemDataRole.UserRole).id, new_part.id)
                self.assertEqual(new_part['value'], float(nominal))
                self.assertTrue(view.viewport().rect().intersects(view.visualRect(view.currentIndex())))
                self.assertEqual(view.horizontalHeader().sortIndicatorSection(), value_column)
                self.assertEqual(view.horizontalHeader().sortIndicatorOrder(), order)
                view.close()

    def test_empty_keys_rejected_without_saving(self):
        section = self.factory.appendType('Test', None)
        dialog = HeaderEditDialog(None, self.factory)
        self.addCleanup(dialog.close)
        dialog.loadData(section.recId)
        model = dialog.tableModel
        model.setData(model.index(model.rowsList.index('part_num'), model.columnsList.index('is_key')),
                      Qt.CheckState.Unchecked, Qt.ItemDataRole.CheckStateRole)
        with mock.patch('ElHdrEditDialog.QMessageBox.warning') as warning:
            self.assertFalse(dialog.onSave())
        warning.assert_called_once()
        self.assertTrue(section.refreshHeaders()['part_num']['is_key'])

    def test_v6_migration_preserves_existing_headers_and_parts(self):
        section = self.factory.appendType('Конденсатор', None)
        child = self.factory.appendType('Керамика', section)
        part = self.factory.createPart(child, {'part_num': 'old', 'value': 10})
        header = child.getHeaders()['value']
        header['display'] = 'Ёмкость'
        header['width'] = 145
        header.save()
        conn = self.factory.scheme.db.conn
        with conn:
            conn.execute('ALTER TABLE TYPES DROP COLUMN basic_type_id')
            conn.execute('ALTER TABLE HEADERS DROP COLUMN is_key')
            conn.execute('DROP TABLE BASIC_TYPES')
            conn.execute('DROP TABLE PROJECT_COLUMN_WIDTHS')
            conn.execute("UPDATE ENVIRONMENT SET value='6' WHERE name='db_version'")
        self.factory.scheme.db.set_foreign_keys(True)
        self.factory.scheme.migrate()
        self.assertTrue(self.factory.scheme.db.get_foreign_keys())
        self.factory.disconnect()
        self.factory = DBFactory(self.path)
        migrated = self.factory.getTypeByID(child.recId)
        self.assertEqual(migrated.basic_type_id, 2)
        self.assertEqual([h['field_name'] for h in ElDBDataParts.keyHeaders(migrated)], ['value'])
        self.assertEqual(migrated.getHeaders()['value']['display'], 'Ёмкость')
        self.assertEqual(migrated.getHeaders()['value']['width'], 145)
        self.assertEqual(self.factory.loadElementById(part.id)['part_num'], 'old')
        self.assertEqual(self.factory.scheme.getDBVersion(), 7)

    def test_default_key_tracks_basic_type_after_saving_width(self):
        section = self.factory.appendType('Generic', None)
        header = section.getHeaders()['part_num']
        header['width'] = 180
        header.save()
        ElDBDataParts.setBasicType(section, 2)
        self.assertEqual([h['field_name'] for h in ElDBDataParts.keyHeaders(section)], ['value'])

    def test_migration_failure_rolls_back_ddl_and_preserves_version(self):
        conn = self.factory.scheme.db.conn
        with conn:
            conn.execute('ALTER TABLE TYPES DROP COLUMN basic_type_id')
            conn.execute('ALTER TABLE HEADERS DROP COLUMN is_key')
            conn.execute('DROP TABLE BASIC_TYPES')
            conn.execute('DROP TABLE PROJECT_COLUMN_WIDTHS')
            conn.execute("UPDATE ENVIRONMENT SET value='6' WHERE name='db_version'")
        self.factory.scheme.db.set_foreign_keys(True)
        with mock.patch('ElData.ElDBScheme.PROJECT_COLUMN_WIDTHS_SQL', 'INVALID SQL'):
            with self.assertRaises(Exception):
                self.factory.scheme.migrate()
        self.assertEqual(self.factory.scheme.getDBVersion(), 6)
        self.assertTrue(self.factory.scheme.db.get_foreign_keys())
        names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertNotIn('BASIC_TYPES', names)
        self.assertNotIn('is_key', [row[1] for row in conn.execute('PRAGMA table_info(HEADERS)')])
        self.factory.scheme.migrate()
        self.assertEqual(self.factory.scheme.getDBVersion(), 7)

    def test_shared_delegate_tree_subtitle_and_config(self):
        section = self.factory.appendType('Custom', None, 4)
        tree = QTreeView()
        controller = TypesTree(self.factory, tree)
        controller.load()
        self.assertEqual(controller.treeModel.index(0, 0).data(SUBTITLE_ROLE), 'Transistor')
        self.assertIsInstance(tree.itemDelegate(), TwoLineDelegate)
        config = ElConfig()
        delegate = TwoLineDelegate(None, config)
        self.assertEqual(config.get_value('title_size', 'list_fonts'), 16)
        config.set_value('title_size', 21, 'list_fonts')
        self.assertEqual(delegate.fonts(QStyleOptionViewItem())[0].pixelSize(), 21)
        dialog = SectionDialog(None, ElDBDataParts.basicTypes(self.factory), section.name, section.basic_type_id)
        self.assertEqual(dialog.typeCombo.currentText(), 'Transistor')
        dialog.close()

    def test_widths_expand_proportionally_stop_and_remain_separate(self):
        fields = PROJECT_TABLE_FIELDS
        widths = {field: 60 + index * 10 for index, field in enumerate(fields)}
        ElDBDataProj.saveColumnWidths(self.factory, 'all', widths)
        view = QTableView()
        self.addCleanup(view.close)
        model = QStandardItemModel(2, len(fields))
        view.setModel(model)
        layout = ProjectTableLayout(view, self.factory, 'all')
        view.resize(1400, 250)
        view.show()
        events()
        header = view.horizontalHeader()
        self.assertEqual(sum(header.sectionSize(i) for i in range(len(fields))), view.viewport().width())
        ratio = header.sectionSize(0) / header.sectionSize(1)
        self.assertAlmostEqual(ratio, widths[fields[0]] / widths[fields[1]], delta=.02)
        view.resize(400, 250)
        events()
        self.assertEqual([header.sectionSize(i) for i in range(len(fields))], list(widths.values()))
        self.assertGreater(view.horizontalScrollBar().maximum(), 0)
        layout.dragging = True
        header.resizeSection(0, 123)
        layout.dragging = False
        self.assertTrue(layout.dirty)
        layout.saveUserWidths()
        self.assertEqual(ElDBDataProj.columnWidths(self.factory, 'all')[fields[0]], 123)
        self.assertEqual(ElDBDataProj.columnWidths(self.factory, 'unmatched'), {})
        view.resize(1600, 250)
        events()
        self.assertEqual(ElDBDataProj.columnWidths(self.factory, 'all')[fields[0]], 123)
        other = DBFactory(str(Path(self.temp.name) / 'other.sqlite'))
        self.addCleanup(other.disconnect)
        layout.setFactory(other)
        self.assertEqual(layout.minimums, {})
