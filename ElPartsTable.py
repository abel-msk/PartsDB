import logging
import sys
import time

from PyQt6 import QtCore, QtWidgets
from PyQt6.QtCore import Qt, QModelIndex, pyqtSignal, QSize, QTimer, QVariant, QObject, QMimeData
from PyQt6.QtGui import QStandardItemModel, QStandardItem, QColor, QAction, QFont, QMouseEvent, QDrag, QDragEnterEvent
from PyQt6.QtWidgets import QTreeWidget, QTreeView, QHeaderView, QMenu, QInputDialog, QAbstractItemView, QMessageBox, \
    QListWidget

import ElDBScheme
import ElLogger
from ElDBScheme import DBFactory, Type, Types, Parts, Part, Document
from ElHdrEditDialog import HeaderEditDialog
from ElIconListWidget import IconsListWidget

# logger = logging.getLogger(__name__)
# logger.setLevel(level=logging.DEBUG)
# handler = logging.StreamHandler(stream=sys.stderr)
# handler.setFormatter(logging.Formatter(fmt='%(asctime)s [%(levelname)s] %(module)s/%(funcName)s: %(message)s'))
# logger.addHandler(handler)

logger = ElLogger.setLogger(__name__)

DB_COLUMNS = list(ElDBScheme.ELEMENT_FIELDS.keys())
PARTS_COLUMN_COUNT = len(DB_COLUMNS) - 2
timestamp = {}

CLICK_EVENT_NAME = "on_click"
MODEL_TYPECHILD = 1
MODEL_SEARCHLIST = 2


class Communicate(QObject):
    documentSelect = pyqtSignal(ElDBScheme.Document)
    partSelect = pyqtSignal(Part)
    partsTypeRequest = pyqtSignal(Part)
    error = pyqtSignal(str)
    hdrEditRequest = pyqtSignal()


def ErrorDialog(parent, message):
    button = QMessageBox.critical(
        parent,
        "Error!",
        message,
        buttons=QMessageBox.StandardButton.Ok,
        defaultButton=QMessageBox.StandardButton.Ok)


class SearchTableModel(QtCore.QAbstractTableModel):

    def __init__(self, factory: DBFactory, parts: Parts):
        super(SearchTableModel, self).__init__()
        self.factory: DBFactory = factory
        self.parts: Parts = parts
        self.theType = None
        self.headers = None

    def flags(self, index):
        column = index.column()
        fieldName = ElDBScheme.ELEMENT_FLD_NAMES[column + 2]
        return super().flags(index)
        # if index.column() == 0:
        #     return super().flags(index) | Qt.ItemFlag.ItemIsEditable
        # elif ElDBScheme.ELEMENT_FIELDS[fieldName] == "BOOLEAN":
        #     return super().flags(index) | Qt.ItemFlag.ItemIsUserCheckable
        # else:
        #     return super().flags(index) | Qt.ItemFlag.ItemIsEditable | Qt.ItemFlag.ItemIsEnabled

    def rowCount(self, index: QModelIndex = ...):
        return len(self.parts)

    def columnCount(self, index: QModelIndex = ...) -> int:
        return PARTS_COLUMN_COUNT

    def data(self, index: QModelIndex, role=None):
        row = index.row()
        column = index.column()
        # thePart: Part = self.parts[row - 1]
        thePart: Part = self.parts[row]
        # hdr = self.headers[ElDBScheme.ELEMENT_FLD_NAMES[column + 2]]
        columnName = DB_COLUMNS[column + 2]
        if (role == Qt.ItemDataRole.DisplayRole) or (role == Qt.ItemDataRole.EditRole):  # Display Cell Context
            fieldData = thePart[columnName]
            if ElDBScheme.ELEMENT_FIELDS[columnName].strip() != "BOOLEAN":
                return fieldData
        elif role == Qt.ItemDataRole.UserRole:
            return thePart

    def sort(self, column: int, order: Qt.SortOrder = ...):
        columnName = DB_COLUMNS[column + 2]
        logger.debug("Sorting by field %s", columnName)

        def sort_func(Item):
            retval = Item[columnName]
            if ElDBScheme.ELEMENT_FIELDS[columnName].strip() == "TEXT":
                return "" if retval is None else str(retval)
            elif ElDBScheme.ELEMENT_FIELDS[columnName].strip() == "INTEGER":
                return 0 if retval is None or retval == '' else int(retval)
            elif ElDBScheme.ELEMENT_FIELDS[columnName].strip() == "REAL":
                return 0.0 if retval is None or retval == '' else float(str(retval).strip().replace(",", "."))
            return retval

        if order == Qt.SortOrder.AscendingOrder:
            self.parts.partsAr.sort(reverse=True, key=sort_func)
        else:
            self.parts.partsAr.sort(reverse=False, key=sort_func)

        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("Sorting result: %s", " | ".join(map(lambda p: str(p[columnName]), self.parts.partsAr)))

        self.layoutChanged.emit()

    def headerData(self, section, orientation, role=None):
        if role == Qt.ItemDataRole.DisplayRole:
            if orientation == Qt.Orientation.Horizontal:
                column = section + 2
                result = list(ElDBScheme.ELEMENT_FIELDS.keys())[column]
                return result

        elif role == Qt.ItemDataRole.FontRole:
            font = QFont()
            font.setBold(True)
            font.setPixelSize(12)
            return QVariant(font)

        elif role == Qt.ItemDataRole.SizeHintRole:
            if orientation == Qt.Orientation.Horizontal:
                # logger.debug("data: Got resize event. Section {}".format(section))
                return QSize(100, 30)


