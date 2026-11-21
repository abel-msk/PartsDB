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
    """Dispatch Qt language changes to handwritten window texts; stores no independent state."""
    def changeEvent(self, event):
        """Refresh window texts after a Qt language-change event.

        @param event [QEvent, QKeyEvent] Qt change or keyboard event delivered to the handler.
        @return [None] Update the owned UI or state without returning a value."""
        super().changeEvent(event)
        if event.type() == QEvent.Type.LanguageChange and hasattr(self, "ui"):
            self.retranslate()

    def retranslate(self):
        """Require a subclass to apply its window-specific localized captions.

        @return [None] Update the owned UI or state without returning a value."""
        raise NotImplementedError("Dialogs must apply their window texts")


class TranslatedAction(QAction):
    """Keep English action captions and status tips for later language switches.

    @attr sourceText [str] Original English action text.
    @attr sourceStatusTip [str] Original English status hint."""
    def __init__(self, source, parent=None):
        """Keep an English source caption and create the translated action.

        @param source [str] Original English caption or status hint.
        @param parent [QWidget, QObject, None] Qt owner of the created object.
        @return [None] Update the owned UI or state without returning a value."""
        self.sourceText = source
        self.sourceStatusTip = ""
        super().__init__(translate("PartsDB", source), parent)

    def setStatusTip(self, source):
        """Keep the English status hint and display its current translation.

        @param source [str] Original English caption or status hint.
        @return [None] Update the owned UI or state without returning a value."""
        self.sourceStatusTip = source
        super().setStatusTip(translate("PartsDB", source))

    def retranslate(self):
        """Refresh the action caption and status hint.

        @return [None] Update the owned UI or state without returning a value."""
        self.setText(translate("PartsDB", self.sourceText))
        super().setStatusTip(translate("PartsDB", self.sourceStatusTip))


def defaultHeaderText(header, field):
    """Translate built-in titles for display only; never translate user-defined DB content."""
    from ElData.ElDBScheme import ELEMENT_FIELDS_DISPLAY
    text = header["display"]
    return translate("PartsDB", text) if text == ELEMENT_FIELDS_DISPLAY.get(field) else text


class LanguageManager(QObject):
    """Manage application catalogs and language preferences.

    @attr app [QApplication] Owning application.
    @attr config [ElConfig] Active configuration.
    @attr preference [str, None] Requested system/en/ru preference.
    @attr language [str, None] Resolved en/ru language.
    @attr translators [list[QTranslator]] Installed catalogs in precedence order."""
    languageChanged = pyqtSignal()

    def __init__(self, app, config):
        """Initialize catalog ownership and an unresolved language preference.

        @param app [QApplication] Application owning the translation manager.
        @param config [ElConfig] Active application preferences.
        @return [None] Update the owned UI or state without returning a value."""
        super().__init__(app)
        self.app = app
        self.config = config
        self.preference = None
        self.language = None
        self.translators = []

    @classmethod
    def forApplication(cls, config):
        """Get or create the shared language manager using the active configuration.

        @param config [ElConfig] Active application preferences.
        @return [LanguageManager] Shared manager for the application."""
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
        """Resolve the system language to supported Russian or English.

        @return [str] ru when supported by the system, otherwise en."""
        for name in QLocale.system().uiLanguages():
            language = name.replace("_", "-").split("-")[0].lower()
            if language in ("en", "ru"):
                return language
        return "en"

    def setLanguage(self, preference, persist=True):
        """Install language catalogs, refresh actions and optionally persist the preference.

        @param preference [str] system, en or ru; unsupported values fall back to system.
        @param persist [bool] True saves the selected language preference to configuration.
        @return [None] Update the owned UI or state without returning a value."""
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
        """Uninstall owned catalogs and release the application manager reference.

        @return [None] Update the owned UI or state without returning a value."""
        for translator in reversed(self.translators):
            self.app.removeTranslator(translator)
            translator.deleteLater()
        self.translators = []
        self.language = None
        if getattr(self.app, "partsdbLanguageManager", None) is self:
            del self.app.partsdbLanguageManager
