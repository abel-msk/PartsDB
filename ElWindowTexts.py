"""Window texts for the bilingual interface, independent of generated Qt forms.

Call the matching function after setupUi and again when the language changes.
Only interface texts are updated; user input and widget state are preserved.
"""
from ElTranslations import translate


def mainWindowTexts(window):
    """Apply localized main window captions without changing user data.

    @param window [MainWindow] Initialized main form with its application menus.
    @return [None] No value is returned."""
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
    """Apply localized captions to the Projects tab.

    @param window [MainWindow] Main form containing project actions, labels and tables.
    @return [None] No value is returned."""
    ui = window
    ui.label.setText(translate("MainWindow", "Projects Folders"))
    ui.proj_remove_cmd.setText(translate("MainWindow", "Remove project"))
    ui.proj_add_cmd.setText(translate("MainWindow", "Add Project"))
    ui.d_prj_open_cmd.setText(translate('MainWindow', 'Open App'))
    ui.d_prj_reload_cmd.setText(translate("MainWindow", "Reload Data"))
    ui.prj_parts.setItemText(ui.prj_parts.indexOf(ui.prj_parts_lt1), translate("MainWindow", "Used Parts"))
    ui.prj_parts.setItemText(ui.prj_parts.indexOf(ui.prj_parts_lt2), translate("PluginWorkflow", "Unmatched parts"))
    ui.view.setTabText(ui.view.indexOf(ui.project_tab), translate("MainWindow", "Projects"))
    ui.label_2.setText(translate("MainWindow", "Last Import"))
    ui.label_3.setText(translate("MainWindow", "Imported by"))
    ui.label_5.setText(translate("MainWindow", "Refresh date"))
    ui.d_proj_link_cmd.setText(translate("MainWindow", "Link Part"))


def pluginsDialogTexts(window):
    """Apply plugin manager captions before the selected card is redisplayed.

    @param window [PluginsDialog] Initialized plugin dialog containing its generated ui object.
    @return [None] No value is returned."""
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
    ui.label_3.setText(translate('PluginsDialog', 'Application path'))
    ui.label_7.setText(translate('PluginsDialog', 'Arguments'))
    ui.get_path_cmd.setToolTip(translate('PluginsDialog', 'Select application'))
    ui.info.setHtml(translate('PluginsDialog', '<p><b>Application path:</b> Path to the application executable.</p>'
                            '<p><b>Arguments:</b> Use {file} for the project file path. Quote arguments containing spaces.</p>'))
    ui.app_params_input.setToolTip(translate('PluginsDialog', 'Use {file} for the project file path. Quote arguments containing spaces.'))
    ui.pl_status.clear()
    ui.pushButton_3.setToolTip(translate("PluginWorkflow", "This plugin has no configurable settings"))


def appPathDialogTexts(window):
    """Apply document application editor labels, help and standard button captions.

    @param window [QWidget] Initialized window exposing the widgets required by this text function.
    @return [None] Updated captions or completed maintenance operation."""
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
    dialogButtonTexts(ui.buttonBox)


def openFileDialogTexts(window):
    """Apply local file/URL selector labels and standard button captions.

    @param window [QWidget] Initialized window exposing the widgets required by this text function.
    @return [None] Updated captions or completed maintenance operation."""
    ui = window.ui
    window.setWindowTitle(translate("OpenFileWnd", "Select file or URL"))
    ui.label_2.setText(translate("OpenFileWnd", "Path"))
    ui.isFilesOnly.setText(translate("OpenFileWnd", "Show files only"))
    ui.tabWidget.setTabText(ui.tabWidget.indexOf(ui.fileTab), translate("OpenFileWnd", "Local file"))
    ui.label.setText(translate("OpenFileWnd", "URL"))
    ui.clearBtn.setText(translate("OpenFileWnd", "X"))
    ui.tabWidget.setTabText(ui.tabWidget.indexOf(ui.webTab), translate("OpenFileWnd", "WEB URL"))
    dialogButtonTexts(ui.buttonBox)


