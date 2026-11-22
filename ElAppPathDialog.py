from PyQt6.QtWidgets import QFileDialog
from ElTranslations import translate
from ElTranslations import TranslatedDialogMixin
from ElWindowTexts import appPathDialogTexts
from PyQt6.QtCore import QT_TRANSLATE_NOOP
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QListWidgetItem, QInputDialog, QWidget

import ElCommon as ElCommon
from ElAppList import AppList, AppDef
from ElAppPathWnd import Ui_AppPathDialog
import logging
import os
import sys

from ElConfig import ElConfig
logger = ElCommon.setLogger(__name__)

# logger = logging.getLogger(__name__)
# logger.setLevel(level=logging.DEBUG)
#
# handler = logging.StreamHandler(stream=sys.stderr)
# handler.setFormatter(logging.Formatter(fmt='%(asctime)s [%(levelname)s] %(module)s/%(funcName)s: %(message)s'))
# logger.addHandler(handler)


class AppPathConfig(TranslatedDialogMixin, QDialog):
    """Edit configured applications for opening part documents.

    @attr ui [Ui_AppPathDialog] Generated form widgets.
    @attr appList [AppList] Application rules and their configuration storage."""
    def __init__(self, parent, app_list: AppList):
        """Populate application rules and connect the editor controls.

        @param parent [QWidget, QObject, None] Qt owner of the created object.
        @param app_list [AppList] Configured applications for opening part documents.
        @return [None] Update the owned UI or state without returning a value."""
        super().__init__(parent)
        self.ui = Ui_AppPathDialog()

        self.ui.setupUi(self)
        self.retranslate()
        self.ui.buttonBox.accepted.connect(self.onAccepted)

        self.appList: AppList = app_list
        logger.debug("Load config %s", )
        for name in self.appList.getNames():
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, self.appList[name])
            self.ui.appNamesList.addItem(item)

        self.ui.appNamesList.clicked.connect(self.onAppSelect)
        self.ui.appOpenBtn.clicked.connect(self.onOpenApp)
        self.ui.addBtn.clicked.connect(self.onAddApp)
        self.ui.delBtn.clicked.connect(self.onDelApp)
        self.ui.saveBtn.clicked.connect(self.onSave)

    def retranslate(self):
        """Refresh application editor captions without changing pending input.

        @return [None] Update the owned UI or state without returning a value."""
        appPathDialogTexts(self)

    def onAppSelect(self, index):
        """Display the selected application rule in the input fields.

        @param index [QModelIndex] Qt model index supplied by the view; parent indices are ignored for flat counts.
        @return [None] Update the owned UI or state without returning a value."""
        logger.debug("App Selected")
        items = self.ui.appNamesList.selectedItems()
        app = index.data(Qt.ItemDataRole.UserRole)
        if app is not None:
            self.ui.appNameInput.setText(app.name)
            self.ui.appExeInput.setText(app.exe)
            self.ui.appExtInput.setText(app.ext)
            self.ui.appArgsInput.setText(app.args)
        else:
            logger.error("Incorrect selection")

    def onAddApp(self):
        """Ask for a rule name and append a new application rule.

        @return [None] Update the owned UI or state without returning a value."""
        value, ok = QInputDialog.getText(self, translate("PartsDB", 'Add application'), translate("PartsDB", 'Enter application name'))
        if ok and value:
            app = self.appList.add(value)
            item = QListWidgetItem(value)
            item.setData(Qt.ItemDataRole.UserRole, app)
            self.ui.appNamesList.addItem(item)

    def onAccepted(self):
        """Save the application configuration on acceptance.

        @return [None] Update the owned UI or state without returning a value."""
        logger.debug("Dialog OK button pressed.")
        self.appList.save()

    def onDelApp(self):
        """Remove selected application rules and persist their configuration.

        @return [None] Update the owned UI or state without returning a value."""
        for item in self.ui.appNamesList.selectedItems():
            app: AppDef = item.data(Qt.ItemDataRole.UserRole)
            self.appList.remove(app.name)
            self.ui.appNamesList.takeItem(self.ui.appNamesList.row(item))
            logger.debug("Delete app description %s", app.name)
            # app.remove()
            # self.appList.remove(app.name)
            self.appList.save()

    def onOpenApp(self):
        """Choose an application executable using the file selection dialog.

        @return [None] Update the owned UI or state without returning a value."""
        filename, _ = QFileDialog.getOpenFileName(self, translate('PartsDB', 'Select application'), '/Applications')
        if filename:
            self.ui.appExeInput.setText(filename)

    def onAddDocSelected(self, uri, type, docRoot=None):
        """Copy the selected application URI into the executable input.

        @param uri [str] Chosen application file path or URI.
        @param type [int] Document type returned by the selector; not used for this field.
        @param docRoot [str, None] Legacy selector root argument; not used by this handler.
        @return [None] Update the owned UI or state without returning a value."""
        self.ui.appExeInput.setText(uri)

    def onSave(self):
        """Create or update the displayed application rule and save its fields.

        @return [None] Update the owned UI or state without returning a value."""
        app = None
        items = self.ui.appNamesList.selectedItems()
        name = self.ui.appNameInput.text()
        if len(items) > 0:
            app: AppDef = items[0].data(Qt.ItemDataRole.UserRole)
        else:
            if name in self.appList.getNames():
                app = self.appList.getAppByName(name)
            else:
                app = self.appList.add(name)
                item = QListWidgetItem(name)
                item.setData(Qt.ItemDataRole.UserRole, app)
                self.ui.appNamesList.addItem(item)

        if app is not None:
            app.exe = self.ui.appExeInput.text()
            app.ext = self.ui.appExtInput.text()
            app.args = self.ui.appArgsInput.text()
            app.save()
        else:
            logger.error("Wrong app name %s", name)

        self.appList.save()
