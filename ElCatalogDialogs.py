"""Small catalog dialogs with translated labels and preserved input on language changes."""
from PyQt6.QtWidgets import (QDialog, QDialogButtonBox, QFormLayout, QLineEdit,
                             QComboBox, QLabel)
from ElTranslations import TranslatedDialogMixin
from ElWindowTexts import sectionDialogTexts, partValuesDialogTexts


class SectionDialog(TranslatedDialogMixin, QDialog):
    """Edit a section name and reference type; stores the name editor and reference combo."""

    def __init__(self, parent, basic_types, name='', basic_type_id=1):
        """Prepare input. @param parent [QWidget]; basic_types [list[tuple]]; name [str]; basic_type_id [int]."""
        super().__init__(parent)
        self.ui = self
        self.nameEdit = QLineEdit(name, self)
        self.typeCombo = QComboBox(self)
        for key, title, designator, _ in basic_types:
            self.typeCombo.addItem(title, key)
        self.typeCombo.setCurrentIndex(max(0, self.typeCombo.findData(basic_type_id)))
        self.nameLabel = QLabel(self)
        self.typeLabel = QLabel(self)
        form = QFormLayout(self)
        form.addRow(self.nameLabel, self.nameEdit)
        form.addRow(self.typeLabel, self.typeCombo)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        form.addRow(self.buttons)
        self.nameEdit.textChanged.connect(self.validate)
        self.validate()
        self.retranslate()

    def validate(self):
        """Enable acceptance only for a nonempty section name; takes no parameters."""
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(bool(self.nameEdit.text().strip()))

    def retranslate(self):
        """Refresh section labels without changing reference names or user input."""
        sectionDialogTexts(self)


class PartValuesDialog(TranslatedDialogMixin, QDialog):
    """Collect all configured key values; stores header metadata and labeled editors."""

    def __init__(self, parent, headers):
        """Build one field per key. @param parent [QWidget]; headers [list[Header]] ordered keys."""
        super().__init__(parent)
        self.ui = self
        self.headers = headers
        self.editors = {}
        self.labels = {}
        form = QFormLayout(self)
        self.prompt = QLabel(self)
        form.addRow(self.prompt)
        for header in headers:
            field = header['field_name']
            editor = QLineEdit(self)
            self.editors[field] = editor
            self.labels[field] = QLabel(self)
            form.addRow(self.labels[field], editor)
            editor.textChanged.connect(self.validate)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        form.addRow(self.buttons)
        self.validate()
        self.retranslate()

    def values(self):
        """Return all key values. @return [dict[str,str]] trimmed, nonempty values."""
        return {field: editor.text().strip() for field, editor in self.editors.items()}

    def validate(self):
        """Require a value in every key editor; takes no parameters."""
        valid = bool(self.editors) and all(self.values().values())
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(valid)

    def retranslate(self):
        """Refresh prompt and displayed header labels while preserving editor content."""
        partValuesDialogTexts(self)
