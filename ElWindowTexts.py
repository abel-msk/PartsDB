"""Window texts for the bilingual interface, independent of generated Qt forms.

Call the matching function after setupUi and again when the language changes.
Only interface texts are updated; user input and widget state are preserved.
"""
from ElTranslations import translate


def mainWindowTexts(window):
    ui = window
    window.setWindowTitle(translate("PartsDB", "Electronic parts workbench"))
    ui.searchBtn.setText(translate("MainWindow", "Search"))
    ui.EditHdrBtn.setText(translate("MainWindow", "Edit Header"))
    ui.CloneHdrBtn.setText(translate("MainWindow", "Propagate Header"))
    ui.addPartBtn.setText(translate("MainWindow", "Add Part"))
    ui.DelPartBtn.setText(translate("MainWindow", "Delete Part"))
    ui.delTypeBtn.setText(translate("MainWindow", "Delete"))
    ui.addTypeBtn.setText(translate("MainWindow", "Add"))
    ui.addDocBtn.setText(translate("MainWindow", "Attach Document"))
    ui.delDocBtn.setText(translate("MainWindow", "Remove Document"))
    ui.view.setTabText(ui.view.indexOf(ui.catalog_tab), translate("MainWindow", "Catalog"))
    window.fileMenu.setTitle(translate("PartsDB", "File"))
    window.setupMenu.setTitle(translate("PartsDB", "Setup"))
    window.languageMenu.setTitle(translate("PartsDB", "Language"))


def projWindowTexts(window):
    ui = window
    ui.label.setText(translate("MainWindow", "Projects Folders"))
    ui.proj_remove_cmd.setText(translate("MainWindow", "Remove project"))
    ui.proj_add_cmd.setText(translate("MainWindow", "Add Project"))
    ui.d_prj_reload_cmd.setText(translate("MainWindow", "Reload Data"))
    ui.prj_parts.setItemText(ui.prj_parts.indexOf(ui.prj_parts_lt1), translate("MainWindow", "Used Parts"))
    ui.prj_parts.setItemText(ui.prj_parts.indexOf(ui.prj_parts_lt2), translate("PluginWorkflow", "Unmatched parts"))
    ui.view.setTabText(ui.view.indexOf(ui.project_tab), translate("MainWindow", "Projects"))
    ui.label_2.setText(translate("MainWindow", "Last Import"))


def pluginsDialogTexts(window):
    ui = window.ui
    window.setWindowTitle(translate("PluginsDialog", "Plugins"))
    ui.label.setText(translate("PluginsDialog", "Installed plugins"))
    ui.pl_add_file_cmd.setText(translate("PluginsDialog", "Install from file..."))
    ui.pl_delete.setText(translate("PluginsDialog", "Remove"))
    ui.pl_name.setText(translate("PluginsDialog", "Select a plugin"))
    ui.pl_descr.clear()
    ui.label_2.setText(translate("PluginsDialog", "Author"))
    ui.label_4.setText(translate("PluginsDialog", "Type"))
    ui.label_5.setText(translate("PluginsDialog", "Version"))
    ui.label_6.setText(translate("PluginsDialog", "Enabled"))
    ui.pl_author.clear()
    ui.pl_type.clear()
    ui.pl_version.clear()
    ui.pushButton_3.setText(translate("PluginsDialog", "Settings"))
    ui.pushButton_2.setText(translate("PluginsDialog", "Logs"))
    ui.pushButton.setText(translate("PluginsDialog", "Close"))
    ui.pl_status.clear()
    ui.pushButton_3.setToolTip(translate("PluginWorkflow", "This plugin has no configurable settings"))


def appPathDialogTexts(window):
    ui = window.ui
    window.setWindowTitle(translate("PartsDB", "Document applications"))
    ui.addBtn.setText(translate("AppPathDialog", "Add"))
    ui.delBtn.setText(translate("AppPathDialog", "Delete"))
    ui.label_2.setText(translate("AppPathDialog", "App exec path:"))
    ui.appOpenBtn.setText(translate("AppPathDialog", "..."))
    ui.textBrowser.setHtml(translate("AppPathDialog", "<!DOCTYPE HTML PUBLIC \"-//W3C//DTD HTML 4.0//EN\" \"http://www.w3.org/TR/REC-html40/strict.dtd\">\n"
        "<html><head><meta name=\"qrichtext\" content=\"1\" /><style type=\"text/css\">\n"
        "p, li { white-space: pre-wrap; }\n"
        "</style></head><body style=\" font-family:\'.AppleSystemUIFont\'; font-size:13pt; font-weight:400; font-style:normal;\">\n"
        "<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><span style=\" font-weight:600;\">App name</span>: the name for this rule</p>\n"
        "<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><span style=\" font-weight:600;\">App exec path:</span> The path to executable</p>\n"
        "<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><span style=\" font-weight:600;\">Params format: </span> the string will send to executables  use {file} placeholder for insert document file path</p>\n"
        "<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\"><span style=\" font-weight:600;\">Doc file extension:</span>  Document file extension for witch we are use this executables</p></body></html>"))
    ui.saveBtn.setText(translate("AppPathDialog", "Save"))
    ui.label.setText(translate("AppPathDialog", "App name:"))
    ui.label_4.setText(translate("AppPathDialog", "Doc file extension:"))
    ui.label_3.setText(translate("AppPathDialog", "Params format:"))


