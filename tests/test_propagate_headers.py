"""Header propagation uses only temporary inventory databases."""
import os
import sqlite3
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from ElConfig import ElConfig
from ElData.ElDBScheme import DBFactory, ELEMENT_FLD_NAMES, HEADER_FLD_NAMES
from ElMainWindow import MainWindow
from tests.qt_support import application

app = application()


class TestPropagateHeaders(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="partsdb-propagate-")
        self.addCleanup(self.tmp.cleanup)
        self.factory = DBFactory(os.path.join(self.tmp.name, "test.sqlite"))
        self.addCleanup(self.factory.disconnect)
        self.parent = self.factory.appendType("Parent", None)
        self.source = self.factory.appendType("Source", self.parent)
        self.child = self.factory.appendType("Child", self.source)
        self.grandchild = self.factory.appendType("Grandchild", self.child)
        self.sibling = self.factory.appendType("Sibling", self.parent)
        self.db = self.factory.scheme.db.conn

    def snapshot(self, section):
        return self.db.execute("SELECT * FROM HEADERS WHERE type_id=? ORDER BY field_name",
                               (section.recId,)).fetchall()

    def settings(self, section):
        headers = section.refreshHeaders()
        return {name: {field: headers[name][field] for field in HEADER_FLD_NAMES
                       if field not in ("id", "type_id")}
                for name in ELEMENT_FLD_NAMES[2:]}

    def test_all_settings_defaults_and_all_descendants(self):
        # A separate editor can change headers after the tree has cached them.
        self.source.getHeaders()
        header = self.factory.getHeadersByType(self.source.recId)["value"]
        for field, value in dict(label="L", display="Номинал 'test'", hidden=True,
                                 sort=True, align="RIGHT", width=123, position=8).items():
            header[field] = value
        header.save()
        for section in (self.child, self.grandchild, self.sibling):
            header = section.getHeaders()["description"]
            header["hidden"] = True
            header["width"] = 77
            header.save()
        before = {section.recId: self.snapshot(section)
                  for section in (self.parent, self.source, self.sibling)}
        part = self.factory.createPart(self.grandchild, {"part_num": "Keep"})
        self.assertEqual(self.source.propagateHeaders(), 2)
        expected = self.settings(self.source)
        for section in (self.child, self.grandchild):
            self.assertEqual(section.getHeaders()["value"]["width"], 123)
            self.assertEqual(self.settings(section), expected)
        for section in (self.parent, self.source, self.sibling):
            self.assertEqual(self.snapshot(section), before[section.recId])
        self.assertEqual(self.factory.scheme.loadPart(part.id)[ELEMENT_FLD_NAMES.index("part_num")], "Keep")
        self.source.propagateHeaders()
        self.assertEqual(len(self.snapshot(self.child)), len(ELEMENT_FLD_NAMES[2:]))

    def test_failure_rolls_back_every_descendant(self):
        before = {section.recId: self.snapshot(section) for section in (self.child, self.grandchild)}
        self.db.execute("""CREATE TRIGGER fail_headers BEFORE INSERT ON HEADERS
            WHEN NEW.type_id = {} BEGIN SELECT RAISE(ABORT, 'test failure'); END""".format(
                self.grandchild.recId))
        with self.assertRaises(sqlite3.IntegrityError):
            self.source.propagateHeaders()
        for section in (self.child, self.grandchild):
            self.assertEqual(self.snapshot(section), before[section.recId])

    def test_leaf_is_noop(self):
        self.assertEqual(self.grandchild.propagateHeaders(), 0)
        self.assertEqual(self.snapshot(self.grandchild), [])

    def test_button_uses_selected_tree_type(self):
        window = MainWindow(self.factory, ElConfig())
        self.addCleanup(window.close)
        window.typesTree.load()
        root = window.typesTree.rootNode.child(0)
        source_item = next(root.child(i) for i in range(root.rowCount())
                           if root.child(i).text() == "Source")
        window.typesTree.selectItem(source_item)
        window.CloneHdrBtn.click()
        self.assertEqual(self.settings(self.child), self.settings(self.source))
        self.assertTrue(self.snapshot(self.grandchild))
        with mock.patch.object(window.typesTree, "getSelectedIndex", return_value=None):
            window.CloneHdrBtn.click()
