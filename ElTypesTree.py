import logging
import sys
from typing import Any

from PyQt6 import QtCore, QtGui
from PyQt6.QtCore import Qt, QModelIndex, QObject, pyqtSignal
from PyQt6.QtGui import QStandardItemModel, QStandardItem, QAction, QDropEvent
from PyQt6.QtWidgets import QTreeWidget, QTreeView, QMenu, QInputDialog, QMessageBox
from ElDBScheme import DBFactory, Type, Types, Part

logger = logging.getLogger(__name__)
logger.setLevel(level=logging.DEBUG)
handler = logging.StreamHandler(stream=sys.stderr)
handler.setFormatter(logging.Formatter(fmt='%(asctime)s [%(levelname)s] %(module)s/%(funcName)s: %(message)s'))
logger.addHandler(handler)

#  https://stackoverflow.com/questions/55553660/how-to-emit-custom-events-to-the-event-loop-in-pyqt

# CLICK_EVENT_NAME = "on_click"


class Communicate(QObject):
    typeSelect = pyqtSignal(Type, object)


class TypesTree(QtCore.QObject):
    def __init__(self, factory: DBFactory, treeWidget: QTreeView):
        super().__init__()
        self.comm = Communicate()
        self._events = {}
        self.dbFactory = factory
        self.rootElements = None
        self.treeWidget: QTreeView = treeWidget
        self.treeModel = QStandardItemModel()
        self.treeWidget.setModel(self.treeModel)
        # self.rootNode = self.treeModel.invisibleRootItem()
        self.rootNode: QStandardItem = None

        self.treeWidget.setRootIsDecorated(True)  # Clear current tree content
        self.treeWidget.setUniformRowHeights(True)
        self.treeWidget.setHeaderHidden(True)
        self.treeWidget.clicked.connect(self.onClick)
        self.lastClickedItem: QStandardItem = None

        self.treeWidget.model().dataChanged.connect(self.onDataChanged)

        self.treeWidget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.treeWidget.customContextMenuRequested.connect(self.onMenuEvent)

        self.menu = self._defineMenu()
        # self.selector_view.setFocus()
        # self.selector_view.clicked['QModelIndex'].connect(self.on_tree_selected)
        # treeView.scrollTo(item.index())

        # self.treeWidget.setAcceptDrops(True)
        # # self.treeWidget.setDropIndicatorShown(True)
        self.treeWidget.viewport().setAcceptDrops(True)
        self.treeWidget.setAcceptDrops(True)
        self.treeWidget.setDragEnabled(True)
        # self.treeWidget.setDragDropMode()

        #
        # self.savedDropEvent = self.treeWidget.dropEvent
        # self.treeWidget.dropEvent = self.localDropEvent

    def localDropEvent(self, event: QDropEvent):
        logger.debug("Got Drop Event")
        pos = event.pos()
        widget = event.source()
        event.accept()

    def _defineMenu(self):
        addAct = QAction("Add Type", self.treeWidget)
        addAct.setStatusTip("Add new type object at the current level.")
        addAct.triggered.connect(self.add)

        addChildAct = QAction("Add Child Type", self.treeWidget)
        addChildAct.setStatusTip("Add new 'Type' object as child of selected.")
        addChildAct.triggered.connect(self.addChild)

        RenAct = QAction("Rename Type", self.treeWidget)
        RenAct.setStatusTip("Rename selected 'Type' object.")
        RenAct.triggered.connect(self.rename)

        delAct = QAction("Delete Child", self.treeWidget)
        delAct.setStatusTip("Delete selected 'Type' object with all included Parts.")
        delAct.triggered.connect(self.delete)

        # # show menu about the column
        menu = QMenu(self.treeWidget)
        menu.addAction(addAct)
        menu.addAction(addChildAct)
        menu.addAction(RenAct)
        menu.addSeparator()
        menu.addAction(delAct)
        return menu

    def onClick(self, sel: QModelIndex):
        self.lastClickedItem = self.treeModel.itemFromIndex(sel)
        theType: Type = self.lastClickedItem.data(Qt.ItemDataRole.UserRole)
        logger.debug("Clicked: %s", theType.name)
        # self.dispatchEvent(CLICK_EVENT_NAME, theType)
        self.comm.typeSelect.emit(theType, None)

    def onMenuEvent(self, point):
        idx: QModelIndex = self.treeWidget.indexAt(point)
        logger.debug("Got Menu Event for tables cells.  row=%s, column=%s", idx.row(), idx.column())
        coord = self.treeWidget.mapToGlobal(point)
        self.menu.popup(coord)

    def clear(self):
        model: QStandardItemModel = self.treeWidget.model()
        if model is not None:
            model.clear()       # works
            model.setRowCount(0)  # works

    def load(self):
        if self.rootNode is not None:
            self.clear()
        # self.clearQTreeWidget(self.treeWidget)

        self.rootNode = self.treeModel.invisibleRootItem()
        self.rootNode.setData(None, Qt.ItemDataRole.UserRole)
        self._loadNodes_(self.rootNode, self.dbFactory.getRootTypes())
        logger.debug("Tree Complete.")

        ### Select first item
        if self.rootNode.hasChildren():
            item = self.rootNode.child(0, 0)
            self.selectItem(item)
            self.treeWidget.setFocus()
            # self.dispatchEvent(CLICK_EVENT_NAME, item.data(Qt.ItemDataRole.UserRole))

        self.treeModel.sort(0, Qt.SortOrder.AscendingOrder)
        # self.treeModel.setSortRole(Qt.ItemDataRole.DisplayRole)
        # self.treeModel.sort(self.modelColumn(), Qt.DescendingOrder)

    def selectItem(self, item, part:Part=None):
        """
        Select Type item in tree view and select part in table (if parts param are sent)
        :param item:
        :param part:
        :return:
        """
        newIndex = self.treeWidget.model().indexFromItem(item)
        self._expandInDeep(item)

        self.treeWidget.selectionModel().select(
            newIndex,
            QtCore.QItemSelectionModel.SelectionFlag.ClearAndSelect)

        self.treeWidget.selectionModel().currentRowChanged.emit(
            newIndex,
            newIndex)

        # self.dispatchEvent(CLICK_EVENT_NAME, item.data(Qt.ItemDataRole.UserRole))
        self.comm.typeSelect.emit(item.data(Qt.ItemDataRole.UserRole), part)

    def _expandInDeep(self, item:QStandardItem ):
        prnt:QStandardItem = item.parent()
        if prnt is not None and prnt != self.rootNode:
            self._expandInDeep(prnt)
        index = self.treeWidget.model().indexFromItem(item)
        self.treeWidget.setExpanded(index, True)

    def getSelectedIndex(self):
        # return self.treeWidget.selectionModel().selectedIndexes()
        # self.treeWidget.getSelectedIndex()[0] if len(self.typesTree.getSelectedIndex()) > 0 else None
        return self.treeWidget.selectionModel().selectedIndexes()[0] \
            if len(self.treeWidget.selectionModel().selectedIndexes()) > 0 else None

    def _loadNodes_(self, node: QStandardItem, types_list: Types):
        for theType in types_list:
            childNode = QStandardItem(theType.name)
            childNode.setData(theType, Qt.ItemDataRole.UserRole)

            # Check for children.
            if theType.isChildren():
                self._loadNodes_(childNode, theType.getChildren())
            node.appendRow(childNode)

    def add(self):
        logger.debug("Add menu clicked.")
        name = self.getInput()
        if name.strip() != "":
            self._add(name)

    def _add(self, name, parentIndex: QModelIndex = None):
        if name == "":
            raise ValueError("Type name cannot be empty.")
        if parentIndex is None:
            parentIndex: QModelIndex = self.treeModel.indexFromItem(self.rootNode)
            # self.treeModel.invisibleRootItem()
            # parentItem: QStandardItem = self.rootNode
            # # index: QModelIndex = self.treeWidget.selectedIndexes()[0]
            # neighbor: Type = index.data(Qt.ItemDataRole.UserRole)
            # neighborItem :QStandardItem = index.model().itemFromIndex(index)

        # parentItem: QStandardItem = neighborItem.parent() if neighborItem.parent() is not None else self.rootNode
        # parentType: Type = parentItem.data(Qt.ItemDataRole.UserRole)
        return self._addChild(name, parentIndex)

    def addChild(self):
        logger.debug("Add child menu clicked.")
        index: QModelIndex = self.treeWidget.selectedIndexes()[0]
        name = self.getInput()
        if name.strip() != "":
            self._addChild(name, index)

    def _addChild(self, name, parentIndex: QModelIndex ):
        if name == "":
            raise ValueError("Type name cannot be empty.")
        parentType: Type = parentIndex.data(Qt.ItemDataRole.UserRole)
        parentItem: QStandardItem = self.treeModel.itemFromIndex(parentIndex)
        if parentItem is None:
            parentItem = self.rootNode

        newType = self.dbFactory.appendType(name, parentType)
        childItem = QStandardItem(newType.name)
        childItem.setData(newType, Qt.ItemDataRole.UserRole)
        parentItem.appendRow(childItem)
        self.treeModel.sort(0, Qt.SortOrder.AscendingOrder)
        return newType

    def onDataChanged(self, top_left, bottom_right, roles):
        logger.debug("Got data changed event.  Data = %s, roles=%s", top_left.data(), "|".join(str(x) for x in roles))
        if top_left == bottom_right and Qt.ItemDataRole.DisplayRole in roles:
            theType = top_left.data(Qt.ItemDataRole.UserRole)
            theType.rename(top_left.data())
            self.treeModel.sort(0, Qt.SortOrder.AscendingOrder)

    def rename(self):
        logger.debug("Delete menu clicked.")
        index: QModelIndex = self.treeWidget.selectedIndexes()[0]
        name = self.getInput()
        if name.strip() != "":
            self._rename(name)

    def _rename(self, value):
        if value == "":
            raise ValueError("Type name cannot be empty.")
        index: QModelIndex = self.treeWidget.selectedIndexes()[0]
        theType = index.data(Qt.ItemDataRole.UserRole)
        item: QStandardItem = index.model().itemFromIndex(index)
        # theType: Type = item.data(Qt.ItemDataRole.UserRole)
        logger.debug("Selected Item %s", theType.name)
        theType.rename(value)
        # self.treeModel.beginResetModel()
        item.setData(value, Qt.ItemDataRole.DisplayRole)
        self.treeWidget.model().dataChanged.emit(index, index, [Qt.ItemDataRole.DisplayRole])
        self.treeModel.sort(0, Qt.SortOrder.AscendingOrder)

    def delete(self):
        logger.debug("Delete menu clicked.")
        index: QModelIndex = self.treeWidget.selectedIndexes()[0]
        theType: Type = index.data(Qt.ItemDataRole.UserRole)
        if theType is None:
            logger.warning("Empty object in type %s", index.data(Qt.ItemDataRole.DisplayRole))
            return
        button = QMessageBox.question(self.treeWidget,"Delete type",
                                   "Are you shure want to delete Type {} ?".format(theType.name))
        if button == QMessageBox.StandardButton.Yes:
            self._delete(index)

        # dlg.setWindowTitle("Delete type")
        # dlg.setText("Are you shure want to delete Type {} ?".format(theType.name))
        # dlg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        # dlg.setIcon(QMessageBox.Icon.Question)
        # button = dlg.exec()

    def _delete(self, index):
        if index is None:
            raise ValueError("Type name cannot be empty.")
        theType: Type = index.data(Qt.ItemDataRole.UserRole)
        Item: QStandardItem = self.treeModel.itemFromIndex(index)
        #TODO:
        # Get Type object
        # Get Types Parent
        # Move items to parent

        self.treeWidget.model().removeRow(index.row(), index.parent())
        self.dbFactory.scheme.delType(theType.recId)
        self.treeModel.sort(0, Qt.SortOrder.AscendingOrder)

        item = self.rootNode.child(0, 0)
        self.selectItem(item)
        self.treeWidget.setFocus()

    # def addEventListener(self, name, func):
    #     if name not in self._events:
    #         self._events[name] = [func]
    #     else:
    #         self._events[name].append(func)

    # def dispatchEvent(self, name, arg):
    #     functions = self._events.get(name, [])
    #     for func in functions:
    #         QtCore.QTimer.singleShot(0, lambda: func(arg))

    def getInput(self, prompt = "") -> str:
        if prompt == "":
            prompt = 'Enter Type Object Name:'
        value, ok = QInputDialog.getText(self.treeWidget, 'Enter Name', prompt)
        if ok and value:
            return value
        else:
            return ""

    def getItemByID(self, theId):
        return self._scanChilds(theId,self.rootNode)

    def getIndexByID(self, theId):
        """
        Expand and select Type item by their db id in the types tree
        :param theId:
        :return:
        """
        foundItem = self._scanChilds(theId, self.rootNode)
        if foundItem is not None:
            return self.treeWidget.model().indexFromItem(foundItem)
        return None

    def _scanChilds(self, theId, item: QStandardItem ):
        for row in range(0, item.rowCount()):
            childItem = item.child(row,0)
            theType: Type = childItem.data(Qt.ItemDataRole.UserRole)
            if theType.recId == theId:
                logger.debug("Found child Item. Path = %s", theType.path)
                return childItem
            elif childItem.hasChildren():
                foundItem = self._scanChilds(theId, childItem)
                if foundItem is not None:
                    return foundItem
        return None