class PartsTableModel(QtCore.QAbstractTableModel):
    data_changed = pyqtSignal(QModelIndex, Part, name='dataChanged')

    def __init__(self, factory: DBFactory, theType: Type):
        super(PartsTableModel, self).__init__()
        self.factory: DBFactory = factory
        self.theType: Type = theType
        self.parts: Parts = factory.loadPartsByType(self.theType)
        self.headers: ElDBScheme.Headers = self.theType.getHeaders()
        self.needReload = False

    def data(self, index: QModelIndex, role=None):
        if self.needReload:
            self.headers: ElDBScheme.Headers = self.theType.refreshHeaders()
            self.needReload = False
        row = index.row()
        column = index.column()
        # thePart: Part = self.parts[row - 1]
        thePart: Part = self.parts[row]
        hdr = self.headers[ElDBScheme.ELEMENT_FLD_NAMES[column + 2]]
        columnName = DB_COLUMNS[column + 2]
        if (role == Qt.ItemDataRole.DisplayRole) or (role == Qt.ItemDataRole.EditRole):  # Display Cell Context
            fieldData = thePart[columnName]
            if ElDBScheme.ELEMENT_FIELDS[columnName].strip() != "BOOLEAN":
                return fieldData

        elif role == Qt.ItemDataRole.TextAlignmentRole:

            if ElDBScheme.ELEMENT_FIELDS[columnName].strip() == "BOOLEAN":
                return Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
            elif hdr["align"] == ElDBScheme.F_ALIGN_CENTER:
                return Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
            elif hdr["align"] == ElDBScheme.F_ALIGN_LEFT:
                return Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            elif hdr["align"] == ElDBScheme.F_ALIGN_RIGHT:
                return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter

        elif role == Qt.ItemDataRole.UserRole:
            return thePart

        elif role == Qt.ItemDataRole.CheckStateRole:
            if ElDBScheme.ELEMENT_FIELDS[columnName].strip() == "BOOLEAN":
                return Qt.CheckState.Checked if thePart[columnName] else Qt.CheckState.Unchecked

        elif role == Qt.ItemDataRole.BackgroundRole:
            if thePart["present"] is not None and not thePart["present"]:
                color = QColor(245, 239, 255, 127)
                return color

    def flags(self, index):
        column = index.column()
        fieldName = ElDBScheme.ELEMENT_FLD_NAMES[column + 2]

        if index.column() == 0:
            return super().flags(index) | Qt.ItemFlag.ItemIsEditable
        elif ElDBScheme.ELEMENT_FIELDS[fieldName] == "BOOLEAN":
            return super().flags(index) | Qt.ItemFlag.ItemIsUserCheckable
        else:
            return super().flags(index) | Qt.ItemFlag.ItemIsEditable | Qt.ItemFlag.ItemIsEnabled

    def rowCount(self, index: QModelIndex = ...):
        return len(self.parts)

    def columnCount(self, index: QModelIndex = ...) -> int:
        return PARTS_COLUMN_COUNT

    # def updateHeaders(self):
    #     self.headers: ElDBScheme.Headers = self.theType.getHeaders()

    def headerData(self, section, orientation, role=None):
        if self.needReload:
            self.headers: ElDBScheme.Headers = self.theType.refreshHeaders()
            self.needReload = False

        if role == Qt.ItemDataRole.DisplayRole:
            if orientation == Qt.Orientation.Horizontal:
                column = section + 2
                fldName = list(ElDBScheme.ELEMENT_FIELDS.keys())[column]
                result = self.headers[fldName].display
                # logger.debug("Header %s, value %s",fldName, result)
                # result = self.headers[fldName].display
                return result

        elif role == Qt.ItemDataRole.FontRole:
            font = QFont()
            font.setBold(True)
            font.setPixelSize(12)
            return QVariant(font)

        elif role == Qt.ItemDataRole.SizeHintRole:
            if orientation == Qt.Orientation.Horizontal:
                # logger.debug("data: Got resize event. Section {}".format(section))
                return QSize(100, 30)

    # https://doc.qt.io/qt-6/qabstractitemmodel.html#dataChanged
    def setData(self, index, value, role=None):
        if not index.isValid():
            return False
        row = index.row()
        column = index.column()
        # thePart: Part = self.parts[row - 1]
        thePart: Part = self.parts[row]
        columnName = DB_COLUMNS[column + 2]

        if role == Qt.ItemDataRole.EditRole:
            logger.debug("Call edit. row=%s column=%s, value=%s", index.row(), index.column(), value)
            # column = index.column()
            try:
                if ElDBScheme.ELEMENT_FIELDS[columnName].strip() == "INTEGER":
                    thePart[columnName] = int(value) if value != "" else 0
                elif ElDBScheme.ELEMENT_FIELDS[columnName].strip() == "REAL":
                    transTbl = str.maketrans("," , ".")
                    thePart[columnName] = float(str(value).translate(transTbl)) if value != "" else 0.0
                else:
                    thePart[columnName] = value
                thePart.save()
            except ValueError as e:
                # logger.error(e)
                logging.exception("ValueError")
                ErrorDialog(None, "Incorrect value type for column {}".format(columnName))
            return True

        elif role == Qt.ItemDataRole.CheckStateRole and ElDBScheme.ELEMENT_FIELDS[columnName].strip() == "BOOLEAN":
            logger.debug("Check State %s, value %s", role, value)
            if thePart[columnName]:
                thePart[columnName] = False
            else:
                thePart[columnName] = True
            # self.dataChanged.emit(index, index)
            thePart.save()
            return True

        return super().setData(index, value, role)

    def removeRow(self, row: int, parent: QModelIndex = ...) -> bool:
        # index = self.selectionModel().currentIndex()
        # super(PartsTableModel, self).selectionModel().currentIndex()
        # thePart: Part = index.sibling(row, 1).data(Qt.ItemDataRole.UserRole)

        self.beginRemoveRows(QModelIndex(), row, row)
        thePart: Part = self.parts.partsAr.pop(row)
        try:
            logger.debug("Remove part=%s(%s), row=%s", thePart["part_num"], thePart.id, row)
            self.factory.deletePart(thePart)
        except BaseException as e:
            logger.error(e)
            self.parts.partsAr.append(thePart)
            ErrorDialog(self, "DB error when removing part {}".format(thePart["part_num"]))
            return False
        self.endRemoveRows()
        return True

    def appendRow(self, thePart: Part):
        newRow = len(self.parts.partsAr) + 1
        self.beginInsertRows(QModelIndex(), newRow, newRow)
        self.parts.partsAr.append(thePart)
        self.endInsertRows()
        return True

    def setHeaderData(self, section, orientation, value, role=None):
        if role == Qt.ItemDataRole.DisplayRole:
            if orientation == Qt.Orientation.Horizontal:
                logger.debug("Call Header edit. Section=%s, value=%s", section, value)
                # column = index.column()
                # thePart: Part = self.parts[index.row() - 1]
                # thePart.setFiledData(DB_COLUMNS[column+2], value)
                self.headerDataChanged.emit(orientation, section, section)
                return True
        return False

    def sort(self, column: int, order: Qt.SortOrder = ...):
        # self.beginResetModel()
        columnName = DB_COLUMNS[column + 2]
        logger.debug("Sorting by field %s", columnName)

        def sort_func(Item):
            retval = Item[columnName]
            if ElDBScheme.ELEMENT_FIELDS[columnName].strip() == "TEXT":
                return "" if retval is None else str(retval)
            elif ElDBScheme.ELEMENT_FIELDS[columnName].strip() == "INTEGER":
                return 0 if retval is None or retval == '' else int(retval)
            elif ElDBScheme.ELEMENT_FIELDS[columnName].strip() == "REAL":
                return 0.0 if retval is None or retval == '' else float(str(retval).strip().replace(",", "."))
            return retval

        if order == Qt.SortOrder.AscendingOrder:
            self.parts.partsAr.sort(reverse=True, key=sort_func)
        else:
            self.parts.partsAr.sort(reverse=False, key=sort_func)

        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("Sorting result: %s", " | ".join(map(lambda p: str(p[columnName]), self.parts.partsAr)))

        # self.endResetModel()
        self.layoutChanged.emit()


