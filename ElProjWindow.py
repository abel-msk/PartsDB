"""Controller for the Projects tab; import actions are exposed to its backend."""
from PyQt6.QtCore import QObject, Qt, pyqtSignal

from ElProjList import ProjList
from ElWindowTexts import projWindowTexts


class ProjWindow(QObject):
    addProjectRequested = pyqtSignal()
    removeProjectRequested = pyqtSignal(object)
    reloadProjectRequested = pyqtSignal(object)

    def __init__(self, factory, window):
        super().__init__(window)
        self.ui = window
        self.project = None
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
        self.onProjectSelected(self.project)

    def onProjectSelected(self, project):
        self.project = project
        self.ui.d_proj_name.setText((project.name or project.source_uri or str(project.id)) if project else '')
        self.ui.d_proj_descr.setText((project.descr or '') if project else '')
        self.ui.d_proj_omp_date.setText((project.last_imported_at or '--') if project else '--')
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
