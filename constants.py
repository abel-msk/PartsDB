LAST_OPEN_FILE = "last_open_file"
STARTUP_MODE_CATALOG = "C"
STARTUP_MODE_PROJECTS = "P"
CONFIG_DB_FILE = "db_file"
CONFIG_DATA_PATH = "data_path"  # Folder with the data: the sqlite DB and its icons folder
CONFIG_LANGUAGE = "language"  # system, en or ru; interface only, never database content
CONFIG_STARTUP_MODE = "startup_mode"
LOG_LEVEL = "log_level"
LOG_FILE = "log_file"


# Defined by the public SDK so plugins and the host use the same identifiers.
from ElPartsPluginApi.constants import (
    PLUGIN_TYPE_IMPORT, PLUGIN_TYPE_PARTS_ORDER, PLUGIN_TYPE_SHIPMENT_TRACKING, PLUGIN_TYPES,
)
