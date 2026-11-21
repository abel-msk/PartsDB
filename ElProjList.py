"""Loading and selection of projects in the main window's proj_list."""
from dataclasses import dataclass
from ElTwoLineDelegate import TwoLineDelegate
from ElConstants import SUBTITLE_ROLE

from PyQt6.QtCore import QAbstractListModel, QModelIndex, QObject, Qt, pyqtSignal
from PyQt6.QtWidgets import QAbstractItemView


@dataclass(frozen=True)
class Project:
    """Immutable database project card used by the list and details pane.

    @attr id [int] Persistent project ID.
    @attr name [str, None] User-visible project name.
    @attr descr [str, None] Project description.
    @attr plugin_id [str, None] Importer plugin ID.
    @attr external_id [str, None] Project identifier supplied by the importer.
    @attr source_uri [str, None] Original project source URI.
    @attr last_imported_at [str, None] Last successful import time in UTC.
    @attr needs_reload [int] Reload flag: 0 or 1.
    @attr properties_json [str] Additional project properties encoded as JSON."""
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
    """Expose project cards and installed plugin subtitles to the project list.

    @attr projects [list[Project]] Ordered project cards loaded from the database.
    @attr plugins [dict[str, dict]] Installed plugin metadata indexed by plugin ID."""
    TypeRole = SUBTITLE_ROLE

    def __init__(self, parent=None):
        """Create an empty project list model.

        @param parent [QObject, None] Qt owner of the model.
        @return [None] No value is returned."""
        super().__init__(parent)
        self.projects = []
        self.plugins = {}

    def rowCount(self, parent=QModelIndex()):
        """Return the number of root project rows.

        @param parent [QModelIndex] Invalid for the root; valid parents have no children.
        @return [int] Number of projects, or zero for a child index."""
        return 0 if parent.isValid() else len(self.projects)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        """Return a project label, card, tooltip or plugin subtitle.

        @param index [QModelIndex] Requested project row.
        @param role [int, Qt.ItemDataRole] DisplayRole, UserRole, ToolTipRole or TypeRole.
        @return [str, Project, None] Role value, or None for invalid indices and unsupported roles."""
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
        """Replace all project rows and notify attached views.

        @param projects [Iterable[Project]] Cards in display order.
        @return [None] No value is returned."""
        self.beginResetModel()
        self.projects = list(projects)
        self.endResetModel()

    def clear(self):
        """Remove all project rows while retaining plugin metadata.

        @return [None] No value is returned."""
        self.setProjects([])

    def setPlugins(self, plugins):
        """Replace installed plugin metadata and refresh row subtitles.

        @param plugins [Mapping[str, dict]] Plugin IDs mapped to optional type/name metadata.
        @return [None] No value is returned."""
        self.plugins = dict(plugins)
        if self.projects:
            self.dataChanged.emit(self.index(0), self.index(len(self.projects) - 1),
                                  [self.TypeRole])


# Compatibility name for existing users of the project delegate.
ProjectListDelegate = TwoLineDelegate

class ProjList(QObject):
    """Load projects and coordinate mouse or keyboard selection in proj_list.

    @attr factory [DBFactory] Active database factory.
    @attr view [QListView] Project list widget.
    @attr model [ProjectListModel] Loaded project cards and plugin subtitles.
    @attr delegate [TwoLineDelegate] Renderer for project titles and subtitles."""
    projectSelected = pyqtSignal(object)

    def __init__(self, factory, view):
        """Attach a project model, delegate and selection handlers to the view.

        @param factory [DBFactory] Factory connected to the active database.
        @param view [QListView] Project list widget owned by the main window.
        @return [None] No value is returned."""
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
        """Reload database cards, retaining the selected ID when present.

        Select the first row if the previous project disappeared; emit None for an empty list.

        @return [None] No value is returned."""
        selected = self.getSelected()
        selected_id = selected.id if selected is not None else None
        projects = [Project(*row) for row in self.factory.scheme.loadProjectRows()]
        self.model.setProjects(projects)
        if not self.selectByID(selected_id) and self.model.rowCount():
            self.view.setCurrentIndex(self.model.index(0, 0))
        if not projects:
            self.projectSelected.emit(None)

    def setFactory(self, factory):
        """Switch databases, clear the old selection and load the new project list.

        @param factory [DBFactory] Factory connected to the active database.
        @return [None] No value is returned."""
        self.factory = factory
        # IDs from another database do not identify the same projects.
        self.model.clear()
        self.load()

    def getSelected(self):
        """Read the current project card from the view.

        @return [Project, None] Selected card, or None for an invalid current index."""
        return self.view.currentIndex().data(Qt.ItemDataRole.UserRole)

    def selectByID(self, project_id):
        """Select and scroll to a project by its persistent ID.

        @param project_id [int, None] Existing project ID; None matches no project.
        @return [bool] True if the project was found and selected."""
        for row in range(self.model.rowCount()):
            index = self.model.index(row, 0)
            if index.data(Qt.ItemDataRole.UserRole).id == project_id:
                self.view.setCurrentIndex(index)
                self.view.scrollTo(index)
                return True
        return False

    def onCurrentChanged(self, current, previous):
        """Emit the current project card after mouse or keyboard navigation.

        @param current [QModelIndex] New current row; an invalid index emits None.
        @param previous [QModelIndex] Previous row supplied by Qt; not used.
        @return [None] No value is returned."""
        self.projectSelected.emit(current.data(Qt.ItemDataRole.UserRole))
