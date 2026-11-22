"""Catalog SI unit editors and file-backed basic type icons use temporary references."""
import tempfile
import unittest
from pathlib import Path
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QComboBox, QTableView
from ElData.ElDBScheme import DBFactory, ELEMENT_FLD_NAMES
from ElData.ElDBDataUnits import UnitsDataStore
from ElPartsTable import PartsTableModel, PartUnitDelegate
from ElUnitsDialog import UnitsDialog
from ElCommonUI import IconCellDelegate
import ElCommon

from tests.qt_support import application

app=application()


class CatalogSiEditingTests(unittest.TestCase):
    """Verify dimension-specific selectors, automatic conversion and explicit icon seeding.

    @attr factory [DBFactory] Disposable test catalog.
    """

    def setUp(self):
        """Create a clean catalog and arrange resource-aware Qt widgets.

        @return [None] Register connection and temporary directory cleanup.
        """
        folder=tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.factory=DBFactory(str(Path(folder.name)/'catalog.sqlite'))
        self.addCleanup(self.factory.disconnect)

    def test_creation_editing_blank_and_unknown_units_keep_reduced_fields_consistent(self):
        """Convert scaled values to the canonical dimension on both creation and editing.

        @return [None] Verify kiloohms, numeric edits, canonical unit correction and clearing.
        """
        section=self.factory.appendType('Resistors',None,3)
        part=self.factory.createPart(section,{'part_num':'R','value':4.7,'units':'кОм'})
        self.assertAlmostEqual(part['reduced_val'],4700)
        self.assertEqual(part['reduced_val_units'],'R')
        model=PartsTableModel(self.factory,section)
        def edit(field,value):
            """Commit a field through the real catalog model.

            @param field [str] Existing catalog field.
            @param value [str] Editor text.
            @return [None] Assert successful persistence.
            """
            self.assertTrue(model.setData(model.index(0,ELEMENT_FLD_NAMES.index(field)-2),value,Qt.ItemDataRole.EditRole))
        edit('value','10')
        self.assertEqual(model.parts[0]['reduced_val'],10000)
        edit('units','мОм')
        self.assertEqual(model.parts[0]['reduced_val'],10000000)
        edit('units','mR')
        self.assertEqual(model.parts[0]['reduced_val'],.01)
        edit('reduced_val_units','V')
        self.assertEqual(model.parts[0]['reduced_val_units'],'R')
        edit('value','')
        self.assertIsNone(model.parts[0]['reduced_val'])
        edit('value','10')
        edit('units','')
        self.assertIsNone(model.parts[0]['reduced_val'])
        loaded=self.factory.scheme.loadPart(part.id)
        self.assertIsNone(loaded[ELEMENT_FLD_NAMES.index('reduced_val')])

    def test_unit_combo_contains_only_its_dimension_and_has_text_fallback(self):
        """Offer a base unit and every multiplier only for sections with assigned SI units.

        @return [None] Verify resistance choices exclude farads and generic types keep free text.
        """
        section=self.factory.appendType('R',None,3)
        self.factory.createPart(section,{'part_num':'R','value':1,'units':'R'})
        model=PartsTableModel(self.factory,section)
        view=QTableView()
        self.addCleanup(view.close)
        delegate=PartUnitDelegate(view)
        index=model.index(0,ELEMENT_FLD_NAMES.index('units')-2)
        editor=delegate.createEditor(view,None,index)
        self.assertIsInstance(editor,QComboBox)
        choices=[editor.itemText(i) for i in range(editor.count())]
        self.assertIn('R',choices)
        self.assertIn('kR',choices)
        self.assertNotIn('F',choices)
        editor.setCurrentText('kR')
        delegate.setModelData(editor,model,index)
        self.assertEqual(model.parts[0]['reduced_val'],1000)

    def test_icon_paths_are_files_and_leftmost_cells_use_the_shared_delegate(self):
        """Assign file icons explicitly and render them through the common icon delegate.

        @return [None] Verify installed paths, empty defaults, column order and resource removal.
        """
        from PyQt6.QtCore import QFile
        store=UnitsDataStore(self.factory.scheme)
        self.assertTrue(all(not row[3] for row in store.basicTypes()))
        data_path=Path(self.factory.db_file).parent
        installed=ElCommon.installBasicTypeIcons(str(data_path),str(Path(__file__).resolve().parents[1]/'qt'/'el_icons'))
        self.assertGreater(store.assignDefaultIcons(installed),10)
        types={row[1]:row for row in store.basicTypes()}
        expected=str((data_path/'el_icons'/'resistor.png').resolve())
        self.assertEqual(types['Resistor'][3],expected)
        self.assertFalse(QIcon(expected).isNull())
        self.assertFalse(QFile.exists(':/basic-components/resistor.png'))
        dialog=UnitsDialog(self.factory.scheme)
        self.addCleanup(dialog.close)
        self.assertEqual(dialog.ui.b_types_tbl.horizontalHeader().visualIndex(3),0)
        row=next(i for i in range(dialog.typesModel.rowCount()) if dialog.typesModel.item(i,1).text()=='Resistor')
        index=dialog.typesModel.index(row,3)
        delegate=dialog.ui.b_types_tbl.itemDelegateForColumn(3)
        self.assertIsInstance(delegate,IconCellDelegate)
        self.assertEqual(delegate.imagePath(index),expected)
        self.assertIsNone(delegate.defaultIcons)
