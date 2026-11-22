"""Responsive progress/log window for explicit catalog matching passes."""
import ElCommon
from PyQt6.QtWidgets import QDialog, QDialogButtonBox
from ElLogWnd import Ui_Dialog
from ElTranslations import TranslatedDialogMixin, translate
from ElWindowTexts import matchingLogTexts


logger = ElCommon.setLogger(__name__)


class MatchingLogDialog(TranslatedDialogMixin, QDialog):
    """Keep matching progress and plain-text results visible after a pass completes.

    @attr running [bool] Whether scheduled matching steps may continue.
    @attr ui [Ui_Dialog] Generated ElLogWnd layout.
    """

    def __init__(self, total, parent=None):
        """Prepare progress and cancellation controls.

        @param total [int] Number of grouped components to process.
        @param parent [QWidget, None] Owning project window.
        @return [None] Initialize an empty read-only log.
        """
        super().__init__(parent)
        self.ui = Ui_Dialog()
        self.ui.setupUi(self)
        self.running = True
        self.ui.progressBar.setRange(0, max(1, total))
        self.ui.progressBar.setValue(0)
        self.ui.buttonBox.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        self.retranslate()

    def record(self, progress, component, candidates):
        """Append one ID-free result and advance progress.

        @param progress [int] Number of completed component groups.
        @param component [dict] Group reference, Value and quantity.
        @param candidates [list[CatalogMatch]] Catalog candidates found in this step.
        @return [None] Display plain text, including an explicit missing-result line.
        """
        result = (translate('MatchingLog', 'Found: {}').format(', '.join(item.key_text for item in candidates))
                  if candidates else translate('MatchingLog', 'No match'))
        self.ui.plainTextEdit.appendPlainText('{} | {} | {}: {} | {}'.format(
            component['reference'], component['value_raw'], translate('PluginWorkflow', 'Quantity'),
            component['quantity'], result))
        logger.debug('Matching result: progress=%s/%s reference=%s value=%r quantity=%s candidates=%s',
                     progress, self.ui.progressBar.maximum(), component['reference'],
                     component['value_raw'], component['quantity'], [item.part_id for item in candidates])
        self.ui.progressBar.setValue(progress)

    def finish(self, cancelled=False):
        """Finish or cancel the pass while keeping the accumulated log available.

        @param cancelled [bool] True for an interrupted pass.
        @return [None] Enable Close and stop future steps.
        """
        logger.debug('Matching pass finished: cancelled=%s completed=%s total=%s',
                     cancelled, self.ui.progressBar.value(), self.ui.progressBar.maximum())
        self.running = False
        self.ui.plainTextEdit.appendPlainText(translate('MatchingLog', 'Cancelled') if cancelled
                                             else translate('MatchingLog', 'Completed'))
        if not cancelled:
            self.ui.progressBar.setValue(self.ui.progressBar.maximum())
        self.ui.buttonBox.button(QDialogButtonBox.StandardButton.Ok).setEnabled(True)
        self.ui.buttonBox.button(QDialogButtonBox.StandardButton.Cancel).setEnabled(False)

    def fail(self, message):
        """Report a failed step without discarding previous results.

        @param message [str] Exception diagnostic rendered as plain text.
        @return [None] Finish the pass and preserve the error log.
        """
        self.ui.plainTextEdit.appendPlainText(translate('MatchingLog', 'Error: {}').format(message))
        self.finish(cancelled=True)

    def reject(self):
        """Cancel scheduled steps and retain the log until Close is pressed.

        @return [None] A second close action dismisses the completed dialog.
        """
        if self.running:
            self.finish(cancelled=True)
        else:
            super().reject()

    def retranslate(self):
        """Refresh captions without changing existing log lines.

        @return [None] Apply the current application language.
        """
        matchingLogTexts(self)
