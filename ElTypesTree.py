from ElTranslations import translate
from PyQt6.QtCore import QT_TRANSLATE_NOOP
from ElTranslations import TranslatedAction as QAction
import logging
import sys
from typing import Any

from PyQt6 import QtCore, QtGui
from PyQt6.QtCore import Qt, QModelIndex, QObject, pyqtSignal, QMimeData
from PyQt6.QtGui import QStandardItemModel, QStandardItem, QDropEvent
from PyQt6.QtWidgets import QTreeWidget, QTreeView, QMenu, QInputDialog, QMessageBox

import ElCommon
from ElCommonUI import ElTreeEditDlg
from ElCommonUI import TwoLineDelegate
from ElConstants import SUBTITLE_ROLE
from ElData import ElDBDataParts
from ElData.ElDBScheme import DBFactory, Type, Types, Part

# logger = logging.getLogger(__name__)
# logger.setLevel(level=logging.DEBUG)
# handler = logging.StreamHandler(stream=sys.stderr)
# handler.setFormatter(logging.Formatter(fmt='%(asctime)s [%(levelname)s] %(module)s/%(funcName)s: %(message)s'))
# logger.addHandler(handler)
logger = ElCommon.setLogger(__name__)

#  https://stackoverflow.com/questions/55553660/how-to-emit-custom-events-to-the-event-loop-in-pyqt

# CLICK_EVENT_NAME = "on_click"


class Communicate(QObject):
    """Publish the selected section and optional stock card to catalog controllers."""
    typeSelect = pyqtSignal(Type, object)


class SectionTreeModel(QStandardItemModel):
    """Keep live section objects in item roles while exporting only plain text to Qt MIME.

    @attr parent [QObject, None] Optional owner; section roles retain their existing database objects.
    """

    def mimeData(self, indexes):
        """Export section captions without serializing Type objects or SQLite connections.

        @param indexes [list[QModelIndex]] Selected tree cells; invalid indexes are ignored.
        @return [QMimeData] Plain-text captions without Qt's serialized item-role payload.
        """
        mime = QMimeData()
        captions = [str(index.data(Qt.ItemDataRole.DisplayRole) or '')
                    for index in indexes if index.isValid()]
        mime.setText('\n'.join(captions))
        logger.debug('Section MIME export: captions=%s formats=%s; database roles excluded',
                     captions, mime.formats())
        return mime


