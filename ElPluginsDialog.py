"""Install plugins and display their saved metadata in the manager window."""
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import QDialog, QFileDialog, QMessageBox, QPlainTextEdit, QVBoxLayout

from ElPluginsWnd import Ui_Dialog
from ElTranslations import TranslatedDialogMixin, translate
from ElWindowTexts import pluginsDialogTexts, pluginLogsTexts, pluginTypeText
from ElPluginMgr.installer import PluginInstaller
from ElPluginMgr.manager import PluginManager, plugin_record
from ElData.ElDBDataPlagins import PluginData, PluginDataStore
from ElImportTask import run_import_task


class PluginLogsDialog(TranslatedDialogMixin, QDialog):
    """Show installation logs with a title and empty-state text that follow the UI language.

    @attr ui [PluginLogsDialog] Self-reference used by the translation mixin.
    @attr logText [str] Original installation log, never translated.
    @attr text [QPlainTextEdit] Read-only log viewer.
    """

    def __init__(self, log_text, parent=None):
        """Create the read-only log window.

        @param log_text [str, None] Raw log content; empty input displays a localized placeholder.
        @param parent [QWidget, None] Owner of the dialog.
        @return [None] Build the viewer and apply current window texts.
        """
        super().__init__(parent)
        self.ui = self
        self.logText = log_text or ''
        self.resize(850, 500)
        layout = QVBoxLayout(self)
        self.text = QPlainTextEdit(self)
        self.text.setReadOnly(True)
        self.text.setPlainText(self.logText)
        layout.addWidget(self.text)
        self.retranslate()

    def retranslate(self):
        """Update captions and the empty-state placeholder without rewriting real log content.

        @return [None] Preserve log data and its scroll position.
        """
        pluginLogsTexts(self)