def headerEditDialogTexts(window):
    """Apply header editor labels, automatic icon text and standard button captions.

    @param window [QWidget] Initialized window exposing the widgets required by this text function.
    @return [None] Updated captions or completed maintenance operation."""
    ui = window.ui
    window.setWindowTitle(translate("HdrEditDialog", "Edit headers"))
    ui.label.setText(translate("HdrEditDialog", "Section:"))
    ui.label_2.setText(translate("HdrEditDialog", "Default part icon:"))
    ui.icon_selector.setItemText(0, translate("PartsDB", "Auto (from parent section / built-in rule)"))
    dialogButtonTexts(ui.buttonBox)


def importProgressTexts(window, installing=False):
    """Apply progress title, operation label and cancellation availability.

    @param window [QWidget] Initialized window exposing the widgets required by this text function.
    @param installing [bool] True disables cancellation and displays plugin installation captions.
    @return [None] Updated captions or completed maintenance operation."""
    window.setWindowTitle(translate('PluginWorkflow', 'Install plugin') if installing
                          else translate('PluginWorkflow', 'Import project'))
    window.setLabelText(translate('PluginWorkflow', 'Preparing plugin environment...') if installing
                        else translate('PluginWorkflow', 'Reading project...'))
    if installing:
        window.setCancelButton(None)
    else:
        window.setCancelButtonText(translate('PluginWorkflow', 'Cancel'))


def componentHeaders():
    """Build localized imported-component column captions.

    @return [list[str]] Requested translated values or collected metadata."""
    return [translate('PluginWorkflow', 'Reference'), translate('PluginWorkflow', 'Kind'),
            translate('PluginWorkflow', 'Value'), translate('PluginWorkflow', 'Footprint'),
            translate('PluginWorkflow', 'In BOM'), translate('PluginWorkflow', 'On board'),
            translate('PluginWorkflow', 'DNP')]


def importPreviewTexts(window):
    """Apply preview captions and change labels without modifying the import result.

    @param window [QWidget] Initialized window exposing the widgets required by this text function.
    @return [None] Updated captions or completed maintenance operation."""
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
    """Apply localized link and clear captions to component context-menu actions.

    @param link [QAction] Action linking a project component to the selected stock part.
    @param clear [QAction] Action clearing the selected component stock match.
    @return [None] Updated captions or completed maintenance operation."""
    link.setText(translate('PluginWorkflow', 'Link selected stock part'))
    clear.setText(translate('PluginWorkflow', 'Clear stock match'))


def pluginLogsTexts(window):
    """Apply the log window title and localized empty-state text.

    @param window [QWidget] Initialized window exposing the widgets required by this text function.
    @return [None] Updated captions or completed maintenance operation."""
    window.setWindowTitle(translate('PluginWorkflow', 'Plugin logs'))
    if not window.logText:
        window.text.setPlainText(translate('PluginWorkflow', 'No log entries'))


def pluginTypeText(plugin_type):
    """Translate a known functional plugin type, retaining unknown type IDs.

    @param plugin_type [str] Functional plugin type ID from validated metadata.
    @return [str] Requested translated values or collected metadata."""
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
    """Apply section editor captions and standard acceptance/cancellation texts.

    @param window [QWidget] Initialized window exposing the widgets required by this text function.
    @return [None] Updated captions or completed maintenance operation."""
    window.setWindowTitle(translate('PartsDB', 'Section'))
    window.nameLabel.setText(translate('PartsDB', 'Section name:'))
    window.typeLabel.setText(translate('PartsDB', 'Basic type:'))
    dialogButtonTexts(window.buttons)


def partValuesDialogTexts(window):
    """Apply key-input captions and preserve custom database header titles.

    @param window [QWidget] Initialized window exposing the widgets required by this text function.
    @return [None] Updated captions or completed maintenance operation."""
    from ElTranslations import defaultHeaderText
    window.setWindowTitle(translate('PartsDB', 'Add part'))
    window.prompt.setText(translate('PartsDB', 'Enter part nominal'))
    dialogButtonTexts(window.buttons)
    for header in window.headers:
        field = header['field_name']
        window.labels[field].setText(defaultHeaderText(header, field))


