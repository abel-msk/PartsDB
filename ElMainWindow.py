import logging
import os
import sys

from PyQt6 import QtWidgets, QtGui, QtCore
from PyQt6.QtCore import Qt, QItemSelectionModel, QPoint, QPointF, QModelIndex
from PyQt6.QtGui import QIcon, QAction, QDragEnterEvent, QDropEvent, QDragMoveEvent
from PyQt6.QtWidgets import QApplication, QWidget, QMainWindow, QInputDialog, QMessageBox, QFileDialog, QDialog

import ElConfig
import ElDBScheme
import ElLogger
import ElTypesTree
import constants
from ElAppList import AppList
from ElAppPathDialog import AppPathConfig
from ElDBScheme import DBFactory, Type, Part, Document
from ElFileDialog import FileListW
from ElHdrEditDialog import HeaderEditDialog
from ElOpenFileDialog import OpenFileDialog
from ElParts import Ui_MainWindow
from ElPartsTable import PartsTableModel, TableView
from ElProcess import ProcessFactory, Process
from ElTypesTree import TypesTree

logger = ElLogger.setLogger(__name__)
# logger = logging.getLogger(__name__)
# logger.setLevel(level=logging.DEBUG)
# handler = logging.StreamHandler(stream=sys.stderr)
# handler.setFormatter(logging.Formatter(fmt='%(asctime)s [%(levelname)s] %(module)s/%(funcName)s: %(message)s'))
# logger.addHandler(handler)

#
# icon = QtGui.QIcon()
# icon.addPixmap(QtGui.QPixmap(":/icons/search.png"), QtGui.QIcon.Mode.Normal, QtGui.QIcon.State.Off)
# self.toolButton_2.setIcon(icon)
#


###
###   PyQT dialogs https://zetcode.com/pyqt6/dialogs/
###


def showWarn(parent, text):
    """
    Macro for
    :param parent:
    :param text:
    :return:
    """
    button = QMessageBox.warning(
        parent,
        "Warning",
        text,
        buttons=QMessageBox.StandardButton.Ok,
        defaultButton=QMessageBox.StandardButton.Ok,
    )


