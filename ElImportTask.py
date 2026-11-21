"""Run blocking plugin work away from Qt's GUI and SQLite connection."""
import threading

from PyQt6.QtCore import QEventLoop, QThread, Qt, pyqtSignal
from PyQt6.QtWidgets import QProgressDialog

from ElWindowTexts import importProgressTexts
from ElTranslations import TranslatedDialogMixin


class ImportProgressDialog(TranslatedDialogMixin, QProgressDialog):
    """Display localized progress for imports or installations while preserving task progress.

    @attr ui [ImportProgressDialog] Self-reference used by the translation mixin.
    @attr installing [bool] True for installation, where cancellation is unavailable.
    """

    def __init__(self, parent=None, installing=False):
        """Build a progress window for the selected operation.

        @param parent [QWidget, None] Owner of the progress dialog.
        @param installing [bool] True for plugin installation; False for project import.
        @return [None] Initialize operation-specific localized captions.
        """
        super().__init__(parent)
        self.ui = self
        self.installing = installing
        self.retranslate()

    def retranslate(self):
        """Update title, progress label and cancellation caption for the active language.

        @return [None] Keep the current progress range and value.
        """
        importProgressTexts(self, self.installing)


class ImportTask(QThread):
    """Run a blocking plugin operation in a Qt worker thread.

    @attr function [Callable] Operation accepting a cancellation event and progress callback.
    @attr cancel [threading.Event] Cooperative cancellation flag."""
    succeeded = pyqtSignal(object)
    failed = pyqtSignal(object)
    progress = pyqtSignal(object)

    def __init__(self, function, parent):
        """Store the blocking operation and create its cancellation flag.

        @param function [Callable] Blocking operation accepting a cancellation event and progress callback.
        @param parent [QWidget, QObject, None] Qt owner of the created object.
        @return [None] Update the owned UI or state without returning a value."""
        super().__init__(parent)
        self.function = function
        self.cancel = threading.Event()

    def run(self):
        """Execute the operation and emit either its result or exception.

        @return [None] Update the owned UI or state without returning a value."""
        try:
            self.succeeded.emit(self.function(self.cancel, self.progress.emit))
        except Exception as exc:
            self.failed.emit(exc)


def run_import_task(parent, function, installing=False):
    """Run a blocking plugin operation with localized progress while keeping Qt responsive.

    @param parent [QWidget] Owner of the progress window and worker thread.
    @param function [Callable] Operation accepting a cancellation event and progress callback.
    @param installing [bool] True for a non-cancellable installation; False for an import.
    @return [object] Operation result; worker failures are raised in the GUI thread.
    """
    progress = ImportProgressDialog(parent, installing)
    progress.setWindowModality(Qt.WindowModality.WindowModal)
    progress.setMinimumDuration(0)
    progress.setRange(0, 0)
    task = ImportTask(function, parent)
    result, errors = [], []
    task.succeeded.connect(result.append)
    task.failed.connect(errors.append)
    progress.canceled.connect(task.cancel.set)

    def update(event):
        """Apply a worker progress event without changing the operation captions.

        @param event [dict] Event with type and optional total/completed integer fields.
        @return [None] Update the range/value or use indeterminate progress.
        """
        if event.get('type') == 'progress':
            total, completed = event.get('total'), event.get('completed')
            if type(total) is int and total > 0 and type(completed) is int:
                progress.setRange(0, total)
                progress.setValue(min(max(completed, 0), total))
            else:
                progress.setRange(0, 0)

    task.progress.connect(update)
    loop = QEventLoop(parent)
    task.finished.connect(loop.quit)
    progress.show()
    task.start()
    loop.exec()
    task.wait()
    progress.close()
    task.deleteLater()
    if errors:
        raise errors[0]
    return result[0]
