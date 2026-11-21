"""Review imported data and the repeat-import delta before a database write."""
from types import SimpleNamespace

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QAbstractItemView, QDialog, QDialogButtonBox, QHeaderView,
                             QLabel, QPlainTextEdit, QTableWidget, QTableWidgetItem, QVBoxLayout)
from ElTranslations import TranslatedDialogMixin
from ElWindowTexts import importPreviewTexts


class ImportPreview(TranslatedDialogMixin, QDialog):
    """Preview imported components and their changes before database persistence.

    @attr project [ImportedProject] Validated import result.
    @attr changes [ImportChanges] Added, changed and removed references.
    @attr ui [SimpleNamespace] Summary, component table, warnings and acceptance controls."""
    def __init__(self, project, changes, parent=None):
        """Build a read-only component preview, warnings and confirmation controls.

        @param project [ImportedProject, Project] Imported preview data or saved project card, as required by the controller.
        @param changes [ImportChanges] Added, changed and removed component references.
        @param parent [QWidget, QObject, None] Qt owner of the created object.
        @return [None] Update the owned UI or state without returning a value."""
        super().__init__(parent)
        self.project = project
        self.changes = changes
        self.ui = SimpleNamespace()
        self.resize(1050, 620)
        layout = QVBoxLayout(self)
        self.ui.summary = QLabel(self)
        self.ui.summary.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.ui.summary)
        self.ui.table = QTableWidget(len(project.components) + len(changes.removed), 7, self)
        self.ui.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.ui.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.ui.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.ui.table)
        self.ui.warnings = QPlainTextEdit(self)
        self.ui.warnings.setReadOnly(True)
        self.ui.warnings.setMaximumHeight(100)
        self.ui.warnings.setPlainText('\n'.join(f'{w.code}: {w.message}' for w in project.warnings))
        self.ui.warnings.setVisible(bool(project.warnings))
        layout.addWidget(self.ui.warnings)
        self.ui.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel, self)
        self.ui.buttons.accepted.connect(self.accept)
        self.ui.buttons.rejected.connect(self.reject)
        layout.addWidget(self.ui.buttons)
        self.retranslate()

    def retranslate(self):
        """Refresh the preview captions and state labels while keeping imported data.

        @return [None] Update the owned UI or state without returning a value."""
        importPreviewTexts(self)