class PluginsDialog(TranslatedDialogMixin, QDialog):
    """Manage installed plugin cards and edit database-specific launch settings.

    @attr manager [PluginManager] Installation and registry manager.
    @attr conn [DBScheme, sqlite3.Connection, None] Borrowed database; None disables persisted application editing.
    @attr applicationDrafts [dict[str, tuple[str, str]]] Unsaved executable paths and argument templates keyed by plugin ID.
    @attr loadingApplication [bool] Guard preventing programmatic field updates from creating drafts.
    @attr ui [Ui_Dialog] Generated plugin manager widgets.
    @attr pluginsModel [QStandardItemModel] Displayed plugin cards."""

    def __init__(self, parent=None, manager=None, conn=None):
        """Build the plugin manager, connect actions and load saved cards.

        @param parent [QWidget, None] Qt owner of the dialog.
        @param manager [PluginManager, None] Installation manager; None creates the default manager.
        @param conn [DBScheme, sqlite3.Connection, None] Borrowed active database; None displays installation metadata only.
        @return [None] No value is returned."""
        super().__init__(parent)
        self.manager = manager or PluginManager()
        self.conn = conn
        self.applicationDrafts = {}
        self.loadingApplication = False
        self.ui = Ui_Dialog()
        self.ui.setupUi(self)
        self.pluginsModel = QStandardItemModel(self)
        self.ui.pl_list.setModel(self.pluginsModel)
        self.ui.pl_list.selectionModel().currentChanged.connect(self.onSelection)
        self.ui.pl_list.setEditTriggers(self.ui.pl_list.EditTrigger.NoEditTriggers)
        self.ui.pushButton.clicked.connect(self.accept)
        self.ui.get_path_cmd.clicked.connect(self.chooseApplication)
        self.ui.app_path_input.textChanged.connect(self.editApplication)
        self.ui.app_params_input.textChanged.connect(self.editApplication)
        self.ui.pl_add_file_cmd.clicked.connect(self.installFile)
        self.ui.pl_delete.clicked.connect(self.removePlugin)
        self.ui.pl_enable.setTristate(False)
        self.ui.pl_enable.toggled.connect(self.enablePlugin)
        self.ui.pushButton_2.clicked.connect(self.showLogs)
        self.ui.pushButton_3.setEnabled(False)  # API v1 has no declared settings schema.
        for label in (self.ui.pl_name, self.ui.pl_descr, self.ui.pl_author,
                      self.ui.pl_type, self.ui.pl_version, self.ui.pl_status):
            label.setTextFormat(Qt.TextFormat.PlainText)
        self.ui.splitter.setStretchFactor(0, 1)
        self.ui.splitter.setStretchFactor(1, 2)
        self.retranslate()
        self.refresh()

    def selected(self):
        """Read the selected plugin card.

        @return [PluginData, None] Selected card or None when no row is current."""
        return self.ui.pl_list.currentIndex().data(Qt.ItemDataRole.UserRole)

    def refresh(self, selected_id=None):
        """Synchronize installation metadata and reload plugin cards.

        @param selected_id [str, None] Plugin ID to reselect; None retains the previous selection if available.
        @return [bool] True on success; False after displaying an error."""
        previous = self.selected()
        selected_id = selected_id or (previous.id if previous else None)
        try:
            if self.conn is not None:
                self.manager.sync(self.conn)
                plugins = PluginDataStore(self.conn).all()
            else:
                plugins = [PluginData.from_record(plugin_record(plugin))
                           for plugin in self.manager.list_plugins()]
            self.pluginsModel.clear()
            for plugin in plugins:
                item = QStandardItem(f'{plugin.name} — {pluginTypeText(plugin.plugin_type)}')
                item.setData(plugin, Qt.ItemDataRole.UserRole)
                item.setToolTip('\n'.join((plugin.id, plugin.version, plugin.description)))
                self.pluginsModel.appendRow(item)
                if plugin.id == selected_id:
                    self.ui.pl_list.setCurrentIndex(item.index())
            if not self.ui.pl_list.currentIndex().isValid() and plugins:
                self.ui.pl_list.setCurrentIndex(self.pluginsModel.index(0, 0))
            self.onSelection()
            return True
        except Exception as exc:
            self.error(exc)
            return False

    def onSelection(self, *args):
        """Display the current plugin card and restore its pending application edits.

        @param args [tuple] Qt selection-change arguments; ignored.
        @return [None] No value is returned."""
        plugin = self.selected()
        self.ui.pl_data_frame.setEnabled(plugin is not None)
        self.ui.pl_delete.setEnabled(plugin is not None)
        if plugin:
            self.ui.pl_name.setText(plugin.name)
            self.ui.pl_descr.setText(plugin.description)
            self.ui.pl_author.setText(plugin.author)
            self.ui.pl_type.setText(f'{pluginTypeText(plugin.plugin_type)} ({plugin.system_name})')
            self.ui.pl_version.setText(plugin.version)
        else:
            self.ui.pl_name.setText(translate('PluginsDialog', 'Select a plugin'))
            for label in (self.ui.pl_descr, self.ui.pl_author, self.ui.pl_type, self.ui.pl_version):
                label.clear()
        self.loadingApplication = True
        path, params = self.applicationDrafts.get(plugin.id, (plugin.app_path, plugin.app_params)) if plugin else ('', '')
        self.ui.app_path_input.setText(path)
        self.ui.app_params_input.setText(params)
        self.loadingApplication = False
        for widget in (self.ui.app_path_input, self.ui.app_params_input, self.ui.get_path_cmd):
            widget.setEnabled(plugin is not None and self.conn is not None)
        self.ui.pl_enable.blockSignals(True)
        self.ui.pl_enable.setChecked(bool(plugin and plugin.enabled))
        self.ui.pl_enable.blockSignals(False)

    def chooseApplication(self):
        """Open the native file picker and copy the chosen application path into the form.

        @return [None] No value is returned."""
        filename, _ = QFileDialog.getOpenFileName(self, translate('PluginsDialog', 'Select application'),
                                                self.ui.app_path_input.text())
        if filename:
            self.ui.app_path_input.setText(filename)

    def editApplication(self, text):
        """Store edited application fields in the selected plugin draft.

        @param text [str] Changed field text supplied by Qt; values are read from both inputs.
        @return [None] No value is returned."""
        plugin = self.selected()
        if not self.loadingApplication and plugin is not None and self.conn is not None:
            self.applicationDrafts[plugin.id] = (self.ui.app_path_input.text(), self.ui.app_params_input.text())

    def done(self, result):
        """Save pending application settings before accepting, rejecting or closing the dialog.

        Ignore drafts for removed plugins. On a database error, report it and leave the dialog open.

        @param result [int] QDialog result code, normally Accepted or Rejected.
        @return [None] No value is returned."""
        try:
            if self.conn is not None and self.applicationDrafts:
                existing = {plugin.id for plugin in PluginDataStore(self.conn).all()}
                PluginDataStore(self.conn).saveApplications(
                    {key: value for key, value in self.applicationDrafts.items() if key in existing})
                self.applicationDrafts.clear()
        except Exception as exc:
            self.error(exc)
            return
        super().done(result)

    def installFile(self):
        """Choose and validate a plugin wheel, confirm installation and select the new card.

        @return [None] No value is returned."""
        filename, _ = QFileDialog.getOpenFileName(self, translate('PluginWorkflow', 'Install plugin'), '',
                                                translate('PluginWorkflow', 'Plugin wheels (*.whl)'))
        if not filename:
            return
        try:
            manifest = self.manager.inspect(filename)
            info = '\n'.join((manifest.name, manifest.description, manifest.author,
                              manifest.system_name, pluginTypeText(manifest.plugin_type), manifest.version))
            if QMessageBox.question(self, translate('PluginWorkflow', 'Install plugin'), info,
                                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                    QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
                return
            # Offer an explicit same-system replacement; keeping both is also supported.
            replacement = None
            existing = self.manager.list_plugins()
            same_system = [p for p in existing if p.manifest.system_id == manifest.system_id
                           and p.manifest.plugin_type == manifest.plugin_type]
            if not any(p.manifest.id == manifest.id for p in existing) and same_system:
                from PyQt6.QtWidgets import QInputDialog
                keep = translate('PluginWorkflow', 'Install alongside existing plugins')
                choices = [keep] + [f'{p.manifest.name} ({p.manifest.id})' for p in same_system]
                choice, accepted = QInputDialog.getItem(self, translate('PluginWorkflow', 'Install plugin'),
                                                       translate('PluginWorkflow', 'Plugin to replace'), choices, 0, False)
                if not accepted:
                    return
                if choice != keep:
                    replacement = same_system[choices.index(choice) - 1].manifest.id
            installer = PluginInstaller(self.manager.root, self.manager.python)
            candidate = run_import_task(self, lambda cancel, emit: installer.prepare(filename), installing=True)
            try:
                plugin = self.manager.install(filename, self.conn, replace_id=replacement, prepare=lambda _: candidate)
            except Exception:
                try:
                    installer.discard(candidate)
                except OSError:
                    pass
                raise
            if self.refresh(plugin.manifest.id):
                self.ui.pl_status.setText(translate('PluginWorkflow', 'Plugin installed'))
        except Exception as exc:
            self.error(exc)

    def removePlugin(self):
        """Confirm and remove the selected installation while retaining project data.

        @return [None] No value is returned."""
        plugin = self.selected()
        if not plugin:
            return
        if QMessageBox.question(self, translate('PluginWorkflow', 'Remove plugin'),
                                translate('PluginWorkflow', 'Remove {}? Imported projects will be kept.').format(plugin.name),
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        try:
            self.manager.remove(plugin.id, self.conn)
            self.refresh()
            self.ui.pl_status.setText(translate('PluginWorkflow', 'Plugin removed'))
        except Exception as exc:
            self.error(exc)

    def enablePlugin(self, enabled):
        """Persist the selected plugin enabled state and reload its saved card.

        @param enabled [bool] True enables the installation; False disables it.
        @return [None] No value is returned."""
        plugin = self.selected()
        if plugin:
            try:
                self.manager.set_enabled(plugin.id, enabled, self.conn)
                self.refresh(plugin.id)
            except Exception as exc:
                self.error(exc)
                self.refresh(plugin.id)

    def showLogs(self):
        """Open a read-only log viewer for the selected plugin installation.

        @return [None] No value is returned."""
        plugin = self.selected()
        if plugin:
            dialog = PluginLogsDialog(self.manager.logs(plugin.id), self)
            dialog.exec()
            dialog.deleteLater()

    def error(self, exc):
        """Show a plugin error in the status label and a critical message box.

        @param exc [Exception] Failure whose text is presented to the user.
        @return [None] No value is returned."""
        self.ui.pl_status.setText(str(exc))
        QMessageBox.critical(self, translate('PluginWorkflow', 'Plugin error'), str(exc))

    def retranslate(self):
        """Update localized captions and plugin labels, retaining pending application edits.

        @return [None] No value is returned."""
        pluginsDialogTexts(self)
        for row in range(self.pluginsModel.rowCount()):
            item = self.pluginsModel.item(row)
            plugin = item.data(Qt.ItemDataRole.UserRole)
            item.setText(f'{plugin.name} — {pluginTypeText(plugin.plugin_type)}')
        self.onSelection()
