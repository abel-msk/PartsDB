"""Projects tab navigation on temporary databases, without importing or writing stock."""
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMainWindow

from ElData.ElDBScheme import DBFactory
from ElParts import Ui_MainWindow
from ElProjWindow import ProjWindow
from tests.qt_support import application

app = application()


class ProjectTestWindow(QMainWindow, Ui_MainWindow):
    pass


class TestProjWindow(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.factory = self.makeFactory('first')
        self.window = ProjectTestWindow()
        self.window.setupUi(self.window)
        self.addCleanup(self.window.close)
        self.controller = ProjWindow(self.factory, self.window)

    def makeFactory(self, name):
        factory = DBFactory(str(self.root / (name + '.sqlite')))
        self.addCleanup(factory.disconnect)
        return factory

    def seed(self):
        conn = self.factory.scheme.db.conn
        with conn:
            conn.execute("INSERT INTO PROJECTS(id, name, descr, source_uri, last_imported_at) "
                         "VALUES(1, 'Zulu', '<b>plain text</b>', 'file:///tmp/z', '2026-11-16T09:00:00Z')")
            conn.execute("INSERT INTO PROJECTS(id, name) VALUES(2, 'Alpha')")
        self.controller.refresh()

    def test_empty_list_and_navigation_updates_details(self):
        self.assertIsNone(self.controller.project)
        self.assertFalse(self.window.proj_remove_cmd.isEnabled())
        self.assertEqual(self.window.d_proj_descr.text(), '')
        self.seed()
        self.assertEqual(self.controller.project.id, 2)
        self.assertFalse(self.window.d_prj_reload_cmd.isEnabled())
        # Changing current index is also how keyboard navigation selects a row.
        self.window.proj_list.setCurrentIndex(self.controller.projList.model.index(1, 0))
        self.assertEqual(self.window.d_proj_name.text(), 'Zulu')
        self.assertEqual(self.window.d_proj_descr.text(), '<b>plain text</b>')
        self.assertEqual(self.window.d_proj_descr.textFormat(), Qt.TextFormat.PlainText)
        self.assertEqual(self.window.d_proj_omp_date.text(), '2026-11-16T09:00:00Z')
        self.assertTrue(self.window.d_prj_reload_cmd.isEnabled())

    def test_refresh_preserves_id_and_updates_data_without_writing(self):
        self.seed()
        self.controller.projList.selectByID(1)
        conn = self.factory.scheme.db.conn
        with conn:
            conn.execute("UPDATE PROJECTS SET name='Updated' WHERE id=1")
        before = list(conn.iterdump())
        self.controller.refresh()
        self.controller.retranslate()
        self.assertEqual(self.controller.project.id, 1)
        self.assertEqual(self.window.d_proj_name.text(), 'Updated')
        self.assertEqual(list(conn.iterdump()), before)
        with conn:
            conn.execute('DELETE FROM PROJECTS')
        self.controller.refresh()
        self.assertIsNone(self.controller.project)
        self.assertEqual(self.window.d_proj_name.text(), '')
        self.assertFalse(self.window.det_frm.isEnabled())

    def test_switch_database_and_button_requests(self):
        self.seed()
        self.controller.projList.selectByID(1)
        requests = []
        self.controller.addProjectRequested.connect(lambda: requests.append('add'))
        self.controller.removeProjectRequested.connect(lambda p: requests.append(('remove', p.id)))
        self.controller.reloadProjectRequested.connect(lambda p: requests.append(('reload', p.id)))
        self.window.proj_add_cmd.click()
        self.window.proj_remove_cmd.click()
        self.window.d_prj_reload_cmd.click()
        self.assertEqual(requests, ['add', ('remove', 1), ('reload', 1)])
        self.controller.setFactory(self.makeFactory('second'))
        self.assertEqual(self.controller.projList.model.rowCount(), 0)
        self.assertIsNone(self.controller.project)
        self.assertEqual(self.window.d_proj_omp_date.text(), '--')
