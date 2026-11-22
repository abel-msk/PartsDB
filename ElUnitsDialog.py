"""Edit the SI units and basic component type references for the active database."""
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import QComboBox, QDialog, QMessageBox, QStyledItemDelegate

from ElConstants import UNIT_FIELDS, BASIC_TYPE_FIELDS, UNIT_REFERENCE_ROLE, UNIT_ALIAS_COLUMN, BASIC_TYPE_ICON_COLUMN
from ElData.ElDBDataUnits import UnitsDataStore
from ElTranslations import TranslatedDialogMixin, translate
from ElUnitsWnd import Ui_units_dialog
from ElWindowTexts import unitsDialogTexts, unitsDialogErrorText, iconDropErrorText
from ElCommonUI import IconCellDelegate
import ElCommon
from pathlib import Path

logger = ElCommon.setLogger(__name__)


class BaseUnitDelegate(QStyledItemDelegate):
    """Edit base unit references using names while storing database or temporary IDs.

    @attr dialog [UnitsDialog] Reference editor supplying the current unsaved base unit choices.
    """

    def __init__(self, dialog, parent):
        """Attach a reference selector to its table.

        @param dialog [UnitsDialog] Owner of the pending unit model.
        @param parent [QTableView] View owning the delegate.
        @return [None] Initialize the selector delegate.
        """
        super().__init__(parent)
        self.dialog = dialog

    def createEditor(self, parent, option, index):
        """Create a name selector from the currently available base units.

        @param parent [QWidget] Owner of the temporary editor.
        @param option [QStyleOptionViewItem] Qt cell styling information.
        @param index [QModelIndex] Reference cell being edited.
        @return [QComboBox] Selector with a blank choice and multiplier-1 unit choices.
        """
        editor = QComboBox(parent)
        # Native combo boxes can be transparent: cover the cell text while editing.
        editor.setAutoFillBackground(True)
        editor.addItem('', None)
        for unit_id, label in self.choices(index).items():
            editor.addItem(label, unit_id)
        return editor

    def choices(self, index):
        """Supply the current base unit choices.

        @param index [QModelIndex] Cell being edited; unused for unit references.
        @return [dict[int, str]] Available unit IDs and display labels.
        """
        return self.dialog.baseUnits()

    def setEditorData(self, editor, index):
        """Select the reference currently stored in the model.

        @param editor [QComboBox] Open base unit selector.
        @param index [QModelIndex] Cell storing an optional unit ID in UNIT_REFERENCE_ROLE.
        @return [None] Select the matching entry or the blank entry.
        """
        editor.setCurrentIndex(max(0, editor.findData(index.data(UNIT_REFERENCE_ROLE))))

    def setModelData(self, editor, model, index):
        """Write the selected ID and visible label into the reference cell.

        @param editor [QComboBox] Selector containing current pending unit choices.
        @param model [QStandardItemModel] Edited reference model.
        @param index [QModelIndex] Target reference cell.
        @return [None] Store the optional unit ID without parsing its visible label.
        """
        model.setData(index, editor.currentData(), UNIT_REFERENCE_ROLE)
        model.setData(index, editor.currentText(), Qt.ItemDataRole.DisplayRole)


class BasicTypeAliasDelegate(BaseUnitDelegate):
    """Edit alias targets using current non-alias types from the owner dialog.

    @attr dialog [UnitsDialog] Owner supplying pending type rows and temporary IDs.
    """

    def choices(self, index):
        """Exclude aliases and the edited row from available targets.

        @param index [QModelIndex] Alias cell being edited.
        @return [dict[int, str]] Canonical type IDs mapped to their current names.
        """
        own_id = index.model().item(index.row(), 0).data(Qt.ItemDataRole.UserRole)
        return {key: name for key, name in self.dialog.basicTypes().items() if key != own_id}


