"""Controller for the Projects tab; import actions are exposed to its backend."""
from PyQt6.QtCore import QObject, Qt, QProcess, QUrl, pyqtSignal
from pathlib import Path
import shlex
import sys
from PyQt6.QtGui import QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import QAbstractItemView, QMenu, QMessageBox, QPushButton

from ElData.ElDBDataPlagins import PluginDataStore
from ElProjList import ProjList
from ElProjectTableLayout import ProjectTableLayout
from ElConstants import (PROJECT_TABLE_ALL, PROJECT_TABLE_UNMATCHED, MATCHING_CANDIDATES_ROLE,
                         PROJECT_MATCH_STATUS_COLUMN, MATCHING_STATUS_ROLE, MATCHING_LABEL_ROLE,
                         PROJECT_MATCHED_COLOR, PROJECT_UNMATCHED_COLOR, PROJECT_MATCH_BUTTON_STYLE)
from ElPartsMatching import PartsMatching
from ElWindowTexts import (projWindowTexts, projectMatchTexts, projectComponentHeaders,
                           projectMatchingButtonTexts)
from ElTranslations import translate
from ElPluginMgr.repository import ProjectRepository


class ProjWindow(QObject):
    """Manage the Projects tab, project actions and component tables.

    @attr ui [MainWindow] Main window containing the project widgets.
    @attr project [Project, None] Currently selected database project.
    @attr projList [ProjList] Loader and navigation controller.
    @attr componentsModel [QStandardItemModel] All imported component rows.
    @attr unmatchedModel [QStandardItemModel] Rows with neither catalog candidates nor a confirmed link.
    @attr matchingRequested [pyqtBoundSignal] Emits an internal component ID for the future matching form.
    @attr matchingCandidates [dict[int, list[CatalogMatch]]] Automatic candidates keyed by hidden component ID.
    @attr tableLayouts [list[ProjectTableLayout]] Saved sizing preferences for both tables."""
    addProjectRequested = pyqtSignal()
    removeProjectRequested = pyqtSignal(object)
    reloadProjectRequested = pyqtSignal(object)
    matchingRequested = pyqtSignal(int)

    def __init__(self, factory, window):
        """Connect project widgets, models and action signals, then load projects.

        @param factory [DBFactory] Factory connected to the active database.
        @param window [MainWindow] Owner containing the generated project widgets.
        @return [None] No value is returned."""
        super().__init__(window)
        self.ui = window
        self.project = None
        self.matchingCandidates = {}
        self.componentsModel = QStandardItemModel(self)
        window.prj_parts_all.setModel(self.componentsModel)
        window.prj_parts_all.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        window.prj_parts_all.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        window.prj_parts_all.customContextMenuRequested.connect(self.matchMenu)
        self.unmatchedModel = QStandardItemModel(self)
        window.no_matched_tbl.setModel(self.unmatchedModel)
        window.no_matched_tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tableLayouts = [ProjectTableLayout(window.prj_parts_all, factory, PROJECT_TABLE_ALL),
                             ProjectTableLayout(window.no_matched_tbl, factory, PROJECT_TABLE_UNMATCHED)]
        self.projList = ProjList(factory, window.proj_list)
        self.projList.projectSelected.connect(self.onProjectSelected)
        window.proj_add_cmd.clicked.connect(self.onAddProject)
        window.proj_remove_cmd.clicked.connect(self.onRemoveProject)
        window.d_prj_reload_cmd.clicked.connect(self.onReloadProject)
        window.d_prj_open_cmd.clicked.connect(self.onOpenProject)
        for label in (window.d_proj_name, window.d_proj_descr, window.d_proj_imp_date):
            label.setTextFormat(Qt.TextFormat.PlainText)
        self.retranslate()
        self.projList.load()

    def setFactory(self, factory):
        """Switch project data and table preferences to another database.

        @param factory [DBFactory] Factory connected to the active database.
        @return [None] No value is returned."""
        for layout in self.tableLayouts:
            layout.setFactory(factory)
        self.projList.setFactory(factory)

    def refresh(self):
        """Reload cards and update details after backend changes.

        @return [None] No value is returned."""
        self.projList.load()

    def retranslate(self):
        """Update captions and table headers without reloading component data.

        @return [None] No value is returned."""
        projWindowTexts(self.ui)
        self.onProjectSelected(self.project, load_components=False)
        headers = projectComponentHeaders()
        self.componentsModel.setHorizontalHeaderLabels(headers)
        self.unmatchedModel.setHorizontalHeaderLabels(headers)
        self.updateMatchingButtons()

    def onProjectSelected(self, project, load_components=True):
        """Display a selected project and update action availability.

        @param project [Project, None] Selected database card; None clears the details.
        @param load_components [bool] True reloads component rows; False updates only the details.
        @return [None] No value is returned."""
        self.project = project
        self.ui.d_proj_name.setText((project.name or project.source_uri or '') if project else '')
        self.ui.d_proj_descr.setText((project.descr or '') if project else '')
        self.ui.d_proj_imp_date.setText((project.last_imported_at or '--') if project else '--')
        if load_components:
            self.loadComponents(project)
        self.ui.det_frm.setEnabled(project is not None)
        self.ui.proj_remove_cmd.setEnabled(project is not None)
        self.ui.d_prj_reload_cmd.setEnabled(project is not None and bool(project.source_uri))
        self.ui.d_prj_open_cmd.setEnabled(project is not None and bool(project.source_uri))

    def onAddProject(self):
        """Request a new project from the import backend.

        @return [None] No value is returned."""
        self.addProjectRequested.emit()

    def onRemoveProject(self):
        """Request removal of the selected project, if one is selected.

        @return [None] No value is returned."""
        if self.project is not None:
            self.removeProjectRequested.emit(self.project)

    def onReloadProject(self):
        """Request import of the selected project when it has a source URI.

        @return [None] No value is returned."""
        if self.project is not None and self.project.source_uri:
            self.reloadProjectRequested.emit(self.project)

    def onOpenProject(self):
        """Launch the selected project application independently of PartsDB.

        Read launch settings from the project plugin. Decode file URIs and replace {file}
        in parsed arguments; report configuration or launch failures in a message box.

        @return [None] No value is returned."""
        if self.project is None or not self.project.source_uri:
            return
        try:
            plugin = PluginDataStore(self.projList.factory.scheme).application(self.project.plugin_id)
            if plugin is None or not plugin.app_path.strip():
                QMessageBox.information(self.ui, translate('PluginsDialog', 'Select application'),
                                        translate('PluginsDialog', 'Configure the application path in Settings → Plugins.'))
                return
            source = QUrl(self.project.source_uri)
            filename = source.toLocalFile() if source.isLocalFile() else self.project.source_uri
            if not source.scheme():
                filename = str((Path(self.projList.factory.db_file).parent / filename).resolve())
            # Tokenize first: filenames containing spaces or quotes remain a single argument.
            arguments = [arg.replace('{file}', filename) for arg in shlex.split(plugin.app_params)]
            program = str(Path(plugin.app_path).expanduser())
            if sys.platform == 'darwin' and program.lower().endswith('.app'):
                if not Path(program).is_dir():
                    raise ValueError(translate('PluginsDialog', 'Application bundle does not exist'))
                arguments = ['-a', program, '--args', *arguments]
                program = '/usr/bin/open'
            started, pid = QProcess.startDetached(program, arguments)
            if not started:
                raise RuntimeError(translate('PluginsDialog', 'Could not start the application'))
        except Exception as exc:
            QMessageBox.critical(self.ui, translate('PluginsDialog', 'Application launch error'), str(exc))

    def loadComponents(self, project):
        """Populate all-component and not-found tables, attaching matching status buttons.

        @param project [Project, None] Selected database card; None clears the details.
        @return [None] No value is returned."""
        self.componentsModel.clear()
        self.unmatchedModel.clear()
        self.matchingCandidates.clear()
        headers = projectComponentHeaders()
        self.componentsModel.setHorizontalHeaderLabels(headers)
        self.unmatchedModel.setHorizontalHeaderLabels(headers)
        if project:
            repository = ProjectRepository(self.projList.factory.scheme)
            matches = repository.matches(project.id)
            matcher = PartsMatching(self.projList.factory)
            for row in repository.components(project.id):
                match = matches.get(row['id'])
                candidates = matcher.findCandidates(row)
                self.matchingCandidates[row['id']] = candidates
                confirmed = next((candidate for candidate in candidates
                                  if match and candidate.part_id == match['part_id']), None)
                stock_text = ((confirmed.key_text if confirmed else matcher.keyText(match['part_id']))
                              if match else candidates[0].key_text if candidates else '')
                found = bool(match or candidates)
                values = [row['reference'], row['kind'], row['value_raw'], row['footprint'] or '',
                          str(row['in_bom']), str(row['on_board']), str(row['dnp']),
                          '',
                          str(match['needs_review']) if match else '']
                items = [QStandardItem(value) for value in values]
                items[0].setData(row['id'], Qt.ItemDataRole.UserRole)
                items[0].setData(tuple(candidate.part_id for candidate in candidates), MATCHING_CANDIDATES_ROLE)
                status = items[PROJECT_MATCH_STATUS_COLUMN]
                status.setData(found, MATCHING_STATUS_ROLE)
                status.setData(stock_text, MATCHING_LABEL_ROLE)
                self.componentsModel.appendRow(items)
                self.addMatchingButton(self.ui.prj_parts_all, self.componentsModel,
                                       self.componentsModel.rowCount() - 1, row['id'])
                if not found:
                    unmatched = [QStandardItem(value) for value in values]
                    unmatched[0].setData(row['id'], Qt.ItemDataRole.UserRole)
                    unmatched[0].setData(tuple(candidate.part_id for candidate in candidates), MATCHING_CANDIDATES_ROLE)
                    unmatched[PROJECT_MATCH_STATUS_COLUMN].setData(False, MATCHING_STATUS_ROLE)
                    unmatched[PROJECT_MATCH_STATUS_COLUMN].setData('', MATCHING_LABEL_ROLE)
                    self.unmatchedModel.appendRow(unmatched)
                    self.addMatchingButton(self.ui.no_matched_tbl, self.unmatchedModel,
                                           self.unmatchedModel.rowCount() - 1, row['id'])

        for layout in self.tableLayouts:
            layout.schedule()

    def addMatchingButton(self, view, model, row, component_id):
        """Place a matching action in one status cell and retain its stable component identity.

        @param view [QTableView] All-components or not-found table.
        @param model [QStandardItemModel] Model currently attached to the table.
        @param row [int] Existing row in the supplied model.
        @param component_id [int] Internal position ID passed to the future matching form signal.
        @return [None] Create a button; clicking emits matchingRequested without changing links.
        """
        index = model.index(row, PROJECT_MATCH_STATUS_COLUMN)
        button = QPushButton(view)
        button.clicked.connect(lambda checked=False, identity=component_id: self.matchingRequested.emit(identity))
        view.setIndexWidget(index, button)
        self.updateMatchingButton(model, index, button)

    def updateMatchingButton(self, model, index, button):
        """Apply translated button text and the model's found/not-found color.

        @param model [QStandardItemModel] Component model storing status metadata.
        @param index [QModelIndex] Existing status cell.
        @param button [QPushButton] Widget attached to that cell.
        @return [None] Green means found/linked; red means no candidate and no link.
        """
        found = bool(index.data(MATCHING_STATUS_ROLE))
        label = index.data(MATCHING_LABEL_ROLE) or ''
        projectMatchingButtonTexts(button, found, label)
        color = PROJECT_MATCHED_COLOR if found else PROJECT_UNMATCHED_COLOR
        button.setStyleSheet(PROJECT_MATCH_BUTTON_STYLE.format(color))
        model.setData(index, button.text(), Qt.ItemDataRole.DisplayRole)

    def updateMatchingButtons(self):
        """Retranslate existing action cells without querying SQLite or replacing models.

        @return [None] Keep colors, hidden identities and click connections intact.
        """
        for view, model in ((self.ui.prj_parts_all, self.componentsModel),
                            (self.ui.no_matched_tbl, self.unmatchedModel)):
            for row in range(model.rowCount()):
                index = model.index(row, PROJECT_MATCH_STATUS_COLUMN)
                button = view.indexWidget(index)
                if button is not None:
                    self.updateMatchingButton(model, index, button)

    def matchMenu(self, position):
        """Offer stock matching actions for the component under the pointer.

        @param position [QPoint] Context-menu position in the component table viewport.
        @return [None] No value is returned."""
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
                translate('PluginWorkflow', 'Link {} to the selected stock part?').format(index.siblingAtColumn(0).data()),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        try:
            ProjectRepository(self.projList.factory.scheme).set_match(component_id, part_id)
            self.loadComponents(self.project)
        except Exception as exc:
            QMessageBox.critical(self.ui, translate('PluginWorkflow', 'Import error'), str(exc))
