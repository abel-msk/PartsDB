from ElTranslations import translate
from ElTranslations import TranslatedDialogMixin
from ElWindowTexts import openFileDialogTexts
from PyQt6.QtCore import QT_TRANSLATE_NOOP
from PyQt6.QtCore import Qt, QDir, QModelIndex, QObject, pyqtSignal
from PyQt6.QtGui import QFileSystemModel, QKeyEvent
from PyQt6.QtWidgets import QDialog, QListWidgetItem, QInputDialog

from ElData import ElDBScheme
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
    """Emit a selected URI, document type and directory; stores Qt signal connections."""
    uriSelected = pyqtSignal(str, int, str)


class OpenFileDialog(TranslatedDialogMixin, QDialog):
    """Select a local file or URL and publish it to the calling controller.

    @attr ui [Ui_OpenFileWnd] Generated selection widgets.
    @attr userRoot [str] Current directory.
    @attr dirModel [QFileSystemModel] Directory tree model.
    @attr fileModel [QFileSystemModel] Current directory contents.
    @attr comm [Communicate] URI selection signal carrier."""
    def __init__(self, parent, userRoot = None):
        """Build local-file and URL selection modes with a starting directory.

        @param parent [QWidget, QObject, None] Qt owner of the created object.
        @param userRoot [str, None] Starting directory; None uses the current user home directory.
        @return [None] Update the owned UI or state without returning a value."""
        super().__init__(parent)
        self.comm = Communicate()
        self.ui = Ui_OpenFileWnd()
        self.ui.setupUi(self)
        self.retranslate()
        self.ui.buttonBox.accepted.connect(self.onAccepted)

        path = QDir.rootPath()
        # path = QDir(os.environ.get('HOME', '/'))
        self.userRoot = os.environ.get('HOME', '/') if userRoot is None else userRoot
        self.ui.pathInput.setText(self.userRoot)
        self.ui.pathInput.returnPressed.connect(self.onChangeRoot)

        self.dirModel = QFileSystemModel()  # for exclude use FilterProxy
        self.dirModel.setRootPath(QDir.rootPath())
        self.dirModel.setFilter(QDir.Filter.NoDotAndDotDot | QDir.Filter.AllDirs)
        self.ui.treeView.setModel(self.dirModel)
        # self.ui.treeView.resizeColumnToContents(1)
        self.ui.treeView.setColumnHidden(1, True)
        self.ui.treeView.setColumnHidden(2, True)
        self.ui.treeView.setColumnHidden(3, True)

        self.fileModel = QFileSystemModel()
        if (self.ui.isFilesOnly.isChecked()):
            self.fileModel.setFilter(QDir.Filter.Files)
        else:
            self.fileModel.setFilter(QDir.Filter.AllDirs | QDir.Filter.Files)
        self.ui.listView.setModel(self.fileModel)

        self.ui.treeView.setRootIndex(self.dirModel.index(self.userRoot))
        self.ui.listView.setRootIndex(self.fileModel.setRootPath(self.userRoot))

        self.ui.treeView.clicked.connect(self.on_clicked)
        self.ui.listView.doubleClicked.connect(self.onFileSelect)

        self.ui.treeView.clicked.connect(self.on_clicked)
        self.ui.isFilesOnly.stateChanged.connect(self.onFilesOnlyChanged)

    def retranslate(self):
        """Refresh selector captions while preserving the path and URL inputs.

        @return [None] Update the owned UI or state without returning a value."""
        openFileDialogTexts(self)

    def keyPressEvent(self, event: QKeyEvent):
        """Keep path-input key handling local or forward it to QDialog.

        @param event [QEvent, QKeyEvent] Qt change or keyboard event delivered to the handler.
        @return [None] Update the owned UI or state without returning a value."""
        if self.ui.pathInput.hasFocus():
            event.accept()
        else:
            super().keyPressEvent(event)

    def on_clicked(self, index):
        """Display the selected directory and update the current path.

        @param index [QModelIndex] Qt model index supplied by the view; parent indices are ignored for flat counts.
        @return [None] Update the owned UI or state without returning a value."""
        path = self.dirModel.fileInfo(index).absoluteFilePath()
        self.ui.listView.setRootIndex(self.fileModel.setRootPath(path))
        self.userRoot = path
        self.ui.pathInput.setText(path)

    def onFilesOnlyChanged(self):
        """Update the current contents model filter after a checkbox change.

        @return [None] Update the owned UI or state without returning a value."""
        fileViewMode = self.ui.listView.model()
        if (self.ui.isFilesOnly.isChecked()):
            fileViewMode.setFilter(QDir.Filter.AllDirs)
        else:
            fileViewMode.setFilter(QDir.Filter.AllDirs | QDir.Filter.Files)
        self.ui.listView.setModel(fileViewMode)

        # self.ui.listView.reset();

    def onChangeRoot(self):
        """Navigate the directory and file views to the entered path.

        @return [None] Update the owned UI or state without returning a value."""
        path = self.ui.pathInput.text()
        # self.ui.listView.setRootIndex(self.fileModel.setRootPath(path))
        self.ui.treeView.setRootIndex(self.dirModel.index(path))
        self.ui.listView.setRootIndex(self.fileModel.setRootPath(path))

    def onAccepted(self):
        """Emit the selected local file or web URI and close the dialog.

        @return [None] Update the owned UI or state without returning a value."""
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
        """Navigate into a directory or emit a selected file and close.

        @param index [QModelIndex] Qt model index supplied by the view; parent indices are ignored for flat counts.
        @return [None] Update the owned UI or state without returning a value."""
        path = self.fileModel.filePath(index)
        if os.path.isdir(path):
            self.ui.treeView.setRootIndex(self.dirModel.index(path))
            self.ui.listView.setRootIndex(self.fileModel.setRootPath(path))
        else:
            logger.debug("File selected: %s", path)
            self.comm.uriSelected.emit(path, ElDBScheme.getTypeByExt(path), self.userRoot)
            self.close()


