"""Small catalog dialogs with translated labels and preserved input on language changes."""
from PyQt6.QtWidgets import (QDialog, QDialogButtonBox, QFormLayout, QLineEdit,
                             QComboBox, QLabel)
from ElTranslations import TranslatedDialogMixin
from ElWindowTexts import sectionDialogTexts, partValuesDialogTexts


class SectionDialog(TranslatedDialogMixin, QDialog):
    """Edit a section name and basic type while retaining user input across language changes.

    @attr ui [SectionDialog] Self-reference for translation events.
    @attr nameEdit [QLineEdit] Pending section name.
    @attr typeCombo [QComboBox] Basic type names and persistent IDs.
    @attr buttons [QDialogButtonBox] Acceptance/cancellation controls."""

    def __init__(self, parent, basic_types, name='', basic_type_id=1):
        """Build editors from a section name and available basic type records.

        @param parent [QWidget, QObject, None] Qt owner of the created object.
        @param basic_types [list[tuple]] Basic type records: ID, name, designator and optional icon.
        @param name [str] Initial section name, preserved as user data.
        @param basic_type_id [int] Initial basic type ID; unknown IDs fall back to the first choice.
        @return [None] Update the owned UI or state without returning a value."""
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
        """Enable acceptance only when the pending name is nonempty.

        @return [None] Update the owned UI or state without returning a value."""
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(bool(self.nameEdit.text().strip()))

    def retranslate(self):
        """Refresh section captions without changing reference names or input.

        @return [None] Update the owned UI or state without returning a value."""
        sectionDialogTexts(self)


class PartValuesDialog(TranslatedDialogMixin, QDialog):
    """Collect configured key values for a new part.

    @attr headers [list[Header]] Ordered key metadata.
    @attr editors [dict[str, QLineEdit]] Pending values by field name.
    @attr labels [dict[str, QLabel]] Localized field labels.
    @attr buttons [QDialogButtonBox] Acceptance/cancellation controls."""

    def __init__(self, parent, headers):
        """Build one editor for each configured key field.

        @param parent [QWidget, QObject, None] Qt owner of the created object.
        @param headers [list[Header]] Ordered metadata for the required key fields.
        @return [None] Update the owned UI or state without returning a value."""
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
        """Read all pending key values with surrounding whitespace removed.

        @return [dict[str, str]] Trimmed pending key values."""
        return {field: editor.text().strip() for field, editor in self.editors.items()}

    def validate(self):
        """Enable acceptance only when every key field contains a value.

        @return [None] Update the owned UI or state without returning a value."""
        valid = bool(self.editors) and all(self.values().values())
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(valid)

    def retranslate(self):
        """Refresh the prompt and field captions while preserving values.

        @return [None] Update the owned UI or state without returning a value."""
        partValuesDialogTexts(self)
