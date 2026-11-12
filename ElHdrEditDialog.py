# from PyQt6 import QtCore
from PyQt6.QtCore import Qt, QModelIndex, QVariant, QObject, QSize, pyqtSignal
from PyQt6.QtGui import QFont, QIcon
from PyQt6.QtWidgets import QDialog, QHeaderView, QMessageBox
from PyQt6 import QtCore, QtWidgets
import logging
import sys
import ElDBScheme
import ElDefaultIcons
import ElLogger
from ElHdrEditWnd import Ui_HdrEditDialog

logger = ElLogger.setLogger(__name__)
# logger = logging.getLogger(__name__)
# logger.setLevel(level=logging.DEBUG)
# logging.basicConfig(filename='example.log', encoding='utf-8', level=logging.DEBUG)
# logging.basicConfig(filename='example.log',
#                     encoding='utf-8',
#                     level=logging.DEBUG,
#                     format='%(asctime)s [%(levelname)s] %(module)s/%(funcName)s: %(message)s')
#
# handler = logging.StreamHandler(stream=sys.stderr)
# handler.setFormatter(logging.Formatter(fmt='%(asctime)s [%(levelname)s] %(module)s/%(funcName)s: %(message)s'))
# logger.addHandler(handler)

# HEADER_FIELDS = {
#     "id": "INTEGER PRIMARY KEY AUTOINCREMENT",
#     "type_id": "INTEGER NOT NULL",
#     "field_name": "TEXT NOT NULL",   # Название поля в таблице  PARTS
#     "label": "TEXT",
#     "align": "TEXT",
#     "hidden": "BOOLEAN",
#     "sort": "BOOLEAN",
#     "display": "TEXT",
#     "width": "INTEGER"
# }

COLUMNS_DICT = {
    "field_name": "TEXT",
    "display": "TEXT",
    "hidden": "BOOL",
    "sort": "BOOL",
    "align": "TEXT"
}

ICON_SELECTOR_SIZE = 48  # icon size in icon_selector, px

TBL_VAL = "value"
TBL_CHNG = "changed"
TBL_FLD_OBJ = "data"
TBL_FLD_COLNAME = "colname"


class Communicate(QObject):
    tblUpdateRequest = pyqtSignal(ElDBScheme.Header)
    typeIconChanged = pyqtSignal(int)  # type id whose default icon was saved


