"""Qt translation catalogs and application-wide language switching."""
from pathlib import Path

from PyQt6.QtCore import QObject, QCoreApplication, QLocale, QTranslator, QLibraryInfo, QEvent, pyqtSignal
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QApplication
from constants import CONFIG_LANGUAGE
import ElLogger

translate = QCoreApplication.translate
logger = ElLogger.setLogger(__name__)
CATALOG_DIR = Path(__file__).resolve().parent / "translations"
LANGUAGES = ("system", "en", "ru")


class TranslatedDialogMixin:
    """Apply window texts on language changes without rebuilding models or clearing edits."""
    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.LanguageChange and hasattr(self, "ui"):
            self.retranslate()

    def retranslate(self):
        raise NotImplementedError("Dialogs must apply their window texts")


class TranslatedAction(QAction):
    """An action retains its source strings so existing menus can be retranslated."""
    def __init__(self, source, parent=None):
        self.sourceText = source
        self.sourceStatusTip = ""
        super().__init__(translate("PartsDB", source), parent)

    def setStatusTip(self, source):
        self.sourceStatusTip = source
        super().setStatusTip(translate("PartsDB", source))

    def retranslate(self):
        self.setText(translate("PartsDB", self.sourceText))
        super().setStatusTip(translate("PartsDB", self.sourceStatusTip))


def defaultHeaderText(header, field):
    """Translate built-in titles for display only; never translate user-defined DB content."""
    from ElData.ElDBScheme import ELEMENT_FIELDS_DISPLAY
    text = header["display"]
    return translate("PartsDB", text) if text == ELEMENT_FIELDS_DISPLAY.get(field) else text


class LanguageManager(QObject):
    languageChanged = pyqtSignal()

    def __init__(self, app, config):
        super().__init__(app)
        self.app = app
        self.config = config
        self.preference = None
        self.language = None
        self.translators = []

    @classmethod
    def forApplication(cls, config):
        app = QApplication.instance()
        manager = getattr(app, "partsdbLanguageManager", None)
        if manager is None:
            manager = cls(app, config)
            app.partsdbLanguageManager = manager
        manager.config = config
        manager.setLanguage(config.get_value(CONFIG_LANGUAGE) or "system", persist=False)
        return manager

    @staticmethod
    def systemLanguage():
        for name in QLocale.system().uiLanguages():
            language = name.replace("_", "-").split("-")[0].lower()
            if language in ("en", "ru"):
                return language
        return "en"

    def setLanguage(self, preference, persist=True):
        if preference not in LANGUAGES:
            preference = "system"
        language = self.systemLanguage() if preference == "system" else preference
        if language != self.language:
            catalog = QTranslator(self)
            if not catalog.load(str(CATALOG_DIR / ("partsdb_" + language + ".qm"))):
                raise RuntimeError("Translation catalog is missing: partsdb_{}.qm".format(language))
            translators = []
            if language != "en":
                standard = QTranslator(self)
                # A bundled copy also supports PyInstaller, independent of its Qt hooks.
                if (standard.load(str(CATALOG_DIR / ("qtbase_" + language + ".qm")))
                        or standard.load("qtbase_" + language,
                                         QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath))):
                    translators.append(standard)
                else:
                    logger.warning("Qt standard translations unavailable for %s", language)
            translators.append(catalog)
            for old in reversed(self.translators):
                self.app.removeTranslator(old)
                old.deleteLater()
            self.translators = translators
            self.language = language
            for translator in translators:
                self.app.installTranslator(translator)
        self.preference = preference
        logger.info("Interface language: %s (preference: %s)", language, preference)
        if persist:
            self.config.set_value(CONFIG_LANGUAGE, preference)
            self.config.save()
        # QAction is not a widget: update both menu-bar and cached context-menu actions explicitly.
        actions = set()
        for widget in self.app.allWidgets():
            actions.update(widget.findChildren(TranslatedAction))
        for action in actions:
            action.retranslate()
        self.languageChanged.emit()

    def close(self):
        for translator in reversed(self.translators):
            self.app.removeTranslator(translator)
            translator.deleteLater()
        self.translators = []
        self.language = None
        if getattr(self.app, "partsdbLanguageManager", None) is self:
            del self.app.partsdbLanguageManager
