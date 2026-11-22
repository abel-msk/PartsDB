from ElConstants import UNIT_REFERENCE_ROLE
from ElTranslations import translate
from PyQt6.QtCore import QT_TRANSLATE_NOOP
from ElTranslations import TranslatedAction as QAction
from ElTranslations import defaultHeaderText
import logging
import sys
import time

from PyQt6 import QtCore, QtWidgets
from PyQt6.QtCore import Qt, QModelIndex, pyqtSignal, QSize, QTimer, QVariant, QObject, QMimeData, QEvent
from PyQt6.QtGui import QStandardItemModel, QStandardItem, QColor, QFont, QMouseEvent, QDrag, QDragEnterEvent
from PyQt6.QtWidgets import QTreeWidget, QTreeView, QHeaderView, QMenu, QInputDialog, QAbstractItemView, QMessageBox, \
    QListWidget

from ElData import ElDBScheme
import ElCommon
from ElData.ElDBScheme import DBFactory, Type, Types, Parts, Part, Document
from ElHdrEditDialog import HeaderEditDialog
from ElCommonUI import PartValuesDialog
from ElData import ElDBDataParts
from ElIconListWidget import IconsListWidget
from ElCommonUI import IconCellDelegate
from ElDefaultIcons import DefaultPartIcons

# logger = logging.getLogger(__name__)
# logger.setLevel(level=logging.DEBUG)
# handler = logging.StreamHandler(stream=sys.stderr)
# handler.setFormatter(logging.Formatter(fmt='%(asctime)s [%(levelname)s] %(module)s/%(funcName)s: %(message)s'))
# logger.addHandler(handler)

logger = ElCommon.setLogger(__name__)

DB_COLUMNS = list(ElDBScheme.ELEMENT_FIELDS.keys())
PARTS_COLUMN_COUNT = len(DB_COLUMNS) - 2
ICON_COLUMN = DB_COLUMNS.index("icon") - 2  # view column of PARTS.icon (models skip id, type_id)
ROW_HEIGHT = 60  # px, tall enough for readable part icons
DEFAULT_COLUMN_WIDTH = 100  # px, for a column shown again that has no saved width
timestamp = {}

CLICK_EVENT_NAME = "on_click"
MODEL_TYPECHILD = 1
MODEL_SEARCHLIST = 2


class Communicate(QObject):
    """Represent catalog rows or their Qt interactions; retain the active factory and row data."""
    documentSelect = pyqtSignal(ElDBScheme.Document)
    partSelect = pyqtSignal(Part)
    partsTypeRequest = pyqtSignal(Part)
    error = pyqtSignal(str)
    hdrEditRequest = pyqtSignal()


def ErrorDialog(parent, message):
    button = QMessageBox.critical(
        parent,
        translate("PartsDB", 'Error'),
        message,
        buttons=QMessageBox.StandardButton.Ok,
        defaultButton=QMessageBox.StandardButton.Ok)


def _removePartRow(model, row):
    """Delete from the DB before notifying Qt; a failed transaction leaves the model intact."""
    if row < 0 or row >= len(model.parts):
        return False
    part = model.parts[row]
    try:
        iconError = model.factory.deletePart(part)
    except ElDBScheme.PartInProjectsError as err:
        QMessageBox.warning(None, translate("PartsDB", 'Delete part'), translate("PartsDB", str(err)))
        return False
    except Exception:
        logger.exception("Can't delete part %s", part.id)
        ErrorDialog(None, translate("PartsDB", "Can't delete part {}.").format(part["part_num"]))
        return False
    model.beginRemoveRows(QModelIndex(), row, row)
    model.parts.partsAr.pop(row)
    model.endRemoveRows()
    if iconError:
        QMessageBox.warning(None, translate("PartsDB", 'Delete icon'),
                            translate("PartsDB", 'The part was deleted, but its icon file could not be removed:\n{}').format(iconError))
    return True


