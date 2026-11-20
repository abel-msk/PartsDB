"""Loading and selection of projects in the main window's proj_list."""
from dataclasses import dataclass
from ElTwoLineDelegate import TwoLineDelegate
from ElConstants import SUBTITLE_ROLE

from PyQt6.QtCore import QAbstractListModel, QModelIndex, QObject, Qt, pyqtSignal
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


class ProjectListModel(QAbstractListModel):
    """Project rows and metadata of currently installed plugins.

    plugins maps plugin IDs to metadata dictionaries with optional type/name.
    Missing plugins deliberately have no subtitle, even if DB data remains.
    """
    TypeRole = SUBTITLE_ROLE

    def __init__(self, parent=None):
        super().__init__(parent)
        self.projects = []
        self.plugins = {}

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.projects)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.projects):
            return None
        project = self.projects[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return project.name or project.source_uri or str(project.id)
        if role == Qt.ItemDataRole.UserRole:
            return project
        if role == Qt.ItemDataRole.ToolTipRole:
            return project.source_uri or ''
        if role == self.TypeRole:
            plugin = self.plugins.get(project.plugin_id)
            return (plugin.get('type') or plugin.get('name') or '') if plugin else ''
        return None

    def setProjects(self, projects):
        self.beginResetModel()
        self.projects = list(projects)
        self.endResetModel()

    def clear(self):
        self.setProjects([])

    def setPlugins(self, plugins):
        """Refresh installed metadata after plugin installation/removal."""
        self.plugins = dict(plugins)
        if self.projects:
            self.dataChanged.emit(self.index(0), self.index(len(self.projects) - 1),
                                  [self.TypeRole])


# Compatibility name for existing users of the project delegate.
ProjectListDelegate = TwoLineDelegate

class ProjList(QObject):
    projectSelected = pyqtSignal(object)

    def __init__(self, factory, view):
        super().__init__(view)
        self.factory = factory
        self.view = view
        self.model = ProjectListModel(self)
        self.delegate = ProjectListDelegate(view, getattr(view.window(), "config", None))
        view.setItemDelegate(self.delegate)
        view.setModel(self.model)
        view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        view.selectionModel().currentChanged.connect(self.onCurrentChanged)

    def load(self):
        """Refresh from the DB, retaining the selected project when possible."""
        selected = self.getSelected()
        selected_id = selected.id if selected is not None else None
        projects = [Project(*row) for row in self.factory.scheme.loadProjectRows()]
        self.model.setProjects(projects)
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
