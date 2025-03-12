import yaml
import logging
import sys
import os
from pathlib import Path
from logging import StreamHandler, Formatter

import ElLogger

logger = ElLogger.setLogger(__name__)
# logger = logging.getLogger(__name__)
# logger.setLevel(level=logging.DEBUG)
# handler = StreamHandler(stream=sys.stderr)
# handler.setFormatter(Formatter(fmt='%(asctime)s [%(levelname)s] %(module)s/%(funcName)s: %(message)s'))
# logger.addHandler(handler)

CONFIG_OBJECT = None


class ElConfig:
    def __init__(self):
        self.filename = ""
        self.data = {}
        self.config = None
        self.is_loaded = False
        self.is_changed = False

    def __bool__(self):
        return self.is_loaded

    def get_location(self):
        return self.filename

    def load(self, fn=""):
        if fn != "":
            self.filename = fn

        if self.filename != "":
            logger.debug("Load config file %s", self.filename)
            with open(self.filename) as f:
                self.data = yaml.load(f, Loader=yaml.FullLoader)
                self.is_loaded = True

    def has_value(self, name: str, section: str = "main"):
        if section not in self.data.keys():
            return False
        if name not in self.data[section].keys():
            return False

        return True

    def set_value(self, name: str, value, section: str = "main"):
        if section not in self.data:
            self.data[section] = {}

        if name not in self.data[section] or self.data[section][name] != value:
            self.data[section][name] = value
            self.is_changed = True

    def get_value(self, name: str, section: str = "main"):
        if self.data is not None and section in self.data:
            if name is not None and name in self.data[section]:
                return self.data[section][name]
        return None

    def print_config(self):
        print(yaml.dump(self.data))

    def save(self, fn=""):
        if not self.is_changed:
            logger.info("Nothing to save. cancel procedure.")
            return

        if fn:
            self.filename = fn

        if self.filename:
            if not os.path.isfile(self.filename):
                self.create_config(self.filename)

            try:
                logger.info("Save config file %s",self.filename)
                # logger.debug("Save config file %s", self.filename)
                with open(self.filename, 'w') as yaml_file:
                    yaml.dump(self.data, yaml_file, default_flow_style=False)
                    # logger.debug("Save config file to %s", self.filename)
                    self.is_changed = False

            except FileNotFoundError as err:
                logger.error("Config Not saved. Error: %s", err)
        else:
            logger.warning("Config file name not defined.")

    def create_config(self, filename):
        self.filename = filename
        p = Path(filename)
        os.makedirs(str(p.parent), exist_ok=True)
        # os.system("attrib +h " + str(p.parent))

    def sectionsList(self) -> list:
        return list(self.data.keys())

    def removeSection(self, name):
        del self.data[name]
        self.is_changed = True