class SearchTableModel(QtCore.QAbstractTableModel):

    """Represent catalog rows or their Qt interactions; retain the active factory and row data."""
    def __init__(self, factory: DBFactory, parts: Parts):
        """Initialize the controller or data model with its owning widgets and catalog.

        @param factory [DBFactory] factory supplied by the caller.
        @param parts [Parts] parts supplied by the caller.
        @return [object, None] Requested data or completion of the documented catalog operation.
        """
        super(SearchTableModel, self).__init__()
        self.factory: DBFactory = factory
        self.parts: Parts = parts
        self.theType = None
        self.headers = None

    def removeRow(self, row: int, parent=QModelIndex()) -> bool:
        """Delete a catalog row through the persistence layer before notifying Qt.

        @param row [int] row supplied by the caller.
        @param parent [QModelIndex] parent supplied by the caller.
        @return [object, None] Requested data or completion of the documented catalog operation.
        """
        return _removePartRow(self, row)

    def flags(self, index):
        """Return the supported selection, editing and checkbox flags for a cell.

        @param index [QModelIndex] index supplied by the caller.
        @return [object, None] Requested data or completion of the documented catalog operation.
        """
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
        """Return the number of loaded catalog rows.

        @param index [QModelIndex] index supplied by the caller.
        @return [object, None] Requested data or completion of the documented catalog operation.
        """
        return len(self.parts)

    def columnCount(self, index: QModelIndex = ...) -> int:
        """Return the number of visible-model catalog fields.

        @param index [QModelIndex] index supplied by the caller.
        @return [object, None] Requested data or completion of the documented catalog operation.
        """
        return PARTS_COLUMN_COUNT

    def data(self, index: QModelIndex, role=None):
        """Return catalog cell contents or metadata for the requested Qt role.

        @param index [QModelIndex] index supplied by the caller.
        @param role [Qt.ItemDataRole, None] role supplied by the caller.
        @return [object, None] Requested data or completion of the documented catalog operation.
        """
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
        """Sort loaded catalog rows by a field and notify the view.

        @param column [int] column supplied by the caller.
        @param order [Qt.SortOrder] order supplied by the caller.
        @return [object, None] Requested data or completion of the documented catalog operation.
        """
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
        """Return translated column captions and header styling for a Qt role.

        @param section [int] section supplied by the caller.
        @param orientation [Qt.Orientation] orientation supplied by the caller.
        @param role [Qt.ItemDataRole, None] role supplied by the caller.
        @return [object, None] Requested data or completion of the documented catalog operation.
        """
        if role == Qt.ItemDataRole.DisplayRole:
            if orientation == Qt.Orientation.Horizontal:
                column = section + 2
                field = list(ElDBScheme.ELEMENT_FIELDS.keys())[column]
                result = translate("PartsDB", ElDBScheme.ELEMENT_FIELDS_DISPLAY.get(field, field))
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


class PartUnitDelegate(QtWidgets.QStyledItemDelegate):
    """Edit nominal SI units using the section's dimension and all configured multipliers.

    @attr parent [QTableView] Catalog view supplying the edited Part in UserRole.
    """

    def paint(self, painter, option, index):
        """Draw a visible dropdown indicator for sections with a configured SI dimension.

        @param painter [QPainter] Qt view painter.
        @param option [QStyleOptionViewItem] Cell rectangle and selection style.
        @param index [QModelIndex] Units cell with a dimension flag in UNIT_REFERENCE_ROLE.
        @return [None] Render a combo-style cell, otherwise the standard text cell.
        """
        if not index.data(UNIT_REFERENCE_ROLE):
            return super().paint(painter, option, index)
        combo = QtWidgets.QStyleOptionComboBox()
        combo.rect = option.rect
        combo.state = option.state
        combo.palette = option.palette
        combo.currentText = str(index.data(Qt.ItemDataRole.DisplayRole) or '')
        style = option.widget.style() if option.widget else QtWidgets.QApplication.style()
        style.drawComplexControl(QtWidgets.QStyle.ComplexControl.CC_ComboBox, combo, painter, option.widget)
        style.drawControl(QtWidgets.QStyle.ControlElement.CE_ComboBoxLabel, combo, painter, option.widget)

    def createEditor(self, parent, option, index):
        """Create a constrained unit selector or the default editor for types without SI units.

        @param parent [QWidget] Editor owner.
        @param option [QStyleOptionViewItem] Qt style options.
        @param index [QModelIndex] Unit cell whose UserRole stores a Part.
        @return [QWidget] Combo box for an SI dimension, otherwise the normal text editor.
        """
        from ElData.ElDBDataUnits import UnitsDataStore
        part = index.data(Qt.ItemDataRole.UserRole)
        store = UnitsDataStore(part.scheme)
        base, units = store.sectionUnits(part['type_id'])
        if base is None:
            return super().createEditor(parent, option, index)
        editor = QtWidgets.QComboBox(parent)
        editor.addItem('')
        aliases = store.aliases()
        for unit in sorted(units, key=lambda row: row[5]):
            for marker in dict.fromkeys((unit[3], unit[4], *aliases.get(unit[0], ()))):
                editor.addItem(marker)
        return editor

    def setEditorData(self, editor, index):
        """Select the saved spelling without losing a legacy custom value.

        @param editor [QWidget] Combo box or normal Qt editor.
        @param index [QModelIndex] Source nominal unit cell.
        @return [None] Populate the current editor.
        """
        if not isinstance(editor, QtWidgets.QComboBox):
            return super().setEditorData(editor, index)
        value = str(index.data(Qt.ItemDataRole.EditRole) or '')
        selected = editor.findText(value)
        if selected < 0:
            editor.addItem(value)
            selected = editor.count()-1
        editor.setCurrentIndex(selected)

    def setModelData(self, editor, model, index):
        """Commit the selected unit through the regular model save and normalization path.

        @param editor [QWidget] Active cell editor.
        @param model [PartsTableModel] Writable catalog model.
        @param index [QModelIndex] Target units cell.
        @return [None] Persist the unit and recomputed nominal.
        """
        if isinstance(editor, QtWidgets.QComboBox):
            model.setData(index, editor.currentText(), Qt.ItemDataRole.EditRole)
        else:
            super().setModelData(editor, model, index)