def unitsDialogTexts(window):
    """Apply localized reference editor captions, column headers and button texts.

    @param window [UnitsDialog] Initialized dialog with unit/type models and generated widgets.
    @return [None] No value is returned."""
    from PyQt6.QtWidgets import QDialogButtonBox
    ui = window.ui
    window.setWindowTitle(translate('UnitsDialog', 'Units and basic types'))
    ui.add_type_cmd.setText(translate('UnitsDialog', 'Add type'))
    ui.del_type_cmd.setText(translate('UnitsDialog', 'Delete type'))
    ui.add_unit_cmd.setText(translate('UnitsDialog', 'Add unit'))
    ui.del_unit_cmd.setText(translate('UnitsDialog', 'Delete unit'))
    ui.tabWidget.setTabText(ui.tabWidget.indexOf(ui.types_frame), translate('UnitsDialog', 'Basic component types'))
    ui.tabWidget.setTabText(ui.tabWidget.indexOf(ui.units_frame), translate('UnitsDialog', 'SI units'))
    window.unitsModel.setHorizontalHeaderLabels([
        translate('UnitsDialog', 'ID'), translate('UnitsDialog', 'Name (English)'),
        translate('UnitsDialog', 'Name (Russian)'), translate('UnitsDialog', 'Marker (English)'),
        translate('UnitsDialog', 'Marker (Russian)'), translate('UnitsDialog', 'Multiplier'),
        translate('UnitsDialog', 'Base SI unit')])
    window.typesModel.setHorizontalHeaderLabels([
        translate('UnitsDialog', 'ID'), translate('UnitsDialog', 'Name'),
        translate('UnitsDialog', 'Designator'), translate('UnitsDialog', 'Icon'),
        translate('UnitsDialog', 'Base SI unit')])
    ui.buttonBox.button(QDialogButtonBox.StandardButton.Ok).setText(translate('UnitsDialog', 'Save'))
    ui.buttonBox.button(QDialogButtonBox.StandardButton.Cancel).setText(translate('UnitsDialog', 'Cancel'))


def unitsDialogErrorText(message):
    """Translate known reference validation failures and retain unknown diagnostics.

    @param message [str] Data-layer validation or database error text.
    @return [str] Localized known message, otherwise the original diagnostic."""
    messages = {
        'A base unit must not reference another unit': translate('UnitsDialog', 'A base unit must not reference another unit'),
        'Select an existing base unit with multiplier 1 for each prefixed unit': translate('UnitsDialog', 'Select an existing base unit with multiplier 1 for each prefixed unit'),
        'A basic type may reference only a base unit with multiplier 1': translate('UnitsDialog', 'A basic type may reference only a base unit with multiplier 1'),
        'Unit names and markers must not be empty': translate('UnitsDialog', 'Unit names and markers must not be empty'),
        'English unit names and markers must use ASCII characters': translate('UnitsDialog', 'English unit names and markers must use ASCII characters'),
        'The multiplier must be a finite number greater than zero': translate('UnitsDialog', 'The multiplier must be a finite number greater than zero'),
        'Basic type names must not be empty': translate('UnitsDialog', 'Basic type names must not be empty'),
        'Reference data changed; reopen the dialog': translate('UnitsDialog', 'Reference data changed; reopen the dialog'),
        'Cannot delete a basic type used by the catalog or its default type': translate('UnitsDialog', 'Cannot delete a basic type used by the catalog or its default type'),
    }
    return messages.get(message, message)


def dialogButtonTexts(buttons):
    """Apply localized standard acceptance/cancellation captions for handwritten dialogs.

    @param buttons [QDialogButtonBox] Existing button box; absent button kinds are ignored.
    @return [None] Update only the existing standard button captions.
    """
    from PyQt6.QtWidgets import QDialogButtonBox
    for kind, text in ((QDialogButtonBox.StandardButton.Ok, translate('DialogButtons', 'OK')),
                       (QDialogButtonBox.StandardButton.Cancel, translate('DialogButtons', 'Cancel'))):
        button = buttons.button(kind)
        if button is not None:
            button.setText(text)