class TableView(QtCore.QObject):
    # comm = Communicate()

    def __init__(self, factory: DBFactory, tableView: QtWidgets.QTableView, docList: QListWidget):
        super(TableView, self).__init__()
        self.searchMode = False
        self.saveResize = False
        self.comm = Communicate()
        # self._events = {}
        self.docListWidget = docList
        self.tableView: QtWidgets.QTableView = tableView
        self.factory: DBFactory = factory
        self.theType: Type = None
        self.headers: ElDBScheme.Headers = None
        self.hdrNamesList = []
        self.timestamp = {}
        self.tableView.verticalHeader().setVisible(False)
        self.tableView.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tableView.customContextMenuRequested.connect(self.tableMenuEvent)
        self.tableView.setSortingEnabled(True)
        self.tableView.horizontalHeader().setSortIndicatorShown(True)

        self.tableView.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)

        self.tableModel: PartsTableModel = None
        self.header: QHeaderView = self.tableView.horizontalHeader()
        # self.header.contextMenuEvent = self.headerMenuEvent
        self.header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.header.customContextMenuRequested.connect(self.headerMenuEvent)
        self.header.ResizeMode(QtWidgets.QHeaderView.ResizeMode.Interactive)  # ResizeToContents
        # self.header.ResizeMode(QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.header.setContentsMargins(15, 5, 15, 5)
        self.header.stretchLastSection()
        # self.header.sectionResized.connect(self.onColumnResize)
        self.tableView.setHorizontalHeader(self.header)
        self.headerMenu = None
        self.bodyMenu = None
        self.bodySearchMenu = None
        self.menuColumnSelected = None
        self.menuRowSelected = None

        self.tableView.setSortingEnabled(True)
        self.tableView.horizontalHeader().setSortIndicatorShown(True)
        # self.tableView.sortByColumn(col, Qt.DescendingOrder)
        # self.tableView.clicked.connect(self.onClick)

        self.iconsListWidget: IconsListWidget = IconsListWidget(self.factory, self.docListWidget)
        self.iconsListWidget.comm.itemSelect.connect(self.onDocumentSelect)

        # self.tableView.setDragEnabled(True)
        # self.tableView.setDropIndicatorShown(True)
        # self.tableView.viewport().setAcceptDrops(True)

        self.savedMouseMoveEvent = self.tableView.mouseMoveEvent
        self.tableView.mouseMoveEvent = self.localMouseMoveEvent

        # self.savedDragEnterEvent = self.tableView.dragEnterEvent
        # self.tableView.dragEnterEvent = self.localDragEnterEvent

        # https://stackoverflow.com/questions/63899567/dragmoveevent-doesnt-work-properly-when-overriding-mousemoveevent-qt-drag
        # https://www.pythonguis.com/faq/pyqt-drag-drop-widgets/#drag-drop-widgets
        # mouseMoveEvent
        # dragEnterEvent
        # dragMoveEvent

    def setFocus(self):
        self.tableView.setFocus()

    def getCurrentType(self):
        return self.theType

    def localMouseMoveEvent(self, event: QMouseEvent):
        if event.buttons() == Qt.MouseButton.LeftButton:
            drag = QDrag(self.tableView)
            # drag.setDragCursor(QPixmap, DropAction)
            #   QtGui.QPixmap(":/type/icons/kikad_file.png")
            mime = QMimeData()
            drag.setMimeData(mime)
            self.tableView.selectionModel().currentIndex()
            # pixmap = QPixmap(self.size())
            # self.render(pixmap)
            # drag.setPixmap(pixmap)
            dropAction = drag.exec(Qt.DropAction.MoveAction)

    def _defineHeaderMenu(self):
        hideAct = QAction("Hide Column", self.tableView)
        hideAct.setStatusTip("Hide selected Column")
        hideAct.triggered.connect(self.hideColumn)

        showAct = QAction("Show Column on right if any", self.tableView)
        showAct.setStatusTip("Hide selected Column")
        showAct.triggered.connect(self.showColumn)

        renameAct = QAction("Rename selected Header", self.tableView)
        renameAct.setStatusTip("Add new 'Type' object as child of selected.")
        renameAct.triggered.connect(self.renameHeader)

        alRightAct = QAction("Align Right", self.tableView)
        alRightAct.setStatusTip("Align to the right selected column contents")
        alRightAct.triggered.connect(self.alignRight)

        alLeftAct = QAction("Align Left", self.tableView)
        alLeftAct.setStatusTip("Align to the left selected column contents")
        alLeftAct.triggered.connect(self.alignLeft)

        editHdr = QAction("Edit Headers", self.tableView)
        editHdr.setStatusTip("Open headers edit dialog")
        editHdr.triggered.connect(self.editHeader)

        # # show menu about the column
        menu = QMenu(self.tableView)
        menu.addAction(hideAct)
        menu.addAction(showAct)
        menu.addAction(renameAct)
        menu.addAction(alRightAct)
        menu.addAction(alLeftAct)
        menu.addSeparator()
        menu.addAction(editHdr)
        return menu

    def _defineBodySearchMenu(self):
        """
        Define popup menu for Parts Table body
        :return:
        """
        ldOrig = QAction("Load Original", self.tableView)
        ldOrig.setStatusTip("Load corresponding parts type.")
        ldOrig.triggered.connect(self.loadPartsType)

        menu = QMenu(self.tableView)
        menu.addAction(ldOrig)
        return menu

    def _defineBodyMenu(self):
        """
        Define popup menu for Parts Table body
        :return:
        """
        tglAct = QAction("Switch Selection", self.tableView)
        tglAct.setStatusTip("Toggle multiline / singleline selection.")
        tglAct.triggered.connect(self.toggleSelection)

        addAct = QAction("Add Part", self.tableView)
        addAct.setStatusTip("Add new part.")
        addAct.triggered.connect(self.addRow)

        delAct = QAction("Delete Part", self.tableView)
        delAct.setStatusTip("Delete selected part.")
        delAct.triggered.connect(self.deleteRow)

        menu = QMenu(self.tableView)
        menu.addAction(tglAct)
        menu.addAction(addAct)
        menu.addSeparator()
        menu.addAction(delAct)
        return menu

    def loadSearchData(self, parts: Parts):
        self.theType = None
        self.headers = None
        self.searchMode = True
        self.tableModel = SearchTableModel(self.factory, parts)
        self.tableView.setModel(self.tableModel)
        self.tableView.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        selection_model = self.tableView.selectionModel()
        selection_model.selectionChanged.connect(self.onSelectionChanged)
        self.iconsListWidget.clear()

    def loadData(self, theType: Type):
        # try: self.header.sectionResized.disconnect()
        # except TypeError: pass
        self.searchMode = False
        self.timestamp = {}
        self.saveResize = False
        self.theType = theType
        # self.header.sectionResized.disconnect()
        self.tableModel = PartsTableModel(self.factory, self.theType)
        self.tableView.setModel(self.tableModel)  # parts_tbl_view
        self.headers: ElDBScheme.Headers = self.theType.getHeaders()
        self.tableView.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        # headerWidget = self.tableView.horizontalHeader()

        ###   Set initial columns and headers decoration

        for column in range(0, PARTS_COLUMN_COUNT):
            fieldName = ElDBScheme.ELEMENT_FLD_NAMES[column + 2]
            isHidden = self.headers[fieldName]["hidden"]
            self.tableView.setColumnHidden(column, isHidden)
            if not isHidden:
                width = self.headers[fieldName]["width"]
                # logger.debug("Set column %s(%s) width %s", fieldName, column, width)
                if width is not None and width != "" and width != 0:
                    self.tableView.setColumnWidth(column, int(width))
                    # logger.debug("Set column %s(%s) width %s", fieldName,column, width)

            # self.tableView.horizontalHeader().setSortIndicatorShown(True)

        #### Loop throw header section for set size
        # header.resizeSection(col, hdr_width)
        # self.header.sectionResized.connect(self.onColumnResize)

        self.header.sectionResized.connect(self.onColumnResize)  # !!! Do not activate event before initial resize
        selection_model = self.tableView.selectionModel()
        selection_model.selectionChanged.connect(self.onSelectionChanged)
        self.iconsListWidget.clear()
        self.tableView.selectRow(0)
        self.saveResize = True


    # def dataChanged(self, index1, index2):
    #     logger.debug("DataChanged event occurred.")

    def onColumnResize(self, column: int, oldWidth: int, newWidth: int):
        if self.saveResize:
            self.timestamp[column] = [newWidth, time.time()]
            QTimer.singleShot(1550, lambda: self.saveHeaderWidth(column))  # Delay execution by 2 sec

    def saveHeaderWidth(self, column):
        curTime = time.time()
        try:
            width, eventTime = self.timestamp[column]
            if (curTime - eventTime >= 1.5) and width > 0:
                hdr = self.headers[ElDBScheme.ELEMENT_FLD_NAMES[column + 2]]
                # hdr: ElDBScheme.Header = self.theType.getHeaders()[fld]
                if hdr["width"] != width:
                    hdr["width"] = width
                    logger.debug("Save header %s(col=%s) column width %s", hdr["display"], column + 2, width)
                    hdr.save()
        except KeyError:
            logger.warning("Incorrect column %s", column)
            pass

    def onSelectionChanged(self, selected, deselected):
        """
        Receive event when select row in the part table
        :param selected:
        :param deselected:
        :return:
        """
        if len(self.tableView.selectedIndexes()) > 0:
            index: QModelIndex = self.tableView.selectedIndexes()[0]
            thePart: Part = index.data(Qt.ItemDataRole.UserRole)
            logger.debug("Selected row = %s", thePart["part_num"])
            self.iconsListWidget.clear()
            self.iconsListWidget.load(thePart)
            self.comm.partSelect.emit(thePart)

    def onDocumentSelect(self, theDoc: Document):
        """
        Repost Event wyen user select document in this part documentsList
        :param doc:
        :return:
        """
        self.comm.documentSelect.emit(theDoc)

    def headerMenuEvent(self, point):
        column = self.header.logicalIndexAt(point.x())
        hdr = self.headers[ElDBScheme.ELEMENT_FLD_NAMES[column + 2]]
        self.menuColumnSelected = column
        logger.debug("Menu event for Header column %s(col=%s)", hdr["display"], column)
        if self.headerMenu is None:
            self.headerMenu = self._defineHeaderMenu()
        self.headerMenu.popup(self.header.mapToGlobal(point))

    def tableMenuEvent(self, point):
        idx: QModelIndex = self.tableView.indexAt(point)
        logger.debug("Menu event for tables cells row=%s, column=%s", idx.row(), idx.column())
        self.menuColumnSelected = idx.column()
        self.menuRowSelected = idx.row()
        menu =None

        if self.searchMode:
            if self.bodySearchMenu is None:
                self.bodySearchMenu = self._defineBodySearchMenu()
            menu = self.bodySearchMenu
        else:
            if self.bodyMenu is None:
                self.bodyMenu = self._defineBodyMenu()
            menu = self.bodyMenu

        coord = self.tableView.mapToGlobal(point)
        coord.setY(coord.y() + self.tableView.horizontalHeader().height())
        menu.popup(coord)

    def getHeaderByColumn(self, column) -> ElDBScheme.Header:
        hdr = self.headers[ElDBScheme.ELEMENT_FLD_NAMES[column + 2]]
        return hdr

    def hideColumn(self):
        self.tableView.hideColumn(self.menuColumnSelected)
        hdr: ElDBScheme.Header = self.getHeaderByColumn(self.menuColumnSelected)
        hdr["hidden"] = True
        hdr.save()
        self.tableView.update()

    def showColumn(self):
        self.tableView.hideColumn(self.menuColumnSelected + 1)
        hdr: ElDBScheme.Header = self.getHeaderByColumn(self.menuColumnSelected + 1)
        hdr["hidden"] = False
        hdr.save()
        self.tableView.update()

    def renameHeader(self):
        hdr: ElDBScheme.Header = self.getHeaderByColumn(self.menuColumnSelected)
        newName = self._getInput(hdr["display"])
        if newName.strip():
            hdr["display"] = newName
            hdr.save()
            self.tableModel.setHeaderData(self.menuColumnSelected,
                                          Qt.Orientation.Horizontal,
                                          newName,
                                          Qt.ItemDataRole.DisplayRole)
            # self.tableView.horizontalHeader().update()

    def alignRight(self):
        hdr: ElDBScheme.Header = self.getHeaderByColumn(self.menuColumnSelected)
        hdr["align"] = ElDBScheme.F_ALIGN_RIGHT
        hdr.save()
        # self.tableView.changeEvent()
        # index = QModelIndex()
        # idx = self.tableModel.index(self.menuColumnSelected)
        # self.tableModel.dataChanged.emit(idx)
        self.tableView.update()

    def alignLeft(self):
        hdr: ElDBScheme.Header = self.getHeaderByColumn(self.menuColumnSelected)
        hdr["align"] = ElDBScheme.F_ALIGN_LEFT
        hdr.save()
        self.tableView.update()

    def alignCenter(self):
        hdr: ElDBScheme.Header = self.getHeaderByColumn(self.menuColumnSelected)
        hdr["align"] = ElDBScheme.F_ALIGN_CENTER
        hdr.save()

    def editHeader(self):
        self.comm.hdrEditRequest.emit()

    def loadPartsType(self):

        index = (self.tableView.selectionModel().currentIndex())
        thePart: Part = index.sibling(self.menuRowSelected, 1).data(Qt.ItemDataRole.UserRole)
        logger.debug("Got event. Load parts %s type = %s", thePart["part_num"], thePart["type_id"])
        self.comm.partsTypeRequest.emit(thePart)

    def toggleSelection(self):
        if self.tableView.selectionMode() == QAbstractItemView.SelectionMode.MultiSelection:
            logger.debug("Set selection mode SingleSelection")
            index = self.tableView.selectionModel().currentIndex()
            self.tableView.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
            self.tableView.selectRow(index.row())

        else:
            self.tableView.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
            logger.debug("Set selection mode MultiSelection")

    def addRow(self):
        theType = self.tableModel.theType
        logger.debug("Add new part for Type=%s(%s)", theType.name, theType.recId)
        value, ok = QInputDialog.getText(self.tableView, 'Add part', "Enter Part number")
        if ok and value:
            el = {}
            el["part_num"] = value
            thePart = self.factory.createPart(theType, el)
            self.tableModel.appendRow(thePart)

    def deleteRow(self):
        index = (self.tableView.selectionModel().currentIndex())
        thePart: Part = index.sibling(self.menuRowSelected, 1).data(Qt.ItemDataRole.UserRole)

        theType = self.factory.getTypeByID(thePart["type_id"])
        button = QMessageBox.question(self.tableView, "Deleting part",
                                      "Are you sure want to delete the part: {} {} ?".format(theType.path,
                                                                                             thePart["part_num"]))
        if button == QMessageBox.StandardButton.Yes:
            # self._delete(index)
            self.tableModel.removeRow(self.menuRowSelected)
            logger.debug("Menu Clicked on row %s", thePart["part_num"])

    def addDocument(self, file, type: int = ElDBScheme.DOC_TYPE_DEFAULT):
        index = (self.tableView.selectionModel().currentIndex())
        thePart: Part = index.data(Qt.ItemDataRole.UserRole)
        # thePart = sel.data(Qt.ItemDataRole.UserRole)
        logger.debug("Add Document for part %s", thePart["part_num"])
        theDoc = thePart.addDocument(file, type)
        try:
            self.iconsListWidget.appendDocument(theDoc)
        except KeyError as e:
            thePart.removeDocument(theDoc)
            raise e

    def deleteSelectedDocument(self):
        index = (self.tableView.selectionModel().currentIndex())
        thePart: Part = index.data(Qt.ItemDataRole.UserRole)
        theDoc = self.iconsListWidget.getSelectedItem()
        self.iconsListWidget.deleteDocument(theDoc)
        thePart.documents.delete(theDoc)

    def getSelected(self):
        index = (self.tableView.selectionModel().currentIndex())
        return index.data(Qt.ItemDataRole.UserRole)

    def _getInput(self, oldValue) -> str:
        value, ok = QInputDialog.getText(self.tableView, 'Enter name', "Enter new name column")
        if ok and value:
            return value
        else:
            return ""

    def updateHeader(self, hdrObj: ElDBScheme.Header = None):

        #  Get header column count
        fieldList = list(ElDBScheme.ELEMENT_FIELDS.keys())
        idx = fieldList.index(hdrObj["field_name"]) - 2
        logger.debug("Update Header %s, index=%s", hdrObj["display"], idx)

        self.tableView.setColumnHidden(idx, hdrObj["hidden"])
        self.tableModel.needReload = True
        self.tableView.update()

    def selectByID(self, theId):
        parts:Parts = self.tableModel.parts
        if not self.searchMode:
            for row in range(0, len(parts)):
                thePart: Part = parts[row]
                if thePart.id == theId:
                    self.tableView.selectRow(row)
