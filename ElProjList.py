"""Loading and selection of projects in the main window's proj_list."""
from dataclasses import dataclass

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtGui import QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import QAbstractItemView


@dataclass(frozen=True)
class Project:
    id: int
    name: str
    descr: str
    plugin_id: str
    external_id: str
    source_uri: str
    last_imported_at: str
    needs_reload: int
    properties_json: str


class ProjList(QObject):
    projectSelected = pyqtSignal(object)

    def __init__(self, factory, view):
        super().__init__(view)
        self.factory = factory
        self.view = view
        self.model = QStandardItemModel(self)
        view.setModel(self.model)
        view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        view.selectionModel().currentChanged.connect(self.onCurrentChanged)

    def load(self):
        """Refresh from the DB, retaining the selected project when possible."""
        selected = self.getSelected()
        selected_id = selected.id if selected is not None else None
        cursor = self.factory.scheme.db.conn.execute(
            'SELECT id, name, descr, plugin_id, external_id, source_uri, '
            'last_imported_at, needs_reload, properties_json FROM PROJECTS '
            'ORDER BY name COLLATE NOCASE, id')
        try:
            projects = [Project(*row) for row in cursor.fetchall()]
        finally:
            cursor.close()
        self.model.clear()
        for project in projects:
            item = QStandardItem(project.name or project.source_uri or str(project.id))
            item.setData(project, Qt.ItemDataRole.UserRole)
            item.setToolTip(project.source_uri or '')
            self.model.appendRow(item)
        if not self.selectByID(selected_id) and self.model.rowCount():
            self.view.setCurrentIndex(self.model.index(0, 0))
        if not projects:
            self.projectSelected.emit(None)

    def setFactory(self, factory):
        self.factory = factory
        # IDs from another database do not identify the same projects.
        self.model.clear()
        self.load()

    def getSelected(self):
        return self.view.currentIndex().data(Qt.ItemDataRole.UserRole)

    def selectByID(self, project_id):
        for row in range(self.model.rowCount()):
            index = self.model.index(row, 0)
            if index.data(Qt.ItemDataRole.UserRole).id == project_id:
                self.view.setCurrentIndex(index)
                self.view.scrollTo(index)
                return True
        return False

    def onCurrentChanged(self, current, previous):
        self.projectSelected.emit(current.data(Qt.ItemDataRole.UserRole))