class HeaderTableModel(QtCore.QAbstractTableModel):
    # data_changed = pyqtSignal(QModelIndex, Part, name='dataChanged')

    def __init__(self, factory: ElDBScheme.DBFactory):
        super(HeaderTableModel, self).__init__()
        self.factory: ElDBScheme.DBFactory = factory
        self.columnsList = list(COLUMNS_DICT.keys())
        self.rowsList = []
        self.dataAr = []
        for filedName in ElDBScheme.ELEMENT_FIELDS.keys():
            if filedName != "id" and filedName != "type_id":
                self.rowsList.append(filedName)
        self.rows = 0

    def _column_type_(self, colIndex):
        return COLUMNS_DICT.get(self.columnsList[colIndex])

    def getCell(self, row, column):
        return self.dataAr[row][column]

    def load(self, typeID):
        """
        Generate table contents for an entered type
        :param typeID:
        :return:
        """
        # dataAr[row][column]
        self.beginResetModel()
        self.rows = 0
        self.dataAr = []
        self.typeID = typeID
        #  Return header object for a selected type
        headers: ElDBScheme.Headers = self.factory.getHeadersByType(typeID)
        for filedName in self.rowsList:
            theHeader: ElDBScheme.Header = headers[filedName]
            dataRow = []
            for colName in self.columnsList:
                dataRow.append({TBL_VAL: headers[filedName][colName],
                                TBL_CHNG: False,
                                TBL_FLD_OBJ: theHeader,
                                TBL_FLD_COLNAME: colName})
            self.dataAr.append(dataRow)
            self.rows += 1
        self.endResetModel()

    def isChanged(self) -> bool:
        return any(cell.get(TBL_CHNG) for row in self.dataAr for cell in row)

    def data(self, index: QModelIndex, role=None):
        row = index.row()
        column = index.column()
        if (role == Qt.ItemDataRole.DisplayRole) or (role == Qt.ItemDataRole.EditRole):  # Display Cell Context
            if self._column_type_(column) != "BOOL":
                return self.dataAr[row][column].get(TBL_VAL)

        elif role == Qt.ItemDataRole.UserRole:
            return self.dataAr[row][column].get(TBL_FLD_OBJ)

        elif role == Qt.ItemDataRole.CheckStateRole:
            if self._column_type_(column) == "BOOL":
                value = self.dataAr[row][column].get(TBL_VAL)
                return Qt.CheckState.Checked if value else Qt.CheckState.Unchecked

    def flags(self, index):
        column = index.column()
        # fieldName = ElDBScheme.ELEMENT_FLD_NAMES[column + 2]
        # if index.column() == 0:
        #     return super().flags(index) | Qt.ItemFlag.ItemIsEditable
        if self._column_type_(column) == "BOOL":
            return super().flags(index) | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled
        else:
            return super().flags(index) | Qt.ItemFlag.ItemIsEditable | Qt.ItemFlag.ItemIsEnabled

    def rowCount(self, index: QModelIndex = ...):
        return self.rows

    def columnCount(self, index: QModelIndex = ...) -> int:
        return len(self.columnsList)

    def headerData(self, section, orientation, role=None):
        if role == Qt.ItemDataRole.DisplayRole:
            if orientation == Qt.Orientation.Horizontal:
                return self.columnsList[section]
        elif role == Qt.ItemDataRole.FontRole:
            font = QFont()
            font.setBold(True)
            font.setPixelSize(12)
            return QVariant(font)
        # elif role == Qt.ItemDataRole.SizeHintRole:
        #     if orientation == Qt.Orientation.Horizontal:
        #         # logger.debug("data: Got resize event. Section {}".format(section))
        #         return QSize(100, 30)

    # https://doc.qt.io/qt-6/qabstractitemmodel.html#dataChanged
    def setData(self, index, value, role=None):
        if not index.isValid():
            return False
        row = index.row()
        column = index.column()

        if role == Qt.ItemDataRole.EditRole:
            self.dataAr[row][column][TBL_VAL] = value
            self.dataAr[row][column][TBL_CHNG] = True
            return True

        elif role == Qt.ItemDataRole.CheckStateRole and self._column_type_(column) == "BOOL":
            self.dataAr[row][column][TBL_VAL] = not self.dataAr[row][column][TBL_VAL]
            self.dataAr[row][column][TBL_CHNG] = True
            return True

        return super().setData(index, value, role)