class PartsTableModel(QtCore.QAbstractTableModel):
    """Represent catalog rows or their Qt interactions; retain the active factory and row data."""
    data_changed = pyqtSignal(QModelIndex, Part, name='dataChanged')

    def __init__(self, factory: DBFactory, theType: Type):
        """Initialize the controller or data model with its owning widgets and catalog.

        @param factory [DBFactory] factory supplied by the caller.
        @param theType [Type] theType supplied by the caller.
        @return [object, None] Requested data or completion of the documented catalog operation.
        """
        super(PartsTableModel, self).__init__()
        self.factory: DBFactory = factory
        self.theType: Type = theType
        self.parts: Parts = factory.loadPartsByType(self.theType)
        self.headers: ElDBScheme.Headers = self.theType.refreshHeaders()
        from ElData.ElDBDataUnits import UnitsDataStore
        self.siBase, self.siUnits = UnitsDataStore(factory.scheme).sectionUnits(theType.recId)
        self.needReload = False

    def data(self, index: QModelIndex, role=None):
        """Return catalog cell contents or metadata for the requested Qt role.

        @param index [QModelIndex] index supplied by the caller.
        @param role [Qt.ItemDataRole, None] role supplied by the caller.
        @return [object, None] Requested data or completion of the documented catalog operation.
        """
        if role == UNIT_REFERENCE_ROLE:
            return bool(self.siBase) if DB_COLUMNS[index.column()+2] == 'units' else False
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
        """Return the supported selection, editing and checkbox flags for a cell.

        @param index [QModelIndex] index supplied by the caller.
        @return [object, None] Requested data or completion of the documented catalog operation.
        """
        column = index.column()
        fieldName = ElDBScheme.ELEMENT_FLD_NAMES[column + 2]

        if index.column() == 0:
            return super().flags(index) | Qt.ItemFlag.ItemIsEditable
        elif ElDBScheme.ELEMENT_FIELDS[fieldName] == "BOOLEAN":
            return super().flags(index) | Qt.ItemFlag.ItemIsUserCheckable
        else:
            return super().flags(index) | Qt.ItemFlag.ItemIsEditable | Qt.ItemFlag.ItemIsEnabled

    def rowCount(self, index: QModelIndex = ...):
        """Return the number of loaded catalog rows.

        @param index [QModelIndex] index supplied by the caller.
        @return [object, None] Requested data or completion of the documented catalog operation.
        """
        return len(self.parts)

    def columnCount(self, index: QModelIndex = ...) -> int:
        """Return the number of visible-model catalog fields.

        @param index [QModelIndex] index supplied by the caller.
        @return [object, None] Requested data or completion of the documented catalog operation.
        """
        return PARTS_COLUMN_COUNT

    # def updateHeaders(self):
    #     self.headers: ElDBScheme.Headers = self.theType.getHeaders()

    def headerData(self, section, orientation, role=None):
        """Return translated column captions and header styling for a Qt role.

        @param section [int] section supplied by the caller.
        @param orientation [Qt.Orientation] orientation supplied by the caller.
        @param role [Qt.ItemDataRole, None] role supplied by the caller.
        @return [object, None] Requested data or completion of the documented catalog operation.
        """
        if self.needReload:
            self.headers: ElDBScheme.Headers = self.theType.refreshHeaders()
            self.needReload = False

        if role == Qt.ItemDataRole.DisplayRole:
            if orientation == Qt.Orientation.Horizontal:
                column = section + 2
                fldName = list(ElDBScheme.ELEMENT_FIELDS.keys())[column]
                result = defaultHeaderText(self.headers[fldName], fldName)
                # logger.debug("Header %s, value %s",fldName, result)
                # result = self.headers[fldName].display
                return result

        elif role == Qt.ItemDataRole.FontRole:
            font = QFont()
            font.setBold(bool(self.headers[DB_COLUMNS[section + 2]]["is_key"])
                         if orientation == Qt.Orientation.Horizontal else False)
            font.setPixelSize(12)
            return QVariant(font)

        elif role == Qt.ItemDataRole.SizeHintRole:
            if orientation == Qt.Orientation.Horizontal:
                # logger.debug("data: Got resize event. Section {}".format(section))
                return QSize(100, 30)

    # https://doc.qt.io/qt-6/qabstractitemmodel.html#dataChanged
    def setData(self, index, value, role=None):
        """Validate an edited catalog field, persist it and update dependent nominal fields.

        @param index [QModelIndex] index supplied by the caller.
        @param value [object] value supplied by the caller.
        @param role [Qt.ItemDataRole, None] role supplied by the caller.
        @return [object, None] Requested data or completion of the documented catalog operation.
        """
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
                    thePart[columnName] = float(str(value).translate(transTbl)) if value != "" else None
                else:
                    thePart[columnName] = value
                thePart.save()
                self.dataChanged.emit(self.index(row, 0), self.index(row, self.columnCount()-1))
            except ValueError as e:
                # logger.error(e)
                logging.exception("ValueError")
                ErrorDialog(None, translate("PartsDB", 'Incorrect value type for column {}').format(columnName))
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
        """Delete a catalog row through the persistence layer before notifying Qt.

        @param row [int] row supplied by the caller.
        @param parent [QModelIndex] parent supplied by the caller.
        @return [object, None] Requested data or completion of the documented catalog operation.
        """
        return _removePartRow(self, row)

    def appendRow(self, thePart: Part):
        """Append a persisted stock card and notify the table view.

        @param thePart [Part] thePart supplied by the caller.
        @return [object, None] Requested data or completion of the documented catalog operation.
        """
        newRow = len(self.parts.partsAr)  # rows are 0-based: the appended row goes at index rowCount()
        self.beginInsertRows(QModelIndex(), newRow, newRow)
        self.parts.partsAr.append(thePart)
        self.endInsertRows()
        return True

    def setHeaderData(self, section, orientation, value, role=None):
        """Update a column caption in the current model.

        @param section [int] section supplied by the caller.
        @param orientation [Qt.Orientation] orientation supplied by the caller.
        @param value [object] value supplied by the caller.
        @param role [Qt.ItemDataRole, None] role supplied by the caller.
        @return [object, None] Requested data or completion of the documented catalog operation.
        """
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
        """Sort loaded catalog rows by a field and notify the view.

        @param column [int] column supplied by the caller.
        @param order [Qt.SortOrder] order supplied by the caller.
        @return [object, None] Requested data or completion of the documented catalog operation.
        """
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

    """Represent catalog rows or their Qt interactions; retain the active factory and row data."""
    def __init__(self, factory: DBFactory, tableView: QtWidgets.QTableView, docList: QListWidget):
        """Initialize the controller or data model with its owning widgets and catalog.

        @param factory [DBFactory] factory supplied by the caller.
        @param tableView [QTableView] tableView supplied by the caller.
        @param docList [QListWidget] docList supplied by the caller.
        @return [object, None] Requested data or completion of the documented catalog operation.
        """
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

        # Draw the picture from the "icon" column instead of its path text
        self.iconDelegate = IconCellDelegate(self.tableView, iconsDir=self.factory.getIconsDir(),
                                             defaultIcons=DefaultPartIcons(self.factory))
        self.tableView.setItemDelegateForColumn(ICON_COLUMN, self.iconDelegate)
        self.tableView.setItemDelegateForColumn(DB_COLUMNS.index('units')-2, PartUnitDelegate(self.tableView))
        self.tableView.verticalHeader().setDefaultSectionSize(ROW_HEIGHT)
        # Pictures dropped from the desktop or a browser onto the icon cell become the part's icon
        self.tableView.viewport().setAcceptDrops(True)
        self.tableView.viewport().installEventFilter(self)

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
        """Move keyboard focus to the catalog table.

        @return [object, None] Requested data or completion of the documented catalog operation.
        """
        self.tableView.setFocus()

    def setFactory(self, factory: DBFactory, iconsDir: str):
        """Switch databases without retaining old models, documents or icon caches."""
        self.saveResize = False
        self.timestamp = {}
        self.headers = None
        self.theType = None
        self.tableModel = None
        self.searchMode = False
        self.menuColumnSelected = None
        self.menuRowSelected = None
        self.factory = factory
        self.tableView.setModel(QStandardItemModel(self.tableView))
        self.iconsListWidget.clear()
        self.iconsListWidget.factory = factory
        self.iconsListWidget.currentPart = None
        self.iconsListWidget.documents = None
        self.iconDelegate.iconsDir = iconsDir
        self.iconDelegate.defaultIcons = DefaultPartIcons(factory)
        self.iconDelegate.clearCache()
        self._setDropRow(-1)

    # ---------- drop a picture onto the icon cell ----------

    def _isPictureDrag(self, event) -> bool:
        """An external drag carrying a picture (drags started inside the program are not ours)."""
        return (event.source() is None and self.tableModel is not None
                and ElCommon.canProvideImage(event.mimeData()))

    def _iconDropIndex(self, event) -> QModelIndex | None:
        """Icon cell under the cursor for an external drag carrying a picture, else None."""
        if not self._isPictureDrag(event):
            return None
        index = self.tableView.indexAt(event.position().toPoint())
        if not index.isValid() or index.column() != ICON_COLUMN:
            return None
        return index

    def _setDropRow(self, row: int):
        """Select the target row of a document or icon drop.

        @param row [int] row supplied by the caller.
        @return [object, None] Requested data or completion of the documented catalog operation.
        """
        if self.iconDelegate.dropRow != row:
            self.iconDelegate.dropRow = row
            self.tableView.viewport().update()

    def eventFilter(self, obj, event) -> bool:
        """Handle catalog view events, including document and icon drops.

        @param obj [QObject] obj supplied by the caller.
        @param event [QEvent] event supplied by the caller.
        @return [object, None] Requested data or completion of the documented catalog operation.
        """
        try:
            if obj is not self.tableView.viewport():
                return False
        except RuntimeError:  # the view is already destroyed (program exit)
            return False
        etype = event.type()
        if etype == QEvent.Type.DragEnter and self._isPictureDrag(event) and self._iconDropIndex(event) is None:
            # A picture enters the table over another column. Accept the enter anyway: Qt sends no DragMove
            # to a widget that ignored DragEnter, so moving on to the icon cell would never be noticed.
            # The cursor still shows "no drop" (proposed action ignored) until the icon column is reached.
            event.setDropAction(Qt.DropAction.IgnoreAction)
            event.accept()
            self._setDropRow(-1)
            return True
        if etype in (QEvent.Type.DragEnter, QEvent.Type.DragMove):
            index = self._iconDropIndex(event)
            if index is None:
                self._setDropRow(-1)
                event.ignore()  # not ours: an ignored drag event goes on to the main window, as before
                return True
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
            self._setDropRow(index.row())
            return True
        if etype == QEvent.Type.DragLeave:
            self._setDropRow(-1)
            return False
        if etype == QEvent.Type.Drop:
            self._setDropRow(-1)
            index = self._iconDropIndex(event)
            if index is None:
                event.ignore()
                return True
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
            logger.info("Picture dropped on row %s: %s", index.row(), ElCommon.describeMime(event.mimeData()))
            # The drag's data (and on macOS the image memory) is gone once the event returns: deep copy now
            mime = ElCommon.copyMimeData(event.mimeData())
            row = index.row()
            QTimer.singleShot(0, lambda: self.setIconFromMime(row, mime))
            return True
        return False

    def setIconFromMime(self, row: int, mime: QMimeData) -> bool:
        """Save the dropped picture as PNG in the icons folder and make it the icon of the part in `row`."""
        index = self.tableModel.index(row, ICON_COLUMN)
        thePart: Part = index.data(Qt.ItemDataRole.UserRole)
        if thePart is None:
            return False
        QtWidgets.QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            img = ElCommon.imageFromMime(mime)
            if img is None:
                QtWidgets.QApplication.restoreOverrideCursor()
                ErrorDialog(self.tableView, translate("PartsDB", "The dropped object is not a picture or it can't be downloaded."))
                return False
            fileName = ElCommon.saveIcon(img, self.factory.getIconsDir(), thePart["part_num"])
            oldIcon = thePart["icon"]
            thePart["icon"] = fileName
            thePart.save()
            logger.info("Part %s(%s): icon '%s' -> '%s'", thePart["part_num"], thePart.id, oldIcon, fileName)
        except Exception as e:
            logger.exception("Can't set the dropped icon")
            QtWidgets.QApplication.restoreOverrideCursor()
            ErrorDialog(self.tableView, translate("PartsDB", "Can't save the icon: {}").format(e))
            return False
        QtWidgets.QApplication.restoreOverrideCursor()
        self.tableModel.dataChanged.emit(index, index)
        # Make the row active and bring the program to the front (the drag came from another app)
        self.tableView.selectRow(row)
        self.tableView.setCurrentIndex(index)
        self.tableView.scrollTo(index)
        self.tableView.window().raise_()
        self.tableView.window().activateWindow()
        self.tableView.setFocus()
        return True

    def getCurrentType(self):
        """Return the currently selected catalog section.

        @return [object, None] Requested data or completion of the documented catalog operation.
        """
        return self.theType

    def localMouseMoveEvent(self, event: QMouseEvent):
        """Handle mouse movement for catalog row dragging.

        @param event [QEvent] event supplied by the caller.
        @return [object, None] Requested data or completion of the documented catalog operation.
        """
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
        """Build the catalog column visibility, alignment and editing menu.

        @return [object, None] Requested data or completion of the documented catalog operation.
        """
        hideAct = QAction(QT_TRANSLATE_NOOP("PartsDB", 'Hide Column'), self.tableView)
        hideAct.setStatusTip(QT_TRANSLATE_NOOP("PartsDB", 'Hide selected Column'))
        hideAct.triggered.connect(self.hideColumn)

        showAct = QAction(QT_TRANSLATE_NOOP("PartsDB", 'Show Column on right if any'), self.tableView)
        showAct.setStatusTip(QT_TRANSLATE_NOOP("PartsDB", 'Hide selected Column'))
        showAct.triggered.connect(self.showColumn)

        renameAct = QAction(QT_TRANSLATE_NOOP("PartsDB", 'Rename selected Header'), self.tableView)
        renameAct.setStatusTip(QT_TRANSLATE_NOOP("PartsDB", "Add new 'Type' object as child of selected."))
        renameAct.triggered.connect(self.renameHeader)

        alRightAct = QAction(QT_TRANSLATE_NOOP("PartsDB", 'Align Right'), self.tableView)
        alRightAct.setStatusTip(QT_TRANSLATE_NOOP("PartsDB", 'Align to the right selected column contents'))
        alRightAct.triggered.connect(self.alignRight)

        alLeftAct = QAction(QT_TRANSLATE_NOOP("PartsDB", 'Align Left'), self.tableView)
        alLeftAct.setStatusTip(QT_TRANSLATE_NOOP("PartsDB", 'Align to the left selected column contents'))
        alLeftAct.triggered.connect(self.alignLeft)

        editHdr = QAction(QT_TRANSLATE_NOOP("PartsDB", 'Edit Headers'), self.tableView)
        editHdr.setStatusTip(QT_TRANSLATE_NOOP("PartsDB", 'Open headers edit dialog'))
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
        ldOrig = QAction(QT_TRANSLATE_NOOP("PartsDB", 'Load Original'), self.tableView)
        ldOrig.setStatusTip(QT_TRANSLATE_NOOP("PartsDB", 'Load corresponding parts type.'))
        ldOrig.triggered.connect(self.loadPartsType)

        menu = QMenu(self.tableView)
        menu.addAction(ldOrig)
        return menu

    def _defineBodyMenu(self):
        """
        Define popup menu for Parts Table body
        :return:
        """
        tglAct = QAction(QT_TRANSLATE_NOOP("PartsDB", 'Switch Selection'), self.tableView)
        tglAct.setStatusTip(QT_TRANSLATE_NOOP("PartsDB", 'Toggle multiline / singleline selection.'))
        tglAct.triggered.connect(self.toggleSelection)

        addAct = QAction(QT_TRANSLATE_NOOP("PartsDB", 'Add Part'), self.tableView)
        addAct.setStatusTip(QT_TRANSLATE_NOOP("PartsDB", 'Add new part.'))
        addAct.triggered.connect(self.addRow)

        delAct = QAction(QT_TRANSLATE_NOOP("PartsDB", 'Delete Part'), self.tableView)
        delAct.setStatusTip(QT_TRANSLATE_NOOP("PartsDB", 'Delete selected part.'))
        delAct.triggered.connect(self.deleteRow)

        menu = QMenu(self.tableView)
        menu.addAction(tglAct)
        menu.addAction(addAct)
        menu.addSeparator()
        menu.addAction(delAct)
        return menu

    def loadSearchData(self, parts: Parts):
        """Display read-only search results and connect their selection events.

        @param parts [Parts] parts supplied by the caller.
        @return [object, None] Requested data or completion of the documented catalog operation.
        """
        self.theType = None
        self.headers = None
        self.searchMode = True
        self.tableModel = SearchTableModel(self.factory, parts)
        self.tableView.setModel(self.tableModel)
        self.applyColumnOrder()
        self.tableView.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        selection_model = self.tableView.selectionModel()
        selection_model.selectionChanged.connect(self.onSelectionChanged)
        self.iconsListWidget.clear()

    def loadData(self, theType: Type):
        # try: self.header.sectionResized.disconnect()
        # except TypeError: pass
        """Load a section, configure its columns and reconnect catalog selection events.

        @param theType [Type] theType supplied by the caller.
        @return [object, None] Requested data or completion of the documented catalog operation.
        """
        self.searchMode = False
        self.timestamp = {}
        self.saveResize = False
        self.theType = theType
        # self.header.sectionResized.disconnect()
        self.tableModel = PartsTableModel(self.factory, self.theType)
        self.tableView.setModel(self.tableModel)  # parts_tbl_view
        self.headers: ElDBScheme.Headers = self.tableModel.headers  # fresh from the DB
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

        self.applyColumnOrder()

        #### Loop throw header section for set size
        # header.resizeSection(col, hdr_width)
        # self.header.sectionResized.connect(self.onColumnResize)

        self.header.sectionResized.connect(self.onColumnResize)  # !!! Do not activate event before initial resize
        selection_model = self.tableView.selectionModel()
        selection_model.selectionChanged.connect(self.onSelectionChanged)
        self.iconsListWidget.clear()
        self.tableView.selectRow(0)
        self.saveResize = True


    def applyColumnOrder(self):
        """Arrange columns visually by HEADERS.position (defaults when there are no headers, e.g. search)."""

        def position(column):
            fieldName = ElDBScheme.ELEMENT_FLD_NAMES[column + 2]
            if self.headers is not None:
                return self.headers[fieldName]["position"]
            return ElDBScheme.defaultHeaderPosition(fieldName)

        order = sorted(range(PARTS_COLUMN_COUNT), key=lambda column: (position(column), column))
        for visual, logical in enumerate(order):
            self.header.moveSection(self.header.visualIndex(logical), visual)

    # def dataChanged(self, index1, index2):
    #     logger.debug("DataChanged event occurred.")

    def onColumnResize(self, column: int, oldWidth: int, newWidth: int):
        """Schedule persistence of a user-resized catalog column.

        @param column [int] column supplied by the caller.
        @param oldWidth [int] oldWidth supplied by the caller.
        @param newWidth [int] newWidth supplied by the caller.
        @return [object, None] Requested data or completion of the documented catalog operation.
        """
        if self.saveResize:
            self.timestamp[column] = [newWidth, time.time()]
            QTimer.singleShot(1550, lambda: self.saveHeaderWidth(column))  # Delay execution by 2 sec

    def saveHeaderWidth(self, column):
        """Persist a column width after the resize debounce period.

        @param column [int] column supplied by the caller.
        @return [object, None] Requested data or completion of the documented catalog operation.
        """
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
        """Open the column settings menu at the requested header position.

        @param point [QPoint] point supplied by the caller.
        @return [object, None] Requested data or completion of the documented catalog operation.
        """
        if self.headers is None:
            return
        column = self.header.logicalIndexAt(point.x())
        hdr = self.headers[ElDBScheme.ELEMENT_FLD_NAMES[column + 2]]
        self.menuColumnSelected = column
        logger.debug("Menu event for Header column %s(col=%s)", hdr["display"], column)
        if self.headerMenu is None:
            self.headerMenu = self._defineHeaderMenu()
        self.headerMenu.popup(self.header.mapToGlobal(point))

    def tableMenuEvent(self, point):
        """Open the context menu for a catalog or search-result row.

        @param point [QPoint] point supplied by the caller.
        @return [object, None] Requested data or completion of the documented catalog operation.
        """
        idx: QModelIndex = self.tableView.indexAt(point)
        if idx.isValid():
            self.tableView.setCurrentIndex(idx)
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
        """Return the effective header settings for a catalog column.

        @param column [int] column supplied by the caller.
        @return [object, None] Requested data or completion of the documented catalog operation.
        """
        hdr = self.headers[ElDBScheme.ELEMENT_FLD_NAMES[column + 2]]
        return hdr

    def hideColumn(self):
        """Hide the selected catalog column and save its visibility.

        @return [object, None] Requested data or completion of the documented catalog operation.
        """
        self.tableView.hideColumn(self.menuColumnSelected)
        hdr: ElDBScheme.Header = self.getHeaderByColumn(self.menuColumnSelected)
        hdr["hidden"] = True
        hdr.save()
        self.tableView.update()

    def showColumn(self):
        """Show the adjacent catalog column and save its visibility.

        @return [object, None] Requested data or completion of the documented catalog operation.
        """
        self.tableView.hideColumn(self.menuColumnSelected + 1)
        hdr: ElDBScheme.Header = self.getHeaderByColumn(self.menuColumnSelected + 1)
        hdr["hidden"] = False
        hdr.save()
        self.tableView.update()

    def renameHeader(self):
        """Prompt for and persist the selected catalog column caption.

        @return [object, None] Requested data or completion of the documented catalog operation.
        """
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
        """Persist right alignment for the selected catalog column.

        @return [object, None] Requested data or completion of the documented catalog operation.
        """
        hdr: ElDBScheme.Header = self.getHeaderByColumn(self.menuColumnSelected)
        hdr["align"] = ElDBScheme.F_ALIGN_RIGHT
        hdr.save()
        # self.tableView.changeEvent()
        # index = QModelIndex()
        # idx = self.tableModel.index(self.menuColumnSelected)
        # self.tableModel.dataChanged.emit(idx)
        self.tableView.update()

    def alignLeft(self):
        """Persist left alignment for the selected catalog column.

        @return [object, None] Requested data or completion of the documented catalog operation.
        """
        hdr: ElDBScheme.Header = self.getHeaderByColumn(self.menuColumnSelected)
        hdr["align"] = ElDBScheme.F_ALIGN_LEFT
        hdr.save()
        self.tableView.update()

    def alignCenter(self):
        """Persist centered alignment for the selected catalog column.

        @return [object, None] Requested data or completion of the documented catalog operation.
        """
        hdr: ElDBScheme.Header = self.getHeaderByColumn(self.menuColumnSelected)
        hdr["align"] = ElDBScheme.F_ALIGN_CENTER
        hdr.save()

    def editHeader(self):
        """Request the section header editor.

        @return [object, None] Requested data or completion of the documented catalog operation.
        """
        self.comm.hdrEditRequest.emit()

    def loadPartsType(self):

        """Request the original section for a selected search-result card.

        @return [object, None] Requested data or completion of the documented catalog operation.
        """
        index = (self.tableView.selectionModel().currentIndex())
        thePart: Part = index.sibling(self.menuRowSelected, 1).data(Qt.ItemDataRole.UserRole)
        logger.debug("Got event. Load parts %s type = %s", thePart["part_num"], thePart["type_id"])
        self.comm.partsTypeRequest.emit(thePart)

    def toggleSelection(self):
        """Switch between single-row and multiple-row selection.

        @return [object, None] Requested data or completion of the documented catalog operation.
        """
        if self.tableView.selectionMode() == QAbstractItemView.SelectionMode.MultiSelection:
            logger.debug("Set selection mode SingleSelection")
            index = self.tableView.selectionModel().currentIndex()
            self.tableView.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
            self.tableView.selectRow(index.row())

        else:
            self.tableView.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
            logger.debug("Set selection mode MultiSelection")

    def addRow(self):
        """Create a card from its required key fields and select it in sorted order.

        @return [object, None] Requested data or completion of the documented catalog operation.
        """
        theType = self.tableModel.theType
        if theType is None:
            return
        dialog = PartValuesDialog(self.tableView, ElDBDataParts.keyHeaders(theType))
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            thePart = ElDBDataParts.createPart(self.factory, theType, dialog.values())
            self.tableModel.appendRow(thePart)
            column = self.header.sortIndicatorSection()
            if column >= 0:
                self.tableModel.sort(column, self.header.sortIndicatorOrder())
            row = next(row for row, part in enumerate(self.tableModel.parts.partsAr)
                       if part.id == thePart.id)
            column = next((self.header.logicalIndex(visual)
                           for visual in range(self.header.count())
                           if not self.header.isSectionHidden(self.header.logicalIndex(visual))), 0)
            index = self.tableModel.index(row, column)
            self.tableView.selectionModel().setCurrentIndex(
                index, QtCore.QItemSelectionModel.SelectionFlag.ClearAndSelect
                | QtCore.QItemSelectionModel.SelectionFlag.Rows)
            self.tableView.scrollTo(index, QAbstractItemView.ScrollHint.EnsureVisible)

    def deleteRow(self):
        """Confirm and delete the selected card while preserving project integrity.

        @return [object, None] Requested data or completion of the documented catalog operation.
        """
        selection = self.tableView.selectionModel()
        if self.tableModel is None or selection is None or not selection.hasSelection():
            QMessageBox.information(self.tableView, translate("PartsDB", 'Delete part'), translate("PartsDB", 'Please select a part first.'))
            return
        index = selection.currentIndex()
        if not index.isValid() or not selection.isSelected(index):
            index = selection.selectedIndexes()[0]
        part = index.data(Qt.ItemDataRole.UserRole)
        if part is None:
            QMessageBox.information(self.tableView, translate("PartsDB", 'Delete part'), translate("PartsDB", 'Please select a part first.'))
            return
        try:
            self.factory.scheme.ensurePartNotInProjects(part.id)
        except ElDBScheme.PartInProjectsError as err:
            QMessageBox.warning(self.tableView, translate("PartsDB", 'Delete part'), translate("PartsDB", str(err)))
            return
        message = translate("PartsDB", 'Delete part "{}" and all its document links?\nDocument files will remain on disk. The icon file in the icons folder will be deleted (unless attached as a document).').format(part["part_num"])
        matchCount = self.factory.scheme.countProjectComponentMatches(part.id)
        if matchCount:
            message += "\n\n" + translate("PartsDB", 'Warning: this will remove {} stock matches from imported project components. The project components will remain and will need to be matched again.').format(matchCount)
        answer = QMessageBox.question(
            self.tableView, translate("PartsDB", 'Delete part'), message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        if self.tableModel.removeRow(index.row()):
            self.iconDelegate.clearCache()
            self.iconsListWidget.clear()
            self.iconsListWidget.currentPart = None
            self.iconsListWidget.documents = None
            if self.tableModel.rowCount():
                row = min(index.row(), self.tableModel.rowCount() - 1)
                self.tableView.selectRow(row)
                self.tableView.setCurrentIndex(self.tableModel.index(row, 0))
                # A surviving row can already be selected after Qt's removal notifications.
                self.onSelectionChanged(None, None)

    def addDocument(self, file, type: int = ElDBScheme.DOC_TYPE_DEFAULT):
        """Attach a document to the currently selected stock card.

        @param file [str] file supplied by the caller.
        @param type [int] type supplied by the caller.
        @return [object, None] Requested data or completion of the documented catalog operation.
        """
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
        """Delete the selected document link from the active stock card.

        @return [object, None] Requested data or completion of the documented catalog operation.
        """
        index = (self.tableView.selectionModel().currentIndex())
        thePart: Part = index.data(Qt.ItemDataRole.UserRole)
        theDoc = self.iconsListWidget.getSelectedItem()
        self.iconsListWidget.deleteDocument(theDoc)
        thePart.documents.delete(theDoc)

    def getSelected(self):
        """Return the stock card stored in the selected row metadata.

        @return [object, None] Requested data or completion of the documented catalog operation.
        """
        index = (self.tableView.selectionModel().currentIndex())
        return index.data(Qt.ItemDataRole.UserRole)

    def _getInput(self, oldValue) -> str:
        """Request a new catalog column caption from the user.

        @param oldValue [str] oldValue supplied by the caller.
        @return [object, None] Requested data or completion of the documented catalog operation.
        """
        value, ok = QInputDialog.getText(self.tableView, translate("PartsDB", 'Enter name'), translate("PartsDB", 'Enter new name column'))
        if ok and value:
            return value
        else:
            return ""

    def onTypeIconChanged(self, typeId: int = None):
        """A section's default icon was changed: redraw the icons of parts without a picture."""
        self.iconDelegate.defaultIcons.reload()
        self.tableView.viewport().update()

    def updateHeader(self, hdrObj: ElDBScheme.Header = None):
        # Headers of another type do not affect the table shown now
        """Refresh column settings after editing the current section headers.

        @param hdrObj [Header, None] hdrObj supplied by the caller.
        @return [object, None] Requested data or completion of the documented catalog operation.
        """
        if hdrObj is None or self.theType is None or int(hdrObj["type_id"]) != int(self.theType.recId):
            return

        #  Get header column count
        fieldList = list(ElDBScheme.ELEMENT_FIELDS.keys())
        idx = fieldList.index(hdrObj["field_name"]) - 2
        logger.debug("Update Header %s, index=%s", hdrObj["display"], idx)

        # Reload headers from the DB: the cached copies are stale after the dialog saved
        self.headers = self.theType.refreshHeaders()
        self.tableModel.headers = self.headers
        self.tableModel.needReload = False
        hdr = self.headers[hdrObj["field_name"]]
        saveResize, self.saveResize = self.saveResize, False  # showing a column is not a user resize
        self.tableView.setColumnHidden(idx, hdr["hidden"])
        if not hdr["hidden"]:
            width = hdr["width"]
            self.tableView.setColumnWidth(idx, int(width) if width else DEFAULT_COLUMN_WIDTH)
        self.saveResize = saveResize
        self.tableView.horizontalHeader().viewport().update()
        self.tableView.viewport().update()

    def selectByID(self, theId):
        """Select the row corresponding to a stored catalog card identity.

        @param theId [int] theId supplied by the caller.
        @return [object, None] Requested data or completion of the documented catalog operation.
        """
        parts:Parts = self.tableModel.parts
        if not self.searchMode:
            for row in range(0, len(parts)):
                thePart: Part = parts[row]
                if thePart.id == theId:
                    self.tableView.selectRow(row)