class MainWindow(QMainWindow, Ui_MainWindow):

    def __init__(self, dbFactory: DBFactory, config: ElConfig, *args, **kwargs):
        super(MainWindow, self).__init__(*args, **kwargs)
        self.setupUi(self)
        self.documentRoot = None
        self.setObjectName("Electronic parts workbench")
        self.setWindowTitle("Electronic parts workbench")
        self.config: ElConfig = config
        self.factory: DBFactory = dbFactory

        self.procFactory: ProcessFactory = ProcessFactory()
        self.appList: AppList = AppList(self.config)

        self.typesTree: TypesTree = TypesTree(dbFactory, self.types_tree_view)
        # self.typesTree.addEventListener(ElTypesTree.CLICK_EVENT_NAME, self.onTreeSelect)
        self.typesTree.comm.typeSelect.connect(self.onTreeSelect)

        self.partsTable = TableView(self.factory, self.parts_tbl_view, self.docListWidget)
        self.docList = self.partsTable.iconsListWidget

        #
        #   Define events
        #
        self.partsTable.comm.documentSelect.connect(self.onDocumentSelect)
        self.partsTable.comm.partSelect.connect(self.onPartSelect)
        self.partsTable.comm.partsTypeRequest.connect(self.onLoadPartsType)
        self.partsTable.comm.hdrEditRequest.connect(self.onEditHeader)

        # self.typesTree.addEventListener(ElTypesTree.CLICK_EDIT_HEADER, self.onTreeSelect)

        #  >>>> self.docListView.setObjectName("docListView")
        self.addTypeBtn.clicked.connect(self.onTypeAddBtn)
        self.delTypeBtn.clicked.connect(self.onTypeDelBtn)
        self.addPartBtn.clicked.connect(self.onAddPart)
        self.addDocBtn.clicked.connect(self.onAddDoc)
        self.delDocBtn.clicked.connect(self.onDelDoc)
        self.searchBtn.clicked.connect(self.onSearch)

        self._defineMenu_()
        self.savedTreeSelection = self.typesTree.getSelectedIndex()

    def dragEnterEvent(self, event: QDragEnterEvent):
        """
        Process event and accepts. Start Drag action.
        :param event:
        :return:
        """
        event.ignore()

        if event.source() == self.partsTable.tableView:
            # self.dragged_index = self.partsTable.tableView.selectionModel().selectedIndexes()[0]
            # self.dragged_item = self.tableView.model.itemFromIndex(self.dragged_index)
            # self.types_tree_view.setEnabled(True)
            # self.docListWidget.setEnabled(False)
            # self.parts_tbl_view.setEnabled(True)
            self.statusbar.showMessage("Drag Records to types tree area.", 2000)
            event.accept()

        elif event.source() is None:
            event.setDropAction(Qt.DropAction.LinkAction)
            # self.types_tree_view.setEnabled(False)
            # self.parts_tbl_view.setEnabled(False)
            # self.docListWidget.setEnabled(True)
            self.statusbar.showMessage("Drag file to Document view area.", 2000)
            event.accept()

    def dragLeaveEvent(self, event):
        """
        Process event when drop action canceled
        :param event:
        :return:
        """
        # Restore selection
        self.types_tree_view.selectionModel().select(self.savedTreeSelection,
                                                     QtCore.QItemSelectionModel.SelectionFlag.ClearAndSelect)
        # self.types_tree_view.setEnabled(True)
        # self.parts_tbl_view.setEnabled(True)
        # self.docListWidget.setEnabled(True)
        event.accept()
        super().dragLeaveEvent(event)
        self.statusbar.showMessage("Drag cancel.", 1000)

    def dropEvent(self, event: QDropEvent):
        """
        Process event when for dropping.
        :param event:
        :return:
        """
        super().dropEvent(event)
        success = False
        #
        #  Drop parts to new selected Type
        #
        if event.source() == self.partsTable.tableView:
            logger.debug("Got Drop event for parts")
            pos = self.types_tree_view.viewport().mapFromGlobal(QtGui.QCursor().pos())
            if pos.y() > 0 and pos.x() > 0:
                index = self.types_tree_view.indexAt(pos)
                if index is not None and index.isValid():
                    theType = index.data(Qt.ItemDataRole.UserRole)   #itemFromIndex
                    # self.partsTable.tableView.model().beginRemoveRows()
                    for partIndex in self.partsTable.tableView.selectionModel().selectedRows(column=1):
                        thePart: Part = partIndex.data(Qt.ItemDataRole.UserRole)
                        theType.appendExistChild(thePart.id)
                    self.onTreeSelect(theType)
                    self.statusbar.showMessage("Drop records to the `{}` type.".format(theType.name), 2000)
                    success = True
        #
        #  Drop file to the Part document list
        #
        else:
            pos: QPoint = self.docListWidget.mapFromGlobal(self.mapToGlobal(event.position()))
            if pos.x() > 0 and pos.y() > 0:
                dataList = event.mimeData().urls()
                mimeData: QtCore.QByteArray = event.mimeData().data("text/plain")
                # data = event.mimeData().data("text/csv")
                dataAr = mimeData.data().decode().split("\n")
                for data in dataAr:
                    if str(data).startswith("file:///"):
                        fname = data[len("file:///")-1:]
                        ext = os.path.splitext(fname)[1][1:]
                        type = ElDBScheme.extToDocType(ext)
                        logger.debug("Add file %s, ext=%s", fname, ext)
                        try:
                            self.onAddDocSelected(fname, type)
                        except KeyError as er:
                            pass
                        self.statusbar.showMessage("Add link to Document : `{}`.".format(fname), 2000)
                    elif str(data).startswith("http:") or str(data).startswith("https:"):
                        self.onAddDocSelected(data, ElDBScheme.DOC_TYPE_URL)
                        logger.debug("Add URL %s", data)
                        self.statusbar.showMessage("Add link to URL : `{}`.".format(data), 2000)

                success = True

            else:
                logger.debug("Drop action out of area. x=%s, y=%s", pos.x(), pos.y())
            # self.types_tree_view.setEnabled(True)
            # self.parts_tbl_view.setEnabled(True)
            # self.docListWidget.setEnabled(True)
            if success:
                event.accept()
            else:
                event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent):
        """
        Process event when mouse in D&D mode moved.
        :param event:
        :return:
        """

        ###
        #   Process moving D&D from PartsTale to TypesList. Select a corresponding type while hover
        #
        if event.source() == self.partsTable.tableView:
            pos = self.types_tree_view.viewport().mapFromGlobal(QtGui.QCursor().pos())
            if pos.y() > 0 and pos.x() > 0:
                index = self.types_tree_view.indexAt(pos)
                if index.data(Qt.ItemDataRole.UserRole) is not None:
                    self.types_tree_view.selectionModel().select(index,
                        QtCore.QItemSelectionModel.SelectionFlag.ClearAndSelect)
            self.statusbar.showMessage("Drag Records to types tree area.", 2000)
        else:
            self.statusbar.showMessage("Drag file to Document view area.", 2000)
        super().dragMoveEvent(event)

    def _defineMenu_(self):
        """
        Define popup menus items
        :return:
        """
        bar = self.menuBar()
        bar.setNativeMenuBar(True)

        file = bar.addMenu("File")
        setup = bar.addMenu("Setup")

        open_act = QAction("Open DB", self)
        open_act.setStatusTip("Open an existing DB")
        open_act.setShortcut("Ctrl+O")
        open_act.triggered.connect(self.onOpenDB)
        file.addAction(open_act)

        save_act = QAction("Create new DB", self)
        save_act.setShortcut("Ctrl+N")
        save_act.triggered.connect(self.newDB)
        file.addAction(save_act)

        open_act = QAction("Docs open exe", self)
        open_act.setStatusTip("Configure applications for opening documents")
        open_act.triggered.connect(self.ConfigureAppsExe)
        setup.addAction(open_act)

        header_act = QAction("Edit headers", self)
        header_act.setStatusTip("Edit parts tbl header property for each type")
        header_act.triggered.connect(self.onEditHeader)
        setup.addAction(header_act)

    def onTreeSelect(self, theType: Type, thePart:Part=None):
        """
        Process event when Type selected.  Redrew parts table with this types parts
        :param theType:
        :return:
        """
        self.savedTreeSelection = self.typesTree.getSelectedIndex()
        self.typesTree.getSelectedIndex()
        self.partsTable.loadData(theType)

        # Clear search string
        self.searchStr.setText("")
        # self.types_tree_view.setEnabled(True)
        if thePart is not None:
            self.partsTable.selectByID(thePart.id)

        self.partsTable.setFocus()

    def onPartSelect(self, thePart: Part):
        """
        Process event when part selected
        :param thePart:
        :return:
        """
        # logger.debug("Got Event onClick. Type %s", thePart["part_num"])
        self.statusbar.showMessage("Part selected.", 2000)

    def onLoadPartsType(self, thePart:Part):
        self.statusbar.showMessage("Part selected.", 2000)
        theType:Type = self.factory.getTypeByID(thePart["type_id"])
        logger.debug("Matched Types path = %s, name= %s", theType.path, theType.name)

        item = self.typesTree.getItemByID(theType.recId)
        if item is not None:
            self.typesTree.selectItem(item, thePart)
            # self.partsTable.selectByID(thePart.id)
            # self.treeWidget.setFocus()


        # rootIndex: QModelIndex = self.typesTree.treeModel.indexFromItem(self.typesTree.rootNode)
        #
        # self.typesTree.selectItem(theType)

        # treeModel = self.types_tree_view.model()
        # firstIndex = treeModel.sibling(0,0,self.types_tree_view.rootIndex())
        #
        # selectItem
        #
        # index = treeModel.match(firstIndex,
        #                 Qt.ItemDataRole.UserRole,
        #                 theType,
        #                 hits=1,
        #                 flags=Qt.MatchFlag.MatchWrap
        # )
        #
        # # flags = Qt.MatchFlags(Qt.MatchStartsWith | Qt.MatchWrap)]])
        #
        # self.types_tree_view.selectionModel().select(index[0],
        #                                              QtCore.QItemSelectionModel.SelectionFlag.ClearAndSelect)

        # self.onTreeSelect(theType)
        # self.partsTable.loadData(theType)


    def onDocumentSelect(self, doc: Document):
        """
        Open selected document. Get corresponding application from AppList
        and run it with document as parameter
        :param doc:
        :return:
        """
        logger.debug("Select Document %s", doc.link)
        app = self.appList.getAppByExt(doc.getLinkExt())
        if app is not None:
            # args = str(app.args).format(file=doc.link)
            argsAr = []
            for token in str(app.args).split(" "):
                if token == "{file}":
                    token = doc.link
                argsAr.append(token)

            # process = self.procFactory.createProcess(app.name+" : "+doc.link)
            process = self.procFactory.createProcess(app.name)
            # process = Process(app.name)
            process.setAppExe(app.exe)
            process.run(argsAr)
            #TODO: Clenup finished jobs

            self.statusbar.showMessage("Open Document.", 4000)
        else:
            self.statusbar.showMessage("No application for open document", 4000)

    def onTypeAddBtn(self):
        """
        Got event when Add type btn pressed
        :return:
        """
        self.statusbar.showMessage("Add type", 2000)
        self.typesTree.add()

    def onTypeRenBtn(self):
        """
        Got event when rename
        """
        self.statusbar.showMessage("Rename type", 2000)
        self.typesTree.rename()

    def onTypeDelBtn(self):
        """
        Got event when delete btn pressed
        """
        self.statusbar.showMessage("Delete type", 2000)
        self.typesTree.delete()

    def onAddPart(self):
        """
        Got event when add part pressed
        """
        self.statusbar.showMessage("Add part", 2000)
        self.partsTable.addRow()

    def onAddDoc(self):
        """
        Got event when add Document pressed
        :return:
        """
        self.statusbar.showMessage("Select Document", 2000)
        sel = self.partsTable.getSelected()
        if sel is not None:
            dlg = OpenFileDialog(self, self.documentRoot)
            dlg.comm.uriSelected.connect(self.onAddDocSelected)
            dlg.exec()
        else:
            showWarn(self, "Please select part first.")

    def onEditHeader(self):
        dlg = HeaderEditDialog(self.documentRoot, self.factory)
        # dlg.comm.uriSelected.connect(self.onAddDocSelected)
        index = self.typesTree.getSelectedIndex()
        theType: Type = index.data(Qt.ItemDataRole.UserRole)
        dlg.loadData(theType.recId)

        #  Set listener for header changed
        dlg.comm.tblUpdateRequest.connect(self.updateTableColHeader)
        dlg.exec()

    def updateTableColHeader(self, hdrObj: ElDBScheme.Header = None):
        # logger.debug("Got event  update table")
        # self.partsTable.tableView.update()
        # self.partsTable.tableView.horizontalHeader().update()
        # self.partsTable.tableView.verticalHeader().update()
        self.partsTable.updateHeader(hdrObj)

    def onAddDocSelected(self, uri, type, docRoot=None):
        """
        Process event when file for add selected.
        :param uri:
        :param type:
        :param docRoot:
        :return:
        """
        if docRoot is not None:
            self.documentRoot = docRoot
        logger.debug("Got event. Add document selected. %s", uri)
        try:
            self.partsTable.addDocument(uri, type)
        except KeyError as er:
            er = "Incorrect file extension {}".format(er)
            logger.error(er)
            showWarn(self, er)
            # raise er
        self.statusbar.showMessage("Add Document link {}".format(uri), 2000)

    def onDelDoc(self):
        """
        Delete document currently selected
        :return:
        """
        self.partsTable.deleteSelectedDocument()
        self.statusbar.showMessage("Delete Document link", 2000)

    def onSearch(self):
        searchStr = str(self.searchStr.text()).strip()
        if searchStr:
            parts: ElDBScheme.Parts = self.factory.search(searchStr)
            self.partsTable.loadSearchData(parts)
        # self.types_tree_view.setEnabled(False)
        self.statusbar.showMessage("Looking for parts with '{}'".format(searchStr))

    def closeEvent(self, event):
        """
        Event occurred when the main window classed
        :param event:
        :return:
        """
        # self.DB.disconnect()
        if self.config is not None:
            self.config.set_value("width", super(MainWindow, self).width(), "window")
            self.config.set_value("height", super(MainWindow, self).height(), "window")

            # (x, y) = self.location_on_the_screen()
            self.config.set_value("x", self.pos().x(), "window")
            self.config.set_value("y", self.pos().y(), "window")
        else:
            logger.warning("Not defined config. Skip.")
        logger.debug("Got Close Event")

    def onOpenDB(self):
        """
        Open file selection dialog
        :return:
        """
        dlg = OpenFileDialog(self, os.path.expanduser("~"))
        dlg.comm.uriSelected.connect(self.loadDB)
        dlg.exec()

    def loadDB(self, uri, type, docRoot=None):
        """
        Reload DBFactory. Called from OpenFileDialog.
        :param uri: Path to DB file
        :param type:
        :param docRoot:
        :return:
        """
        if type != ElDBScheme.DOC_TYPE_URL:
            self.factory = DBFactory(uri)
            ElDBScheme.DB_FACTORY = self.factory
            self.typesTree = TypesTree(self.factory, self.types_tree_view)
            # self.typesTree.addEventListener(ElTypesTree.CLICK_EVENT_NAME, self.onTreeSelect)

            self.typesTree.comm.typeSelect.connect(self.onTreeSelect)

            self.config.set_value(constants.CONFIG_DB_FILE, self.factory.db_file)
        else:
            logger.warning("Selected file '%s' not local.", uri)

    def newDB(self):
        pass

    def ConfigureAppsExe(self):
        """
        Open selecting application dialog per file types
        :return:
        """
        dlg = AppPathConfig(self, self.appList)
        dlg.exec()
        self.statusbar.showMessage("Configure applications for opening documents")

    def resize_contents(self):
        self.selector_split.setSizes([int(self.selector_split.size().width() * 0.2),
                                     int(self.selector_split.size().width() * 0.8) + 1])

    def setStartupMode(self, startupMode):
        ###  Load Tree
        self.typesTree.load()
        # pass




