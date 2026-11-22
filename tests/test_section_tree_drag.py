"""Prevent Qt MIME serialization of live database-backed section objects."""
import pickle
import tempfile
import unittest
from pathlib import Path
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QStandardItem
from PyQt6.QtWidgets import QTreeView
from ElData.ElDBScheme import DBFactory
from ElTypesTree import SectionTreeModel, TypesTree
from tests.qt_support import application

app = application()


class SectionTreeDragTests(unittest.TestCase):
    """Exercise the exact MIME path responsible for the reported fatal Qt abort.

    @attr factory [DBFactory] Disposable connected catalog containing a section.
    """

    def setUp(self):
        """Create an isolated catalog and a section holding its live SQLite connector.

        @return [None] Register temporary directory and connection cleanup.
        """
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.factory = DBFactory(str(Path(folder.name) / 'catalog.sqlite'))
        self.addCleanup(self.factory.disconnect)
        self.section = self.factory.appendType('Resistors', None, 3)

    def test_mime_exports_text_without_pickling_database_roles(self):
        """Export a section whose default PyQt role serialization would terminate the process.

        @return [None] Verify captions, safe MIME formats and unchanged live role objects.
        """
        with self.assertRaises(TypeError):
            pickle.dumps(self.section)
        model = SectionTreeModel()
        item = QStandardItem('Resistors')
        item.setData(self.section, Qt.ItemDataRole.UserRole)
        model.appendRow(item)
        mime = model.mimeData([model.index(0, 0)])
        self.assertEqual(mime.text(), 'Resistors')
        self.assertFalse(mime.hasFormat('application/x-qstandarditemmodeldatalist'))
        self.assertFalse(mime.hasFormat('application/x-qabstractitemmodeldatalist'))
        self.assertIs(item.data(Qt.ItemDataRole.UserRole), self.section)
        self.assertEqual(model.mimeData([]).text(), '')

    def test_tree_keeps_incoming_drops_and_section_selection(self):
        """Disable unsupported section-origin drags while retaining navigation and drop targets.

        @return [None] Section selection still emits the live section and MIME remains safe.
        """
        view = QTreeView()
        self.addCleanup(view.close)
        controller = TypesTree(self.factory, view)
        selected = []
        controller.comm.typeSelect.connect(lambda section, part: selected.append(section.recId))
        controller.load()
        self.assertFalse(view.dragEnabled())
        self.assertTrue(view.acceptDrops())
        self.assertTrue(view.viewport().acceptDrops())
        index = controller.getIndexByID(self.section.recId)
        controller.onClick(index)
        self.assertEqual(selected[-1], self.section.recId)
        self.assertEqual(controller.treeModel.mimeData([index]).text(), 'Resistors')
