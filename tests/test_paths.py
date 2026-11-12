"""Unit tests: data folder from the config, icons folder and relative icon paths.

Run from the project root:
    python -m unittest tests.test_paths -v
"""
import os
import shutil
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtGui import QStandardItemModel, QStandardItem
from PyQt6.QtWidgets import QApplication

import constants
import ElDBScheme
from ElConfig import ElConfig
from ElDBScheme import DBFactory, ENV_ICONS_PATH, DEFAULT_ICONS_DIR
from ElIconDelegate import IconCellDelegate
from main import checkDataPath

app = QApplication.instance() or QApplication(sys.argv)


class TmpDirTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="partsdb-paths-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def path(self, *parts):
        return os.path.join(self.tmp, *parts)


class TestCheckDataPath(TmpDirTestCase):
    def setUp(self):
        super().setUp()
        self.confFile = self.path("conf", "elworks.conf")
        os.makedirs(os.path.dirname(self.confFile))
        self.config = ElConfig()

    def test_missing_data_path_is_set_to_config_folder(self):
        dataPath = checkDataPath(self.config, self.confFile, self.path("default"))
        self.assertEqual(dataPath, self.path("conf"))
        self.assertEqual(self.config.get_value(constants.CONFIG_DATA_PATH), self.path("conf"))
        self.assertTrue(self.config.is_changed, "new entry must be saved to the config")

    def test_existing_absolute_data_path_is_kept(self):
        self.config.set_value(constants.CONFIG_DATA_PATH, self.path("data"))
        os.makedirs(self.path("data"))
        self.config.is_changed = False
        self.assertEqual(checkDataPath(self.config, self.confFile, self.path("default")), self.path("data"))
        self.assertFalse(self.config.is_changed)

    def test_relative_data_path_is_relative_to_config_folder(self):
        self.config.set_value(constants.CONFIG_DATA_PATH, "../data")
        self.assertEqual(checkDataPath(self.config, self.confFile, self.path("default")), self.path("data"))
        self.assertEqual(self.config.get_value(constants.CONFIG_DATA_PATH), "../data")  # stored value unchanged

    def test_missing_data_folder_is_created(self):
        self.config.set_value(constants.CONFIG_DATA_PATH, self.path("new", "data"))
        checkDataPath(self.config, self.confFile, self.path("default"))
        self.assertTrue(os.path.isdir(self.path("new", "data")))

    def test_no_config_file_uses_default_folder(self):
        self.assertEqual(checkDataPath(self.config, "", self.path("default")), self.path("default"))
        self.assertTrue(os.path.isdir(self.path("default")))


class TestIconsDir(TmpDirTestCase):
    def setUp(self):
        super().setUp()
        self.dbFile = self.path("db", "parts.sqlite")
        os.makedirs(os.path.dirname(self.dbFile))

    def factory(self, dataPath=None) -> DBFactory:
        factory = DBFactory(self.dbFile, dataPath)
        self.addCleanup(factory.disconnect)
        return factory

    def test_data_path_defaults_to_db_folder(self):
        self.assertEqual(self.factory().dataPath, self.path("db"))

    def test_new_db_has_default_icons_path(self):
        self.assertEqual(self.factory().scheme.getEnvironment(ENV_ICONS_PATH), DEFAULT_ICONS_DIR)

    def test_icons_dir_is_inside_data_path_and_created(self):
        iconsDir = self.factory(self.path("data")).getIconsDir()
        self.assertEqual(iconsDir, self.path("data", DEFAULT_ICONS_DIR))
        self.assertTrue(os.path.isdir(iconsDir))

    def test_icons_dir_not_created_when_asked(self):
        iconsDir = self.factory().getIconsDir(create=False)
        self.assertFalse(os.path.exists(iconsDir))

    def test_empty_setting_gets_default_and_is_saved(self):
        factory = self.factory()
        factory.scheme.setEnvironment(ENV_ICONS_PATH, "")
        self.assertEqual(factory.getIconsDir(), self.path("db", DEFAULT_ICONS_DIR))
        self.assertEqual(factory.scheme.getEnvironment(ENV_ICONS_PATH), DEFAULT_ICONS_DIR)

    def test_missing_setting_gets_default(self):
        factory = self.factory()
        factory.scheme.db.exec("DELETE FROM ENVIRONMENT WHERE name = '%s';" % ENV_ICONS_PATH)
        self.assertEqual(factory.getIconsDir(), self.path("db", DEFAULT_ICONS_DIR))
        self.assertEqual(factory.scheme.getEnvironment(ENV_ICONS_PATH), DEFAULT_ICONS_DIR)

    def test_custom_relative_setting(self):
        factory = self.factory()
        factory.scheme.setEnvironment(ENV_ICONS_PATH, "media/pics")
        self.assertEqual(factory.getIconsDir(), self.path("db", "media", "pics"))

    def test_absolute_setting_is_kept(self):
        factory = self.factory()
        factory.scheme.setEnvironment(ENV_ICONS_PATH, self.path("elsewhere"))
        self.assertEqual(factory.getIconsDir(), self.path("elsewhere"))

    def test_resolve_icon_path(self):
        factory = self.factory()
        self.assertEqual(factory.resolveIconPath("1N4007.png"), self.path("db", DEFAULT_ICONS_DIR, "1N4007.png"))
        self.assertEqual(factory.resolveIconPath("diodes/1N4007.png"),
                         self.path("db", DEFAULT_ICONS_DIR, "diodes", "1N4007.png"))
        self.assertEqual(factory.resolveIconPath("/abs/x.png"), "/abs/x.png")
        self.assertEqual(factory.resolveIconPath(""), "")
        self.assertEqual(factory.resolveIconPath(None), "")

    def test_migrated_old_db_gets_default_icons_path(self):
        # old DB without ENVIRONMENT rows -> upgrade adds icons_path = default
        import sqlite3
        conn = sqlite3.connect(self.dbFile)
        conn.execute(ElDBScheme.TYPES_TABLE_SQL)
        conn.commit()
        conn.close()
        self.assertEqual(self.factory().scheme.getEnvironment(ENV_ICONS_PATH), DEFAULT_ICONS_DIR)


class TestDelegateIconPath(TmpDirTestCase):
    def imagePath(self, value, iconsDir):
        model = QStandardItemModel(1, 1)
        model.setItem(0, 0, QStandardItem(value))
        return IconCellDelegate(iconsDir=iconsDir).imagePath(model.index(0, 0))

    def test_relative_value_is_inside_icons_dir(self):
        self.assertEqual(self.imagePath("a.png", self.path("icons")), self.path("icons", "a.png"))

    def test_absolute_value_is_kept(self):
        self.assertEqual(self.imagePath("/abs/a.png", self.path("icons")), "/abs/a.png")

    def test_file_url_is_converted(self):
        self.assertEqual(self.imagePath("file:///abs/a.png", self.path("icons")), "/abs/a.png")

    def test_empty_value(self):
        self.assertEqual(self.imagePath("", self.path("icons")), "")
        self.assertEqual(self.imagePath("   ", self.path("icons")), "")


if __name__ == "__main__":
    unittest.main()
