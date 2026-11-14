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
    if (QApplication.platformName() == "offscreen"
            and kind == QtMsgType.QtWarningMsg and message in _OFFSCREEN_MESSAGES):
        return
    if _previous_handler is not None:
        _previous_handler(kind, context, message)
    else:
        print(message, file=sys.stderr)


_previous_handler = qInstallMessageHandler(_message_handler)


def application():
    app = QApplication.instance() or QApplication([])
    # Avoid resolving the unavailable default "Sans Serif" family on macOS.
    font = QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont)
    QFont.insertSubstitution("Sans Serif", font.family())
    app.setFont(font)
    return app
