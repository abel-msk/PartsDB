"""Optional runtime context; project methods still take only source_uri."""
from .errors import ImportCancelled


class ImportContext:
    def __init__(self, emit=None, cancelled=None):
        self._emit = emit or (lambda event: None)
        self._cancelled = cancelled or (lambda: False)

    def check_cancelled(self):
        if self._cancelled():
            raise ImportCancelled('Import cancelled')

    def log(self, level, message):
        self._emit({'type': 'log', 'level': str(level), 'message': str(message)})

    def progress(self, completed, total=None, message=''):
        self.check_cancelled()
        self._emit({'type': 'progress', 'completed': completed, 'total': total,
                    'message': str(message)})
