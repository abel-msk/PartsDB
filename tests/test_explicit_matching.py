"""Explicit project matching reports progress, supports cancellation and keeps catalog data intact."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from PyQt6.QtCore import Qt
from ElConfig import ElConfig
from ElData.ElDBScheme import DBFactory
from ElMainWindow import MainWindow
from ElPartsMatching import PartsMatching
from ElPartsPluginApi.importers import ImportedComponent, ImportedProject
from ElPluginMgr.repository import ProjectRepository
from tests.qt_support import application

app=application()


class ExplicitMatchingTests(unittest.TestCase):
    """Use a real main window and a disposable catalog to verify the Link Part workflow.

    @attr window [MainWindow] Test application window with translated project controls.
    """

    def setUp(self):
        """Create grouped import rows and a catalog candidate.

        @return [None] Register isolated database, Qt and translator cleanup.
        """
        folder=tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root=Path(folder.name)
        self.factory=DBFactory(str(self.root/'catalog.sqlite'))
        self.addCleanup(self.factory.disconnect)
        section=self.factory.appendType('R',None,3)
        self.factory.createPart(section,{'part_num':'R','value':1,'units':'кОм'})
        self.repo=ProjectRepository(self.factory.scheme)
        self.project_id=self.repo.save(ImportedProject('Match',components=[
            ImportedComponent('a','R1',kind='resistor',value_raw='1K'),
            ImportedComponent('b','R2',kind='resistor',value_raw='7K')]),'test','file:///tmp/match')
        config=ElConfig()
        config.filename=str(self.root/'test.conf')
        config.set_value('language','en')
        self.window=MainWindow(self.factory,config)
        self.addCleanup(self.window.close)
        self.addCleanup(self.window.languageManager.close)

    def test_link_part_runs_only_on_click_logs_each_row_and_retranslates(self):
        """Loading and refreshing rows must not invoke the matching algorithm.

        @return [None] Verify progress completion, ID-free logs and read-only candidate storage.
        """
        controller=self.window.projWindow
        with mock.patch.object(PartsMatching,'findCandidates',side_effect=AssertionError('automatic matching')):
            controller.refresh()
        self.assertEqual(controller.unmatchedModel.rowCount(),2)
        before=list(self.factory.scheme.db.conn.iterdump())
        self.window.d_proj_link_cmd.click()
        dialog=controller.matchingLog
        for _ in range(20):app.processEvents()
        self.addCleanup(dialog.close)
        self.assertFalse(dialog.running)
        self.assertEqual(dialog.ui.progressBar.value(),2)
        log=dialog.ui.plainTextEdit.toPlainText()
        self.assertIn('R1 | 1K',log)
        self.assertIn('R2 | 7K',log)
        self.assertIn('No match',log)
        self.assertEqual(controller.unmatchedModel.rowCount(),1)
        self.window.languageManager.setLanguage('ru')
        app.processEvents()
        self.assertEqual(dialog.windowTitle(),'Сопоставление компонентов')
        self.assertEqual(dialog.ui.plainTextEdit.toPlainText(),log)
        self.assertEqual(controller.componentsModel.headerData(4,Qt.Orientation.Horizontal),'Количество')
        self.assertEqual(list(self.factory.scheme.db.conn.iterdump()),before)

    def test_cancel_stops_scheduled_work(self):
        """Cancel before the first timer fires and keep the partial log visible.

        @return [None] No component is matched after cancellation.
        """
        self.window.d_proj_link_cmd.click()
        dialog=self.window.projWindow.matchingLog
        self.addCleanup(dialog.close)
        dialog.reject()
        for _ in range(10):app.processEvents()
        self.assertFalse(dialog.running)
        self.assertEqual(dialog.ui.progressBar.value(),0)
        self.assertEqual(dialog.ui.plainTextEdit.toPlainText().count('Cancelled'),1)
        self.assertEqual(self.window.projWindow.matchingCandidates,
                         {row['id']:[] for row in self.repo.components(self.project_id)})

    def test_native_database_dialog_cancel_and_file_selection(self):
        """Use the standard file picker and preserve the current DB on cancellation.

        @return [None] Forward a selected local file through the existing database loader.
        """
        with mock.patch('ElMainWindow.QFileDialog.getOpenFileName',return_value=('', '')), \
             mock.patch.object(self.window,'loadDB') as load:
            self.window.onOpenDB()
            load.assert_not_called()
        with mock.patch('ElMainWindow.QFileDialog.getOpenFileName',return_value=('/tmp/test.sqlite','')), \
             mock.patch.object(self.window,'loadDB') as load:
            self.window.onOpenDB()
            self.assertEqual(load.call_args.args[0],'/tmp/test.sqlite')
