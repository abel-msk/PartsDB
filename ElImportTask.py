"""Run blocking plugin work away from Qt's GUI and SQLite connection."""
import threading

from PyQt6.QtCore import QEventLoop, QThread, Qt, pyqtSignal
from PyQt6.QtWidgets import QProgressDialog

from ElWindowTexts import importProgressTexts


class ImportTask(QThread):
    succeeded = pyqtSignal(object)
    failed = pyqtSignal(object)
    progress = pyqtSignal(object)

    def __init__(self, function, parent):
        super().__init__(parent)
        self.function = function
        self.cancel = threading.Event()

    def run(self):
        try:
            self.succeeded.emit(self.function(self.cancel, self.progress.emit))
        except Exception as exc:
            self.failed.emit(exc)


def run_import_task(parent, function, installing=False):
    progress = QProgressDialog(parent)
    progress.setWindowModality(Qt.WindowModality.WindowModal)
    progress.setMinimumDuration(0)
    progress.setRange(0, 0)
    importProgressTexts(progress, installing)
    if installing:
        progress.setCancelButton(None)
    task = ImportTask(function, parent)
    result, errors = [], []
    task.succeeded.connect(result.append)
    task.failed.connect(errors.append)
    progress.canceled.connect(task.cancel.set)

    def update(event):
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
