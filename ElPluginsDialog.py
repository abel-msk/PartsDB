"""Install, update, enable and remove project importers from the plugins window."""
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import QDialog, QFileDialog, QMessageBox

from ElPluginsWnd import Ui_Dialog
from ElTranslations import TranslatedDialogMixin, translate
from ElWindowTexts import pluginsDialogTexts, pluginLogsTexts, pluginTypeText
from ElPluginMgr.installer import PluginInstaller
from ElPluginMgr.manager import PluginManager
from ElImportTask import run_import_task


class PluginsDialog(TranslatedDialogMixin, QDialog):
    def __init__(self, parent=None, manager=None, conn=None):
        super().__init__(parent)
        self.manager = manager or PluginManager()
        self.conn = conn
        self.ui = Ui_Dialog()
        self.ui.setupUi(self)
        self.pluginsModel = QStandardItemModel(self)
        self.ui.pl_list.setModel(self.pluginsModel)
        self.ui.pl_list.selectionModel().currentChanged.connect(self.onSelection)
        self.ui.pl_list.setEditTriggers(self.ui.pl_list.EditTrigger.NoEditTriggers)
        self.ui.pushButton.clicked.connect(self.reject)
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
        return self.ui.pl_list.currentIndex().data(Qt.ItemDataRole.UserRole)

    def refresh(self, selected_id=None):
        self.pluginsModel.clear()
        try:
            plugins = self.manager.list_plugins()
            for plugin in plugins:
                item = QStandardItem(f'{plugin.manifest.name} — {pluginTypeText(plugin.manifest.plugin_type)}')
                item.setData(plugin, Qt.ItemDataRole.UserRole)
                self.pluginsModel.appendRow(item)
                if plugin.manifest.id == selected_id:
                    self.ui.pl_list.setCurrentIndex(item.index())
            if not self.ui.pl_list.currentIndex().isValid() and plugins:
                self.ui.pl_list.setCurrentIndex(self.pluginsModel.index(0, 0))
            self.onSelection()
        except Exception as exc:
            self.error(exc)

    def onSelection(self, *args):
        plugin = self.selected()
        self.ui.pl_data_frame.setEnabled(plugin is not None)
        self.ui.pl_delete.setEnabled(plugin is not None)
        if plugin:
            manifest = plugin.manifest
            self.ui.pl_name.setText(manifest.name)
            self.ui.pl_descr.setText(manifest.description)
            self.ui.pl_author.setText(manifest.author)
            self.ui.pl_type.setText(f'{pluginTypeText(manifest.plugin_type)} ({manifest.system_name})')
            self.ui.pl_version.setText(manifest.version)
        else:
            self.ui.pl_name.setText(translate('PluginsDialog', 'Select a plugin'))
            for label in (self.ui.pl_descr, self.ui.pl_author, self.ui.pl_type, self.ui.pl_version):
                label.clear()
        self.ui.pl_enable.blockSignals(True)
        self.ui.pl_enable.setChecked(bool(plugin and plugin.enabled))
        self.ui.pl_enable.blockSignals(False)

    def installFile(self):
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
            self.refresh(plugin.manifest.id)
            self.ui.pl_status.setText(translate('PluginWorkflow', 'Plugin installed'))
        except Exception as exc:
            self.error(exc)

    def removePlugin(self):
        plugin = self.selected()
        if not plugin:
            return
        if QMessageBox.question(self, translate('PluginWorkflow', 'Remove plugin'),
                                translate('PluginWorkflow', 'Remove {}? Imported projects will be kept.').format(plugin.manifest.name),
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        try:
            self.manager.remove(plugin.manifest.id, self.conn)
            self.refresh()
            self.ui.pl_status.setText(translate('PluginWorkflow', 'Plugin removed'))
        except Exception as exc:
            self.error(exc)

    def enablePlugin(self, enabled):
        plugin = self.selected()
        if plugin:
            try:
                self.manager.set_enabled(plugin.manifest.id, enabled, self.conn)
                self.refresh(plugin.manifest.id)
            except Exception as exc:
                self.error(exc)
                self.refresh(plugin.manifest.id)

    def showLogs(self):
        plugin = self.selected()
        if plugin:
            from PyQt6.QtWidgets import QPlainTextEdit, QVBoxLayout
            dialog = QDialog(self)
            pluginLogsTexts(dialog)
            dialog.resize(850, 500)
            layout = QVBoxLayout(dialog)
            text = QPlainTextEdit(dialog)
            text.setReadOnly(True)
            text.setPlainText(self.manager.logs(plugin.manifest.id) or translate('PluginWorkflow', 'No log entries'))
            layout.addWidget(text)
            dialog.exec()

    def error(self, exc):
        self.ui.pl_status.setText(str(exc))
        QMessageBox.critical(self, translate('PluginWorkflow', 'Plugin error'), str(exc))

    def retranslate(self):
        pluginsDialogTexts(self)
        for row in range(self.pluginsModel.rowCount()):
            item = self.pluginsModel.item(row)
            plugin = item.data(Qt.ItemDataRole.UserRole)
            item.setText(f'{plugin.manifest.name} — {pluginTypeText(plugin.manifest.plugin_type)}')
        self.onSelection()
