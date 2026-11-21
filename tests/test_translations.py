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

from types import SimpleNamespace
from PyQt6.QtWidgets import QDialogButtonBox
from ElCatalogDialogs import SectionDialog, PartValuesDialog
from ElData import ElDBDataParts
from ElPluginsDialog import PluginsDialog, PluginLogsDialog
from ElImportTask import ImportProgressDialog
from ElImportPreview import ImportPreview
from ElUnitsDialog import UnitsDialog
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
    """Dispatch pending Qt events so live translation assertions observe updated widgets.

    @return [None] Updated captions or completed maintenance operation."""
    for _ in range(3):
        app.processEvents()


class TestLiveTranslations(unittest.TestCase):
    """Verify live language switching without changing user input or database records.

    @attr factory [DBFactory] Temporary database factory.
    @attr config [ElConfig] Temporary preferences.
    @attr window [MainWindow] Main form under test.
    @attr manager [LanguageManager] Active language manager.
    @attr root [Path] Temporary test directory."""
    def setUp(self):
        """Create a temporary catalog, configuration and main window.

        @return [None] Complete the setup, cleanup or assertions."""
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
        """Release translators and dispatch remaining Qt events.

        @return [None] Complete the setup, cleanup or assertions."""
        manager = getattr(app, "partsdbLanguageManager", None)
        if manager is not None:
            manager.close()
        processEvents()

    def switch(self, language):
        """Trigger the requested language action and wait for its UI updates.

        @param language [str] en, ru or system preference to select.
        @return [None] Complete the setup, cleanup or assertions."""
        self.window.languageActions[language].trigger()
        processEvents()

    def test_menu_switches_existing_window_both_ways(self):
        """Verify menu switches existing window both ways.

        @return [None] Complete the setup, cleanup or assertions."""
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
        """Verify language saved immediately.

        @return [None] Complete the setup, cleanup or assertions."""
        self.switch("ru")
        data = yaml.safe_load(Path(self.config.filename).read_text(encoding="utf-8"))
        self.assertEqual(data["main"]["language"], "ru")

    def test_saved_language_restored_when_window_reopens(self):
        """Verify saved language restored when window reopens.

        @return [None] Complete the setup, cleanup or assertions."""
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
        """Verify switch preserves selection search text and database content.

        @return [None] Complete the setup, cleanup or assertions."""
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
        """Verify default headers translated custom headers unchanged.

        @return [None] Complete the setup, cleanup or assertions."""
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
        """Verify cached context menus update without recreation.

        @return [None] Complete the setup, cleanup or assertions."""
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
        """Verify open header dialog keeps unsaved edits.

        @return [None] Complete the setup, cleanup or assertions."""
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
        """Verify open file and application dialogs keep input.

        @return [None] Complete the setup, cleanup or assertions."""
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
        """Verify window texts do not depend on generated retranslation.

        @return [None] Complete the setup, cleanup or assertions."""
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
        """Verify qt standard buttons are translated.

        @return [None] Complete the setup, cleanup or assertions."""
        self.switch("ru")
        message = QMessageBox(self.window)
        message.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        self.addCleanup(message.close)
        self.assertEqual(message.button(QMessageBox.StandardButton.Yes).text().replace("&", ""), "Да")
        self.switch("en")
        self.assertEqual(message.button(QMessageBox.StandardButton.Yes).text().replace("&", ""), "Yes")

    def test_warning_uses_selected_language(self):
        """Verify warning uses selected language.

        @return [None] Complete the setup, cleanup or assertions."""
        self.switch("ru")
        self.window.partsTable.tableView.clearSelection()
        with mock.patch.object(QMessageBox, "information") as info:
            self.window.DelPartBtn.click()
        self.assertEqual(info.call_args.args[2], "Сначала выберите деталь.")

    def test_system_language_and_fallback(self):
        """Verify system language and fallback.

        @return [None] Complete the setup, cleanup or assertions."""
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
        """Verify missing catalog keeps previous language.

        @return [None] Complete the setup, cleanup or assertions."""
        with mock.patch("ElTranslations.CATALOG_DIR", self.root / "missing"):
            with self.assertRaises(RuntimeError):
                self.manager.setLanguage("ru")
        self.assertEqual(self.manager.language, "en")
        self.assertEqual(self.window.DelPartBtn.text(), "Delete Part")

    def test_repeated_switches_keep_one_checked_action_and_no_extra_menus(self):
        """Verify repeated switches keep one checked action and no extra menus.

        @return [None] Complete the setup, cleanup or assertions."""
        count = len(self.window.menuBar().actions())
        for language in ("ru", "en", "ru", "en"):
            self.switch(language)
            self.assertEqual(sum(action.isChecked() for action in self.window.languageActions.values()), 1)
            self.assertEqual(len(self.window.menuBar().actions()), count)
            self.assertLessEqual(len(self.manager.translators), 2)


    def test_all_forms_retranslate_labels_and_buttons_without_generated_texts(self):
        """Verify live RU/EN captions across all six Designer forms and handwritten dialogs.

        @return [None] Ensure localization works even when generated retranslateUi is disabled.
        """
        with ExitStack() as stack:
            for target in ('ElParts.Ui_MainWindow', 'ElAppPathWnd.Ui_AppPathDialog',
                           'ElOpenFileWnd.Ui_OpenFileWnd', 'ElHdrEditWnd.Ui_HdrEditDialog',
                           'ElPluginsWnd.Ui_Dialog', 'ElUnitsWnd.Ui_units_dialog'):
                stack.enter_context(mock.patch(target + '.retranslateUi'))
            window = MainWindow(self.factory, self.config)
            self.addCleanup(window.close)
            files = OpenFileDialog(window, str(self.root))
            apps = AppPathConfig(window, window.appList)
            headers = HeaderEditDialog(window, self.factory)
            with self.factory.scheme.transaction():
                self.factory.scheme.storePluginMetadata(dict(
                    id='test.importer', plugin_type='project_import', name='Test importer',
                    version='1', api_version=1, system_id='test', system_name='Test',
                    description='', author='', enabled=1, manifest_json='{}'))
            plugins = PluginsDialog(window, manager=SimpleNamespace(sync=lambda database: None), conn=self.factory.scheme)
            units = UnitsDialog(self.factory.scheme, window)
            section = SectionDialog(window, ElDBDataParts.basicTypes(self.factory), 'User section')
            values = PartValuesDialog(window, [self.section.getHeaders()['part_num']])
            preview = ImportPreview(SimpleNamespace(name='User project', components=[], warnings=[]),
                                    SimpleNamespace(added=(), changed=(), removed=()), window)
            logs = PluginLogsDialog('', window)
            progress = ImportProgressDialog(window)
            installation = ImportProgressDialog(window, installing=True)
            for dialog in (files, apps, headers, plugins, units, section, values, preview, logs, progress, installation):
                self.addCleanup(dialog.close)
            plugins.ui.app_path_input.setText('/tmp/user application')
            units.unitsModel.item(0, 2).setText('User unit')
            section.nameEdit.setText('User name')
            values.editors['part_num'].setText('User value')
            for language, expected in (
                    ('ru', ('Импортировано с помощью', 'Дата обновления', 'Сопоставить деталь',
                            'Основная единица СИ', 'Путь к приложению', 'Отмена', 'Журнал плагина')),
                    ('en', ('Imported by', 'Refresh date', 'Link Part',
                            'Base SI unit', 'Application path', 'Cancel', 'Plugin logs'))):
                self.switch(language)
                imported, refreshed, link, base, application_path, cancel, log_title = expected
                self.assertEqual(window.label_3.text(), imported)
                self.assertEqual(window.label_5.text(), refreshed)
                self.assertEqual(window.d_proj_link_cmd.text(), link)
                self.assertEqual(units.unitsModel.headerData(6, Qt.Orientation.Horizontal), base)
                self.assertEqual(plugins.ui.label_3.text(), application_path)
                self.assertIn(application_path, plugins.ui.info.toPlainText())
                self.assertEqual(logs.windowTitle(), log_title)
                for box in (files.ui.buttonBox, apps.ui.buttonBox, headers.ui.buttonBox,
                            section.buttons, values.buttons, units.ui.buttonBox, preview.ui.buttons):
                    self.assertEqual(box.button(QDialogButtonBox.StandardButton.Cancel).text(), cancel)
                self.assertEqual(plugins.ui.app_path_input.text(), '/tmp/user application')
                self.assertEqual(units.unitsModel.item(0, 2).text(), 'User unit')
                self.assertEqual(section.nameEdit.text(), 'User name')
                self.assertEqual(values.editors['part_num'].text(), 'User value')

    def test_progress_and_log_windows_follow_language_without_resetting_content(self):
        """Verify task windows translate their controls while retaining progress and raw logs.

        @return [None] Installation must not acquire a cancel button after a language switch.
        """
        from PyQt6.QtWidgets import QPushButton
        progress = ImportProgressDialog(self.window)
        installing = ImportProgressDialog(self.window, installing=True)
        logs = PluginLogsDialog('User log / журнал', self.window)
        for dialog in (progress, installing, logs):
            self.addCleanup(dialog.close)
            dialog.show()
        progress.setRange(0, 100)
        progress.setValue(25)
        self.switch('ru')
        self.assertEqual(progress.windowTitle(), 'Импорт проекта')
        self.assertEqual(progress.findChild(QPushButton).text(), 'Отмена')
        self.assertEqual(progress.value(), 25)
        self.assertFalse(installing.findChildren(QPushButton))
        self.assertEqual(logs.text.toPlainText(), 'User log / журнал')
        self.switch('en')
        self.assertEqual(progress.windowTitle(), 'Import project')
        self.assertEqual(logs.windowTitle(), 'Plugin logs')
        self.assertEqual(logs.text.toPlainText(), 'User log / журнал')


class TestTranslationCatalogs(unittest.TestCase):
    """Verify translation source coverage and matching compiled catalogs; stores no database state."""
    def test_sources_are_covered_and_placeholders_preserved(self):
        """Verify sources are covered and placeholders preserved.

        @return [None] Complete the setup, cleanup or assertions."""
        result = subprocess.run([sys.executable, str(ROOT / "tools" / "translations.py"), "--check"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_compiled_catalogs_match_translation_sources(self):
        """Verify compiled catalogs match translation sources.

        @return [None] Complete the setup, cleanup or assertions."""
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