def openFileDialogTexts(window):
    ui = window.ui
    window.setWindowTitle(translate("OpenFileWnd", "Select file or URL"))
    ui.label_2.setText(translate("OpenFileWnd", "Path"))
    ui.isFilesOnly.setText(translate("OpenFileWnd", "Show files only"))
    ui.tabWidget.setTabText(ui.tabWidget.indexOf(ui.fileTab), translate("OpenFileWnd", "Local file"))
    ui.label.setText(translate("OpenFileWnd", "URL"))
    ui.clearBtn.setText(translate("OpenFileWnd", "X"))
    ui.tabWidget.setTabText(ui.tabWidget.indexOf(ui.webTab), translate("OpenFileWnd", "WEB URL"))


def headerEditDialogTexts(window):
    ui = window.ui
    window.setWindowTitle(translate("HdrEditDialog", "Edit headers"))
    ui.label.setText(translate("HdrEditDialog", "Section:"))
    ui.label_2.setText(translate("HdrEditDialog", "Default part icon:"))
    ui.icon_selector.setItemText(0, translate("PartsDB", "Auto (from parent section / built-in rule)"))


def importProgressTexts(window, installing=False):
    window.setWindowTitle(translate('PluginWorkflow', 'Install plugin') if installing
                          else translate('PluginWorkflow', 'Import project'))
    window.setLabelText(translate('PluginWorkflow', 'Preparing plugin environment...') if installing
                        else translate('PluginWorkflow', 'Reading project...'))
    window.setCancelButtonText(translate('PluginWorkflow', 'Cancel'))


def componentHeaders():
    return [translate('PluginWorkflow', 'Reference'), translate('PluginWorkflow', 'Kind'),
            translate('PluginWorkflow', 'Value'), translate('PluginWorkflow', 'Footprint'),
            translate('PluginWorkflow', 'In BOM'), translate('PluginWorkflow', 'On board'),
            translate('PluginWorkflow', 'DNP')]


def importPreviewTexts(window):
    from PyQt6.QtWidgets import QDialogButtonBox, QTableWidgetItem
    ui, project, changes = window.ui, window.project, window.changes
    window.setWindowTitle(translate('PluginWorkflow', 'Import preview'))
    ui.summary.setText(translate('PluginWorkflow', '{}: {} components. Added: {}; changed: {}; removed: {}.').format(
        project.name, len(project.components), len(changes.added), len(changes.changed), len(changes.removed)))
    ui.table.setHorizontalHeaderLabels([translate('PluginWorkflow', 'Change'), *componentHeaders()[:4],
                                       translate('PluginWorkflow', 'In BOM'), translate('PluginWorkflow', 'DNP')])
    for row, component in enumerate(project.components):
        state = (translate('PluginWorkflow', 'Added') if component.reference in changes.added else
                 translate('PluginWorkflow', 'Changed') if component.reference in changes.changed else
                 translate('PluginWorkflow', 'Unchanged'))
        values = [state, component.reference, component.kind, component.value_raw, component.footprint or '',
                  str(int(component.in_bom)), str(int(component.dnp))]
        for column, value in enumerate(values):
            ui.table.setItem(row, column, QTableWidgetItem(value))
    for row, reference in enumerate(changes.removed, start=len(project.components)):
        for column, value in enumerate([translate('PluginWorkflow', 'Removed'), reference, '', '', '', '', '']):
            ui.table.setItem(row, column, QTableWidgetItem(value))
    ui.buttons.button(QDialogButtonBox.StandardButton.Save).setText(translate('PluginWorkflow', 'Save'))
    ui.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(translate('PluginWorkflow', 'Cancel'))


def projectMatchTexts(link, clear):
    link.setText(translate('PluginWorkflow', 'Link selected stock part'))
    clear.setText(translate('PluginWorkflow', 'Clear stock match'))


def pluginLogsTexts(window):
    window.setWindowTitle(translate('PluginWorkflow', 'Plugin logs'))


def pluginTypeText(plugin_type):
    from ElPartsPluginApi.constants import (
        PLUGIN_TYPE_IMPORT, PLUGIN_TYPE_PARTS_ORDER, PLUGIN_TYPE_SHIPMENT_TRACKING,
    )
    names = {
        PLUGIN_TYPE_IMPORT: translate('PluginWorkflow', 'Project import'),
        PLUGIN_TYPE_PARTS_ORDER: translate('PluginWorkflow', 'Parts ordering'),
        PLUGIN_TYPE_SHIPMENT_TRACKING: translate('PluginWorkflow', 'Shipment tracking'),
    }
    return names.get(plugin_type, plugin_type)


def sectionDialogTexts(window):
    """Apply section editor labels. @param window [SectionDialog] initialized dialog."""
    window.setWindowTitle(translate('PartsDB', 'Section'))
    window.nameLabel.setText(translate('PartsDB', 'Section name:'))
    window.typeLabel.setText(translate('PartsDB', 'Basic type:'))


def partValuesDialogTexts(window):
    """Apply key input labels. @param window [PartValuesDialog] initialized dialog."""
    from ElTranslations import defaultHeaderText
    window.setWindowTitle(translate('PartsDB', 'Add part'))
    window.prompt.setText(translate('PartsDB', 'Enter part nominal'))
    for header in window.headers:
        field = header['field_name']
        window.labels[field].setText(defaultHeaderText(header, field))
