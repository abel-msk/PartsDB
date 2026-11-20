"""Proportional table expansion with database-backed minimum column widths."""
from PyQt6.QtCore import QObject, QEvent, QTimer
from PyQt6 import sip
from PyQt6.QtWidgets import QHeaderView
from ElConstants import PROJECT_TABLE_FIELDS, PROJECT_TABLE_DEFAULT_WIDTH
from ElData import ElDBDataProj


class ProjectTableLayout(QObject):
    """Keep user widths separate from automatic expansion; holds view, factory and stable table ID."""

    def __init__(self, view, factory, table_name):
        """Bind layout. @param view [QTableView]; factory [DBFactory]; table_name [str] stable identifier."""
        super().__init__(view)
        self.view, self.factory, self.table_name = view, factory, table_name
        self.minimums = {}
        self.applying = False
        self.dragging = False
        self.dirty = False
        self.pending = False
        header = view.horizontalHeader()
        self.headerViewport = header.viewport()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(False)
        header.sectionResized.connect(self.sectionResized)
        view.viewport().installEventFilter(self)
        header.viewport().installEventFilter(self)
        self.setFactory(factory)

    def setFactory(self, factory):
        """Read widths for the selected database. @param factory [DBFactory]."""
        self.factory = factory
        self.minimums = ElDBDataProj.columnWidths(factory, self.table_name)
        self.dragging = self.dirty = False
        self.schedule()

    def schedule(self):
        """Apply after Qt has updated viewport geometry; takes no parameters."""
        if not self.pending:
            self.pending = True
            QTimer.singleShot(0, self.apply)

    def apply(self):
        """Expand in saved proportions; shrink only to saved widths; takes no parameters."""
        self.pending = False
        if sip.isdeleted(self.view) or self.dragging:
            return
        header = self.view.horizontalHeader()
        columns = [(index, field) for index, field in enumerate(PROJECT_TABLE_FIELDS)
                   if index < header.count() and not header.isSectionHidden(index)]
        if not columns:
            return
        bases = [max(header.minimumSectionSize(), self.minimums.get(field, PROJECT_TABLE_DEFAULT_WIDTH))
                 for _, field in columns]
        available = max(sum(bases), self.view.viewport().width())
        # Cumulative rounding gives the viewport's exact width, without one-pixel overflow.
        total, used, accumulated = sum(bases), 0, 0
        self.applying = True
        try:
            for (index, _), base in zip(columns, bases):
                accumulated += base
                boundary = round(available * accumulated / total)
                header.resizeSection(index, max(base, boundary - used))
                used = boundary
        finally:
            self.applying = False

    def sectionResized(self, index, old_size, new_size):
        """Track user gestures only. @param index, old_size, new_size [int] header resize values."""
        if self.dragging and not self.applying:
            self.dirty = True

    def saveUserWidths(self):
        """Persist current widths after a user gesture; automatic expansion never writes the DB."""
        header = self.view.horizontalHeader()
        self.minimums = {field: header.sectionSize(index)
                         for index, field in enumerate(PROJECT_TABLE_FIELDS) if index < header.count()}
        ElDBDataProj.saveColumnWidths(self.factory, self.table_name, self.minimums)
        self.dirty = False
        self.schedule()

    def eventFilter(self, watched, event):
        """Handle viewport geometry and user resize gestures. @param watched [QObject]; event [QEvent]."""
        if sip.isdeleted(self.view):
            return False
        if watched is self.headerViewport:
            if event.type() == QEvent.Type.MouseButtonPress:
                self.dragging = True
            elif event.type() == QEvent.Type.MouseButtonRelease:
                self.dragging = False
                if self.dirty:
                    self.saveUserWidths()
        elif event.type() in (QEvent.Type.Resize, QEvent.Type.Show):
            self.schedule()
        return super().eventFilter(watched, event)
