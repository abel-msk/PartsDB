"""Real Qt catalogs, live language changes and preservation of user data and pending edits."""
import os
from contextlib import ExitStack
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import mock

import yaml

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QMessageBox

from ElAppPathDialog import AppPathConfig
from ElConfig import ElConfig
from ElData.ElDBScheme import DBFactory
from ElHdrEditDialog import HeaderEditDialog
from ElMainWindow import MainWindow
from ElOpenFileDialog import OpenFileDialog
from ElTranslations import CATALOG_DIR, LanguageManager, translate

from tests.qt_support import application

app = application()


def processEvents():
    for _ in range(3):
        app.processEvents()


class TestLiveTranslations(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="partsdb-languages-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.factory = DBFactory(str(self.root / "test.sqlite"))
        self.addCleanup(self.factory.disconnect)
        self.section = self.factory.appendType("Мой раздел / Custom section", None)
        self.part = self.factory.createPart(self.section, {"part_num": "MMBT2222A", "description": "User text / текст"})
        header = self.section.getHeaders()["description"]
        header["display"] = "Мой заголовок / Custom title"
        header.save()
        self.config = ElConfig()
        self.config.filename = str(self.root / "elworks.conf")
        self.config.set_value("language", "en")
        self.window = MainWindow(self.factory, self.config)
        self.window.setStartupMode(None)
        self.manager = self.window.languageManager
        self.addCleanup(self.cleanupLanguage)
        self.addCleanup(self.window.close)

    def cleanupLanguage(self):
        manager = getattr(app, "partsdbLanguageManager", None)
        if manager is not None:
            manager.close()
        processEvents()

    def switch(self, language):
        self.window.languageActions[language].trigger()
        processEvents()

    def test_menu_switches_existing_window_both_ways(self):
        shortcut = self.window.fileMenu.actions()[0].shortcut().toString()
        self.assertEqual(self.window.DelPartBtn.text(), "Delete Part")
        self.switch("ru")
        self.assertEqual(self.window.DelPartBtn.text(), "Удалить деталь")
        self.assertEqual(self.window.fileMenu.title(), "Файл")
        self.assertEqual(self.window.setupMenu.title(), "Настройки")
        self.assertEqual(self.window.languageMenu.title(), "Язык")
        self.assertEqual(self.window.fileMenu.actions()[0].text(), "Открыть базу")
        self.assertTrue(self.window.languageActions["ru"].isChecked())
        self.assertEqual(self.window.fileMenu.actions()[0].shortcut().toString(), shortcut)
        self.switch("en")
        self.assertEqual(self.window.DelPartBtn.text(), "Delete Part")
        self.assertEqual(self.window.fileMenu.title(), "File")
        self.assertEqual(self.window.fileMenu.actions()[0].text(), "Open DB")
        self.assertTrue(self.window.languageActions["en"].isChecked())

    def test_language_saved_immediately(self):
        self.switch("ru")
        data = yaml.safe_load(Path(self.config.filename).read_text(encoding="utf-8"))
        self.assertEqual(data["main"]["language"], "ru")

    def test_saved_language_restored_when_window_reopens(self):
        self.switch("ru")
        self.window.close()
        self.manager.close()
        config = ElConfig()
        config.load(self.config.filename)
        reopened = MainWindow(self.factory, config)
        self.addCleanup(reopened.close)
        self.assertEqual(reopened.languageManager.language, "ru")
        self.assertEqual(reopened.DelPartBtn.text(), "Удалить деталь")
        self.assertTrue(reopened.languageActions["ru"].isChecked())

    def test_switch_preserves_selection_search_text_and_database_content(self):
        before = list(self.factory.scheme.db.conn.iterdump())
        self.window.searchStr.setText("draft search query")
        self.window.view.setCurrentIndex(1)
        self.switch("ru")
        self.assertEqual(self.window.searchStr.text(), "draft search query")
        self.assertEqual(self.window.view.currentIndex(), 1)
        self.assertEqual(self.window.partsTable.getSelected().id, self.part.id)
        self.assertEqual(self.window.typesTree.treeModel.index(0, 0).data(), self.section.name)
        self.assertEqual(list(self.factory.scheme.db.conn.iterdump()), before)

    def test_default_headers_translated_custom_headers_unchanged(self):
        table = self.window.partsTable
        fields = list(__import__("ElData.ElDBScheme", fromlist=["ELEMENT_FIELDS"]).ELEMENT_FIELDS)[2:]
        self.switch("ru")
        model = table.tableModel
        self.assertEqual(model.headerData(fields.index("part_num"), Qt.Orientation.Horizontal,
                                          Qt.ItemDataRole.DisplayRole), "Партномер")
        self.assertEqual(model.headerData(fields.index("description"), Qt.Orientation.Horizontal,
                                          Qt.ItemDataRole.DisplayRole), "Мой заголовок / Custom title")
        self.assertEqual(self.factory.getHeadersByType(self.section.recId)["description"]["display"],
                         "Мой заголовок / Custom title")

    def test_cached_context_menus_update_without_recreation(self):
        table = self.window.partsTable
        body = table._defineBodyMenu()
        header = table._defineHeaderMenu()
        tree = self.window.typesTree.menu
        self.switch("ru")
        self.assertEqual(body.actions()[-1].text(), "Удалить деталь")
        self.assertEqual(header.actions()[0].text(), "Скрыть колонку")
        self.assertEqual(tree.actions()[0].text(), "Добавить раздел")
        self.switch("en")
        self.assertEqual(body.actions()[-1].text(), "Delete Part")

    def test_open_header_dialog_keeps_unsaved_edits(self):
        dialog = HeaderEditDialog(self.window, self.factory)
        self.addCleanup(dialog.close)
        dialog.loadData(self.section.recId)
        dialog.show()
        model = dialog.tableModel
        index = model.index(model.rowsList.index("device_code"), model.columnsList.index("display"))
        model.setData(index, "Unsaved user title", Qt.ItemDataRole.EditRole)
        dialog.ui.icon_selector.setCurrentIndex(1)
        pending = dialog.pendingIcon
        selection = dialog.ui.icon_selector.currentIndex()
        self.switch("ru")
        self.assertEqual(dialog.windowTitle(), "Редактировать колонки")
        self.assertEqual(dialog.ui.label.text(), "Раздел:")
        self.assertEqual(model.data(index, Qt.ItemDataRole.EditRole), "Unsaved user title")
        self.assertTrue(model.isChanged())
        self.assertEqual(dialog.pendingIcon, pending)
        self.assertEqual(dialog.ui.icon_selector.currentIndex(), selection)
        self.assertEqual(dialog.currentTypeId, self.section.recId)
        self.assertNotEqual(self.factory.getHeadersByType(self.section.recId)["device_code"]["display"],
                            "Unsaved user title")

    def test_open_file_and_application_dialogs_keep_input(self):
        files = OpenFileDialog(self.window, str(self.root))
        apps = AppPathConfig(self.window, self.window.appList)
        self.addCleanup(files.close)
        self.addCleanup(apps.close)
        files.ui.webUri.setText("https://example.invalid/user-input")
        apps.ui.appNameInput.setText("My application")
        self.switch("ru")
        self.assertEqual(files.windowTitle(), "Выберите файл или ссылку")
        self.assertEqual(files.ui.webUri.text(), "https://example.invalid/user-input")
        self.assertEqual(apps.windowTitle(), "Приложения для документов")
        self.assertEqual(apps.ui.appNameInput.text(), "My application")
        self.assertEqual(apps.ui.saveBtn.text(), "Сохранить")

    def test_window_texts_do_not_depend_on_generated_retranslation(self):
        # Regenerating forms must not replace the runtime bilingual texts.
        self.switch("ru")
        with ExitStack() as stack:
            for target in ("ElParts.Ui_MainWindow", "ElAppPathWnd.Ui_AppPathDialog",
                           "ElOpenFileWnd.Ui_OpenFileWnd", "ElHdrEditWnd.Ui_HdrEditDialog"):
                stack.enter_context(mock.patch(target + ".retranslateUi"))
            window = MainWindow(self.factory, self.config)
            self.addCleanup(window.close)
            files = OpenFileDialog(window, str(self.root))
            apps = AppPathConfig(window, window.appList)
            headers = HeaderEditDialog(window, self.factory)
            for dialog in (files, apps, headers):
                self.addCleanup(dialog.close)
            self.assertEqual(window.searchBtn.text(), "Поиск")
            self.assertEqual(window.label.text(), "Папки проектов")
            self.assertEqual(window.proj_add_cmd.text(), "Добавить проект")
            self.assertEqual(window.d_prj_reload_cmd.text(), "Обновить данные")
            self.assertEqual(window.prj_parts.itemText(window.prj_parts.indexOf(window.prj_parts_lt2)),
                             "Несопоставленные детали")
            self.assertEqual(files.windowTitle(), "Выберите файл или ссылку")
            self.assertEqual(apps.ui.saveBtn.text(), "Сохранить")
            self.assertEqual(headers.ui.label.text(), "Раздел:")
            self.assertEqual(headers.ui.icon_selector.itemText(0),
                             translate("PartsDB", "Auto (from parent section / built-in rule)"))
            self.switch("en")
            self.assertEqual(window.searchBtn.text(), "Search")
            self.assertEqual(window.label.text(), "Projects Folders")
            self.assertEqual(window.proj_add_cmd.text(), "Add Project")
            self.assertEqual(window.d_prj_reload_cmd.text(), "Reload Data")
            self.assertEqual(window.prj_parts.itemText(window.prj_parts.indexOf(window.prj_parts_lt2)),
                             "Unmatched parts")
            self.assertEqual(files.windowTitle(), "Select file or URL")
            self.assertEqual(apps.ui.saveBtn.text(), "Save")
            self.assertEqual(headers.ui.label.text(), "Section:")

    def test_qt_standard_buttons_are_translated(self):
        self.switch("ru")
        message = QMessageBox(self.window)
        message.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        self.addCleanup(message.close)
        self.assertEqual(message.button(QMessageBox.StandardButton.Yes).text().replace("&", ""), "Да")
        self.switch("en")
        self.assertEqual(message.button(QMessageBox.StandardButton.Yes).text().replace("&", ""), "Yes")

    def test_warning_uses_selected_language(self):
        self.switch("ru")
        self.window.partsTable.tableView.clearSelection()
        with mock.patch.object(QMessageBox, "information") as info:
            self.window.DelPartBtn.click()
        self.assertEqual(info.call_args.args[2], "Сначала выберите деталь.")

    def test_system_language_and_fallback(self):
        with mock.patch("ElTranslations.QLocale.system") as locale:
            locale.return_value.uiLanguages.return_value = ["ru-Cyrl-RU", "en-US"]
            self.switch("system")
            self.assertEqual(self.manager.language, "ru")
            self.assertEqual(self.manager.preference, "system")
            self.assertEqual(self.window.DelPartBtn.text(), "Удалить деталь")
            locale.return_value.uiLanguages.return_value = ["ja-JP"]
            self.manager.setLanguage("system")
            processEvents()
            self.assertEqual(self.manager.language, "en")

    def test_missing_catalog_keeps_previous_language(self):
        with mock.patch("ElTranslations.CATALOG_DIR", self.root / "missing"):
            with self.assertRaises(RuntimeError):
                self.manager.setLanguage("ru")
        self.assertEqual(self.manager.language, "en")
        self.assertEqual(self.window.DelPartBtn.text(), "Delete Part")

    def test_repeated_switches_keep_one_checked_action_and_no_extra_menus(self):
        count = len(self.window.menuBar().actions())
        for language in ("ru", "en", "ru", "en"):
            self.switch(language)
            self.assertEqual(sum(action.isChecked() for action in self.window.languageActions.values()), 1)
            self.assertEqual(len(self.window.menuBar().actions()), count)
            self.assertLessEqual(len(self.manager.translators), 2)


class TestTranslationCatalogs(unittest.TestCase):
    def test_sources_are_covered_and_placeholders_preserved(self):
        result = subprocess.run([sys.executable, str(ROOT / "tools" / "translations.py"), "--check"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_compiled_catalogs_match_translation_sources(self):
        from PyQt6.QtCore import QTranslator
        for language in ("en", "ru"):
            translator = QTranslator()
            self.assertTrue(translator.load(str(CATALOG_DIR / ("partsdb_" + language + ".qm"))))
            for context in ET.parse(CATALOG_DIR / ("partsdb_" + language + ".ts")).findall("context"):
                for message in context.findall("message"):
                    source = message.findtext("source")
                    self.assertEqual(translator.translate(context.findtext("name"), source.encode("utf-8")),
                                     message.findtext("translation"), (language, source))


if __name__ == "__main__":
    unittest.main()
