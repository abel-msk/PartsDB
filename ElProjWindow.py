"""Controller for the Projects tab; import actions are exposed to its backend."""
from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtGui import QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import QAbstractItemView, QMenu, QMessageBox

from ElProjList import ProjList
from ElWindowTexts import projWindowTexts, componentHeaders, projectMatchTexts
from ElTranslations import translate
from ElPluginMgr.repository import ProjectRepository


class ProjWindow(QObject):
    addProjectRequested = pyqtSignal()
    removeProjectRequested = pyqtSignal(object)
    reloadProjectRequested = pyqtSignal(object)

    def __init__(self, factory, window):
        super().__init__(window)
        self.ui = window
        self.project = None
        self.componentsModel = QStandardItemModel(self)
        window.prj_parts_all.setModel(self.componentsModel)
        window.prj_parts_all.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        window.prj_parts_all.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        window.prj_parts_all.customContextMenuRequested.connect(self.matchMenu)
        self.unmatchedModel = QStandardItemModel(self)
        window.tableView_2.setModel(self.unmatchedModel)
        window.tableView_2.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.projList = ProjList(factory, window.proj_list)
        self.projList.projectSelected.connect(self.onProjectSelected)
        window.proj_add_cmd.clicked.connect(self.onAddProject)
        window.proj_remove_cmd.clicked.connect(self.onRemoveProject)
        window.d_prj_reload_cmd.clicked.connect(self.onReloadProject)
        for label in (window.d_proj_name, window.d_proj_descr, window.d_proj_omp_date):
            label.setTextFormat(Qt.TextFormat.PlainText)
        self.retranslate()
        self.projList.load()

    def setFactory(self, factory):
        self.projList.setFactory(factory)

    def refresh(self):
        """Called after the backend changes project data."""
        self.projList.load()

    def retranslate(self):
        projWindowTexts(self.ui)
        self.onProjectSelected(self.project, load_components=False)
        headers = componentHeaders() + [translate('PluginWorkflow', 'Stock part'), translate('PluginWorkflow', 'Review needed')]
        self.componentsModel.setHorizontalHeaderLabels(headers)
        self.unmatchedModel.setHorizontalHeaderLabels(headers)

    def onProjectSelected(self, project, load_components=True):
        self.project = project
        self.ui.d_proj_name.setText((project.name or project.source_uri or str(project.id)) if project else '')
        self.ui.d_proj_descr.setText((project.descr or '') if project else '')
        self.ui.d_proj_omp_date.setText((project.last_imported_at or '--') if project else '--')
        if load_components:
            self.loadComponents(project)
        self.ui.det_frm.setEnabled(project is not None)
        self.ui.proj_remove_cmd.setEnabled(project is not None)
        self.ui.d_prj_reload_cmd.setEnabled(project is not None and bool(project.source_uri))

    def onAddProject(self):
        self.addProjectRequested.emit()

    def onRemoveProject(self):
        if self.project is not None:
            self.removeProjectRequested.emit(self.project)

    def onReloadProject(self):
        if self.project is not None and self.project.source_uri:
            self.reloadProjectRequested.emit(self.project)

    def loadComponents(self, project):
        self.componentsModel.clear()
        self.unmatchedModel.clear()
        headers = componentHeaders() + [translate('PluginWorkflow', 'Stock part'), translate('PluginWorkflow', 'Review needed')]
        self.componentsModel.setHorizontalHeaderLabels(headers)
        self.unmatchedModel.setHorizontalHeaderLabels(headers)
        if project:
            repository = ProjectRepository(self.projList.factory.scheme)
            matches = repository.matches(project.id)
            for row in repository.components(project.id):
                match = matches.get(row['id'])
                values = [row['reference'], row['kind'], row['value_raw'], row['footprint'] or '',
                          str(row['in_bom']), str(row['on_board']), str(row['dnp']),
                          f"{match['part_id']}: {match['part_num'] or ''}" if match else '',
                          str(match['needs_review']) if match else '']
                items = [QStandardItem(value) for value in values]
                items[0].setData(row['id'], Qt.ItemDataRole.UserRole)
                self.componentsModel.appendRow(items)
                if not match:
                    self.unmatchedModel.appendRow([QStandardItem(value) for value in values])

    def matchMenu(self, position):
        index = self.ui.prj_parts_all.indexAt(position)
        if not index.isValid() or not self.project:
            return
        component_id = index.siblingAtColumn(0).data(Qt.ItemDataRole.UserRole)
        menu = QMenu(self.ui)
        link = menu.addAction('')
        clear = menu.addAction('')
        projectMatchTexts(link, clear)
        stock = self.ui.partsTable.getSelected() if hasattr(self.ui, 'partsTable') else None
        link.setEnabled(stock is not None)
        action = menu.exec(self.ui.prj_parts_all.viewport().mapToGlobal(position))
        if action not in (link, clear):
            return
        part_id = stock.id if action == link else None
        if part_id is not None and QMessageBox.question(
                self.ui, translate('PluginWorkflow', 'Stock match'),
                translate('PluginWorkflow', 'Link {} to stock part #{}?').format(index.siblingAtColumn(0).data(), part_id),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        try:
            ProjectRepository(self.projList.factory.scheme).set_match(component_id, part_id)
            self.loadComponents(self.project)
        except Exception as exc:
            QMessageBox.critical(self.ui, translate('PluginWorkflow', 'Import error'), str(exc))