class TypesTree(QtCore.QObject):
    """Manage catalog section navigation, editing and incoming stock-card drops.

    @attr dbFactory [DBFactory] Active catalog factory.
    @attr treeWidget [QTreeView] Section navigation and stock-card drop target.
    @attr treeModel [SectionTreeModel] Captions and live section objects; MIME contains text only.
    """
    def __init__(self, factory: DBFactory, treeWidget: QTreeView):
        """Bind the section model, navigation, menus and incoming drop handling.

        @param factory [DBFactory] factory supplied by the caller.
        @param treeWidget [QTreeView] treeWidget supplied by the caller.
        @return [object, None] Requested section data or completion of the operation.
        """
        super().__init__()
        self.comm = Communicate()
        self._events = {}
        self.dbFactory = factory
        self.rootElements = None
        self.treeWidget: QTreeView = treeWidget
        self.treeModel = SectionTreeModel(treeWidget)
        self.treeWidget.setModel(self.treeModel)
        self.treeWidget.setItemDelegate(TwoLineDelegate(treeWidget, getattr(treeWidget.window(), "config", None)))
        self.treeWidget.setEditTriggers(QTreeView.EditTrigger.NoEditTriggers)
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
        # Sections are drop targets for stock cards; section moves are not implemented.
        self.treeWidget.setDragEnabled(False)
        # self.treeWidget.setDragDropMode()

        #
        # self.savedDropEvent = self.treeWidget.dropEvent
        # self.treeWidget.dropEvent = self.localDropEvent

    def localDropEvent(self, event: QDropEvent):
        """Accept a local drop event for the section view.

        @param event [QDropEvent] event supplied by the caller.
        @return [object, None] Requested section data or completion of the operation.
        """
        logger.debug("Got Drop Event")
        pos = event.pos()
        widget = event.source()
        event.accept()

    def _defineMenu(self):
        """Build section creation, editing and deletion actions.

        @return [object, None] Requested section data or completion of the operation.
        """
        addAct = QAction(QT_TRANSLATE_NOOP("PartsDB", 'Add Section'), self.treeWidget)
        addAct.setStatusTip(QT_TRANSLATE_NOOP("PartsDB", 'Add new type object at the current level.'))
        addAct.triggered.connect(self.add)

        addChildAct = QAction(QT_TRANSLATE_NOOP("PartsDB", 'Add Child Section'), self.treeWidget)
        addChildAct.setStatusTip(QT_TRANSLATE_NOOP("PartsDB", "Add new 'Type' object as child of selected."))
        addChildAct.triggered.connect(self.addChild)

        RenAct = QAction(QT_TRANSLATE_NOOP("PartsDB", 'Edit Section'), self.treeWidget)
        RenAct.setStatusTip(QT_TRANSLATE_NOOP("PartsDB", "Rename selected 'Type' object."))
        RenAct.triggered.connect(self.rename)

        delAct = QAction(QT_TRANSLATE_NOOP("PartsDB", 'Delete Child'), self.treeWidget)
        delAct.setStatusTip(QT_TRANSLATE_NOOP("PartsDB", "Delete selected 'Type' object with all included Parts."))
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
        """Publish the clicked section to the catalog controller.

        @param sel [QModelIndex] sel supplied by the caller.
        @return [object, None] Requested section data or completion of the operation.
        """
        self.lastClickedItem = self.treeModel.itemFromIndex(sel)
        theType: Type = self.lastClickedItem.data(Qt.ItemDataRole.UserRole)
        logger.debug("Clicked: %s", theType.name)
        # self.dispatchEvent(CLICK_EVENT_NAME, theType)
        self.comm.typeSelect.emit(theType, None)

    def onMenuEvent(self, point):
        """Open section actions at the requested view position.

        @param point [QPoint] point supplied by the caller.
        @return [object, None] Requested section data or completion of the operation.
        """
        idx: QModelIndex = self.treeWidget.indexAt(point)
        logger.debug("Got Menu Event for tables cells.  row=%s, column=%s", idx.row(), idx.column())
        coord = self.treeWidget.mapToGlobal(point)
        self.menu.popup(coord)

    def clear(self):
        """Remove current section rows from the tree model.

        @return [object, None] Requested section data or completion of the operation.
        """
        model: QStandardItemModel = self.treeWidget.model()
        if model is not None:
            model.clear()       # works
            model.setRowCount(0)  # works

    def load(self):
        """Reload catalog sections, select the first section and sort the tree.

        @return [object, None] Requested section data or completion of the operation.
        """
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
        """Expand ancestors and the requested section in the navigation tree.

        @param item [QStandardItem] item supplied by the caller.
        @return [object, None] Requested section data or completion of the operation.
        """
        prnt:QStandardItem = item.parent()
        if prnt is not None and prnt != self.rootNode:
            self._expandInDeep(prnt)
        index = self.treeWidget.model().indexFromItem(item)
        self.treeWidget.setExpanded(index, True)

    def getSelectedIndex(self):
        # return self.treeWidget.selectionModel().selectedIndexes()
        # self.treeWidget.getSelectedIndex()[0] if len(self.typesTree.getSelectedIndex()) > 0 else None
        """Return the selected section index or None for an empty selection.

        @return [object, None] Requested section data or completion of the operation.
        """
        return self.treeWidget.selectionModel().selectedIndexes()[0] \
            if len(self.treeWidget.selectionModel().selectedIndexes()) > 0 else None

    def _loadNodes_(self, node: QStandardItem, types_list: Types):
        """Recursively populate captions, subtitles and live section roles.

        @param node [QStandardItem] node supplied by the caller.
        @param types_list [Types] types_list supplied by the caller.
        @return [object, None] Requested section data or completion of the operation.
        """
        for theType in types_list:
            childNode = QStandardItem(theType.name)
            childNode.setData(theType, Qt.ItemDataRole.UserRole)
            childNode.setData(ElDBDataParts.basicTypeName(self.dbFactory, theType), SUBTITLE_ROLE)

            # Check for children.
            if theType.isChildren():
                self._loadNodes_(childNode, theType.getChildren())
            node.appendRow(childNode)

    def add(self):
        """Add a sibling section, inheriting its parent's basic type; takes no parameters."""
        selected = self.getSelectedIndex()
        parent = selected.parent() if selected is not None else QModelIndex()
        parent_type = parent.data(Qt.ItemDataRole.UserRole)
        result = self.sectionInput(parent_type=parent_type)
        if result:
            self._add(result[0], parent, result[1])

    def sectionInput(self, section=None, parent_type=None):
        """Collect a name and reference. @param section, parent_type [Type, None] editing/default context."""
        context = section or parent_type
        dialog = ElTreeEditDlg(self.treeWidget, ElDBDataParts.basicTypes(self.dbFactory),
                               section.name if section else '', context.basic_type_id if context else 1)
        if dialog.exec() == ElTreeEditDlg.DialogCode.Accepted:
            return dialog.nameEdit.text().strip(), dialog.typeCombo.currentData()
        return None

    def _add(self, name, parentIndex: QModelIndex = None, basic_type_id=None):
        """Persist a sibling section and reload the tree.

        @param name [str] name supplied by the caller.
        @param parentIndex [QModelIndex, None] parentIndex supplied by the caller.
        @param basic_type_id [int, None] basic_type_id supplied by the caller.
        @return [object, None] Requested section data or completion of the operation.
        """
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
        return self._addChild(name, parentIndex, basic_type_id)

    def addChild(self):
        """Add beneath the selected section; takes no parameters."""
        index = self.getSelectedIndex()
        if index is None:
            return
        result = self.sectionInput(parent_type=index.data(Qt.ItemDataRole.UserRole))
        if result:
            self._addChild(result[0], index, result[1])

    def _addChild(self, name, parentIndex: QModelIndex, basic_type_id=None):
        """Persist and display a child section beneath the requested parent.

        @param name [str] name supplied by the caller.
        @param parentIndex [QModelIndex, None] parentIndex supplied by the caller.
        @param basic_type_id [int, None] basic_type_id supplied by the caller.
        @return [object, None] Requested section data or completion of the operation.
        """
        if name == "":
            raise ValueError("Type name cannot be empty.")
        parentType: Type = parentIndex.data(Qt.ItemDataRole.UserRole)
        parentItem: QStandardItem = self.treeModel.itemFromIndex(parentIndex)
        if parentItem is None:
            parentItem = self.rootNode

        newType = self.dbFactory.appendType(name, parentType, basic_type_id)
        childItem = QStandardItem(newType.name)
        childItem.setData(newType, Qt.ItemDataRole.UserRole)
        childItem.setData(ElDBDataParts.basicTypeName(self.dbFactory, newType), SUBTITLE_ROLE)
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
        """Edit selected section name and basic type; takes no parameters."""
        index = self.getSelectedIndex()
        if index is None:
            return
        section = index.data(Qt.ItemDataRole.UserRole)
        result = self.sectionInput(section=section)
        if result:
            ElDBDataParts.setBasicType(section, result[1])
            item = self.treeModel.itemFromIndex(index)
            item.setData(ElDBDataParts.basicTypeName(self.dbFactory, section), SUBTITLE_ROLE)
            self._rename(result[0])
            self.comm.typeSelect.emit(section, None)

    def _rename(self, value):
        """Persist the selected section name and refresh its caption.

        @param value [str] value supplied by the caller.
        @return [object, None] Requested section data or completion of the operation.
        """
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
        """Confirm and remove the selected section.

        @return [object, None] Requested section data or completion of the operation.
        """
        logger.debug("Delete menu clicked.")
        index: QModelIndex = self.treeWidget.selectedIndexes()[0]
        theType: Type = index.data(Qt.ItemDataRole.UserRole)
        if theType is None:
            logger.warning("Empty object in type %s", index.data(Qt.ItemDataRole.DisplayRole))
            return
        button = QMessageBox.question(self.treeWidget,translate("PartsDB", 'Delete type'),
                                   translate("PartsDB", 'Are you sure you want to delete section "{}"?').format(theType.name))
        if button == QMessageBox.StandardButton.Yes:
            self._delete(index)

        # dlg.setWindowTitle("Delete type")
        # dlg.setText("Are you shure want to delete Type {} ?".format(theType.name))
        # dlg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        # dlg.setIcon(QMessageBox.Icon.Question)
        # button = dlg.exec()

    def _delete(self, index):
        """Remove the section from the schema and tree model.

        @param index [QModelIndex] index supplied by the caller.
        @return [object, None] Requested section data or completion of the operation.
        """
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
        """Request a section name with an optional prompt.

        @param prompt [str] prompt supplied by the caller.
        @return [object, None] Requested section data or completion of the operation.
        """
        if prompt == "":
            prompt = translate("PartsDB", "Enter section name:")
        value, ok = QInputDialog.getText(self.treeWidget, translate("PartsDB", 'Enter Name'), prompt)
        if ok and value:
            return value
        else:
            return ""

    def getItemByID(self, theId):
        """Find the tree item corresponding to a catalog section identity.

        @param theId [int] theId supplied by the caller.
        @return [object, None] Requested section data or completion of the operation.
        """
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
        """Search the section subtree recursively for an internal identity.

        @param theId [int] theId supplied by the caller.
        @param item [QStandardItem] item supplied by the caller.
        @return [object, None] Requested section data or completion of the operation.
        """
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
