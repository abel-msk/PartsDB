"""Unit tests: every drag & drop of the main window.

1. A picture dropped on the icon cell of the parts table becomes the part's PNG icon.
2. Parts dragged from the table onto the types tree move to that section.
3. Files and URLs dropped on the document list are attached to the selected part.
4. Drag enter / move / leave feedback of the main window (status line, tree highlight).
5. Starting a drag from the parts table.

Each test works on a copy of tests/imported.sqlite in a temporary folder (icons go there too).
Run from the project root:
    python -m unittest tests.test_drag_drop -v
"""
import os
import ctypes
import shutil
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(TESTS_DIR))

from PyQt6 import sip
from PyQt6.QtCore import QMimeData, QUrl, Qt, QPoint, QPointF, QCoreApplication, QEvent
from PyQt6.QtGui import QImage, QColor, QCursor, QDragEnterEvent, QDragMoveEvent, QDropEvent, QDragLeaveEvent, \
    QMouseEvent
from PyQt6.QtWidgets import QApplication

app = QApplication.instance() or QApplication(sys.argv)

import ElDBScheme
import ElMainWindow
import ElPartsTable
from ElConfig import ElConfig
from ElDBScheme import DBFactory
from ElMainWindow import MainWindow
from ElPartsTable import ICON_COLUMN

SOURCE_DB = os.path.join(TESTS_DIR, "imported.sqlite")
NO_BUTTONS = Qt.MouseButton.NoButton
NO_MODIFIERS = Qt.KeyboardModifier.NoModifier
ACTIONS = Qt.DropAction.CopyAction | Qt.DropAction.MoveAction | Qt.DropAction.LinkAction


def processEvents(times: int = 3):
    for _ in range(times):
        app.processEvents()


# ---------- drag events with a source widget ----------
# QDropEvent.source() comes from the running QDrag, so synthetic events always have source() None.
# These subclasses fake a drag started inside the program; they are passed to the handlers directly.

class _Source:
    def source(self):
        return self._source


class InternalDragEnter(_Source, QDragEnterEvent):
    def __init__(self, source, pos: QPoint, mime: QMimeData):
        QDragEnterEvent.__init__(self, pos, ACTIONS, mime, Qt.MouseButton.LeftButton, NO_MODIFIERS)
        self._source = source


class InternalDragMove(_Source, QDragMoveEvent):
    def __init__(self, source, pos: QPoint, mime: QMimeData):
        QDragMoveEvent.__init__(self, pos, ACTIONS, mime, Qt.MouseButton.LeftButton, NO_MODIFIERS)
        self._source = source


class InternalDrop(_Source, QDropEvent):
    def __init__(self, source, pos: QPointF, mime: QMimeData):
        QDropEvent.__init__(self, pos, ACTIONS, mime, Qt.MouseButton.LeftButton, NO_MODIFIERS)
        self._source = source


def makeImage(path: str, w: int = 900, h: int = 300, color: str = "blue") -> str:
    img = QImage(w, h, QImage.Format.Format_ARGB32)
    img.fill(QColor(color))
    assert img.save(path)
    return path


