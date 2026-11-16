"""Plugin manager window, independent of generated Qt form code."""

from PyQt6.QtGui import QStandardItemModel
from PyQt6.QtWidgets import QDialog

from ElPluginsWnd import Ui_Dialog
from ElTranslations import TranslatedDialogMixin
from ElWindowTexts import pluginsDialogTexts


class PluginsDialog(TranslatedDialogMixin, QDialog):
    """Display the plugin manager shell until its backend is connected."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.ui = Ui_Dialog()
        self.ui.setupUi(self)
        self.pluginsModel = QStandardItemModel(self)
        self.ui.pl_list.setModel(self.pluginsModel)
        self.ui.pushButton.clicked.connect(self.reject)

        # Installation and plugin actions need the future manager backend.
        self.ui.pl_add_file_cmd.setEnabled(False)
        self.ui.pl_delete.setEnabled(False)
        self.ui.pl_data_frame.setEnabled(False)
        self.ui.splitter.setStretchFactor(0, 1)
        self.ui.splitter.setStretchFactor(1, 2)
        self.retranslate()

    def retranslate(self):
        pluginsDialogTexts(self)