class UnitsDialog(TranslatedDialogMixin, QDialog):
    """Edit SI units and basic component types; commit on Save and discard on Cancel.

    @attr store [UnitsDataStore] Data access and validation for both references.
    @attr ui [Ui_units_dialog] Generated form widgets.
    @attr unitsModel [QStandardItemModel] Pending SI unit rows with immutable IDs.
    @attr typesModel [QStandardItemModel] Pending basic type rows with immutable IDs.
    @attr unitAliases [dict[int, tuple[str]]] Saved alternate spellings used to populate editable alias cells.
    @attr iconsDir [str] File-based icon directory inside configured data_path.
    @attr pendingIconFiles [set[str]] Owned new PNGs removed on cancellation or replacement.
    @attr nextTypeID [int] Next negative temporary ID for a newly added type.
    @attr nextUnitID [int] Next negative temporary ID for a newly added unit.
    @attr updatingReferences [bool] Guard against recursive reference label updates."""

    def __init__(self, database, parent=None, data_path=None):
        """Load both reference tables and connect their editing controls.

        @param database [DBScheme] Connected active database.
        @param data_path [str, None] Resolved factory data directory; parent config takes precedence.
        @param parent [QWidget, None] Qt owner of the dialog.
        @return [None] No value is returned."""
        super().__init__(parent)
        self.store = UnitsDataStore(database)
        self.unitAliases = self.store.aliases()
        fallback = data_path or str(Path(self.store.scheme.db.dbPath).expanduser().resolve().parent)
        self.dataPath = ElCommon.configuredDataPath(getattr(parent, 'config', None), fallback)
        self.iconsDir = ElCommon.basicTypeIconsDir(self.dataPath)
        self.pendingIconFiles = set()
        self.iconEditing = True
        logger.debug('Opening basic type editor: database=%s icons=%s', self.store.scheme.db.dbPath, self.iconsDir)
        self.nextUnitID = -1
        self.nextTypeID = -1
        self.updatingReferences = False
        self.ui = Ui_units_dialog()
        self.ui.setupUi(self)
        self.unitsModel = self.makeModel(self.ui.si_units_tbl, self.store.units())
        self.typesModel = self.makeModel(self.ui.b_types_tbl, self.store.basicTypes())
        self.ui.si_units_tbl.setItemDelegateForColumn(len(UNIT_FIELDS) - 1, BaseUnitDelegate(self, self.ui.si_units_tbl))
        self.iconDelegate = IconCellDelegate(self.ui.b_types_tbl, iconsDir=self.iconsDir,
                                            dropColumn=BASIC_TYPE_ICON_COLUMN, onDrop=self.setDroppedIcon)
        self.iconDelegate.dropFailed.connect(self.iconDropError)
        self.ui.b_types_tbl.setItemDelegateForColumn(BASIC_TYPE_ICON_COLUMN, self.iconDelegate)
        self.ui.b_types_tbl.verticalHeader().setDefaultSectionSize(64)
        header = self.ui.b_types_tbl.horizontalHeader()
        header.moveSection(header.visualIndex(3), 0)
        self.ui.b_types_tbl.setItemDelegateForColumn(4, BaseUnitDelegate(self, self.ui.b_types_tbl))
        self.ui.b_types_tbl.setItemDelegateForColumn(5, BasicTypeAliasDelegate(self, self.ui.b_types_tbl))
        self.unitsModel.itemChanged.connect(self.refreshReferences)
        self.unitsModel.rowsRemoved.connect(self.refreshReferences)
        self.typesModel.itemChanged.connect(self.refreshReferences)
        self.typesModel.rowsRemoved.connect(self.refreshReferences)
        self.refreshReferences()
        self.ui.add_unit_cmd.clicked.connect(self.addUnit)
        self.ui.del_unit_cmd.clicked.connect(self.deleteUnit)
        self.ui.add_type_cmd.clicked.connect(self.addType)
        self.ui.del_type_cmd.clicked.connect(self.deleteType)
        self.retranslate()
        self.ui.si_units_tbl.resizeColumnsToContents()
        self.ui.b_types_tbl.resizeColumnsToContents()
        self.ui.si_units_tbl.setColumnWidth(len(UNIT_FIELDS) - 1, 260)
        self.ui.si_units_tbl.setColumnWidth(UNIT_ALIAS_COLUMN, 260)
        self.ui.b_types_tbl.setColumnWidth(len(BASIC_TYPE_FIELDS) - 1, 260)
        self.ui.b_types_tbl.setColumnWidth(3, 64)

    def makeModel(self, view, rows):
        """Attach and populate an editable reference model with its ID column hidden.

        @param view [QTableView] Target reference table widget.
        @param rows [list[tuple]] Reference rows with the persistent ID in column zero.
        @return [QStandardItemModel] Model owned by this dialog."""
        model = QStandardItemModel(self)
        view.setModel(model)
        for row in rows:
            self.appendRow(model, row)
        view.setColumnHidden(0, True)
        return model

    def appendRow(self, model, row):
        """Append an editable reference row while keeping its ID read-only.

        @param model [QStandardItemModel] Target reference model.
        @param row [tuple] ID followed by field values; ID None assigns a negative temporary ID for an unsaved row.
        @return [None] No value is returned."""
        unit_row = len(row) in (len(UNIT_FIELDS), len(UNIT_FIELDS) + 1)
        if row[0] is None and unit_row:
            row = (self.nextUnitID, *row[1:])
            self.nextUnitID -= 1
        if row[0] is None and len(row) == len(BASIC_TYPE_FIELDS):
            row = (self.nextTypeID, *row[1:])
            self.nextTypeID -= 1
        if unit_row and len(row) == len(UNIT_FIELDS):
            row = (*row, ', '.join(self.unitAliases.get(row[0], ())))
        items = [QStandardItem('' if value is None else str(value)) for value in row]
        if row[0] is not None and row[0] < 0:
            items[0].setText('')
        reference_columns = (6,) if unit_row else (4, 5)
        for column in reference_columns:
            items[column].setData(row[column], UNIT_REFERENCE_ROLE)
        items[0].setData(row[0], Qt.ItemDataRole.UserRole)
        items[0].setEditable(False)
        model.appendRow(items)

    def addUnit(self):
        """Append an unsaved unit with multiplier 1 and start editing its name.

        @return [None] No value is returned."""
        self.appendRow(self.unitsModel, (None, '', '', '', '', 1.0, None))
        self.editNewRow(self.ui.si_units_tbl, self.unitsModel)

    def addType(self):
        """Append an unsaved basic type and start editing its name.

        @return [None] No value is returned."""
        self.appendRow(self.typesModel, (None, '', '', '', None, None))
        self.editNewRow(self.ui.b_types_tbl, self.typesModel)

    def editNewRow(self, view, model):
        """Focus and edit the last row name cell.

        @param view [QTableView] View using the supplied model.
        @param model [QStandardItemModel] Nonempty model with a name column at index 1.
        @return [None] No value is returned."""
        index = model.index(model.rowCount() - 1, 1)
        view.setCurrentIndex(index)
        view.edit(index)

    def deleteUnit(self):
        """Request confirmed removal of the selected pending SI unit.

        @return [None] No value is returned."""
        self.deleteRow(self.ui.si_units_tbl, self.unitsModel)

    def deleteType(self):
        """Request confirmed removal of the selected pending basic type.

        @return [None] No value is returned."""
        self.deleteRow(self.ui.b_types_tbl, self.typesModel)

    def deleteRow(self, view, model):
        """Remove the selected pending row only after affirmative confirmation.

        @param view [QTableView] View containing the current row.
        @param model [QStandardItemModel] Editable reference model attached to the view.
        @return [None] No value is returned."""
        index = view.currentIndex()
        if not index.isValid():
            return
        name = model.item(index.row(), 1).text()
        if QMessageBox.question(self, translate('UnitsDialog', 'Delete entry'),
                                translate('UnitsDialog', 'Delete {}?').format(name),
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            model.removeRow(index.row())

    def rows(self, model, fields):
        """Collect pending reference values in database column order.

        @param model [QStandardItemModel] Reference model whose ID column stores the persistent ID.
        @param fields [tuple[str]] Ordered field names defining the number of columns.
        @return [list[tuple]] ID and field values; unsaved rows have negative temporary IDs."""
        return [(model.item(row, 0).data(Qt.ItemDataRole.UserRole),
                 *(model.item(row, col).data(UNIT_REFERENCE_ROLE) if fields[col].endswith('_id')
                   else model.item(row, col).text() for col in range(1, len(fields))))
                for row in range(model.rowCount())]

    def aliasRows(self):
        """Collect editable alternate unit spellings without changing pending reference IDs.

        @return [dict[int, list[str]]] Saved or temporary unit IDs mapped to comma/semicolon-separated aliases.
        """
        result = {}
        for row in range(self.unitsModel.rowCount()):
            unit_id = self.unitsModel.item(row, 0).data(Qt.ItemDataRole.UserRole)
            text = self.unitsModel.item(row, UNIT_ALIAS_COLUMN).text().replace(';', ',')
            result[unit_id] = [marker.strip() for marker in text.split(',') if marker.strip()]
        return result

    def baseUnits(self):
        """Collect valid pending base units, including unsaved rows with temporary IDs.

        @return [dict[int, str]] Unit IDs mapped to bilingual names and English markers.
        """
        choices = {}
        for row in range(self.unitsModel.rowCount()):
            try:
                factor = float(self.unitsModel.item(row, 5).text().replace(',', '.'))
            except ValueError:
                continue
            if factor == 1 and self.unitsModel.item(row, 6).data(UNIT_REFERENCE_ROLE) is None:
                unit_id = self.unitsModel.item(row, 0).data(Qt.ItemDataRole.UserRole)
                name = self.unitsModel.item(row, 1).text()
                if name:
                    choices[unit_id] = '{} / {} ({})'.format(name, self.unitsModel.item(row, 2).text(),
                                                           self.unitsModel.item(row, 3).text())
        return choices

    def basicTypes(self):
        """Collect named non-alias types, including unsaved rows.

        @return [dict[int, str]] Persistent or temporary type IDs mapped to names.
        """
        return {self.typesModel.item(row, 0).data(Qt.ItemDataRole.UserRole): self.typesModel.item(row, 1).text()
                for row in range(self.typesModel.rowCount())
                if self.typesModel.item(row, 5).data(UNIT_REFERENCE_ROLE) is None
                and self.typesModel.item(row, 1).text().strip()}

    def refreshReferences(self, *args):
        """Refresh labels after a reference edit without altering stored reference IDs.

        @param args [tuple] Qt model-change arguments; their values are not used.
        @return [None] Show names for valid links and IDs for unresolved links.
        """
        if self.updatingReferences:
            return
        self.updatingReferences = True
        try:
            choices = self.baseUnits()
            for model, column, choices in ((self.unitsModel, 6, choices), (self.typesModel, 4, choices),
                                           (self.typesModel, 5, self.basicTypes())):
                for row in range(model.rowCount()):
                    item = model.item(row, column)
                    unit_id = item.data(UNIT_REFERENCE_ROLE)
                    item.setText(choices.get(unit_id, str(unit_id)) if unit_id is not None else '')
        finally:
            self.updatingReferences = False

    def accept(self):
        """Validate and commit both references atomically, then close the dialog.

        Commit the active cell editor first; report validation errors and keep the dialog open.

        @return [None] No value is returned."""
        # Transfer the active cell editor's text to its model before reading it.
        self.ui.buttonBox.setFocus()
        try:
            self.store.save(self.rows(self.unitsModel, UNIT_FIELDS), self.rows(self.typesModel, BASIC_TYPE_FIELDS), self.aliasRows())
        except Exception as exc:
            QMessageBox.critical(self, translate('UnitsDialog', 'Cannot save reference data'), unitsDialogErrorText(str(exc)))
            return
        retained = {row[3] for row in self.store.basicTypes() if row[3]}
        self.discardPendingIcons(retained)
        self.iconEditing = False
        logger.debug('Basic type editor saved: retained_icons=%s', len(retained))
        super().accept()

    def setDroppedIcon(self, index, image):
        """Save an owned image to a unique PNG and update only the pending icon cell.

        @param index [QModelIndex] Existing BASIC_TYPES.icon cell in the pending model.
        @param image [QImage] Decoded owned drop image.
        @return [bool] True updates the pending path; closed editors reject delayed drops.
        """
        if not self.iconEditing or not index.isValid() or index.column() != BASIC_TYPE_ICON_COLUMN:
            logger.debug('Ignoring delayed icon drop: editing=%s valid=%s', self.iconEditing, index.isValid())
            return False
        name = self.typesModel.item(index.row(), 1).text()
        filename = ElCommon.saveIcon(image, self.iconsDir, name)
        path = str(Path(self.iconsDir, filename).resolve())
        self.pendingIconFiles.add(path)
        self.typesModel.setData(index, path, Qt.ItemDataRole.EditRole)
        self.iconDelegate.clearCache()
        logger.debug('Basic type icon pending: type=%s row=%s path=%s', name, index.row(), path)
        return True

    def iconDropError(self, message):
        """Show an actionable image-drop error after restoring the normal cursor.

        @param message [str] Diagnostic emitted by the shared delegate.
        @return [None] Keep the editor and all previously saved paths available.
        """
        logger.debug('Basic type icon error: %s', message)
        QMessageBox.critical(self, translate('UnitsDialog', 'Cannot save reference data'), iconDropErrorText(message))

    def discardPendingIcons(self, retained=()):
        """Remove only files created by this dialog and not retained by a successful Save.

        @param retained [collection[str]] Paths referenced by the committed basic type rows.
        @return [None] Preserve existing files and retained icons, clear pending ownership.
        """
        for path in self.pendingIconFiles - set(retained):
            try:
                Path(path).unlink(missing_ok=True)
                logger.debug('Removed unused pending basic type icon: %s', path)
            except OSError:
                logger.exception('Cannot remove pending basic type icon: %s', path)
        self.pendingIconFiles.clear()

    def reject(self):
        """Discard pending reference edits and PNGs created during this editing session.

        @return [None] Keep all previously stored database rows and image files unchanged.
        """
        self.iconEditing = False
        self.discardPendingIcons()
        logger.debug('Basic type editor cancelled')
        super().reject()

    def retranslate(self):
        """Update localized captions and headers while retaining pending edits.

        @return [None] No value is returned."""
        unitsDialogTexts(self)