class HeaderEditDialog(QDialog):
    """Header edit dialog."""
    def __init__(self, parent, factory: ElDBScheme.DBFactory):
        super().__init__(parent)
        self.comm = Communicate()
        self.factory = factory
        self.ui = Ui_HdrEditDialog()
        self.ui.setupUi(self)
        self.tableModel = HeaderTableModel(self.factory)
        self.tableView: QtWidgets.QTableView = self.ui.headersTbl
        self.tableView.setModel(self.tableModel)
        self.tableView.verticalHeader().setVisible(False)
        self.tableView.horizontalHeader().setVisible(True)

        self.header: QHeaderView = self.ui.headersTbl.horizontalHeader()
        self.header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.header.setStretchLastSection(True)
        self.ui.headersTbl.setHorizontalHeader(self.header)

        self.ui.buttonBox.accepted.connect(self.onSave)

        self.currentTypeId = None
        self.pendingIcon = None  # icon chosen for the current type but not saved yet ('' = auto)
        self._fillTypesList()
        self.ui.typesList.currentIndexChanged.connect(self.onTypeSelected)
        self._fillIconSelector()
        self.ui.icon_selector.currentIndexChanged.connect(self.onIconSelected)

    def _fillIconSelector(self):
        """Built-in part icons. The first item is 'auto': the icon comes from the parent section or the built-in rule."""
        combo: QtWidgets.QComboBox = self.ui.icon_selector
        combo.blockSignals(True)
        combo.clear()
        combo.setIconSize(QSize(ICON_SELECTOR_SIZE, ICON_SELECTOR_SIZE))
        # The popup's default (menu-style) delegate draws small icons: use a plain item delegate,
        # which takes the view's icon size
        combo.setItemDelegate(QtWidgets.QStyledItemDelegate(combo))
        combo.view().setIconSize(QSize(ICON_SELECTOR_SIZE, ICON_SELECTOR_SIZE))
        # Tall enough to show the whole icon. On macOS the native combo has a fixed height,
        # so the height is set by a style sheet (it switches the combo to a styled one).
        # A border/background in the sheet makes Qt draw the combo itself instead of the native fixed-height control.
        combo.setStyleSheet(
            "QComboBox#icon_selector {{ min-height: {h}px; padding: 2px 8px;"
            " border: 1px solid palette(mid); border-radius: 6px; background: palette(base); }}"
            .format(h=ICON_SELECTOR_SIZE + 4))
        combo.addItem("Auto (from parent section / built-in rule)", "")
        for path in ElDefaultIcons.availableIcons():
            name = path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
            combo.addItem(QIcon(path), name, path)
        combo.blockSignals(False)

    def _showTypeIcon(self, typeId):
        """Select the type's saved icon in icon_selector."""
        icon = self.factory.scheme.getTypeIcon(typeId)
        combo = self.ui.icon_selector
        index = combo.findData(icon)
        if index < 0:
            # Saved icon is not among the built-in ones: show it as an extra item
            combo.addItem(QIcon(icon), icon, icon)
            index = combo.count() - 1
        combo.blockSignals(True)
        combo.setCurrentIndex(index)
        combo.blockSignals(False)
        self.pendingIcon = None

    def onIconSelected(self, index):
        icon = self.ui.icon_selector.itemData(index)
        if icon is None or self.currentTypeId is None:
            return
        saved = self.factory.scheme.getTypeIcon(self.currentTypeId)
        self.pendingIcon = None if icon == saved else icon
        logger.debug("Icon for type %s selected: '%s'", self.currentTypeId, icon)

    def isChanged(self) -> bool:
        return self.tableModel.isChanged() or self.pendingIcon is not None

    def _fillTypesList(self):
        """Fill the types combo box with every type of the tree, shown as a full path."""
        combo: QtWidgets.QComboBox = self.ui.typesList
        combo.blockSignals(True)
        combo.clear()
        self._addTypes(self.factory.getRootTypes(), [])
        combo.blockSignals(False)

    def _addTypes(self, types: ElDBScheme.Types, path: list):
        for theType in types:
            typePath = path + [theType.name]
            self.ui.typesList.addItem(" / ".join(typePath), theType.recId)
            if theType.isChildren():
                self._addTypes(theType.getChildren(), typePath)

    def onTypeSelected(self, index):
        typeId = self.ui.typesList.itemData(index)
        if typeId is None or typeId == self.currentTypeId:
            return
        if self.isChanged():
            answer = QMessageBox.question(
                self, "Unsaved changes",
                "Save header and icon changes for the current type?",
                QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel)
            if answer == QMessageBox.StandardButton.Cancel:
                # Return the combo to the type being edited
                combo = self.ui.typesList
                combo.blockSignals(True)
                combo.setCurrentIndex(combo.findData(self.currentTypeId))
                combo.blockSignals(False)
                return
            if answer == QMessageBox.StandardButton.Save:
                self.onSave()
        self._load(typeId)

    def _load(self, typeId):
        logger.debug("Load data for Type id %s", typeId)
        self.currentTypeId = typeId
        self.tableModel.load(typeId)
        self._showTypeIcon(typeId)

    def loadData(self, typeId=None):
        """Select the type in the combo box and load its headers.
        Without typeId (or unknown id) the first type of the list is used."""
        combo = self.ui.typesList
        index = combo.findData(typeId) if typeId is not None else -1
        if index < 0:
            index = 0 if combo.count() > 0 else -1
        if index < 0:
            return
        combo.blockSignals(True)
        combo.setCurrentIndex(index)
        combo.blockSignals(False)
        self._load(combo.itemData(index))

    def onSave(self):
        logger.debug("Save button pressed.")

        if self.pendingIcon is not None and self.currentTypeId is not None:
            self.factory.scheme.setTypeIcon(self.currentTypeId, self.pendingIcon)
            logger.debug("Default icon of type %s saved: '%s'", self.currentTypeId, self.pendingIcon)
            self.pendingIcon = None
            self.comm.typeIconChanged.emit(int(self.currentTypeId))

        for theRow in range(0, self.tableModel.rowCount(0)):
            isChanged = False
            hdrObj: ElDBScheme.Header = None
            for theCol in range(0, self.tableModel.columnCount()):
                cellDescr = self.tableModel.getCell(theRow, theCol)
                if cellDescr.get(TBL_CHNG):
                    hdrObj = cellDescr.get(TBL_FLD_OBJ)
                    hdrObj[cellDescr.get(TBL_FLD_COLNAME)] = cellDescr.get(TBL_VAL)
                    isChanged = True

            if isChanged and hdrObj is not None:
                hdrObj.save()
                logger.debug("Header %s saved.", hdrObj["display"])
                self.comm.tblUpdateRequest.emit(hdrObj)
