"""Wire project actions to background imports, preview and atomic storage."""
from pathlib import Path
from urllib.parse import urlsplit

from PyQt6.QtCore import QObject
from PyQt6.QtWidgets import QDialog, QInputDialog, QMessageBox

from ElImportPreview import ImportPreview
from ElImportTask import run_import_task
from ElOpenFileDialog import OpenFileDialog
from ElPartsImport.manager import PluginManager
from ElPartsImport.repository import ProjectRepository
from ElPartsImport.runner import PluginRunner
from ElPartsPluginApi.importers import ImportCancelled
from ElTranslations import translate


class ProjectImports(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        config = window.config
        location = config.get_location() if config is not None else ''
        root = config.get_value('directory', 'plugins') if config is not None else None
        python = config.get_value('python', 'plugins') if config is not None else None
        if not root and location:
            root = Path(location).expanduser().resolve().parent / 'plugins'
        self.manager = PluginManager(root, python)
        window.projWindow.addProjectRequested.connect(self.add)
        window.projWindow.reloadProjectRequested.connect(self.reload)
        window.projWindow.removeProjectRequested.connect(self.remove)
        self.refresh_plugins()

    def refresh_plugins(self):
        try:
            self.window.projWindow.projList.model.setPlugins(self.manager.metadata())
        except Exception as exc:
            self.window.statusbar.showMessage(str(exc))

    def choose_plugin(self):
        plugins = [p for p in self.manager.list_plugins() if p.enabled]
        if not plugins:
            QMessageBox.information(self.window, translate('PluginWorkflow', 'Import project'),
                                    translate('PluginWorkflow', 'Install and enable an importer in Settings → Plugins first.'))
            return None
        if len(plugins) == 1:
            return plugins[0]
        choices = [f'{p.manifest.name} ({p.manifest.id})' for p in plugins]
        choice, accepted = QInputDialog.getItem(self.window, translate('PluginWorkflow', 'Import project'),
                                               translate('PluginWorkflow', 'Importer'), choices, 0, False)
        return plugins[choices.index(choice)] if accepted else None

    def add(self):
        try:
            plugin = self.choose_plugin()
            if plugin is None:
                return
            selections = []
            dialog = OpenFileDialog(self.window, str(Path.home()))
            dialog.comm.uriSelected.connect(lambda uri, kind, root: selections.append(uri))
            dialog.exec()
            dialog.deleteLater()
            if selections and selections[0]:
                source = selections[0]
                if not urlsplit(source).scheme:
                    source = Path(source).expanduser().resolve().as_uri()
                self.import_source(plugin, source)
        except Exception as exc:
            self.error(exc)

    def reload(self, project):
        try:
            plugin = self.manager.get(project.plugin_id) if project.plugin_id else self.choose_plugin()
            if plugin:
                self.import_source(plugin, project.source_uri, project.id)
        except Exception as exc:
            self.error(exc)

    def import_source(self, plugin, source_uri, project_id=None):
        factory = self.window.factory
        try:
            result = run_import_task(self.window, lambda cancel, emit:
                                     PluginRunner().run(plugin, source_uri, cancel=cancel, on_event=emit))
            if self.window.factory is not factory:
                raise RuntimeError('The active database changed during import')
            repository = ProjectRepository(factory.scheme.db.conn)
            changes = repository.changes(result, project_id)
            preview = ImportPreview(result, changes, self.window)
            accepted = preview.exec() == QDialog.DialogCode.Accepted
            preview.deleteLater()
            if not accepted:
                return None
            saved_id = repository.save(result, plugin.manifest.id, source_uri, project_id)
            self.window.projWindow.refresh()
            self.window.projWindow.projList.selectByID(saved_id)
            self.window.statusbar.showMessage(translate('PluginWorkflow', 'Imported {} components').format(len(result.components)), 5000)
            return saved_id
        except ImportCancelled:
            self.window.statusbar.showMessage(translate('PluginWorkflow', 'Import cancelled'), 5000)
        except Exception as exc:
            self.error(exc)
        return None

    def remove(self, project):
        if QMessageBox.question(self.window, translate('PluginWorkflow', 'Remove project'),
                                translate('PluginWorkflow', 'Remove project {}? Stock parts will be kept.').format(project.name),
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        try:
            ProjectRepository(self.window.factory.scheme.db.conn).delete(project.id)
            self.window.projWindow.refresh()
        except Exception as exc:
            self.error(exc)

    def error(self, exc):
        QMessageBox.critical(self.window, translate('PluginWorkflow', 'Import error'), str(exc))
