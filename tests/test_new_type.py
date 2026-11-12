"""Unit tests: create a new part type, then add the first and the second part to it.

Covers both the DB layer (DBFactory / Headers) and the table model the UI uses
(ElPartsTable.PartsTableModel). Every test works on its own temporary DB.

Run from the project root:
    python -m unittest tests.test_new_type -v
"""
import os
import shutil
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

import ElDBScheme
from ElDBScheme import DBFactory, Type
from ElPartsTable import PartsTableModel

TYPE_NAME = "NewType"
PART1 = "AAA-001"
PART2 = "BBB-002"

app = QApplication.instance() or QApplication(sys.argv)


class NewTypeTestCase(unittest.TestCase):
    def setUp(self):
        self.tmpDir = tempfile.mkdtemp(prefix="partsdb-test-")
        self.dbFile = os.path.join(self.tmpDir, "test.sqlite")
        self.factory = DBFactory(self.dbFile)
        ElDBScheme.DB_FACTORY = self.factory
        self.theType: Type = self.factory.appendType(TYPE_NAME, None)

    def tearDown(self):
        self.factory.disconnect()
        shutil.rmtree(self.tmpDir, ignore_errors=True)

    def reopen(self) -> DBFactory:
        """Close and reopen the DB to make sure data really is persisted."""
        self.factory.disconnect()
        self.factory = DBFactory(self.dbFile)
        ElDBScheme.DB_FACTORY = self.factory
        return self.factory


class TestCreateType(NewTypeTestCase):
    def test_type_is_created(self):
        self.assertGreater(self.theType.recId, 0)
        self.assertEqual(self.theType.name, TYPE_NAME)

        factory = self.reopen()
        names = [t.name for t in factory.getRootTypes()]
        self.assertIn(TYPE_NAME, names)
        self.assertEqual(factory.getTypeByPath(TYPE_NAME).recId, self.theType.recId)

    def test_new_type_has_no_parts(self):
        self.assertEqual(len(self.factory.loadPartsByType(self.theType)), 0)

    def test_new_type_default_headers(self):
        # No HEADERS rows are written for a new type; defaults come from code
        self.assertEqual(len(self.theType.getHeaders()), 0)
        headers = self.theType.getHeaders()
        self.assertEqual(headers["icon"]["position"], ElDBScheme.ICON_COLUMN_POSITION)
        self.assertEqual(headers["icon"]["display"], ElDBScheme.ELEMENT_FIELDS_DISPLAY["icon"])
        positions = [headers[f]["position"] for f in ElDBScheme.defaultColumnOrder()]
        self.assertEqual(positions, list(range(len(positions))), "positions must be unique and gap-free")

    def test_new_type_header_saved_with_position(self):
        hdr = self.theType.getHeaders()["icon"]
        hdr["width"] = 60
        hdr.save()
        self.assertGreater(hdr.id, 0)

        factory = self.reopen()
        saved = factory.getHeadersByType(self.theType.recId)["icon"]
        self.assertEqual(saved.id, hdr.id)
        self.assertEqual(saved["position"], ElDBScheme.ICON_COLUMN_POSITION)
        self.assertEqual(saved["width"], 60)


class TestAddPartsDB(NewTypeTestCase):
    def test_add_first_part(self):
        part = self.factory.createPart(self.theType, {"part_num": PART1})
        self.assertGreater(part.id, 0)
        self.assertEqual(part["part_num"], PART1)
        self.assertEqual(part["type_id"], self.theType.recId)

        factory = self.reopen()
        parts = factory.loadPartsByType(factory.getTypeByPath(TYPE_NAME))
        self.assertEqual(len(parts), 1)
        self.assertEqual(parts[0]["part_num"], PART1)

    def test_add_second_part(self):
        part1 = self.factory.createPart(self.theType, {"part_num": PART1})
        part2 = self.factory.createPart(self.theType, {"part_num": PART2})
        self.assertNotEqual(part1.id, part2.id)

        factory = self.reopen()
        parts = factory.loadPartsByType(factory.getTypeByPath(TYPE_NAME))
        self.assertEqual(len(parts), 2)
        self.assertEqual([p["part_num"] for p in parts], [PART1, PART2])  # ORDER BY part_num


class TestAddPartsModel(NewTypeTestCase):
    """Same scenario through PartsTableModel, the way TableView.addRow does it."""

    def setUp(self):
        super().setUp()
        self.model = PartsTableModel(self.factory, self.theType)
        self.inserted = []  # (first, last, rowCount before insert)
        self.model.rowsAboutToBeInserted.connect(
            lambda parent, first, last: self.inserted.append((first, last, self.model.rowCount())))
        self.partNumColumn = ElDBScheme.ELEMENT_FLD_NAMES.index("part_num") - 2

    def addRow(self, partNum):
        part = self.factory.createPart(self.theType, {"part_num": partNum})
        self.model.appendRow(part)
        return part

    def assertAppended(self, expectedRow):
        first, last, rowsBefore = self.inserted[-1]
        self.assertEqual((first, last), (expectedRow, expectedRow),
                         "appendRow must announce the new row at index rowCount() (was %d)" % rowsBefore)

    def test_empty_model(self):
        self.assertEqual(self.model.rowCount(), 0)

    def test_add_first_row(self):
        part = self.addRow(PART1)
        self.assertEqual(self.model.rowCount(), 1)
        self.assertAppended(0)
        index = self.model.index(0, self.partNumColumn)
        self.assertEqual(index.data(Qt.ItemDataRole.DisplayRole), PART1)
        self.assertEqual(index.data(Qt.ItemDataRole.UserRole).id, part.id)

    def test_add_second_row(self):
        self.addRow(PART1)
        part2 = self.addRow(PART2)
        self.assertEqual(self.model.rowCount(), 2)
        self.assertAppended(1)
        index = self.model.index(1, self.partNumColumn)
        self.assertEqual(index.data(Qt.ItemDataRole.DisplayRole), PART2)
        self.assertEqual(index.data(Qt.ItemDataRole.UserRole).id, part2.id)

        # A fresh model (type reopened in the UI) shows both rows
        self.assertEqual(PartsTableModel(self.factory, self.theType).rowCount(), 2)


if __name__ == "__main__":
    unittest.main()
