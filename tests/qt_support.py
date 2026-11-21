"""Shared Qt setup for headless widget tests."""
import sys

from PyQt6.QtCore import QtMsgType, qInstallMessageHandler
from PyQt6.QtGui import QFont, QFontDatabase
from PyQt6.QtWidgets import QApplication

_OFFSCREEN_MESSAGES = {
    "This plugin does not support propagateSizeHints()",
    "This plugin does not support raise()",
}


def _message_handler(kind, context, message):
    # These window-manager operations are unavailable with the offscreen backend.
    """Filter expected offscreen warnings and forward other Qt diagnostic messages.

    @param kind [QtMsgType] Severity of the emitted Qt message.
    @param context [QMessageLogContext] Source context supplied by Qt.
    @param message [str] Diagnostic text supplied by Qt.
    @return [None] Updated captions or completed maintenance operation."""
    if (QApplication.platformName() == "offscreen"
            and kind == QtMsgType.QtWarningMsg and message in _OFFSCREEN_MESSAGES):
        return
    if _previous_handler is not None:
        _previous_handler(kind, context, message)
    else:
        print(message, file=sys.stderr)


_previous_handler = qInstallMessageHandler(_message_handler)


def application():
    """Get the shared Qt application with a valid platform font for widget tests.

    @return [QApplication] Requested translated values or collected metadata."""
    app = QApplication.instance() or QApplication([])
    # Avoid resolving the unavailable default "Sans Serif" family on macOS.
    font = QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont)
    QFont.insertSubstitution("Sans Serif", font.family())
    app.setFont(font)
    return app
