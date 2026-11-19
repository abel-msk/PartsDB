"""Resolve column settings through ancestors without writing on display."""
import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from ElData.ElDBScheme import DBFactory, ELEMENT_FIELDS_DISPLAY, defaultHeaderPosition
from ElPartsTable import PartsTableModel, TableView
from PyQt6.QtWidgets import QTableView, QListWidget
from tests.qt_support import application

app = application()


class TestHeaderInheritance(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="partsdb-inheritance-")
        self.addCleanup(self.tmp.cleanup)
        self.factory = DBFactory(os.path.join(self.tmp.name, "test.sqlite"))
        self.addCleanup(self.factory.disconnect)
        self.root = self.factory.appendType("Root", None)
        self.parent = self.factory.appendType("Parent", self.root)
        self.child = self.factory.appendType("Child", self.parent)

    def configure(self, section, field="value", **settings):
        header = self.factory.getHeadersByType(section.recId)[field]
        for key, value in settings.items():
            header[key] = value
        header.save()
        return header

    def test_root_defaults_and_no_writes(self):
        header = self.child.refreshHeaders()["value"]
        self.assertEqual(header["display"], ELEMENT_FIELDS_DISPLAY["value"])
        self.assertEqual(header["position"], defaultHeaderPosition("value"))
        self.assertEqual(self.factory.scheme.loadHeaders(self.child.recId), [])

    def test_nearest_ancestor_and_per_column_fallback(self):
        self.configure(self.root, display="Root", hidden=True, width=177, position=2)
        self.configure(self.root, "description", display="Root description")
        self.configure(self.parent, display="Parent", hidden=False, width=88)
        self.configure(self.child, "part_num", display="Child")
        headers = self.child.refreshHeaders()
        self.assertEqual(headers["value"]["display"], "Parent")
        self.assertFalse(headers["value"]["hidden"])
        self.assertEqual(headers["value"]["width"], 88)
        self.assertEqual(headers["description"]["display"], "Root description")
        self.assertEqual(headers["part_num"]["display"], "Child")
        self.assertEqual(len(self.factory.scheme.loadHeaders(self.child.recId)), 1)

    def test_edit_inherited_header_creates_local_override(self):
        ancestor = self.configure(self.root, display="Root", hidden=True, width=177)
        header = self.child.refreshHeaders()["value"]
        self.assertEqual(header.id, -1)
        self.assertEqual(header["type_id"], self.child.recId)
        header["width"] = 99
        header.save()
        self.assertNotEqual(header.id, ancestor.id)
        child = self.child.refreshHeaders()["value"]
        self.assertEqual((child["display"], child["hidden"], child["width"]), ("Root", True, 99))
        self.assertEqual(self.root.refreshHeaders()["value"]["width"], 177)

    def test_reopening_table_sees_parent_changes(self):
        self.configure(self.root, display="Before")
        self.assertEqual(PartsTableModel(self.factory, self.child).headers["value"]["display"], "Before")
        self.configure(self.root, display="After")
        self.assertEqual(PartsTableModel(self.factory, self.child).headers["value"]["display"], "After")

    def test_table_applies_inherited_visibility_width_and_order(self):
        self.configure(self.root, hidden=True)
        self.configure(self.root, "part_num", width=177, position=-1)
        widget = QTableView()
        documents = QListWidget()
        table = TableView(self.factory, widget, documents)
        table.loadData(self.child)
        from ElData import ElDBScheme
        value_column = ElDBScheme.ELEMENT_FLD_NAMES.index("value") - 2
        name_column = ElDBScheme.ELEMENT_FLD_NAMES.index("part_num") - 2
        self.assertTrue(widget.isColumnHidden(value_column))
        self.assertEqual(widget.columnWidth(name_column), 177)
        self.assertEqual(widget.horizontalHeader().visualIndex(name_column), 0)
        self.assertEqual(self.factory.scheme.loadHeaders(self.child.recId), [])

    def test_propagation_copies_effective_inherited_settings(self):
        self.configure(self.root, display="Inherited", hidden=True)
        self.parent.propagateHeaders()
        self.assertTrue(self.factory.scheme.loadHeaders(self.child.recId))
        header = self.child.refreshHeaders()["value"]
        self.assertEqual(header["display"], "Inherited")
        self.assertTrue(header["hidden"])
