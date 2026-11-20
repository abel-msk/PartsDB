"""Deletion through the main-window button, using temporary databases and files."""
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

from ElConfig import ElConfig
from ElData.ElDBScheme import DBFactory, DOC_TYPE_PDF, PartInProjectsError
from ElMainWindow import MainWindow
from ElTranslations import translate

from tests.qt_support import application

app = application()


class TestDeletePart(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="partsdb-delete-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.factory = DBFactory(str(self.root / "test.sqlite"))
        self.addCleanup(self.factory.disconnect)
        self.section = self.factory.appendType("Test", None)
        self.other = self.factory.createPart(self.section, {"part_num": "AAA"})
        self.part = self.factory.createPart(self.section, {"part_num": "ZZZ"})
        self.icon = Path(self.factory.getIconsDir()) / "ZZZ.png"
        self.icon.write_bytes(b"icon file")
        self.part["icon"] = self.icon.name
        self.part.save()
        self.doc = self.root / "datasheet.pdf"
        self.doc.write_bytes(b"document must survive")
        self.factory.scheme.addDocument(self.part.id, DOC_TYPE_PDF, str(self.doc))
        self.factory.scheme.addDocument(self.part.id, 1, "https://example.invalid/datasheet")
        self.db = self.factory.scheme.db.conn
        self.window = MainWindow(self.factory, ElConfig())
        self.addCleanup(self.window.close)
        self.window.setStartupMode(None)
        self.table = self.window.partsTable
        self.select(self.part.id)

    def select(self, partId):
        for row, part in enumerate(self.table.tableModel.parts.partsAr):
            if part.id == partId:
                self.table.tableView.selectRow(row)
                self.table.tableView.setCurrentIndex(self.table.tableModel.index(row, 0))
                return
        self.fail("part missing from model")

    def exists(self, table, column="part_id"):
        return self.db.execute("SELECT count(*) FROM {} WHERE {} = ?".format(table, column),
                               (self.part.id,)).fetchone()[0]

    def confirm(self):
        with mock.patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes) as dialog:
            self.window.DelPartBtn.click()
        dialog.assert_called_once()
        self.assertEqual(dialog.call_args.args[-1], QMessageBox.StandardButton.No)

    def test_button_deletes_selected_part_links_and_owned_icon(self):
        # A previous context-menu position must not override the button's current selection.
        self.table.menuRowSelected = 0
        self.confirm()
        self.assertEqual(self.exists("PARTS", "id"), 0)
        self.assertEqual(self.exists("DATASHEETS"), 0)
        self.assertEqual(self.exists("EL_BY_PROJECT"), 0)
        self.assertFalse(self.icon.exists())
        self.assertEqual(self.doc.read_bytes(), b"document must survive")
        self.assertEqual(self.table.tableModel.rowCount(), 1)
        self.assertEqual(self.table.getSelected().id, self.other.id)
        self.assertEqual(self.window.docListWidget.count(), 0)

    def test_no_confirmation_preserves_everything(self):
        with mock.patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No):
            self.window.DelPartBtn.click()
        self.assertEqual(self.exists("PARTS", "id"), 1)
        self.assertEqual(self.exists("DATASHEETS"), 2)
        self.assertTrue(self.icon.exists())
        self.assertTrue(self.doc.exists())
        self.assertEqual(self.table.tableModel.rowCount(), 2)

    def test_cleared_selection_does_not_delete_stale_current_row(self):
        self.table.tableView.clearSelection()
        with mock.patch.object(QMessageBox, "information") as info, \
                mock.patch.object(QMessageBox, "question") as question:
            self.window.DelPartBtn.click()
        info.assert_called_once()
        self.assertEqual(translate("PartsDB", "Please select a part first."), info.call_args.args[2])
        question.assert_not_called()
        self.assertEqual(self.exists("PARTS", "id"), 1)

    def test_empty_database_shows_selection_message(self):
        self.table.setFactory(self.factory, self.factory.getIconsDir())
        with mock.patch.object(QMessageBox, "information") as info:
            self.window.DelPartBtn.click()
        info.assert_called_once()

    def test_other_parts_icon_is_preserved(self):
        otherIcon = self.icon.with_name("AAA.png")
        otherIcon.write_bytes(b"other icon")
        self.other["icon"] = otherIcon.name
        self.other.save()
        self.confirm()
        self.assertTrue(otherIcon.exists())
        self.assertFalse(self.icon.exists())
        self.assertEqual(self.exists("PARTS", "id"), 0)

    def test_icon_used_as_document_is_preserved(self):
        self.factory.scheme.addDocument(self.other.id, 4, self.icon.as_uri())
        self.confirm()
        self.assertTrue(self.icon.exists())

    def test_external_icon_file_is_preserved(self):
        external = self.root / "original.png"
        external.write_bytes(b"original outside icons")
        self.part["icon"] = str(external)
        self.part.save()
        self.table.loadData(self.section)
        self.select(self.part.id)
        self.confirm()
        self.assertTrue(external.exists())

    def test_failed_database_delete_rolls_back_links_and_keeps_model_and_files(self):
        self.db.execute("CREATE TRIGGER prevent_delete BEFORE DELETE ON PARTS "
                        "BEGIN SELECT RAISE(ABORT, 'blocked'); END;")
        self.db.commit()
        with mock.patch("ElPartsTable.ErrorDialog") as error, \
                self.assertLogs("ElPartsTable", level="ERROR") as logs:
            self.confirm()
        self.assertEqual(len(logs.records), 1)
        self.assertIsInstance(logs.records[0].exc_info[1], sqlite3.IntegrityError)
        self.assertEqual(str(logs.records[0].exc_info[1]), "blocked")
        error.assert_called_once()
        self.assertEqual(self.exists("PARTS", "id"), 1)
        self.assertEqual(self.exists("DATASHEETS"), 2)
        self.assertEqual(self.exists("EL_BY_PROJECT"), 0)
        self.assertEqual(self.table.tableModel.rowCount(), 2)
        self.assertEqual(self.table.getSelected().id, self.part.id)
        self.assertTrue(self.icon.exists())
        self.assertTrue(self.doc.exists())

    def test_delete_last_search_result(self):
        self.table.loadSearchData(self.factory.search("ZZZ"))
        self.select(self.part.id)
        self.confirm()
        self.assertEqual(self.exists("PARTS", "id"), 0)
        self.assertEqual(self.table.tableModel.rowCount(), 0)
        self.assertEqual(self.window.docListWidget.count(), 0)
        self.assertIsNone(self.table.iconsListWidget.currentPart)
        self.assertFalse(self.icon.exists())
        self.assertTrue(self.doc.exists())

    def test_icon_remove_failure_warns_after_deleting_database_records(self):
        with mock.patch("ElData.ElDBScheme.os.remove", side_effect=PermissionError("read-only")), \
                mock.patch.object(QMessageBox, "warning") as warning, \
                self.assertLogs("ElData.ElDBScheme", level="ERROR") as logs:
            self.confirm()
        self.assertEqual(len(logs.records), 1)
        self.assertIsInstance(logs.records[0].exc_info[1], PermissionError)
        warning.assert_called_once()
        self.assertEqual(self.exists("PARTS", "id"), 0)
        self.assertEqual(self.table.tableModel.rowCount(), 1)
        self.assertTrue(self.icon.exists())

    def linkProject(self, quantity=2):
        self.db.execute("INSERT INTO EL_BY_PROJECT (project_id, part_id, quantity) VALUES (1, ?, ?)",
                        (self.part.id, quantity))
        self.db.commit()

    def assertPartUntouched(self):
        self.assertEqual(self.exists("PARTS", "id"), 1)
        self.assertEqual(self.exists("DATASHEETS"), 2)
        self.assertEqual(self.exists("EL_BY_PROJECT"), 1)
        self.assertEqual(self.table.tableModel.rowCount(), 2)
        self.assertEqual(self.table.getSelected().id, self.part.id)
        self.assertEqual(self.icon.read_bytes(), b"icon file")
        self.assertEqual(self.doc.read_bytes(), b"document must survive")

    def linkImportedProject(self):
        self.db.execute("INSERT INTO PROJECTS(id, name, plugin_id, source_uri) "
                        "VALUES (1, 'Imported', 'org.partsdb.kicad', 'https://example.org/project')")
        self.db.execute("INSERT INTO PROJECT_COMPONENTS(id, project_id, external_id, reference) "
                        "VALUES (1, 1, 'uuid-1', 'R1')")
        self.db.execute("INSERT INTO PROJECT_COMPONENT_MATCHES(component_id, part_id) VALUES (1, ?)",
                        (self.part.id,))
        self.db.commit()

    def test_imported_match_warns_before_delete_and_preserves_position(self):
        self.linkImportedProject()
        with mock.patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Yes) as question:
            self.window.DelPartBtn.click()
        warning = translate('PartsDB', 'Warning: this will remove {} stock matches from imported project components. The project components will remain and will need to be matched again.').format(1)
        self.assertIn(warning, question.call_args.args[2])
        self.assertEqual(self.exists('PARTS', 'id'), 0)
        self.assertEqual(self.db.execute('SELECT count(*) FROM PROJECT_COMPONENT_MATCHES').fetchone()[0], 0)
        self.assertEqual(self.db.execute('SELECT reference FROM PROJECT_COMPONENTS').fetchall(), [('R1',)])

    def test_cancel_imported_match_deletion_changes_nothing(self):
        self.linkImportedProject()
        before = list(self.db.iterdump())
        with mock.patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.No):
            self.window.DelPartBtn.click()
        self.assertEqual(list(self.db.iterdump()), before)

    def test_project_usage_blocks_button_before_confirmation(self):
        self.linkProject()
        before = list(self.db.iterdump())
        with mock.patch.object(QMessageBox, "warning") as warning, \
                mock.patch.object(QMessageBox, "question") as question:
            self.window.DelPartBtn.click()
        warning.assert_called_once()
        self.assertEqual(translate("PartsDB", "This part is used in projects and cannot be deleted."),
                         warning.call_args.args[2])
        question.assert_not_called()
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertPartUntouched()

    def test_zero_quantity_project_reference_also_blocks_deletion(self):
        self.linkProject(quantity=0)
        with mock.patch.object(QMessageBox, "warning") as warning, \
                mock.patch.object(QMessageBox, "question") as question:
            self.window.DelPartBtn.click()
        warning.assert_called_once()
        question.assert_not_called()
        self.assertPartUntouched()

    def test_factory_and_scheme_cannot_bypass_project_guard(self):
        self.linkProject()
        before = list(self.db.iterdump())
        with self.assertRaises(PartInProjectsError):
            self.factory.deletePart(self.part)
        with self.assertRaises(PartInProjectsError):
            self.factory.scheme.delPart(self.part.id)
        self.assertEqual(list(self.db.iterdump()), before)
        self.assertPartUntouched()

    def test_project_added_during_confirmation_blocks_deletion(self):
        def confirm(*args):
            self.linkProject()
            return QMessageBox.StandardButton.Yes

        with mock.patch.object(QMessageBox, "question", side_effect=confirm), \
                mock.patch.object(QMessageBox, "warning") as warning:
            self.window.DelPartBtn.click()
        warning.assert_called_once()
        self.assertPartUntouched()

    def test_another_parts_project_does_not_block_deletion(self):
        self.db.execute("INSERT INTO EL_BY_PROJECT (project_id, part_id, quantity) VALUES (1, ?, 2)",
                        (self.other.id,))
        self.db.commit()
        self.confirm()
        self.assertEqual(self.exists("PARTS", "id"), 0)
        self.assertFalse(self.icon.exists())
        self.assertEqual(self.db.execute("SELECT part_id FROM EL_BY_PROJECT").fetchall(), [(self.other.id,)])


if __name__ == "__main__":
    unittest.main()
