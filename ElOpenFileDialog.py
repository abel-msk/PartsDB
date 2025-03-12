from PyQt6.QtCore import Qt, QDir, QModelIndex, QObject, pyqtSignal
from PyQt6.QtGui import QFileSystemModel, QKeyEvent
from PyQt6.QtWidgets import QDialog, QListWidgetItem, QInputDialog

import ElDBScheme
import ElLogger
from ElAppList import AppList, AppDef
from ElAppPathWnd import Ui_AppPathDialog
import logging
import os
import sys

from ElConfig import ElConfig
from ElOpenFileWnd import Ui_OpenFileWnd

# logger = logging.getLogger(__name__)
# logger.setLevel(level=logging.DEBUG)
# handler = logging.StreamHandler(stream=sys.stderr)
# handler.setFormatter(logging.Formatter(fmt='%(asctime)s [%(levelname)s] %(module)s/%(funcName)s: %(message)s'))
# logger.addHandler(handler)
logger = ElLogger.setLogger(__name__)

class Communicate(QObject):
    uriSelected = pyqtSignal(str, int, str)


class OpenFileDialog(QDialog):
    """Employee dialog."""
    def __init__(self, parent, userRoot = None):
        super().__init__(parent)
        self.comm = Communicate()
        self.ui = Ui_OpenFileWnd()
        self.ui.setupUi(self)
        self.ui.buttonBox.accepted.connect(self.onAccepted)

        path = QDir.rootPath()
        # path = QDir(os.environ.get('HOME', '/'))
        self.userRoot = os.environ.get('HOME', '/') if userRoot is None else userRoot
        self.ui.pathInput.setText(self.userRoot)
        self.ui.pathInput.returnPressed.connect(self.onChangeRoot)

        self.dirModel = QFileSystemModel()  # for exclude use FilterProxy
        self.dirModel.setRootPath(QDir.rootPath())
        self.dirModel.setFilter(QDir.Filter.NoDotAndDotDot | QDir.Filter.AllDirs )
        self.ui.treeView.setModel(self.dirModel)
        # self.ui.treeView.resizeColumnToContents(1)
        self.ui.treeView.setColumnHidden(1, True)
        self.ui.treeView.setColumnHidden(2, True)
        self.ui.treeView.setColumnHidden(3, True)

        self.fileModel = QFileSystemModel()
        self.fileModel.setFilter(QDir.Filter.AllDirs | QDir.Filter.Files)
        # self.fileModel.setFilter(QDir.Filter.NoDotAndDotDot | QDir.Filter.Files)
        # self.fileModel.setFilter(QDir.Filter.NoDotAndDotDot | QDir.Filter.Files)

        self.ui.listView.setModel(self.fileModel)

        self.ui.treeView.setRootIndex(self.dirModel.index(self.userRoot))
        self.ui.listView.setRootIndex(self.fileModel.setRootPath(self.userRoot))

        self.ui.treeView.clicked.connect(self.on_clicked)
        self.ui.listView.doubleClicked.connect(self.onFileSelect)

    def keyPressEvent(self, event: QKeyEvent):
        if self.ui.pathInput.hasFocus():
            event.accept()
        else:
            super().keyPressEvent(event)

    def on_clicked(self, index):
        path = self.dirModel.fileInfo(index).absoluteFilePath()
        self.ui.listView.setRootIndex(self.fileModel.setRootPath(path))
        self.userRoot = path
        self.ui.pathInput.setText(path)

    def onChangeRoot(self):
        path = self.ui.pathInput.text()
        # self.ui.listView.setRootIndex(self.fileModel.setRootPath(path))
        self.ui.treeView.setRootIndex(self.dirModel.index(path))
        self.ui.listView.setRootIndex(self.fileModel.setRootPath(path))

    def onAccepted(self):
        wName = self.ui.tabWidget.currentWidget().objectName()
        path = ""
        type = ""

        if wName == "fileTab":
            try:
                index: QModelIndex = self.ui.listView.selectedIndexes()[0]
            except IndexError:
                return
            path = self.fileModel.filePath(index)
            type = ElDBScheme.getTypeByExt(path)

        elif wName == "webTab":
            path = self.ui.webUri.text()
            type = ElDBScheme.DOC_TYPE_URL

        logger.debug("Dialog OK button pressed. Selected URI %s", path)
        self.comm.uriSelected.emit(path, type, self.userRoot)
        self.close()

    def onFileSelect(self, index: QModelIndex):
        path = self.fileModel.filePath(index)
        if os.path.isdir(path):
            self.ui.treeView.setRootIndex(self.dirModel.index(path))
            self.ui.listView.setRootIndex(self.fileModel.setRootPath(path))
        else:
            logger.debug("File selected: %s", path)
            self.comm.uriSelected.emit(path, ElDBScheme.getTypeByExt(path), self.userRoot)
            self.close()


