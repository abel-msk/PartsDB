from ElTranslations import translate
from ElTranslations import TranslatedDialogMixin, defaultHeaderText
from ElWindowTexts import headerEditDialogTexts
from PyQt6.QtCore import QT_TRANSLATE_NOOP
# from PyQt6 import QtCore
from PyQt6.QtCore import Qt, QModelIndex, QVariant, QObject, QSize, pyqtSignal
from PyQt6.QtGui import QFont, QIcon
from PyQt6.QtWidgets import QDialog, QHeaderView, QMessageBox
from PyQt6 import QtCore, QtWidgets
import logging
import sys
from ElData import ElDBScheme
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
    "is_key": "BOOL",
    "sort": "BOOL",
    "align": "TEXT"
}

ICON_SELECTOR_SIZE = 48  # icon size in icon_selector, px

TBL_VAL = "value"
TBL_CHNG = "changed"
TBL_FLD_OBJ = "data"
TBL_FLD_COLNAME = "colname"


class Communicate(QObject):
    """Publish header and section-icon changes; stores Qt signal connections."""
    tblUpdateRequest = pyqtSignal(ElDBScheme.Header)
    typeIconChanged = pyqtSignal(int)  # type id whose default icon was saved


class HeaderTableModel(QtCore.QAbstractTableModel):
    # data_changed = pyqtSignal(QModelIndex, Part, name='dataChanged')

    """Expose editable header settings without writing pending edits to the database.

    @attr factory [DBFactory] Active catalog factory.
    @attr columnsList [list[str]] Editable setting names.
    @attr rowsList [list[str]] Catalog field names.
    @attr dataAr [list[list[dict]]] Values, dirty flags and Header references per cell.
    @attr rows [int] Loaded row count.
    @attr typeID [int] Section whose headers are currently loaded."""
    def __init__(self, factory: ElDBScheme.DBFactory):
        """Prepare header setting columns and catalog field rows.

        @param factory [DBFactory] Connected catalog database factory.
        @return [None] Update the owned UI or state without returning a value."""
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
        """Resolve the declared editor type for a setting column.

        @param colIndex [int] Zero-based setting column index within columnsList.
        @return [str, None] TEXT or BOOL editor classification."""
        return COLUMNS_DICT.get(self.columnsList[colIndex])

    def getCell(self, row, column):
        """Read a cell value, dirty flag and backing Header metadata.

        @param row [int] Zero-based loaded header row index.
        @param column [int] Zero-based setting column index.
        @return [dict] Value, changed flag, record and setting name."""
        return self.dataAr[row][column]

    def load(self, typeID):
        """Replace pending cells with settings for the selected section.

        @param typeID [int, None] Section ID; None selects a fallback only in loadData.
        @return [None] Update the owned UI or state without returning a value."""
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
        """Check whether any loaded setting has an unsaved edit.

        @return [bool] True when any pending cell has changed."""
        return any(cell.get(TBL_CHNG) for row in self.dataAr for cell in row)

    def data(self, index: QModelIndex, role=None):
        """Expose a header value, checkbox state or backing record for a Qt role.

        @param index [QModelIndex] Qt model index supplied by the view; parent indices are ignored for flat counts.
        @param role [int, Qt.ItemDataRole, None] Requested Qt display, editing, font or checkbox role.
        @return [object, None] Requested cell role value or None for an unsupported role."""
        row = index.row()
        column = index.column()
        if (role == Qt.ItemDataRole.DisplayRole) or (role == Qt.ItemDataRole.EditRole):  # Display Cell Context
            if self._column_type_(column) != "BOOL":
                if role == Qt.ItemDataRole.DisplayRole and self.columnsList[column] == "display":
                    cell = self.dataAr[row][column]
                    if not cell[TBL_CHNG]:
                        return defaultHeaderText(cell[TBL_FLD_OBJ], self.rowsList[row])
                return self.dataAr[row][column].get(TBL_VAL)

        elif role == Qt.ItemDataRole.UserRole:
            return self.dataAr[row][column].get(TBL_FLD_OBJ)

        elif role == Qt.ItemDataRole.CheckStateRole:
            if self._column_type_(column) == "BOOL":
                value = self.dataAr[row][column].get(TBL_VAL)
                return Qt.CheckState.Checked if value else Qt.CheckState.Unchecked

    def flags(self, index):
        """Select checkbox or text editing behavior for the requested cell.

        @param index [QModelIndex] Qt model index supplied by the view; parent indices are ignored for flat counts.
        @return [Qt.ItemFlag] Supported interaction flags for the requested cell."""
        column = index.column()
        # fieldName = ElDBScheme.ELEMENT_FLD_NAMES[column + 2]
        # if index.column() == 0:
        #     return super().flags(index) | Qt.ItemFlag.ItemIsEditable
        if self._column_type_(column) == "BOOL":
            return super().flags(index) | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled
        else:
            return super().flags(index) | Qt.ItemFlag.ItemIsEditable | Qt.ItemFlag.ItemIsEnabled

    def rowCount(self, index: QModelIndex = ...):
        """Return the number of loaded header rows.

        @param index [QModelIndex] Qt model index supplied by the view; parent indices are ignored for flat counts.
        @return [int] Loaded row count."""
        return self.rows

    def columnCount(self, index: QModelIndex = ...) -> int:
        """Return the number of editable setting columns.

        @param index [QModelIndex] Qt model index supplied by the view; parent indices are ignored for flat counts.
        @return [int] Setting column count."""
        return len(self.columnsList)

    def headerData(self, section, orientation, role=None):
        """Return localized setting titles or the bold header font.

        @param section [int] Zero-based header section index.
        @param orientation [Qt.Orientation] Horizontal or vertical header orientation.
        @param role [int, Qt.ItemDataRole, None] Requested Qt display, editing, font or checkbox role.
        @return [str, QVariant, None] Header caption, font or no supported value."""
        if role == Qt.ItemDataRole.DisplayRole:
            if orientation == Qt.Orientation.Horizontal:
                labels = {"field_name": QT_TRANSLATE_NOOP("PartsDB", "Field"),
                          "display": QT_TRANSLATE_NOOP("PartsDB", "Title"),
                          "hidden": QT_TRANSLATE_NOOP("PartsDB", "Hidden"),
                          "is_key": QT_TRANSLATE_NOOP("PartsDB", "Key value"),
                          "sort": QT_TRANSLATE_NOOP("PartsDB", "Sortable"),
                          "align": QT_TRANSLATE_NOOP("PartsDB", "Alignment")}
                return translate("PartsDB", labels[self.columnsList[section]])
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
        """Record a pending text or checkbox edit without saving it.

        @param index [QModelIndex] Qt model index supplied by the view; parent indices are ignored for flat counts.
        @param value [object] Pending text value or checkbox state supplied by Qt.
        @param role [int, Qt.ItemDataRole, None] Requested Qt display, editing, font or checkbox role.
        @return [bool] True if the edit was recorded."""
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


