"""Create/open database UI integration tests, using only temporary databases."""
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PyQt6.QtWidgets import QApplication, QMessageBox

import constants
import ElDBScheme
from ElConfig import ElConfig
from ElDBScheme import DBFactory
from ElMainWindow import MainWindow

app = QApplication.instance() or QApplication([])


class TestNewDatabase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="partsdb-new-db-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.old = DBFactory(str(self.root / "old.sqlite"))
        section = self.old.appendType("Old section", None)
        self.old.createPart(section, {"part_num": "OLD-001"})
        self.config = ElConfig()
        self.config.set_value(constants.CONFIG_DB_FILE, self.old.db_file)
        self.config.set_value(constants.CONFIG_DATA_PATH, self.old.dataPath)
        self.window = MainWindow(self.old, self.config)
        self.window.setStartupMode(None)
        self.addCleanup(self.cleanupWindow)
        self.previousGlobal = ElDBScheme.DB_FACTORY
        self.addCleanup(setattr, ElDBScheme, "DB_FACTORY", self.previousGlobal)

    def cleanupWindow(self):
        self.window.close()
        self.window.factory.disconnect()

    def create(self, path):
        with mock.patch("ElMainWindow.QFileDialog.getSaveFileName", return_value=(str(path), "")):
            self.window.newDB()

    def test_create_and_switch_every_database_reference(self):
        folder = self.root / "Новая база"
        folder.mkdir()
        path = folder / "inventory.sqlite"
        self.window.searchStr.setText("old query")
        self.create(path)
        factory = self.window.factory
        self.assertEqual(factory.db_file, str(path))
        self.assertIs(ElDBScheme.DB_FACTORY, factory)
        self.assertIs(self.window.typesTree.dbFactory, factory)
        table = self.window.partsTable
        self.assertIs(table.factory, factory)
        self.assertIs(table.iconsListWidget.factory, factory)
        self.assertIs(table.iconDelegate.defaultIcons.factory, factory)
        self.assertEqual(table.iconDelegate.iconsDir, str(folder / "icons"))
        self.assertTrue((folder / "icons").is_dir())
        self.assertEqual(self.window.typesTree.treeModel.rowCount(), 0)
        self.assertEqual(table.tableView.model().rowCount(), 0)
        self.assertIsNone(table.getSelected())
        self.assertIsNone(table.iconsListWidget.currentPart)
        self.assertEqual(self.window.docListWidget.count(), 0)
        self.assertEqual(self.window.searchStr.text(), "")
        self.assertEqual(self.config.get_value(constants.CONFIG_DB_FILE), str(path))
        self.assertEqual(self.config.get_value(constants.CONFIG_DATA_PATH), str(folder))
        with self.assertRaises(sqlite3.ProgrammingError):
            self.old.scheme.db.conn.execute("SELECT 1")
        with sqlite3.connect(path) as db:
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertTrue({"TYPES", "HEADERS", "PARTS", "DATASHEETS", "PROJECTS", "EL_BY_PROJECT",
                             "ENVIRONMENT"}.issubset(tables))
            self.assertEqual(db.execute("SELECT count(*) FROM PARTS").fetchone()[0], 0)
        self.assertEqual(factory.scheme.getDBVersion(), ElDBScheme.DB_VERSION)
        # The new empty inventory is usable: create a section and its first part.
        section = factory.appendType("New section", None)
        factory.createPart(section, {"part_num": "NEW-001"})
        self.window.typesTree.load()
        self.assertEqual(table.tableModel.rowCount(), 1)
        self.assertEqual(table.getSelected()["part_num"], "NEW-001")

    def test_cancel_keeps_current_database(self):
        self.create("")
        self.assertIs(self.window.factory, self.old)
        self.assertEqual(self.window.partsTable.getSelected()["part_num"], "OLD-001")

    def test_add_sqlite_extension(self):
        self.create(self.root / "new")
        self.assertEqual(self.window.factory.db_file, str(self.root / "new.sqlite"))

    def test_existing_file_is_never_overwritten(self):
        for path in (self.root / "existing.db", Path(self.old.db_file)):
            if path.name == "existing.db":
                path.write_bytes(b"leave this untouched")
            before = path.read_bytes()
            with mock.patch.object(QMessageBox, "warning") as warning:
                self.create(path)
            warning.assert_called_once()
            self.assertEqual(path.read_bytes(), before)
            self.assertIs(self.window.factory, self.old)

    def test_creation_failure_removes_partial_file(self):
        path = self.root / "broken.sqlite"
        with mock.patch.object(ElDBScheme.DBScheme, "createTables", side_effect=sqlite3.OperationalError("disk full")), \
                mock.patch.object(QMessageBox, "critical") as error:
            self.create(path)
        error.assert_called_once()
        self.assertFalse(path.exists())
        self.assertIs(self.window.factory, self.old)
        self.assertEqual(self.old.scheme.db.conn.execute("SELECT count(*) FROM PARTS").fetchone()[0], 1)

    def test_invalid_parent_shows_error(self):
        with mock.patch.object(QMessageBox, "critical") as error:
            self.create(self.root / "missing" / "new.sqlite")
        error.assert_called_once()
        self.assertIs(self.window.factory, self.old)

    def test_open_existing_database_reloads_table_and_tree(self):
        path = self.root / "other.sqlite"
        other = DBFactory(str(path))
        section = other.appendType("Other section", None)
        other.createPart(section, {"part_num": "OTHER-001"})
        other.disconnect()
        self.assertTrue(self.window.loadDB(str(path), ElDBScheme.DOC_TYPE_DEFAULT))
        self.assertEqual(self.window.typesTree.treeModel.index(0, 0).data(), "Other section")
        self.assertEqual(self.window.partsTable.getSelected()["part_num"], "OTHER-001")
        self.assertIs(self.window.partsTable.factory, self.window.factory)

    def test_open_invalid_database_keeps_current_ui(self):
        path = self.root / "invalid.sqlite"
        path.write_bytes(b"not sqlite")
        with mock.patch.object(QMessageBox, "critical") as error:
            self.assertFalse(self.window.loadDB(str(path), ElDBScheme.DOC_TYPE_DEFAULT))
        error.assert_called_once()
        self.assertIs(self.window.factory, self.old)
        self.assertEqual(self.window.partsTable.getSelected()["part_num"], "OLD-001")


if __name__ == "__main__":
    unittest.main()
