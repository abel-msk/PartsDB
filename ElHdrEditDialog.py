# from PyQt6 import QtCore
from PyQt6.QtCore import Qt, QModelIndex, QVariant, QObject, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QDialog, QHeaderView
from PyQt6 import QtCore, QtWidgets
import logging
import sys
import ElDBScheme
from ElHdrEditWnd import Ui_HdrEditDialog

logger = logging.getLogger(__name__)
logger.setLevel(level=logging.DEBUG)
handler = logging.StreamHandler(stream=sys.stderr)
handler.setFormatter(logging.Formatter(fmt='%(asctime)s [%(levelname)s] %(module)s/%(funcName)s: %(message)s'))
logger.addHandler(handler)

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

TBL_VAL = "value"
TBL_CHNG = "changed"
TBL_FLD_OBJ = "data"
TBL_FLD_COLNAME = "colname"


class Communicate(QObject):
    tblUpdateRequest = pyqtSignal(ElDBScheme.Header)


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
        self.rows = 0
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

    def loadData(self, typeId):
        # self.tableModel = HeaderTableModel(self.factory)
        # self.ui.headersTbl.setEditTriggers(
        #     QtWidgets.QAbstractItemView.EditTrigger.AnyKeyPressed |
        #     QtWidgets.QAbstractItemView.EditTrigger.DoubleClicked |
        #     QtWidgets.QAbstractItemView.EditTrigger.EditKeyPressed)
        self.tableModel.load(typeId)
        self.ui.headersTbl.setModel(self.tableModel)

    def onSave(self):
        logger.debug("Save button pressed.")

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
