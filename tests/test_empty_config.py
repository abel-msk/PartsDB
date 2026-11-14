"""Startup with an empty config, real temporary SQLite DB and real main window."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PyQt6.QtWidgets import QApplication

import constants
import ElDBScheme
import main
from ElConfig import ElConfig
from ElMainWindow import MainWindow

from tests.qt_support import application

app = application()


class TestEmptyConfigStartup(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="partsdb-empty-config-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.conf = self.root / "elworks.conf"
        self.log = self.root / "app.log"
        self.config = ElConfig()
        self.opened = False

    def runStartup(self, text):
        self.conf.write_text(text, encoding="utf-8")

        def checkWindowAndExit():
            windows = [w for w in app.topLevelWidgets()
                       if isinstance(w, MainWindow) and w.config is self.config]
            self.assertEqual(len(windows), 1)
            window = windows[0]
            self.addCleanup(window.factory.disconnect)
            self.addCleanup(window.close)
            self.assertTrue(window.isVisible())
            self.assertEqual(window.typesTree.treeModel.rowCount(), 0)
            self.assertEqual(window.factory.db_file, str(self.root / "elworks.sqlite"))
            self.assertEqual(window.factory.scheme.getDBVersion(), ElDBScheme.DB_VERSION)
            self.assertEqual(window.factory.getIconsDir(), str(self.root / "icons"))
            self.assertEqual(list(window.factory.getRootTypes()), [])
            self.opened = True
            window.close()
            return 0

        with mock.patch.object(main, "HOME", str(self.home)), \
                mock.patch.object(main, "basedir", str(self.root)), \
                mock.patch.object(main, "config", self.config), \
                mock.patch.object(sys, "argv", ["main.py", "-c", str(self.conf), "-l", str(self.log)]), \
                mock.patch.object(main, "QApplication", return_value=app), \
                mock.patch.object(app, "exec", side_effect=checkWindowAndExit), \
                mock.patch.object(main.ElLogger, "setLogFile"), \
                mock.patch.object(main.ElLogger, "setLevel"), \
                mock.patch.object(main.faulthandler, "enable"), \
                mock.patch.object(main, "faultLog", None, create=True), \
                mock.patch.object(ElDBScheme, "DB_FACTORY"), \
                mock.patch.object(ElConfig, "CONFIG_OBJECT", None, create=True):
            try:
                main.main()
            finally:
                if main.faultLog is not None:
                    main.faultLog.close()

        # main() logs UI exceptions instead of propagating them: check that the window really opened.
        self.assertTrue(self.opened)
        saved = yaml.safe_load(self.conf.read_text(encoding="utf-8"))
        self.assertEqual(saved["main"][constants.CONFIG_DB_FILE], str(self.root / "elworks.sqlite"))
        self.assertEqual(saved["main"][constants.CONFIG_DATA_PATH], str(self.root))
        self.assertEqual(saved["main"][constants.LOG_LEVEL], "err")
        self.assertEqual(saved["main"][constants.CONFIG_STARTUP_MODE], constants.STARTUP_MODE_CATALOG)
        self.assertTrue((self.root / "icons").is_dir())
        self.assertFalse((self.home / ".elworks" / "elworks.sqlite").exists())

    def test_zero_byte_config(self):
        self.runStartup("")

    def test_comments_only_config(self):
        self.runStartup("# No settings yet\n")

    def test_empty_yaml_mapping(self):
        self.runStartup("{}\n")


if __name__ == "__main__":
    unittest.main()
