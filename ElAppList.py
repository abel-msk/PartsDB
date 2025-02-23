import logging
import sys
from PyQt6 import QtGui
from ElConfig import ElConfig

logger = logging.getLogger(__name__)
logger.setLevel(level=logging.DEBUG)
handler = logging.StreamHandler(stream=sys.stderr)
handler.setFormatter(logging.Formatter(fmt='%(asctime)s [%(levelname)s] %(module)s/%(funcName)s: %(message)s'))
logger.addHandler(handler)

CONFIG_APP_SECTION= "application"
CONF_APP_EXE = "exec"
CONF_APP_EXT = "ext"
CONF_APP_ARGS = "args"
CONF_APP_ICON = "icon"


class AppDef:

    def __init__(self, name: str, config: ElConfig):
        self.name = name
        self.appSection = CONFIG_APP_SECTION+"_" + name.replace(' ', '_')
        self.exe = ""
        self.ext = ""
        self.args = ""

        self.config: ElConfig = config
        if self.appSection in self.config.sectionsList():
            self.exe = self.config.get_value(CONF_APP_EXE, self.appSection)
            self.ext = self.config.get_value(CONF_APP_EXT, self.appSection)
            self.args = self.config.get_value(CONF_APP_ARGS, self.appSection)
            # self.icon = self.config.get_value(CONF_APP_ICON, self.appSection)

    def save(self):
        self.config.set_value(CONF_APP_EXE, self.exe, self.appSection)
        self.config.set_value(CONF_APP_EXT, self.ext, self.appSection)
        self.config.set_value(CONF_APP_ARGS, self.args, self.appSection)
        # self.config.set_value(CONF_APP_ICON, self.icon, self.appSection)


class AppList:
    def __init__(self, config: ElConfig):
        self.config: ElConfig = config
        self.apps = {}

        for section in self.config.sectionsList():
            if section.startswith(CONFIG_APP_SECTION):
                appName = section[len(CONFIG_APP_SECTION)+1:]
                appName = appName.replace('_', ' ')
                self.apps[appName] = AppDef(appName, self.config)

    def getNames(self):
        return list(self.apps.keys())

    def __getitem__(self, item):
        return self.apps[item]

    def getAppByName(self, name):
        return self.apps[name]

    def getAppByExt(self, ext):
        for appName in self.apps.keys():
            if self.apps[appName].ext.upper() == ext.upper():
                return self.apps[appName]
        return None

    def add(self, name: str):
        if name in self.apps.keys():
            raise IndexError("App Name already exist.")
        app = AppDef(name, self.config)
        app.save()
        self.apps[name] = app
        return app

    def remove(self, name):
        self.config.removeSection(CONFIG_APP_SECTION+"_" + name.replace(' ', '_'))

    def execute(self):
        # TODO: Start application
        pass
        #  View pdf https://github.com/BBC-Esq/PyQt6-PDF-Viewer/blob/main/pyqt6_pdf_viewer.py
        # https://github.com/BBC-Esq/PyQt6-PDF-Viewer