class HeaderEditDialog(TranslatedDialogMixin, QDialog):
    """Edit a section header and default icon, validating pending changes before saving.

    @attr factory [DBFactory] Active catalog factory.
    @attr ui [Ui_HdrEditDialog] Generated widgets, never modified by the controller.
    @attr tableModel [HeaderTableModel] Pending header settings.
    @attr currentTypeId [int, None] Selected section ID.
    @attr pendingIcon [str, None] Unsaved icon; empty string means automatic selection."""
    def __init__(self, parent, factory: ElDBScheme.DBFactory):
        """Build the header table, section picker and default icon selector.

        @param parent [QWidget, QObject, None] Qt owner of the created object.
        @param factory [DBFactory] Connected catalog database factory.
        @return [None] Update the owned UI or state without returning a value."""
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

        self.ui.buttonBox.accepted.disconnect()
        self.ui.buttonBox.accepted.connect(self.accept)

        self.currentTypeId = None
        self.pendingIcon = None  # icon chosen for the current type but not saved yet ('' = auto)
        self._fillTypesList()
        self.ui.typesList.currentIndexChanged.connect(self.onTypeSelected)
        self._fillIconSelector()
        self.ui.icon_selector.currentIndexChanged.connect(self.onIconSelected)
        self.retranslate()

    def retranslate(self):
        """Refresh captions and model headers without losing pending settings.

        @return [None] Update the owned UI or state without returning a value."""
        headerEditDialogTexts(self)
        if not hasattr(self, "tableModel"):
            return
        model = self.tableModel
        model.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, model.columnCount() - 1)
        if model.rows:
            model.dataChanged.emit(model.index(0, 0), model.index(model.rows - 1, model.columnCount() - 1))

    def _fillIconSelector(self):
        """Populate the automatic choice and available built-in icons.

        @return [None] Update the owned UI or state without returning a value."""
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
        combo.addItem("", "")  # The window texts function supplies the translated label.
        for path in ElDefaultIcons.availableIcons():
            name = path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
            combo.addItem(QIcon(path), name, path)
        combo.blockSignals(False)

    def _showTypeIcon(self, typeId):
        """Display the saved default icon for a section.

        @param typeId [int, None] Section ID; None selects a fallback only in loadData.
        @return [None] Update the owned UI or state without returning a value."""
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
        """Record a pending default icon when the selected icon differs from storage.

        @param index [int] Zero-based combo-box choice index.
        @return [None] Update the owned UI or state without returning a value."""
        icon = self.ui.icon_selector.itemData(index)
        if icon is None or self.currentTypeId is None:
            return
        saved = self.factory.scheme.getTypeIcon(self.currentTypeId)
        self.pendingIcon = None if icon == saved else icon
        logger.debug("Icon for type %s selected: '%s'", self.currentTypeId, icon)

    def isChanged(self) -> bool:
        """Check for pending header edits or an unsaved default icon.

        @return [bool] True when header settings or the icon have unsaved changes."""
        return self.tableModel.isChanged() or self.pendingIcon is not None

    def _fillTypesList(self):
        """Populate section choices using their full tree paths.

        @return [None] Update the owned UI or state without returning a value."""
        combo: QtWidgets.QComboBox = self.ui.typesList
        combo.blockSignals(True)
        combo.clear()
        self._addTypes(self.factory.getRootTypes(), [])
        combo.blockSignals(False)

    def _addTypes(self, types: ElDBScheme.Types, path: list):
        """Append section paths recursively to the type selector.

        @param types [Types] Section collection to traverse recursively.
        @param path [list[str]] Ancestor section names used to form display paths.
        @return [None] Update the owned UI or state without returning a value."""
        for theType in types:
            typePath = path + [theType.name]
            self.ui.typesList.addItem(" / ".join(typePath), theType.recId)
            if theType.isChildren():
                self._addTypes(theType.getChildren(), typePath)

    def onTypeSelected(self, index):
        """Handle section changes, offering to save or discard pending edits.

        @param index [int] Zero-based combo-box choice index.
        @return [None] Update the owned UI or state without returning a value."""
        typeId = self.ui.typesList.itemData(index)
        if typeId is None or typeId == self.currentTypeId:
            return
        if self.isChanged():
            answer = QMessageBox.question(
                self, translate("PartsDB", 'Unsaved changes'),
                translate("PartsDB", 'Save header and icon changes for the current type?'),
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
                if not self.onSave():
                    combo = self.ui.typesList
                    combo.blockSignals(True)
                    combo.setCurrentIndex(combo.findData(self.currentTypeId))
                    combo.blockSignals(False)
                    return
        self._load(typeId)

    def _load(self, typeId):
        """Load settings and the default icon for one section.

        @param typeId [int, None] Section ID; None selects a fallback only in loadData.
        @return [None] Update the owned UI or state without returning a value."""
        logger.debug("Load data for Type id %s", typeId)
        self.currentTypeId = typeId
        self.tableModel.load(typeId)
        self._showTypeIcon(typeId)

    def loadData(self, typeId=None):
        """Select the requested section, falling back to the first available section.

        @param typeId [int, None] Section ID; None selects a fallback only in loadData.
        @return [None] Update the owned UI or state without returning a value."""
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

    def accept(self):
        """Validate and save pending changes before accepting the dialog.

        @return [None] Update the owned UI or state without returning a value."""
        if self.onSave():
            super().accept()

    def onSave(self):
        """Require a key field, persist edited settings and emit update signals.

        @return [bool] True after saving, False when key validation fails."""
        logger.debug("Save button pressed.")
        key_column = self.tableModel.columnsList.index('is_key')
        if self.tableModel.rows and not any(row[key_column][TBL_VAL] for row in self.tableModel.dataAr):
            QMessageBox.warning(self, translate('PartsDB', 'Key value'),
                                translate('PartsDB', 'Select at least one key column.'))
            return False

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
        return True