class DBTestCase(unittest.TestCase):
    """A fresh copy of the test DB and a main window on it for every test."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="partsdb-dnd-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.dbFile = os.path.join(self.tmp, "t.sqlite")
        shutil.copy(SOURCE_DB, self.dbFile)
        self.src = os.path.join(self.tmp, "src")
        os.makedirs(self.src)
        self.factory = DBFactory(self.dbFile)
        self.window = MainWindow(self.factory, ElConfig())
        self.window.resize(1400, 900)
        self.window.setStartupMode(None)  # loads the types tree
        self.window.show()
        processEvents()
        self.addCleanup(self.window.close)
        self.table = self.window.partsTable
        self.view = self.table.tableView

    # ----- DB helpers (read straight from the file, not through the program's caches) -----

    def sql(self, query: str, params=()):
        with sqlite3.connect(self.dbFile) as db:
            return db.execute(query, params).fetchall()

    def typeWithParts(self, minParts: int = 3, exclude=()) -> int:
        rows = self.sql("SELECT type_id FROM PARTS GROUP BY type_id HAVING count(*) >= ? ORDER BY type_id", (minParts,))
        return [r[0] for r in rows if r[0] not in exclude][0]

    def openType(self, typeId: int):
        theType = self.factory.getTypeByID(typeId)
        self.window.onTreeSelect(theType)
        processEvents()
        return theType

    # ----- tree helpers -----

    def treeIndexOf(self, typeId: int):
        model = self.window.typesTree.treeModel

        def walk(parent):
            for row in range(model.rowCount(parent)):
                index = model.index(row, 0, parent)
                theType = index.data(Qt.ItemDataRole.UserRole)
                if theType is not None and int(theType.recId) == int(typeId):
                    return index
                found = walk(index)
                if found is not None:
                    return found
            return None

        from PyQt6.QtCore import QModelIndex
        index = walk(QModelIndex())
        self.assertIsNotNone(index, "type {} not in the tree".format(typeId))
        return index

    def treeGlobalPos(self, typeId: int) -> QPoint:
        tree = self.window.types_tree_view
        tree.expandAll()
        index = self.treeIndexOf(typeId)
        tree.scrollTo(index)
        processEvents()
        rect = tree.visualRect(index)
        self.assertTrue(rect.isValid())
        return tree.viewport().mapToGlobal(rect.center())


# =====================================================================================
# 1. Picture on the icon cell
# =====================================================================================

class TestIconCellDrop(DBTestCase):

    def setUp(self):
        super().setUp()
        self.typeId = self.typeWithParts()
        self.openType(self.typeId)
        self.row = 2
        self.part = self.table.tableModel.index(self.row, 0).data(Qt.ItemDataRole.UserRole)
        self.oldIcon = self.part["icon"]
        self.picture = makeImage(os.path.join(self.src, "photo.jpg"))

    def cellPos(self, row: int, column: int = ICON_COLUMN) -> QPoint:
        return self.view.visualRect(self.table.tableModel.index(row, column)).center()

    def otherColumn(self) -> int:
        return [c for c in range(self.table.tableModel.columnCount())
                if c != ICON_COLUMN and not self.view.isColumnHidden(c)][0]

    def fileMime(self, path: str) -> QMimeData:
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(path)])
        return mime

    def send(self, event):
        QCoreApplication.sendEvent(self.view.viewport(), event)
        return event

    def drag(self, mime: QMimeData, pos: QPoint):
        enter = self.send(QDragEnterEvent(pos, ACTIONS, mime, Qt.MouseButton.LeftButton, NO_MODIFIERS))
        move = self.send(QDragMoveEvent(pos, ACTIONS, mime, Qt.MouseButton.LeftButton, NO_MODIFIERS))
        return enter, move

    def drop(self, mime: QMimeData, pos: QPoint):
        # A real drag always enters before it drops: Qt delivers Drop to the widget that accepted DragEnter
        self.drag(mime, pos)
        event = self.send(QDropEvent(QPointF(pos), ACTIONS, mime, Qt.MouseButton.LeftButton, NO_MODIFIERS))
        processEvents()
        return event

    def dbIcon(self):
        return self.sql("SELECT icon FROM PARTS WHERE id = ?", (self.part.id,))[0][0]

    # ----- accepted drops -----

    def test_hover_icon_cell_marks_the_row(self):
        enter, move = self.drag(self.fileMime(self.picture), self.cellPos(self.row))
        self.assertTrue(enter.isAccepted())
        self.assertTrue(move.isAccepted())
        self.assertEqual(move.dropAction(), Qt.DropAction.CopyAction)
        self.assertEqual(self.table.iconDelegate.dropRow, self.row)
        # leaving the table removes the mark
        self.send(QDragLeaveEvent())
        self.assertEqual(self.table.iconDelegate.dropRow, -1)

    def test_drop_file_sets_png_icon_and_activates_row(self):
        self.assertNotEqual(self.view.currentIndex().row(), self.row)
        event = self.drop(self.fileMime(self.picture), self.cellPos(self.row))
        self.assertTrue(event.isAccepted())

        icon = self.part["icon"]
        self.assertNotEqual(icon, self.oldIcon)
        self.assertTrue(icon.endswith(".png"))
        self.assertFalse(os.path.isabs(icon), "stored relative to the icons folder")
        self.assertEqual(self.dbIcon(), icon)

        path = os.path.join(self.factory.getIconsDir(), icon)
        with open(path, "rb") as f:
            self.assertEqual(f.read(8), b"\x89PNG\r\n\x1a\n")
        saved = QImage(path)
        self.assertEqual((saved.width(), saved.height()), (512, 170))  # 900x300 scaled to 512 px

        self.assertEqual(self.view.currentIndex().row(), self.row)
        self.assertEqual([i.row() for i in self.view.selectionModel().selectedRows()], [self.row])
        self.assertEqual(self.table.iconDelegate.dropRow, -1)
        self.assertTrue(os.path.isfile(self.picture), "the dropped file is not moved")

    def test_second_drop_keeps_first_file(self):
        self.drop(self.fileMime(self.picture), self.cellPos(self.row))
        first = self.part["icon"]
        self.drop(self.fileMime(makeImage(os.path.join(self.src, "other.png"), 50, 50, "red")), self.cellPos(self.row))
        second = self.part["icon"]
        self.assertNotEqual(first, second)
        self.assertTrue(os.path.isfile(os.path.join(self.factory.getIconsDir(), first)))
        self.assertEqual(QImage(os.path.join(self.factory.getIconsDir(), second)).width(), 50)

    def test_drop_browser_image_data(self):
        mime = QMimeData()
        img = QImage(64, 32, QImage.Format.Format_ARGB32)
        img.fill(QColor("green"))
        mime.setImageData(img)
        mime.setUrls([QUrl("https://example.invalid/page.html")])  # page URL that must not be downloaded
        with mock.patch("ElIconDrop.imageFromUrl", side_effect=AssertionError("no download expected")):
            self.drop(mime, self.cellPos(self.row))
        self.assertEqual(QImage(os.path.join(self.factory.getIconsDir(), self.part["icon"])).width(), 64)

    def test_drop_browser_image_freed_after_drop(self):
        """Crash 2026-11-13 (chipdip.ru page): the browser image memory is freed before the deferred save."""
        w, h = 30, 20
        buf = ctypes.create_string_buffer(b"\x00\x00\xff\xff" * (w * h))  # red, BGRA
        foreign = QImage(sip.voidptr(ctypes.addressof(buf)), w, h, w * 4, QImage.Format.Format_ARGB32)
        mime = QMimeData()
        mime.setImageData(foreign)
        mime.setUrls([QUrl("https://www.chipdip.ru/product/mmbt2222a")])
        self.drag(mime, self.cellPos(self.row))
        self.send(QDropEvent(QPointF(self.cellPos(self.row)), ACTIONS, mime, Qt.MouseButton.LeftButton, NO_MODIFIERS))
        ctypes.memset(buf, 0x55, w * h * 4)  # the drag is over before the icon is saved
        with mock.patch("ElIconDrop.imageFromUrl", side_effect=AssertionError("no download expected")):
            processEvents()
        saved = QImage(os.path.join(self.factory.getIconsDir(), self.part["icon"]))
        self.assertEqual((saved.width(), saved.height()), (w, h))
        self.assertEqual(saved.pixelColor(0, 0).name(), "#ff0000")

    def test_drop_web_image_url(self):
        mime = QMimeData()
        mime.setUrls([QUrl("https://example.invalid/pic.jpg")])
        downloaded = QImage(self.picture)
        with mock.patch("ElIconDrop.imageFromUrl", return_value=downloaded) as download:
            self.drop(mime, self.cellPos(self.row))
        download.assert_called_once_with("https://example.invalid/pic.jpg")
        self.assertEqual(self.dbIcon(), self.part["icon"])
        self.assertNotEqual(self.part["icon"], self.oldIcon)

    def test_drop_in_search_results(self):
        parts = self.factory.search(self.part["part_num"])
        self.table.loadSearchData(parts)
        processEvents()
        row = [r for r in range(len(parts)) if parts[r].id == self.part.id][0]
        thePart = parts[row]
        self.drop(self.fileMime(self.picture), self.cellPos(row))
        self.assertTrue(thePart["icon"].endswith(".png"))
        self.assertEqual(self.dbIcon(), thePart["icon"])
        self.assertEqual(self.view.currentIndex().row(), row)

    # ----- refused drops -----

    def test_other_column_refused(self):
        self.drag(self.fileMime(self.picture), self.cellPos(self.row, self.otherColumn()))
        self.assertEqual(self.table.iconDelegate.dropRow, -1)
        self.drop(self.fileMime(self.picture), self.cellPos(self.row, self.otherColumn()))
        self.assertEqual(self.dbIcon(), self.oldIcon)
        self.assertEqual(self.part["icon"], self.oldIcon)

    def test_enter_over_other_column_then_move_to_icon(self):
        """Bug 2026-11-13: entering the table over another column, the icon cell never got the drag.

        Qt sends DragMove only to the widget that accepted DragEnter; the table ignored the enter,
        so moving on to the icon cell went to the main window and the drop was refused.
        """
        mime = self.fileMime(self.picture)
        other = self.cellPos(self.row, self.otherColumn())
        enter = self.send(QDragEnterEvent(other, ACTIONS, mime, Qt.MouseButton.LeftButton, NO_MODIFIERS))
        self.assertTrue(enter.isAccepted(), "the table keeps the drag to see it reach the icon column")
        self.assertEqual(enter.dropAction(), Qt.DropAction.IgnoreAction, "no drop allowed there yet")
        self.assertEqual(self.table.iconDelegate.dropRow, -1)
        move = self.send(QDragMoveEvent(other, ACTIONS, mime, Qt.MouseButton.LeftButton, NO_MODIFIERS))
        self.assertFalse(move.isAccepted())
        move = self.send(QDragMoveEvent(self.cellPos(self.row), ACTIONS, mime, Qt.MouseButton.LeftButton,
                                        NO_MODIFIERS))
        self.assertTrue(move.isAccepted())
        self.assertEqual(move.dropAction(), Qt.DropAction.CopyAction)
        self.assertEqual(self.table.iconDelegate.dropRow, self.row)
        event = self.send(QDropEvent(QPointF(self.cellPos(self.row)), ACTIONS, mime, Qt.MouseButton.LeftButton,
                                     NO_MODIFIERS))
        processEvents()
        self.assertTrue(event.isAccepted())
        self.assertTrue(self.part["icon"].endswith(".png"))
        self.assertEqual(self.dbIcon(), self.part["icon"])

    def test_enter_without_picture_is_left_to_main_window(self):
        pdf = os.path.join(self.src, "datasheet.pdf")
        with open(pdf, "wb") as f:
            f.write(b"%PDF-1.4\n%fake\n")
        mime = self.fileMime(pdf)
        enter = QDragEnterEvent(self.cellPos(self.row), ACTIONS, mime, Qt.MouseButton.LeftButton, NO_MODIFIERS)
        self.table.eventFilter(self.view.viewport(), enter)
        self.assertFalse(enter.isAccepted(), "documents are handled by the main window")

    def test_moving_off_the_icon_column_clears_mark(self):
        mime = self.fileMime(self.picture)
        self.drag(mime, self.cellPos(self.row))
        self.assertEqual(self.table.iconDelegate.dropRow, self.row)
        self.send(QDragMoveEvent(self.cellPos(self.row, self.otherColumn()), ACTIONS, mime,
                                 Qt.MouseButton.LeftButton, NO_MODIFIERS))
        self.assertEqual(self.table.iconDelegate.dropRow, -1)

    def test_not_a_picture_file_refused(self):
        pdf = os.path.join(self.src, "datasheet.pdf")
        with open(pdf, "wb") as f:
            f.write(b"%PDF-1.4\n%fake\n")
        # the table refuses it; the main window may still accept it as a document drag
        self.drag(self.fileMime(pdf), self.cellPos(self.row))
        self.assertEqual(self.table.iconDelegate.dropRow, -1)
        with mock.patch.object(ElPartsTable, "ErrorDialog") as error:
            self.drop(self.fileMime(pdf), self.cellPos(self.row))
        error.assert_not_called()
        self.assertEqual(self.dbIcon(), self.oldIcon)
        self.assertFalse(os.path.isdir(self.factory.getIconsDir(create=False))
                         and os.listdir(self.factory.getIconsDir(create=False)))

    def test_empty_drag_refused(self):
        self.drag(QMimeData(), self.cellPos(self.row))
        self.assertEqual(self.table.iconDelegate.dropRow, -1)

    def test_web_url_that_is_not_a_picture_shows_error(self):
        mime = QMimeData()
        mime.setUrls([QUrl("https://example.invalid/page.html")])
        with mock.patch("ElIconDrop.imageFromUrl", return_value=None), \
                mock.patch.object(ElPartsTable, "ErrorDialog") as error:
            self.drop(mime, self.cellPos(self.row))
        error.assert_called_once()
        self.assertEqual(self.dbIcon(), self.oldIcon)
        self.assertEqual(self.part["icon"], self.oldIcon)
        self.assertEqual(os.listdir(self.factory.getIconsDir()), [])

    def test_internal_drag_is_left_to_main_window(self):
        """Parts dragged out of the table itself are not pictures: the filter ignores them."""
        mime = QMimeData()
        viewport = self.view.viewport()
        for event in (InternalDragEnter(self.view, self.cellPos(self.row), mime),
                      InternalDragMove(self.view, self.cellPos(self.row), mime),
                      InternalDrop(self.view, QPointF(self.cellPos(self.row)), mime)):
            event.accept()
            self.table.eventFilter(viewport, event)
            self.assertFalse(event.isAccepted(), type(event).__name__)
        self.assertEqual(self.table.iconDelegate.dropRow, -1)


# =====================================================================================
# 2. Parts from the table onto the types tree
# =====================================================================================

class TestPartsToTree(DBTestCase):

    def setUp(self):
        super().setUp()
        self.fromId = self.typeWithParts()
        self.toId = self.typeWithParts(exclude=(self.fromId,))
        self.openType(self.fromId)
        self.model = self.table.tableModel

    def partAt(self, row: int):
        return self.model.index(row, 0).data(Qt.ItemDataRole.UserRole)

    def typeOf(self, part) -> int:
        return self.sql("SELECT type_id FROM PARTS WHERE id = ?", (part.id,))[0][0]

    def dropAtCursor(self):
        event = InternalDrop(self.view, QPointF(10, 10), QMimeData())
        self.window.dropEvent(event)
        processEvents()
        return event

    def test_drop_selected_part_on_section(self):
        self.view.selectRow(1)
        part = self.partAt(1)
        QCursor.setPos(self.treeGlobalPos(self.toId))
        self.dropAtCursor()
        self.assertEqual(self.typeOf(part), self.toId)
        # the table now shows the target section with the moved part
        self.assertEqual(int(self.table.theType.recId), self.toId)
        self.assertIn(part.id, [p.id for p in self.table.tableModel.parts])
        self.assertIn("Drop records", self.window.statusbar.currentMessage())

    def test_drop_several_selected_parts(self):
        self.table.toggleSelection()  # multi selection
        self.view.clearSelection()
        self.view.selectRow(0)  # in multi selection mode selectRow toggles the row
        self.view.selectRow(2)
        self.assertEqual(sorted(i.row() for i in self.view.selectionModel().selectedRows()), [0, 2])
        parts = [self.partAt(0), self.partAt(2)]
        # the table may also list parts of subsections: they must keep their own sections
        others = [self.partAt(r) for r in range(self.model.rowCount()) if r not in (0, 2)]
        othersBefore = [self.typeOf(p) for p in others]
        QCursor.setPos(self.treeGlobalPos(self.toId))
        self.dropAtCursor()
        self.assertEqual([self.typeOf(p) for p in parts], [self.toId, self.toId])
        self.assertEqual([self.typeOf(p) for p in others], othersBefore)

    def test_drop_outside_tree_changes_nothing(self):
        self.view.selectRow(0)
        part = self.partAt(0)
        QCursor.setPos(self.view.viewport().mapToGlobal(QPoint(20, 20)))  # over the table itself
        self.dropAtCursor()
        self.assertEqual(self.typeOf(part), self.fromId)

    def test_drop_on_empty_tree_area_changes_nothing(self):
        self.view.selectRow(0)
        part = self.partAt(0)
        tree = self.window.types_tree_view
        tree.collapseAll()
        processEvents()
        QCursor.setPos(tree.viewport().mapToGlobal(QPoint(10, tree.viewport().height() - 5)))
        self.dropAtCursor()
        self.assertEqual(self.typeOf(part), self.fromId)

    def test_drag_move_highlights_section_under_cursor(self):
        QCursor.setPos(self.treeGlobalPos(self.toId))
        self.window.dragMoveEvent(InternalDragMove(self.view, QPoint(10, 10), QMimeData()))
        selected = self.window.typesTree.getSelectedIndex()
        self.assertEqual(int(selected.data(Qt.ItemDataRole.UserRole).recId), self.toId)
        self.assertIn("types tree", self.window.statusbar.currentMessage())

    def test_drag_leave_restores_section_selection(self):
        self.window.typesTree.selectItem(
            self.window.typesTree.treeModel.itemFromIndex(self.treeIndexOf(self.fromId)))
        self.window.savedTreeSelection = self.window.typesTree.getSelectedIndex()
        QCursor.setPos(self.treeGlobalPos(self.toId))
        self.window.dragMoveEvent(InternalDragMove(self.view, QPoint(10, 10), QMimeData()))
        self.window.dragLeaveEvent(QDragLeaveEvent())
        selected = self.window.typesTree.getSelectedIndex()
        self.assertEqual(int(selected.data(Qt.ItemDataRole.UserRole).recId), self.fromId)
        self.assertEqual(self.window.statusbar.currentMessage(), "Drag cancel.")


# =====================================================================================
# 3. Files and URLs onto the document list
# =====================================================================================

class TestDocumentsDrop(DBTestCase):

    def setUp(self):
        super().setUp()
        self.openType(self.typeWithParts())
        self.view.selectRow(0)
        processEvents()
        self.part = self.table.getSelected()
        self.docsBefore = self.docs()
        self.listBefore = self.window.docListWidget.count()

    def docs(self):
        return self.sql("SELECT type, uri FROM DATASHEETS WHERE part_id = ? ORDER BY id", (self.part.id,))

    def newDocs(self):
        return self.docs()[len(self.docsBefore):]

    def textMime(self, *lines: str) -> QMimeData:
        mime = QMimeData()
        mime.setText("\n".join(lines))
        return mime

    def docListPos(self) -> QPointF:
        lst = self.window.docListWidget
        return QPointF(lst.mapTo(self.window, lst.rect().center()))

    def drop(self, mime: QMimeData, pos: QPointF = None):
        event = QDropEvent(pos if pos is not None else self.docListPos(), ACTIONS, mime,
                           Qt.MouseButton.LeftButton, NO_MODIFIERS)
        self.window.dropEvent(event)
        processEvents()
        return event

    def test_drop_pdf_file(self):
        path = os.path.join(self.src, "datasheet.pdf")
        event = self.drop(self.textMime(QUrl.fromLocalFile(path).toString()))
        self.assertTrue(event.isAccepted())
        self.assertEqual(self.newDocs(), [(ElDBScheme.DOC_TYPE_PDF, path)])
        self.assertEqual(self.window.docListWidget.count(), self.listBefore + 1)

    def test_drop_file_with_encoded_name(self):
        path = os.path.join(self.src, "Даташит 2N7000.pdf")
        url = QUrl.fromLocalFile(path).toString(QUrl.ComponentFormattingOption.FullyEncoded)
        self.assertIn("%20", url)
        self.drop(self.textMime(url))
        self.assertEqual(self.newDocs(), [(ElDBScheme.DOC_TYPE_PDF, path)])

    def test_drop_several_files_and_url(self):
        pdf = os.path.join(self.src, "a.pdf")
        png = os.path.join(self.src, "b.png")
        self.drop(self.textMime(QUrl.fromLocalFile(pdf).toString(), QUrl.fromLocalFile(png).toString(),
                                "https://example.com/ds/part.html"))
        self.assertEqual(self.newDocs(), [(ElDBScheme.DOC_TYPE_PDF, pdf), (ElDBScheme.DOC_TYPE_PNG, png),
                                          (ElDBScheme.DOC_TYPE_URL, "https://example.com/ds/part.html")])
        self.assertEqual(self.window.docListWidget.count(), self.listBefore + 3)

    def test_unknown_extension_attached_with_default_type(self):
        path = os.path.join(self.src, "board.xyz")
        with mock.patch.object(ElMainWindow, "showWarn") as warn:
            self.drop(self.textMime(QUrl.fromLocalFile(path).toString()))
        warn.assert_not_called()
        self.assertEqual(self.newDocs(), [(ElDBScheme.DOC_TYPE_DEFAULT, path)])
        self.assertEqual(self.window.docListWidget.count(), self.listBefore + 1)

    def test_plain_text_is_ignored(self):
        self.drop(self.textMime("just some text", "and more"))
        self.assertEqual(self.newDocs(), [])

    def test_drop_outside_document_list(self):
        tree = self.window.types_tree_view  # left of the document list
        pos = QPointF(tree.mapTo(self.window, tree.rect().center()))
        event = self.drop(self.textMime(QUrl.fromLocalFile(os.path.join(self.src, "x.pdf")).toString()), pos)
        self.assertFalse(event.isAccepted())
        self.assertEqual(self.newDocs(), [])


# =====================================================================================
# 4. Main window drag enter feedback
# =====================================================================================

class TestMainWindowDragEnter(DBTestCase):

    def test_external_drag_accepted_as_link(self):
        event = QDragEnterEvent(QPoint(10, 10), ACTIONS, QMimeData(), Qt.MouseButton.LeftButton, NO_MODIFIERS)
        self.window.dragEnterEvent(event)
        self.assertTrue(event.isAccepted())
        self.assertEqual(event.dropAction(), Qt.DropAction.LinkAction)
        self.assertIn("Document view", self.window.statusbar.currentMessage())

    def test_parts_drag_accepted(self):
        event = InternalDragEnter(self.view, QPoint(10, 10), QMimeData())
        self.window.dragEnterEvent(event)
        self.assertTrue(event.isAccepted())
        self.assertIn("types tree", self.window.statusbar.currentMessage())

    def test_drag_from_other_widget_refused(self):
        event = InternalDragEnter(self.window.docListWidget, QPoint(10, 10), QMimeData())
        self.window.dragEnterEvent(event)
        self.assertFalse(event.isAccepted())


# =====================================================================================
# 5. Starting a drag from the parts table
# =====================================================================================

class TestStartDrag(DBTestCase):

    def mouseMove(self, buttons):
        return QMouseEvent(QEvent.Type.MouseMove, QPointF(20, 20), QPointF(20, 20), Qt.MouseButton.NoButton,
                           buttons, NO_MODIFIERS)

    def test_left_button_move_starts_move_drag(self):
        with mock.patch.object(ElPartsTable, "QDrag") as QDrag:
            self.table.localMouseMoveEvent(self.mouseMove(Qt.MouseButton.LeftButton))
        QDrag.assert_called_once_with(self.view)
        QDrag.return_value.exec.assert_called_once_with(Qt.DropAction.MoveAction)

    def test_move_without_button_does_not_drag(self):
        with mock.patch.object(ElPartsTable, "QDrag") as QDrag:
            self.table.localMouseMoveEvent(self.mouseMove(Qt.MouseButton.NoButton))
            self.table.localMouseMoveEvent(self.mouseMove(Qt.MouseButton.RightButton))
        QDrag.assert_not_called()


if __name__ == "__main__":
    unittest.main()
