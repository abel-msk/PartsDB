from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QListWidgetItem, QInputDialog, QWidget

import ElLogger
from ElAppList import AppList, AppDef
from ElAppPathWnd import Ui_AppPathDialog
import logging
import os
import sys

from ElConfig import ElConfig
from ElOpenFileDialog import OpenFileDialog
logger = ElLogger.setLogger(__name__)

# logger = logging.getLogger(__name__)
# logger.setLevel(level=logging.DEBUG)
#
# handler = logging.StreamHandler(stream=sys.stderr)
# handler.setFormatter(logging.Formatter(fmt='%(asctime)s [%(levelname)s] %(module)s/%(funcName)s: %(message)s'))
# logger.addHandler(handler)


class AppPathConfig(QDialog):
    """Employee dialog."""
    def __init__(self, parent, app_list: AppList):
        super().__init__(parent)
        self.ui = Ui_AppPathDialog()

        self.ui.setupUi(self)
        self.ui.buttonBox.accepted.connect(self.onAccepted)
        self.ui.widget.window().setWindowTitle("View application select")

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

    def onAppSelect(self, index):
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
        value, ok = QInputDialog.getText(self, 'Add application', "Enter application name")
        if ok and value:
            app = self.appList.add(value)
            item = QListWidgetItem(value)
            item.setData(Qt.ItemDataRole.UserRole, app)
            self.ui.appNamesList.addItem(item)

    def onAccepted(self):
        logger.debug("Dialog OK button ressed.")
        self.appList.save()

    def onDelApp(self):
        for item in self.ui.appNamesList.selectedItems():
            app: AppDef = item.data(Qt.ItemDataRole.UserRole)
            self.appList.remove(app.name)
            self.ui.appNamesList.takeItem(self.ui.appNamesList.row(item))
            logger.debug("Delete app description %s", app.name)
            # app.remove()
            # self.appList.remove(app.name)
            self.appList.save()

    def onOpenApp(self):
        dlg = OpenFileDialog(self, "/Applications")
        dlg.comm.uriSelected.connect(self.onAddDocSelected)
        dlg.exec()

    def onAddDocSelected(self, uri, type, docRoot=None):
        self.ui.appExeInput.setText(uri)

    def onSave(self):
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
