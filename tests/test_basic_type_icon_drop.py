"""File-backed basic type icons use configured data_path and safe image drops."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from PyQt6.QtCore import Qt, QMimeData, QUrl, QPointF
from PyQt6.QtGui import QImage, QColor, QDragEnterEvent, QDragMoveEvent, QDropEvent
from PyQt6.QtWidgets import QWidget, QApplication, QMessageBox
from ElConfig import ElConfig
from ElData.ElDBScheme import DBFactory
from ElData.ElDBDataUnits import UnitsDataStore
from ElUnitsDialog import UnitsDialog
from ElCommonUI import IconCellDelegate
import ElCommon
from tests.qt_support import application

app=application()


class BasicTypeIconDropTests(unittest.TestCase):
    """Verify deferred PNG writes, correct cell identity and Save/Cancel ownership.

    @attr dialog [UnitsDialog] Reference editor on a disposable catalog.
    @attr root [Path] Temporary files containing separate config, DB and data locations.
    """

    def setUp(self):
        """Prepare a real visible table with a data directory distinct from the database folder.

        @return [None] Register Qt, connection and directory cleanup.
        """
        folder=tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root=Path(folder.name)
        (self.root/'database').mkdir()
        (self.root/'config').mkdir()
        self.factory=DBFactory(str(self.root/'database'/'catalog.sqlite'))
        self.addCleanup(self.factory.disconnect)
        self.owner=QWidget()
        self.addCleanup(self.owner.close)
        self.owner.config=ElConfig()
        self.owner.config.filename=str(self.root/'config'/'app.conf')
        self.owner.config.set_value('data_path','../data')
        self.dialog=UnitsDialog(self.factory.scheme,self.owner,data_path=str(self.root/'wrong-fallback'))
        self.addCleanup(self.dialog.close)
        self.dialog.show()
        app.processEvents()
        self.view=self.dialog.ui.b_types_tbl
        self.row=next(row for row in range(self.dialog.typesModel.rowCount())
                      if self.dialog.typesModel.item(row,1).text()=='Resistor')
        self.index=self.dialog.typesModel.index(self.row,3)
        self.view.scrollTo(self.index)
        app.processEvents()
        image=QImage(24,16,QImage.Format.Format_ARGB32)
        image.fill(QColor('red'))
        self.source=self.root/'external.jpg'
        self.assertTrue(image.save(str(self.source),'JPG'))

    def mime(self):
        """Build an external image-file drag.

        @return [QMimeData] Local JPEG URL with no internal Qt model roles.
        """
        mime=QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(self.source))])
        return mime

    def drop(self, process=True):
        """Send drag enter/drop through the actual viewport event filter.

        @param process [bool] False leaves the deferred image processing pending.
        @return [None] Assert that the correct icon cell accepts the image.
        """
        pos=self.view.visualRect(self.index).center()
        mime=self.mime()
        enter=QDragEnterEvent(pos,Qt.DropAction.CopyAction,mime,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(self.view.viewport(),enter)
        self.assertTrue(enter.isAccepted())
        event=QDropEvent(QPointF(pos),Qt.DropAction.CopyAction,mime,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(self.view.viewport(),event)
        self.assertTrue(event.isAccepted())
        if process:
            for _ in range(5):app.processEvents()

    def savedIcon(self):
        """Read the persisted resistor icon using the reference data boundary.

        @return [str, None] Existing BASIC_TYPES.icon value.
        """
        return next(row[3] for row in UnitsDataStore(self.factory.scheme).basicTypes() if row[1]=='Resistor')

    def test_drop_converts_to_png_in_configured_data_folder_and_save_persists_path(self):
        """Keep DB untouched until Save and store a standalone PNG inside data_path/el_icons.

        @return [None] Verify empty-cell handling, file conversion, persistence and shared delegate reuse.
        """
        self.assertIsInstance(self.dialog.iconDelegate,IconCellDelegate)
        self.assertEqual(self.dialog.iconDelegate.imagePath(self.index),'')
        self.drop()
        path=Path(self.index.data())
        self.assertEqual(path.parent,(self.root/'data'/'el_icons').resolve())
        self.assertEqual(path.suffix,'.png')
        self.assertFalse(QImage(str(path)).isNull())
        self.assertIsNone(self.savedIcon())
        self.dialog.accept()
        self.assertEqual(self.savedIcon(),str(path))
        self.dialog.close()
        self.assertTrue(path.is_file())

    def test_cancel_removes_only_new_files_and_ignores_delayed_drops(self):
        """Cancel a saved pending drop and a still-queued drop without changing existing icons.

        @return [None] Remove session-owned PNGs while preserving preexisting data files.
        """
        directory=self.root/'data'/'el_icons'
        directory.mkdir(parents=True)
        existing=directory/'existing.png'
        existing.write_bytes(self.source.read_bytes())
        self.drop()
        pending=Path(self.index.data())
        self.dialog.reject()
        self.assertFalse(pending.exists())
        self.assertTrue(existing.exists())
        self.assertIsNone(self.savedIcon())
        self.assertFalse(self.dialog.setDroppedIcon(self.index,QImage(str(self.source))))

    def test_replaced_pending_icon_is_removed_after_save(self):
        """Repeated drops create distinct files and Save retains only the referenced new image.

        @return [None] No previous image is overwritten by a subsequent drop.
        """
        self.drop()
        first=Path(self.index.data())
        self.drop()
        second=Path(self.index.data())
        self.assertNotEqual(first,second)
        self.assertTrue(first.exists())
        self.dialog.accept()
        self.assertFalse(first.exists())
        self.assertTrue(second.exists())
        self.assertEqual(self.savedIcon(),str(second))

    def test_removed_row_does_not_redirect_a_queued_drop(self):
        """Retain a persistent index so deletion cannot transfer a queued drop to another type.

        @return [None] Ignore an invalidated destination without creating an icon.
        """
        self.drop(process=False)
        self.dialog.typesModel.removeRow(self.row)
        for _ in range(5):app.processEvents()
        self.assertFalse((self.root/'data'/'el_icons').exists())

    def test_error_is_logged_and_cursor_restored_without_modifying_the_row(self):
        """Report an actual file write failure while keeping the previous icon value.

        @return [None] Verify an error is shown once and no partial model change remains.
        """
        with mock.patch.object(ElCommon,'saveIcon',side_effect=OSError('test write error')), \
                mock.patch.object(QMessageBox,'critical') as error, \
                self.assertLogs('ElCommonUI',level='ERROR'):
            self.drop()
        error.assert_called_once()
        self.assertIsNone(QApplication.overrideCursor())
        self.assertEqual(self.index.data(),'')
        self.assertIsNone(self.savedIcon())

    def test_seed_preserves_existing_files_and_reuses_installed_pngs(self):
        """Install source PNGs without overwriting a user's same-named image.

        @return [None] Repeated installation reuses the alternate path rather than duplicating files.
        """
        source=self.root/'seed'
        source.mkdir()
        image=QImage(str(self.source))
        image.save(str(source/'resistor.png'),'PNG')
        target=self.root/'data'/'el_icons'
        target.mkdir(parents=True)
        original=target/'resistor.png'
        original.write_bytes(b'user-owned contents')
        first=ElCommon.installBasicTypeIcons(str(self.root/'data'),str(source))
        again=ElCommon.installBasicTypeIcons(str(self.root/'data'),str(source))
        self.assertEqual(first,again)
        self.assertNotEqual(first['resistor.png'],str(original))
        self.assertEqual(original.read_bytes(),b'user-owned contents')
