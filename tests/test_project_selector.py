"""Manual project matching and reusable section pickers use disposable databases."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMessageBox
from ElConfig import ElConfig
from ElData.ElDBScheme import DBFactory
from ElHdrEditDialog import HeaderEditDialog
from ElMainWindow import MainWindow
from ElPartsPluginApi.importers import ImportedComponent, ImportedProject
from ElPluginMgr.repository import ProjectRepository
from tests.qt_support import application

app = application()


class ProjectSelectorTests(unittest.TestCase):
    """Exercise sidebar state, confirmed links, vetoes and width persistence.

    @attr factory [DBFactory] Disposable catalog factory.
    @attr window [MainWindow] Complete application using a temporary configuration.
    """

    def setUp(self):
        """Create two catalog cards, a nested section and an imported position."""
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.factory = DBFactory(str(self.root / 'catalog.sqlite'))
        self.addCleanup(self.factory.disconnect)
        self.section = self.factory.appendType('Root', None, 3)
        self.child = self.factory.appendType('Child', self.section, 3)
        headers = self.child.refreshHeaders()
        for field in ('part_num', 'value', 'units', 'description'):
            header = headers[field]
            header['hidden'] = field == 'description'
            header['is_key'] = field in ('part_num', 'value')
            header['position'] = ('part_num', 'value', 'units', 'description').index(field)
            header.save()
        self.first = self.factory.createPart(self.child, {'part_num': 'First', 'value': 1, 'units': 'kR', 'description': 'hidden'})
        self.second = self.factory.createPart(self.child, {'part_num': 'Second', 'value': 2, 'units': 'kR'})
        self.repo = ProjectRepository(self.factory.scheme)
        self.project_id = self.repo.save(ImportedProject('Test', components=[
            ImportedComponent('a', 'R1', kind='resistor', value_raw='missing')]), 'test', 'file:///tmp/sidebar')
        self.component_id = self.repo.components(self.project_id)[0]['id']
        self.config = ElConfig()
        self.config.filename = str(self.root / 'test.conf')
        self.config.set_value('language', 'en')
        self.window = MainWindow(self.factory, self.config)
        self.addCleanup(self.window.languageManager.close)
        self.addCleanup(self.window.close)
        self.controller = self.window.projWindow

    def choose(self, part):
        """Select a stock card. @param part [Part] Card in the child section."""
        self.controller.sectionSelector.select(self.child.recId)
        for row in range(self.controller.catalogModel.rowCount()):
            index = self.controller.catalogModel.index(row, 0)
            if index.data(Qt.ItemDataRole.UserRole).id == part.id:
                self.window.parts_list.setCurrentIndex(index)
                return
        self.fail('Catalog card missing')

    def test_keys_properties_link_and_row_synchronization(self):
        """Join keys, hide private fields and persist a link from the unmatched table."""
        self.window.no_matched_tbl.setCurrentIndex(self.controller.unmatchedModel.index(0, 2))
        self.assertEqual(self.window.section_list.currentIndex(), -1)
        self.choose(self.first)
        self.assertEqual(self.window.parts_list.currentIndex().data(), 'First 1.0')
        values = [self.controller.propertyModel.index(row, 0).data()
                  for row in range(self.controller.propertyModel.rowCount())]
        self.assertFalse(any('hidden' in value for value in values))
        self.assertTrue(any(value.endswith(': First') for value in values))
        self.assertTrue(all(': ' in value and '\n' not in value for value in values))
        self.window.p_link_cmd.click()
        self.assertEqual(self.repo.matches(self.project_id)[self.component_id]['part_id'], self.first.id)
        self.assertEqual(self.controller.unmatchedModel.rowCount(), 0)
        self.choose(self.second)
        self.window.prj_parts_all.setCurrentIndex(self.controller.componentsModel.index(0, 2))
        self.assertEqual(self.window.parts_list.currentIndex().data(Qt.ItemDataRole.UserRole).id, self.first.id)

    def test_missing_selection_and_replacement_confirmation(self):
        """Warn about absent choices and retain the existing link when replacement is rejected."""
        with mock.patch.object(QMessageBox, 'warning') as warning:
            self.window.p_link_cmd.click()
        warning.assert_called_once()
        self.repo.set_match(self.component_id, self.first.id)
        self.controller.refresh()
        self.window.prj_parts_all.setCurrentIndex(self.controller.componentsModel.index(0, 0))
        self.choose(self.second)
        with mock.patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.No):
            self.window.p_link_cmd.click()
        self.assertEqual(self.repo.matches(self.project_id)[self.component_id]['part_id'], self.first.id)
        with mock.patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Yes):
            self.window.p_link_cmd.click()
        self.assertEqual(self.repo.matches(self.project_id)[self.component_id]['part_id'], self.second.id)

    def test_editor_shared_selector_can_veto_section_change(self):
        """Preserve pending header edits and restore the combo when a section change is cancelled."""
        dialog = HeaderEditDialog(self.window, self.factory)
        self.addCleanup(dialog.deleteLater)
        dialog.loadData(self.child.recId)
        self.assertEqual(dialog.ui.typesList.currentText(), 'Root / Child')
        dialog.pendingIcon = 'pending'
        with mock.patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Cancel):
            dialog.ui.typesList.setCurrentIndex(dialog.ui.typesList.findData(self.section.recId))
        self.assertEqual(dialog.currentTypeId, self.child.recId)
        self.assertEqual(dialog.ui.typesList.currentData(), self.child.recId)
        self.assertEqual(dialog.pendingIcon, 'pending')

    def test_candidates_require_confirmation_and_cleared_selection_warns(self):
        """Synchronize automatic candidates, ask before confirming, and reject cleared selections."""
        from ElData.ElDBDataParts import CatalogMatch
        self.controller.matchingCandidates[self.component_id] = [
            CatalogMatch(self.first.id, self.child.recId, 'First', ('part_num',))]
        self.window.no_matched_tbl.setCurrentIndex(self.controller.unmatchedModel.index(0, 0))
        self.assertEqual(self.window.parts_list.currentIndex().data(Qt.ItemDataRole.UserRole).id, self.first.id)
        with mock.patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.No) as question:
            self.window.p_link_cmd.click()
        question.assert_called_once()
        self.assertEqual(self.repo.matches(self.project_id), {})
        self.window.no_matched_tbl.clearSelection()
        with mock.patch.object(QMessageBox, 'warning') as warning:
            self.window.p_link_cmd.click()
        warning.assert_called_once()
        self.assertEqual(self.repo.matches(self.project_id), {})

    def test_switching_database_clears_catalog_cards_and_component(self):
        """Repopulate the shared selector without carrying IDs or cards into another database."""
        self.window.no_matched_tbl.setCurrentIndex(self.controller.unmatchedModel.index(0, 0))
        self.choose(self.first)
        other = DBFactory(str(self.root / 'other.sqlite'))
        self.addCleanup(other.disconnect)
        other.appendType('Other', None, 3)
        self.controller.setFactory(other)
        self.assertEqual(self.window.section_list.count(), 1)
        self.assertEqual(self.window.section_list.itemText(0), 'Other')
        self.assertEqual(self.window.section_list.currentIndex(), -1)
        self.assertEqual(self.controller.catalogModel.rowCount(), 0)
        self.assertEqual(self.controller.propertyModel.rowCount(), 0)
        self.assertIsNone(self.controller.selectedComponentId)

    def test_right_width_is_saved_and_restored(self):
        """Persist the actual right panel width and use it when the project tab first appears."""
        self.window.show()
        self.window.view.setCurrentWidget(self.window.project_tab)
        app.processEvents()
        self.window.project_split.setSizes([230, 400, 310])
        app.processEvents()
        width = self.window.project_split.sizes()[2]
        self.window.close()
        self.assertEqual(self.config.get_value('project_right_width', 'window'), width)
        self.window._project_width_restored = False
        self.window.show()
        self.window.restoreProjectWidth()
        app.processEvents()
        self.assertAlmostEqual(self.window.project_split.sizes()[2], width, delta=1)
