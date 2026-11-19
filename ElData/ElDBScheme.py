from PyQt6.QtCore import QT_TRANSLATE_NOOP
from ElPartsPluginApi.constants import PLUGIN_TYPES
from .ElDBConnect import DBError, DBSyntax, SQLiteConnector

import logging
import json
from contextlib import contextmanager
from datetime import datetime, timezone
import re
import sys
import os
import bisect
import urllib.parse
from pathlib import Path

import ElLogger

# from numpy import *

DB_FACTORY = None


class PartInProjectsError(RuntimeError):
    """Deleting a part referenced by a project is not allowed."""



logger = ElLogger.setLogger(__name__)
# logger = logging.getLogger(__name__)
# logger.setLevel(level=logging.DEBUG)
# handler = logging.StreamHandler(stream=sys.stderr)
# # handler.setFormatter(Formatter(fmt='[%(levelname)s] %(name)s: %(message)s'))
# handler.setFormatter(logging.Formatter(fmt='[%(levelname)s] %(module)s/%(funcName)s: %(message)s'))
# logger.addHandler(handler)

F_ALIGN_LEFT = "LEFT"
F_ALIGN_RIGHT = "RIGHT"
F_ALIGN_CENTER = "CENTER"

ELEMENT_FIELDS = {
    "id": "INTEGER PRIMARY KEY AUTOINCREMENT",
    "type_id": "INTEGER NOT NULL",
    "part_num": "TEXT",
    "device_code": "TEXT", # Обозначение на чипе
    "value": "REAL",  # Номинал
    "units": "TEXT",  # Eдиницы измерения
    "reduced_val": "REAL",  # Приведенное к единой размерности значнеие
    "reduced_val_units": "TEXT",  # Единицы измерения для приведенного к единой размерности значнеия
    "max_current": "TEXT",  # Максимально допустимый ток
    "max_voltage": "TEXT",  # Максимально допустимое напряжение
    "max_desumption": "TEXT",  # Рассеиваемая мощьность
    "description": "TEXT",  # Описание
    "package": "TEXT",      # Корпус
    "present": "BOOLEAN",   # В наличии
    "quantity": "INTEGER",  # Количество
    "price": "REAL",        # Цена за единицу
    "currency": "TEXT",      # Валюта
    "shop": "TEXT",  # URL Магазина
    "local_location": "TEXT",  # Где лежит у меня
    "icon": "TEXT"  # Иконка
}

ELEMENT_FIELDS_DISPLAY = {
    "id": QT_TRANSLATE_NOOP("PartsDB", 'id'),
    "type_id": QT_TRANSLATE_NOOP("PartsDB", 'type_id'),
    "part_num": QT_TRANSLATE_NOOP("PartsDB", 'PartNum'),
    "device_code": QT_TRANSLATE_NOOP("PartsDB", 'Code'),
    "value": QT_TRANSLATE_NOOP("PartsDB", 'Nominal'),
    "units": QT_TRANSLATE_NOOP("PartsDB", 'Unit'),
    "reduced_val": QT_TRANSLATE_NOOP("PartsDB", 'Reduced Value'),
    "reduced_val_units": QT_TRANSLATE_NOOP("PartsDB", 'Reduced Unit'),
    "chip_code": QT_TRANSLATE_NOOP("PartsDB", 'Chip code'),
    "max_current": QT_TRANSLATE_NOOP("PartsDB", 'Current'),
    "max_voltage": QT_TRANSLATE_NOOP("PartsDB", 'Voltage'),
    "max_desumption": QT_TRANSLATE_NOOP("PartsDB", 'Dissipation'),
    "description": QT_TRANSLATE_NOOP("PartsDB", 'Description'),
    "package": QT_TRANSLATE_NOOP("PartsDB", 'Package'),
    "present": QT_TRANSLATE_NOOP("PartsDB", 'Is Present'),
    "quantity": QT_TRANSLATE_NOOP("PartsDB", 'Quantity'),
    "price": QT_TRANSLATE_NOOP("PartsDB", 'Price'),
    "currency": QT_TRANSLATE_NOOP("PartsDB", 'Currency'),
    "shop": QT_TRANSLATE_NOOP("PartsDB", 'Shop link'),
    "local_location": QT_TRANSLATE_NOOP("PartsDB", 'Location'),
    "icon": QT_TRANSLATE_NOOP("PartsDB", 'Icon Link')
}


ELEMENT_FLD_NAMES = list(ELEMENT_FIELDS.keys())

ICON_COLUMN_POSITION = 0  # Visual position of the "icon" column in the parts table (0 = leftmost)


def defaultColumnOrder() -> list:
    """Parts table fields (without id, type_id) in their default visual order."""
    fields = [f for f in ELEMENT_FLD_NAMES[2:] if f != "icon"]
    fields.insert(ICON_COLUMN_POSITION, "icon")
    return fields


def defaultHeaderPosition(field_name: str) -> int:
    order = defaultColumnOrder()
    return order.index(field_name) if field_name in order else len(order)

#  DataSheet
#  Image
#  Project

TYPES_TABLE_NAME = "TYPES"
HEADER_TABLE_NAME = "HEADERS"
PARTS_TABLE_NAME = "PARTS"
DATASHEETS_TABLE_NAME = "DATASHEETS"
PROJECTS_TABLE = "PROJECTS"
PROJECT_COMPONENTS_TABLE = "PROJECT_COMPONENTS"
PROJECT_COMPONENT_MATCHES_TABLE = "PROJECT_COMPONENT_MATCHES"
EL_BY_PROJECT_TABLE = "EL_BY_PROJECT"
ENVIRONMENT_TABLE = "ENVIRONMENT"

TYPES_TABLE_SQL = "CREATE TABLE IF NOT EXISTS " + TYPES_TABLE_NAME + " (" \
                                                                     "id INTEGER PRIMARY KEY AUTOINCREMENT," \
                                                                     "name TEXT NOT NULL," \
                                                                     "path TEXT," \
                                                                     "parent_id INTEGER DEFAULT 0," \
                                                                     "icon TEXT" \
                                                                     ");"

HEADER_FIELDS = {
    "id": "INTEGER PRIMARY KEY AUTOINCREMENT",
    "type_id": "INTEGER NOT NULL",
    "field_name": "TEXT NOT NULL",
    "label": "TEXT",
    "align": "TEXT",
    "hidden": "BOOLEAN",
    "sort": "BOOLEAN",
    "display": "TEXT",
    "width": "INTEGER",
    "position": "INTEGER"  # Visual column position in the parts table
}

HEADER_FLD_NAMES = list(HEADER_FIELDS.keys())

HEADER_TABLE_SQL = "CREATE TABLE IF NOT EXISTS " + HEADER_TABLE_NAME + " ("  + \
    ", ".join(list(map(lambda n: n + " " + HEADER_FIELDS[n], HEADER_FIELDS.keys()))) + \
    ", CONSTRAINT fk_header_types FOREIGN KEY(type_id) REFERENCES " + TYPES_TABLE_NAME + "(id) ON DELETE CASCADE"\
    " );"


# "id INTEGER PRIMARY KEY AUTOINCREMENT," \
# "type_id INTEGER NOT NULL," \
# "field_name TEXT NOT NULL," \
# "label TEXT," \
# "align TEXT," \
# "hidden BOOLEAN," \
# "sort BOOLEAN," \
# "display TEXT" \


def GET_PARTS_TABLE_SQL():
    PARTS_TABLE_SQL = "CREATE TABLE IF NOT EXISTS " + PARTS_TABLE_NAME + " ( "
    for fname in ELEMENT_FIELDS:
        PARTS_TABLE_SQL += fname + " " + ELEMENT_FIELDS[fname] + ","
    # PARTS_TABLE_SQL = PARTS_TABLE_SQL[:-1]

    PARTS_TABLE_SQL += " CONSTRAINT fk_types FOREIGN KEY(type_id) REFERENCES "
    PARTS_TABLE_SQL +=  TYPES_TABLE_NAME + "(id) ON DELETE CASCADE"
    PARTS_TABLE_SQL += ");"
    return PARTS_TABLE_SQL


def get_parts_fld_str() -> str:
    fields_str = ""
    for key in ELEMENT_FIELDS.keys():
        fields_str += key + ","
    return fields_str[:-1]


DATASHEETS_TABLE_SQL = "CREATE TABLE IF NOT EXISTS " + DATASHEETS_TABLE_NAME + " (" \
                  "id INTEGER PRIMARY KEY AUTOINCREMENT, " \
                  "part_id INTEGER NOT NULL, " \
                  "type INTEGER default 1, " \
                  "uri TEXT, " \
                  "CONSTRAINT fk_part_ds FOREIGN KEY(part_id) REFERENCES " \
                   + PARTS_TABLE_NAME + "(id) ON DELETE CASCADE" \
                   ");"


DOC_TYPE_URL = 1
DOC_TYPE_PDF = 2
DOC_TYPE_JPG = 3
DOC_TYPE_PNG = 4
DOC_TYPE_TEXT = 5
DOC_TYPE_DEFAULT = 6

# Plugin metadata is local to this database; environment paths remain in plugins.json.
_PLUGIN_TYPE_SQL = ', '.join(repr(value) for value in sorted(PLUGIN_TYPES))
PLUGINS_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS PLUGINS (
    id TEXT PRIMARY KEY NOT NULL,
    plugin_type TEXT NOT NULL CHECK (plugin_type IN ({_PLUGIN_TYPE_SQL})),
    name TEXT NOT NULL,
    version TEXT NOT NULL,
    api_version INTEGER NOT NULL,
    system_id TEXT NOT NULL,
    system_name TEXT NOT NULL,
    description TEXT NOT NULL,
    author TEXT NOT NULL,
    enabled INTEGER NOT NULL CHECK (enabled IN (0, 1)),
    manifest_json TEXT NOT NULL
);
"""


PROJECTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS PROJECTS (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    descr TEXT,
    plugin_id TEXT,
    external_id TEXT,
    source_uri TEXT,
    last_imported_at TEXT,
    needs_reload INTEGER NOT NULL DEFAULT 1 CHECK (needs_reload IN (0, 1)),
    properties_json TEXT NOT NULL DEFAULT '{}'
);
"""

PROJECT_COMPONENTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS PROJECT_COMPONENTS (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES PROJECTS(id) ON DELETE CASCADE,
    external_id TEXT NOT NULL,
    reference TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'unknown',
    value_raw TEXT NOT NULL DEFAULT '',
    nominal_value TEXT,
    nominal_unit TEXT,
    model TEXT,
    symbol_id TEXT,
    footprint TEXT,
    description TEXT,
    in_bom INTEGER NOT NULL DEFAULT 1 CHECK (in_bom IN (0, 1)),
    on_board INTEGER NOT NULL DEFAULT 1 CHECK (on_board IN (0, 1)),
    dnp INTEGER NOT NULL DEFAULT 0 CHECK (dnp IN (0, 1)),
    properties_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE (project_id, external_id)
);
"""

PROJECT_COMPONENT_MATCHES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS PROJECT_COMPONENT_MATCHES (
    component_id INTEGER PRIMARY KEY REFERENCES PROJECT_COMPONENTS(id) ON DELETE CASCADE,
    part_id INTEGER NOT NULL REFERENCES PARTS(id) ON DELETE CASCADE,
    needs_review INTEGER NOT NULL DEFAULT 0 CHECK (needs_review IN (0, 1)),
    matched_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
"""

PROJECT_IMPORT_SCHEMA_SQL = (
    PROJECT_COMPONENTS_TABLE_SQL,
    PROJECT_COMPONENT_MATCHES_TABLE_SQL,
    "CREATE INDEX IF NOT EXISTS idx_project_component_matches_part ON PROJECT_COMPONENT_MATCHES(part_id);",
)


def _createProjectImportTables(conn):
    for sql in PROJECT_IMPORT_SCHEMA_SQL:
        conn.execute(sql)

EL_BY_PROJECT_TABLE_SQL = "CREATE TABLE IF NOT EXISTS " + EL_BY_PROJECT_TABLE + " (" \
                "id INTEGER PRIMARY KEY AUTOINCREMENT," \
                "project_id INTEGER, " \
                "part_id INTEGER, " \
                "quantity INTEGER" \
                ");"

ENVIRONMENT_TABLE_SQL = "CREATE TABLE IF NOT EXISTS " + ENVIRONMENT_TABLE + " (" \
                "id INTEGER PRIMARY KEY AUTOINCREMENT," \
                "name TEXT, " \
                "value TEXT" \
                ");"

# Current DB structure version, stored in ENVIRONMENT under ENV_DB_VERSION.
# On every scheme change: bump DB_VERSION and add a step for the new number to MIGRATIONS
# (see the end of this class section). Steps run one by one from the DB's version up to DB_VERSION.
DB_VERSION = 6
BASE_DB_VERSION = 1  # Version of a DB that has no ENV_DB_VERSION row (made before versioning)

ENV_DB_VERSION = "db_version"
ENV_ICONS_PATH = "icons_path"  # Folder with part icons, relative to the data folder (or absolute)
DEFAULT_ICONS_DIR = "icons"

# Rows every DB must have in ENVIRONMENT, with their default values
ENVIRONMENT_DEFAULTS = {
    ENV_DB_VERSION: str(DB_VERSION),
    ENV_ICONS_PATH: DEFAULT_ICONS_DIR,
}


COMPONENT_FIELDS = ('external_id', 'reference', 'kind', 'value_raw', 'nominal_value',
                    'nominal_unit', 'model', 'symbol_id', 'footprint', 'description',
                    'in_bom', 'on_board', 'dnp', 'properties_json')
REQUIREMENTS = ('kind', 'value_raw', 'nominal_value', 'nominal_unit', 'model',
                'symbol_id', 'footprint', 'description', 'in_bom', 'on_board', 'dnp')
PLUGIN_COLUMNS = ('id', 'plugin_type', 'name', 'version', 'api_version', 'system_id',
                  'system_name', 'description', 'author', 'enabled', 'manifest_json')


class DBScheme:
    """Own database access, SQL and transactions; stores a connector and type cache."""
    def __init__(self, db_file: str):
        self.db: SQLiteConnector = SQLiteConnector(db_file)
        self.Types = None

    # def createDB(self):
    #     self.db.connect()

    def connect(self):
        self.db.connect()

    def createTables(self):
        if self.db.isConnect():
            # Create Types table
            self.db.exec(TYPES_TABLE_SQL)
            self.db.exec(HEADER_TABLE_SQL)
            self.db.exec(GET_PARTS_TABLE_SQL())
            self.db.exec(DATASHEETS_TABLE_SQL)
            self.db.exec(PLUGINS_TABLE_SQL)
            self.db.exec(PROJECTS_TABLE_SQL)
            _createProjectImportTables(self.db)
            self.db.exec(EL_BY_PROJECT_TABLE_SQL)
            self.db.exec(ENVIRONMENT_TABLE_SQL)
            self.db.commit()
            self.ensureEnvironment()

    def getEnvironment(self, name: str):
        """Value of an ENVIRONMENT row, or None if the row is missing."""
        curr = self.db.select_params("SELECT value FROM " + ENVIRONMENT_TABLE + " WHERE name = ?;", (name,))
        row = curr.fetchone()
        curr.close()
        return None if row is None else row[0]

    def setEnvironment(self, name: str, value):
        """Create or update an ENVIRONMENT row."""
        if self.getEnvironment(name) is None:
            self.db.exec_insert("INSERT INTO " + ENVIRONMENT_TABLE + " (name, value) VALUES (?, ?);",
                                (name, str(value)))
        else:
            self.db.exec_insert("UPDATE " + ENVIRONMENT_TABLE + " SET value = ? WHERE name = ?;",
                                (str(value), name))

    def ensureEnvironment(self):
        """Add missing ENVIRONMENT rows with their default values. Existing rows are kept."""
        for name, value in ENVIRONMENT_DEFAULTS.items():
            if self.getEnvironment(name) is None:
                logger.info("Add ENVIRONMENT.%s = '%s'", name, value)
                self.db.exec_insert("INSERT INTO " + ENVIRONMENT_TABLE + " (name, value) VALUES (?, ?);",
                                    (name, value))

    def getDBVersion(self) -> int:
        """Scheme version stored in the DB; BASE_DB_VERSION if it was never recorded."""
        value = self.getEnvironment(ENV_DB_VERSION)
        try:
            return int(value)
        except (TypeError, ValueError):
            if value not in (None, ""):
                logger.warning("Bad ENVIRONMENT.%s = '%s', treat as %s", ENV_DB_VERSION, value, BASE_DB_VERSION)
            return BASE_DB_VERSION

    def migrate(self):
        """Upgrade an existing DB to DB_VERSION, one MIGRATIONS step per version, in order.

        The version is saved after every step, so if a step fails the DB stays at the last
        completed version and the next open continues from there.
        """
        if not self.db.isConnect():
            return
        self.db.exec(ENVIRONMENT_TABLE_SQL)
        version = self.getDBVersion()

        if version > DB_VERSION:
            logger.warning("DB version %s is newer than this program supports (%s). No upgrade.",
                           version, DB_VERSION)
            return

        for target in range(version + 1, DB_VERSION + 1):
            step = MIGRATIONS.get(target)
            if step is None:
                raise RuntimeError("No migration step to DB version {}".format(target))
            logger.info("Migrate DB: version %s -> %s", target - 1, target)
            step(self)
            self.db.commit()
            self.setEnvironment(ENV_DB_VERSION, target)

        self.ensureEnvironment()

    def loadTypes(self, parent_id: int = 0):
        if self.db.isConnect():
            curr = self.db.select(
                "SELECT id,name,path,parent_id FROM " + TYPES_TABLE_NAME + " WHERE parent_id = '" + str(parent_id) + "' ORDER BY name;")
            res = curr.fetchall()
            curr.close()
            return res

    # def getType(self, type_id):
    #     """
    #     Return tyepe record
    #     :param type_id:
    #     :return: list of fields (id,name,path,parent_id)
    #     """
    #     if self.db.isConnect():
    #         curr = self.db.select(
    #             "SELECT id,name,path,parent_id FROM " + TYPES_TABLE_NAME + " WHERE id = '" + str(type_id) + "';")
    #         row = curr.fetchone()
    #         curr.close()
    #         if row is None:
    #             er_str = "Type with ID={} not found".format(type_id)
    #             logger.error(er_str)
    #             raise ValueError(er_str)
    #         return row[0], row[1], row[2], row[3]

    def loadHeaders(self, type_id: int):
        if self.db.isConnect():
            sql = "SELECT " + ", ".join(HEADER_FIELDS.keys()) + "  FROM " + HEADER_TABLE_NAME
            sql += " WHERE type_id = '" + str(type_id) + "' ORDER BY field_name;"
            curr = self.db.select(sql)
            return curr.fetchall()
        return None

    def loadDocuments(self, partId):
        sql = "SELECT  id, part_id, type, uri "
        sql += " FROM " + DATASHEETS_TABLE_NAME + " WHERE part_id = '" + str(partId) + "'"
        sql += ";"
        curr = self.db.select(sql)
        return curr.fetchall()

    def addType(self, type):
        values = [type.name,type.path,type.parent_id]

        sql = "INSERT INTO " + TYPES_TABLE_NAME + \
              " ( name,path,parent_id ) " \
              "VALUES (?, ?, ?);"
        # logger.debug("SQL > "+sql)
        type.recId = self.db.exec_insert(sql, values)
        self.db.commit()
        return type

    def updateType(self, type_id, name, path=""):
        values = []
        if type_id is None or name == "":
            raise ValueError("Cannot rename, new name cannot be empty.")

        sql = "UPDATE " + TYPES_TABLE_NAME + " SET "
        sql += " name=?"
        values.append(name)
        if path != "":
            sql += ", path=?"
            values.append(path)
        sql += " WHERE id=" + str(type_id) + ";"
        recId = self.db.exec_insert(sql, values)
        self.db.commit()
        return recId

    def getTypeIcon(self, type_id) -> str:
        """TYPES.icon: default icon of the section (Qt resource path), '' if not set."""
        row = self.db.select_params("SELECT icon FROM " + TYPES_TABLE_NAME + " WHERE id = ?;",
                                    (int(type_id),)).fetchone()
        return row[0] if row is not None and row[0] else ""

    def setTypeIcon(self, type_id, icon: str):
        """Set TYPES.icon; empty icon clears it (the section uses the built-in rule)."""
        self.db.exec_insert("UPDATE " + TYPES_TABLE_NAME + " SET icon = ? WHERE id = ?;",
                            (icon if icon else None, int(type_id)))
        self.db.commit()

    def delType(self, recId):
        sql = "DELETE FROM " + TYPES_TABLE_NAME + " WHERE id='" + str(recId) + "';"
        self.db.exec(sql)
        # sql = "DELETE FROM " + TYPES_TABLE_NAME + " WHERE parent_id='" + str(recId) + "';"
        # self.db.exec(sql)
        self.db.commit()

    def loadPart(self, recId: int) -> dict:
        if self.db.isConnect():
            sql = "SELECT " + get_parts_fld_str()
            sql += " FROM " + PARTS_TABLE_NAME + " WHERE id = " + str(recId)
            sql += ";"
            curr = self.db.select(sql)
            return curr.fetchone()
        return None

    def loadPartsByType(self, typeId):
        sql = "SELECT " + get_parts_fld_str()
        sql += " FROM " + PARTS_TABLE_NAME + " WHERE type_id = '" + str(typeId) + "'"
        sql += " ORDER BY part_num;"
        curr = self.db.select(sql)
        return curr.fetchall()

    def addPart(self, type_id: int, els: dict) -> int:
        allow_fields = ELEMENT_FIELDS.keys()
        f_names = ""
        params = ""
        values = []
        els["type_id"] = type_id

        if "part_num" not in els.keys():
            raise RuntimeError("Field part_num Required.")

        for key in els.keys():
            try:
                if key in allow_fields:
                    f_names += key + ","
                    params += "?,"
                    values.append(els[key])
            except AttributeError:
                logger.warning("Try to assign undefined parts field %", key)

        #   Remove trail comas
        f_names = f_names[:-1]
        params = params[:-1]

        sql = "INSERT INTO " + PARTS_TABLE_NAME + " ( " + f_names + " )"
        sql += " VALUES (" + params + ");"
        recId = self.db.exec_insert(sql, values)
        # self.db.commit()
        return recId

    def updatePart(self, els):
        allow_fields = ELEMENT_FIELDS.keys()
        assignments = []
        values = []
        for key in els.keys():
            if key not in allow_fields:
                logger.warning("Try to assign undefined parts field %s", key)
            elif key != "id":
                assignments.append(key + " = ?")
                values.append(els[key])

        values.append(els['id'])
        sql = "UPDATE " + PARTS_TABLE_NAME + " SET " + ", ".join(assignments) + " WHERE id = ?;"
        recId = self.db.exec_insert(sql, values)
        self.db.commit()
        return recId

    def ensurePartNotInProjects(self, partId):
        row = self.db.execute(
            "SELECT 1 FROM EL_BY_PROJECT WHERE part_id = ? LIMIT 1;", (partId,)).fetchone()
        if row is not None:
            raise PartInProjectsError(QT_TRANSLATE_NOOP("PartsDB", 'This part is used in projects and cannot be deleted.'))

    def countProjectComponentMatches(self, partId):
        return self.db.execute(
            "SELECT count(*) FROM PROJECT_COMPONENT_MATCHES WHERE part_id = ?;", (partId,)).fetchone()[0]

    def delPart(self, partId):
        # Foreign-key enforcement may be disabled on older databases. Explicitly remove
        # dependent records in one transaction; linked files are never deleted.
        with self.db.transaction():
            if not self.db.in_transaction:
                self.db.begin(immediate=True)
            self.ensurePartNotInProjects(partId)
            self.db.execute("DELETE FROM PROJECT_COMPONENT_MATCHES WHERE part_id = ?;", (partId,))
            self.db.execute("DELETE FROM DATASHEETS WHERE part_id = ?;", (partId,))
            self.db.execute("DELETE FROM PARTS WHERE id = ?;", (partId,))

    def addDocument(self, parentId, type, link ):
        values = []
        values.append(parentId)
        values.append(type)
        values.append(link)

        sql = "INSERT INTO " + DATASHEETS_TABLE_NAME + " ( part_id, type, uri )"
        sql += " VALUES (?, ?, ?);"
        recId = self.db.exec_insert(sql, values)
        self.db.commit()
        return recId

    def addHeader(self, hdr_dict) -> int:
        fname = ""
        vholder = ""
        values = []
        for key in hdr_dict.keys():
            if key != "id":
                fname += key + ","
                vholder += "?,"
                values.append(hdr_dict[key])

        fname = fname[:-1]
        vholder = vholder[:-1]

        sql = "INSERT INTO " + HEADER_TABLE_NAME + "("+fname+") "
        sql += "VALUES ("+vholder+");"

        logger.debug("SQL: %s", sql)
        recId = self.db.exec_insert(sql, values)
        self.db.commit()
        return recId

    def updateHeader(self, hdr_dict:dict):
        sql = ""
        values = []
        for key in hdr_dict.keys():
            try:
                if key != "id":
                    sql += key + " = ?,"
                    values.append(hdr_dict[key])
            except AttributeError:
                logger.warning("Try to assign undefined parts field %", key)

        #   Remove trail comas
        sql = sql[:-1]
        sql = "UPDATE " + HEADER_TABLE_NAME + "  SET " + sql + " WHERE id=" + str(hdr_dict['id']) + ";"
        recId = self.db.exec_insert(sql, values)
        self.db.commit()
        return recId

    def delDocument(self, docId):
        sql = "DELETE FROM " + DATASHEETS_TABLE_NAME + " WHERE id='" + str(docId) + "';"
        self.db.exec(sql)
        self.db.commit()

    def chPartsType(self, partId, newParentId):
        sql = "UPDATE " + PARTS_TABLE_NAME + "  SET type_id  = ? WHERE id=" + str(partId) + ";"
        recId = self.db.exec_insert(sql, [newParentId])
        self.db.commit()
        return partId

    def partSearch(self, searchStr):
        #"select * from tovari where [ИмяПоля] like '%" + TextBox.Text + "%'"
        sql = "SELECT " + get_parts_fld_str() + " FROM " + PARTS_TABLE_NAME + \
              " WHERE part_num LIKE ? OR device_code LIKE ? OR description LIKE ?;"
        pattern = "%" + searchStr + "%"
        return self.db.select_params(sql, [pattern, pattern, pattern]).fetchall()

    def disconnect(self):
        self.db.disconnect()


    @classmethod
    def using(cls, database) -> 'DBScheme':
        """Accept DBScheme or a borrowed sqlite3.Connection; never open or copy a DB."""
        if isinstance(database, cls):
            return database
        scheme = cls('')
        scheme.db = SQLiteConnector.from_connection(database)
        return scheme

    def isConnected(self) -> bool:
        """Return whether this scheme has a connection, without running SQL."""
        return self.db.isConnect()

    @contextmanager
    def transaction(self, foreign_keys: bool = False):
        """Yield this scheme; reject pending transactions, commit success or roll back errors.

        foreign_keys (bool): enable FK checks before starting when True.
        """
        with self.db.transaction(require_idle=True, foreign_keys=True if foreign_keys else None):
            yield self

    def loadProjectRows(self) -> list:
        """Return project tuples ordered by name/id; no parameters or writes."""
        return self.db.execute(
            'SELECT id, name, descr, plugin_id, external_id, source_uri, '
            'last_imported_at, needs_reload, properties_json FROM PROJECTS '
            'ORDER BY name COLLATE NOCASE, id').fetchall()

    def loadIconTypeRows(self) -> list:
        """Return (id, name, parent_id, icon) tuples; old schemas return NULL icons."""
        columns = [row[1] for row in self.db.table_info('TYPES')]
        icon_column = 'icon' if 'icon' in columns else 'NULL'
        return self.db.execute('SELECT id,name,parent_id,' + icon_column + ' FROM TYPES').fetchall()

    def loadProjectComponents(self, project_id) -> dict:
        """Return component row dictionaries keyed by external_id; ID is int or None."""
        if project_id is None:
            return {}
        rows = self.db.execute('SELECT id, ' + ', '.join(COMPONENT_FIELDS) +
                                    ' FROM PROJECT_COMPONENTS WHERE project_id=? ORDER BY id', (project_id,)).fetchall()
        keys = ('id', *COMPONENT_FIELDS)
        return {row[1]: dict(zip(keys, row)) for row in rows}

    @staticmethod
    def _requirementProperties(properties_json: str) -> dict:
        """Decode JSON properties, excluding duplicated fields and diagnostic UUIDs."""
        return {key: value for key, value in json.loads(properties_json).items()
                if key not in ('Reference', 'Value', 'Footprint', 'Description', 'Datasheet', 'kicad_symbol_uuids')}

    def saveImportedProject(self, project: dict, rows: list, plugin_id: str,
                            source_uri: str, project_id=None) -> int:
        """Atomically save a validated project dict and component dicts; preserve IDs/matches.

        project uses name, descr, external_id, properties_json. rows follow
        COMPONENT_FIELDS. project_id is an existing int ID or None for a new card.
        """
        now = datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
        conn = self.db
        with self.transaction(foreign_keys=True):
            previous = self.loadProjectComponents(project_id)
            values = (project['name'], project['descr'], plugin_id, project['external_id'],
                      source_uri, now, project['properties_json'])
            if project_id is None:
                cursor = conn.execute(
                    'INSERT INTO PROJECTS(name,descr,plugin_id,external_id,source_uri,'
                    'last_imported_at,needs_reload,properties_json) VALUES (?,?,?,?,?,?,0,?)', values)
                project_id = cursor.lastrowid
            else:
                old = conn.execute('SELECT plugin_id FROM PROJECTS WHERE id=?', (project_id,)).fetchone()
                if not old:
                    raise DBError('Project no longer exists')
                if old[0] not in (None, plugin_id):
                    raise DBError('Switch the project plugin before importing with another plugin')
                conn.execute('UPDATE PROJECTS SET name=?,descr=?,plugin_id=?,external_id=?,source_uri=?,'
                             'last_imported_at=?,needs_reload=0,properties_json=? WHERE id=?', values + (project_id,))
            for row in rows:
                old = previous.pop(row['external_id'], None)
                if old:
                    if (any(row[key] != old[key] for key in REQUIREMENTS) or
                            self._requirementProperties(row['properties_json']) !=
                            self._requirementProperties(old['properties_json'])):
                        conn.execute('UPDATE PROJECT_COMPONENT_MATCHES SET needs_review=1 WHERE component_id=?', (old['id'],))
                    conn.execute('UPDATE PROJECT_COMPONENTS SET ' +
                                 ', '.join(key + '=?' for key in COMPONENT_FIELDS) + ' WHERE id=?',
                                 tuple(row[key] for key in COMPONENT_FIELDS) + (old['id'],))
                else:
                    conn.execute('INSERT INTO PROJECT_COMPONENTS(project_id, ' +
                                 ', '.join(COMPONENT_FIELDS) + ') VALUES (' +
                                 ', '.join('?' for _ in range(len(COMPONENT_FIELDS) + 1)) + ')',
                                 (project_id,) + tuple(row[key] for key in COMPONENT_FIELDS))
            for removed in previous.values():
                conn.execute('DELETE FROM PROJECT_COMPONENTS WHERE id=?', (removed['id'],))
        return project_id

    def deleteImportedProject(self, project_id: int):
        """Delete one project's positions, matches and legacy links; preserve stock cards."""
        with self.transaction(foreign_keys=True):
            self.db.execute('DELETE FROM EL_BY_PROJECT WHERE project_id=?', (project_id,))
            self.db.execute('DELETE FROM PROJECTS WHERE id=?', (project_id,))

    def loadProjectMatches(self, project_id: int) -> dict:
        """Return confirmed stock matches keyed by component ID for an int project ID."""
        rows = self.db.execute(
            'SELECT m.component_id,m.part_id,m.needs_review,p.part_num '
            'FROM PROJECT_COMPONENT_MATCHES m JOIN PROJECT_COMPONENTS c ON c.id=m.component_id '
            'JOIN PARTS p ON p.id=m.part_id WHERE c.project_id=?', (project_id,)).fetchall()
        return {row[0]: {'part_id': row[1], 'needs_review': row[2], 'part_num': row[3]} for row in rows}

    def setProjectMatch(self, component_id: int, part_id=None):
        """Confirm a match to an int stock ID, or delete it when part_id is None."""
        with self.transaction(foreign_keys=True):
            if part_id is None:
                self.db.execute('DELETE FROM PROJECT_COMPONENT_MATCHES WHERE component_id=?', (component_id,))
            else:
                self.db.execute(
                    'INSERT INTO PROJECT_COMPONENT_MATCHES(component_id,part_id,needs_review) VALUES (?,?,0) '
                    'ON CONFLICT(component_id) DO UPDATE SET part_id=excluded.part_id,needs_review=0,'
                    "matched_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')", (component_id, part_id))

    @staticmethod
    def _pluginValues(metadata: dict) -> tuple:
        """Order a plugin metadata dict according to PLUGIN_COLUMNS; no DB operations."""
        return tuple(metadata[key] for key in PLUGIN_COLUMNS)

    def storePluginMetadata(self, metadata: dict):
        """Upsert one validated PLUGINS record inside the caller's transaction; no commit."""
        self.db.execute('INSERT INTO PLUGINS (' + ','.join(PLUGIN_COLUMNS) + ') VALUES (' +
                             ','.join('?' for _ in PLUGIN_COLUMNS) + ') ON CONFLICT(id) DO UPDATE SET ' +
                             ','.join(key + '=excluded.' + key for key in PLUGIN_COLUMNS if key != 'id'),
                             self._pluginValues(metadata))

    def deletePluginMetadata(self, plugin_id: str):
        """Delete a PLUGINS metadata row by string ID; keep projects and do not commit."""
        self.db.execute('DELETE FROM PLUGINS WHERE id=?', (plugin_id,))

    def switchProjectPlugin(self, old_id: str, new_id: str):
        """Switch linked projects between string plugin IDs and require reload; no commit."""
        self.db.execute('UPDATE PROJECTS SET plugin_id=?,needs_reload=1 WHERE plugin_id=?', (new_id, old_id))

    def syncPluginMetadata(self, records: list):
        """Sync validated metadata dicts in the caller's transaction and flag changed installs."""
        stored = {row[0]: row for row in self.db.execute('SELECT ' + ','.join(PLUGIN_COLUMNS) + ' FROM PLUGINS')}
        for record in records:
            old = stored.pop(record['id'], None)
            values = self._pluginValues(record)
            if old != values:
                self.storePluginMetadata(record)
                if old is None or any(old[index] != values[index] for index in (1, 3, 4, 5)):
                    self.db.execute('UPDATE PROJECTS SET needs_reload=1 WHERE plugin_id=?', (record['id'],))
        for plugin_id in stored:
            self.deletePluginMetadata(plugin_id)


class Type:
    def __init__(self, scheme: DBScheme, recId: int, name: str, path: str, parent):
        self.recId = recId
        self.name = name
        self.path = path
        self.parent = parent
        self.parent_id = 0 if parent is None else parent.recId
        self.children = None
        self.scheme = scheme
        self.headers: Headers = None

    def __eq__(self, other):
        return self.recId == other.recId
        # if type(other).__name__ == type(self).__name__:
        #     return self.recId == other.recID
        # return self.name == other

    def __repr__(self):
        return self.name

    def __gt__(self, other):
        return self.name > other.name

    def __ge__(self, other):
        return self.name >= other.name

    def __le__(self, other):
        return self.name <= other.name

    def __lt__(self, other):
        return self.name < other.name

    def getChildren(self):
        if self.children is None:
            self.children = Types(self.scheme, self)
        return self.children

    def isChildren(self):
        if self.children is None:
            self.getChildren()
        return len(self.children) != 0

    def addChild(self, name, path):
        type = Type(self.scheme, 0, name, path, self)
        type = self.scheme.addType(type)
        if self.children is None:
            self.children.reload()
        else:
            self.children = Types(self.scheme, self)
        return type

    def appendExistChild(self, partId: int):
        self.scheme.chPartsType(partId, self.recId)

    def getHeaders(self):
        if self.headers is None:
            self.headers = Headers(self.scheme, self.recId)
        return self.headers

    def refreshHeaders(self):
        self.headers = Headers(self.scheme, self.recId)
        return self.headers

    def propagateHeaders(self):
        """Replace every descendant's column settings with this type's settings."""
        headers = self.refreshHeaders()
        fields = [name for name in HEADER_FLD_NAMES if name not in ("id", "type_id")]
        # Include lazy defaults, so missing source rows also overwrite child overrides.
        settings = [tuple(headers[name][field] for field in fields)
                    for name in ELEMENT_FLD_NAMES[2:]]
        descendants = []
        pending = list(self.getChildren())
        while pending:
            child = pending.pop()
            descendants.append(child)
            pending.extend(child.getChildren())

        conn = self.scheme.db
        with conn.transaction():
            for child in descendants:
                conn.execute("DELETE FROM HEADERS WHERE type_id = ?", (child.recId,))
                conn.executemany(
                    "INSERT INTO HEADERS (type_id, {}) VALUES ({})".format(
                        ", ".join(fields), ", ".join("?" for _ in range(len(fields) + 1))),
                    [(child.recId,) + values for values in settings])
        for child in descendants:
            child.refreshHeaders()
        return len(descendants)

    def rename(self, new_name):
        self.scheme.updateType(self.recId, new_name, self.path)
        self.name = new_name


class Types:
    def __init__(self, scheme: DBScheme, parent: Type = None):
        self.scheme = scheme
        self.cursor = None
        self.typesAr = []
        self.IterAr = []
        # self.parentObj = parent_obj
        self.parent: Type = parent
        self.index = 0
        self.reload()

    def reload(self):
        self.typesAr = []
        self.IterAr = []

        parentId = 0
        if self.parent is not None:
            parentId = str(self.parent.recId)

        for row in self.scheme.loadTypes(parentId):

            theType = Type(self.scheme, row[0], row[1], row[2], self.parent)
            self.typesAr.append(theType)

    def __len__(self):
        return len(self.typesAr)

    def __iter__(self):
        self.index = 0
        self.IterAr = []
        for item in sorted(self.typesAr):
            self.IterAr.append(item)
        return self

    def __next__(self) -> Type:
        if self.index < len(self.IterAr):
            res = self.IterAr[self.index]
            self.index += 1
            return res
        else:
            self.IterAr = []
            raise StopIteration

    def __getitem__(self, index):
        if type(index) == int:
            return self.typesAr[index]
        else:
            for theType in self.typesAr:
                if theType.name == index:
                    return theType
            raise IndexError

    def getNodeById(self, db_id):
        for theType in self.typesAr:
            if theType.recId == db_id:
                return theType
        raise IndexError

    # def getByName(self, name) -> Type:
    #     for theType in self.typesAr:
    #         if theType.name == name:
    #             return theType
    #     return None

    def addNode(self, name) -> Type:
        thePath = self.parent.path + " " + name if self.parent is not None else name
        theType = Type(self.scheme, 0, name, thePath, self.parent)
        theType = self.scheme.addType(theType)
        bisect.insort(self.typesAr, theType)
        # self.typesAr.append(theType)
        # self.typesAr.insort = sorted(self.typesAr)
        return theType

    def addNodeByPath(self, name) -> Type:
        path = self.parent.path + " " + name if self.parent is not None else name
        # parentId = 0 if self.parent is None else self.parent.recId
        theType = Type(self.scheme, 0, name, path, self.parent)
        theType = self.scheme.addType(theType)
        # self.typesAr.append(theType)
        bisect.insort(self.typesAr, theType)
        return theType

    def deleteNode(self, theType: Type):
        if theType in self.typesAr:
            # self.scheme.
            pass


# ---------------------------------------------------------------------------------------------
#   DB upgrade steps. MIGRATIONS[n] upgrades a DB from version n-1 to n.
#   Write steps so that re-running them is harmless (check before ALTER etc.).
# ---------------------------------------------------------------------------------------------

def _migrate_to_2(scheme: DBScheme):
    """v2: HEADERS.position (visual column order, icon column first) and ENVIRONMENT defaults."""
    columns = [row[1] for row in scheme.db.table_info(HEADER_TABLE_NAME)]
    if columns and "position" not in columns:
        scheme.db.exec("ALTER TABLE " + HEADER_TABLE_NAME + " ADD COLUMN position INTEGER;")
        for position, field_name in enumerate(defaultColumnOrder()):
            scheme.db.exec_insert("UPDATE " + HEADER_TABLE_NAME + " SET position = ? WHERE field_name = ?;",
                                  (position, field_name))
    if scheme.getEnvironment(ENV_ICONS_PATH) is None:
        scheme.setEnvironment(ENV_ICONS_PATH, ENVIRONMENT_DEFAULTS[ENV_ICONS_PATH])


def _migrate_to_3(scheme: DBScheme):
    """v3: TYPES.icon, the default part icon chosen for a section."""
    columns = [row[1] for row in scheme.db.table_info(TYPES_TABLE_NAME)]
    if columns and "icon" not in columns:
        scheme.db.exec("ALTER TABLE " + TYPES_TABLE_NAME + " ADD COLUMN icon TEXT;")


def _migrate_to_4(scheme: DBScheme):
    """v4: currency has TEXT affinity; preserve NULL and cast existing values."""
    conn = scheme.db
    columns = conn.table_info('PARTS')
    currency = next(row for row in columns if row[1] == 'currency')
    if currency[2].upper() == 'TEXT':
        return
    sql = conn.table_definition('PARTS')
    sql, count = re.subn(r'\bcurrency\s+TXT\b', 'currency TEXT', sql, flags=re.IGNORECASE)
    if count != 1:
        raise RuntimeError('Unexpected PARTS.currency declaration')
    create_sql = re.sub(r'^(CREATE\s+TABLE\s+)(?:"PARTS"|PARTS)\b',
                        r'\1PARTS_currency_v4', sql, count=1, flags=re.IGNORECASE)
    objects = conn.schema_objects('PARTS')
    sequence = conn.sequence_value('PARTS')
    names = ', '.join('"' + row[1].replace('"', '""') + '"' for row in columns)
    values = ', '.join('CAST(currency AS TEXT)' if row[1] == 'currency' else
                       '"' + row[1].replace('"', '""') + '"' for row in columns)
    foreign_keys = conn.get_foreign_keys()
    conn.commit()
    conn.set_foreign_keys(False)
    try:
        conn.begin(immediate=True)
        existing_violations = conn.foreign_key_violations()
        conn.execute(create_sql)
        conn.execute('INSERT INTO PARTS_currency_v4 (' + names + ') SELECT ' + values + ' FROM PARTS')
        conn.execute('DROP TABLE PARTS')
        conn.execute('ALTER TABLE PARTS_currency_v4 RENAME TO PARTS')
        for object_sql in objects:
            conn.execute(object_sql)
        if sequence is not None:
            conn.preserve_sequence('PARTS', sequence)
        if conn.foreign_key_violations() - existing_violations:
            raise RuntimeError('Foreign key violations after currency migration')
        conn.execute("UPDATE ENVIRONMENT SET value='4' WHERE name=?", (ENV_DB_VERSION,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.set_foreign_keys(foreign_keys)


def _legacyProjectUri(value, db_file):
    """Retain existing URIs; resolve old relative paths against the database folder."""
    if not value or urllib.parse.urlsplit(value).scheme:
        return value
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = Path(db_file).absolute().parent / path
    return path.absolute().as_uri()


def _migrate_to_5(scheme: DBScheme):
    """v5: URI-based projects, imported positions, and removable stock matches."""
    conn = scheme.db
    conn.commit()
    foreign_keys = conn.get_foreign_keys()
    conn.set_foreign_keys(False)
    try:
        with conn.transaction():
            conn.begin(immediate=True)
            violations = conn.foreign_key_violations()
            columns = {row[1] for row in conn.table_info('PROJECTS')}
            if "schematic_path" in columns:
                objects = conn.schema_objects('PROJECTS')
                sequence = conn.sequence_value('PROJECTS')
                conn.execute(PROJECTS_TABLE_SQL.replace("PROJECTS (", "PROJECTS_v5 (", 1))
                for project_id, name, description, path in conn.execute(
                        "SELECT id, name, descr, schematic_path FROM PROJECTS;").fetchall():
                    conn.execute("INSERT INTO PROJECTS_v5(id, name, descr, source_uri) VALUES (?, ?, ?, ?);",
                                 (project_id, name, description, _legacyProjectUri(path, scheme.db.dbPath)))
                conn.execute("DROP TABLE PROJECTS;")
                conn.execute("ALTER TABLE PROJECTS_v5 RENAME TO PROJECTS;")
                if sequence is not None:
                    conn.preserve_sequence('PROJECTS', sequence)
                for sql in objects:
                    conn.execute(sql)
            else:
                conn.execute(PROJECTS_TABLE_SQL)
            _createProjectImportTables(conn)
            if conn.foreign_key_violations() - violations:
                raise RuntimeError("Foreign key violations after project import migration")
            # The schema and version must commit together, without connector helpers.
            conn.execute("UPDATE ENVIRONMENT SET value='5' WHERE name=?;", (ENV_DB_VERSION,))
    finally:
        conn.set_foreign_keys(foreign_keys)


def _migrate_to_6(scheme: DBScheme):
    """v6: installed plugin metadata and its declared functional type."""
    conn = scheme.db
    conn.commit()
    with conn.transaction():
        conn.begin(immediate=True)
        conn.execute(PLUGINS_TABLE_SQL)
        conn.execute("UPDATE ENVIRONMENT SET value='6' WHERE name=?", (ENV_DB_VERSION,))


MIGRATIONS = {
    2: _migrate_to_2,
    3: _migrate_to_3,
    4: _migrate_to_4,
    5: _migrate_to_5,
    6: _migrate_to_6,
}


class Header:
    def __init__(self, scheme: DBScheme, type_id, field_name):
        self.scheme = scheme
        self.id = -1
        for key in HEADER_FLD_NAMES:
            if key != "id":
                if HEADER_FIELDS[key] == "BOOLEAN":
                    self.__dict__[key] = False
                elif HEADER_FIELDS[key] == "INTEGER":
                    self.__dict__[key] = 0
                else:
                    self.__dict__[key] = ""

        self.changed = False
        self.changedFields = set()  # fields set since the last load/save: only they are written by save()
        self.type_id = type_id
        self.field_name = field_name
        self.position = defaultHeaderPosition(field_name)

    def setFields(self, el):
        for fldName in HEADER_FLD_NAMES:
            value = el[int(HEADER_FLD_NAMES.index(fldName))]
            if HEADER_FIELDS[fldName] == "BOOLEAN":
                self.__dict__[fldName] = True if value == 1 else False
            elif fldName == "position" and value in (None, ""):
                self.position = defaultHeaderPosition(self.field_name)
            elif HEADER_FIELDS[fldName] == "INTEGER":
                self.__dict__[fldName] = int(value)
            else:
                self.__dict__[fldName] = value

    def getFields(self) -> dict:
        hds_dict: dict = {}
        for fldName in HEADER_FLD_NAMES:
            hds_dict[fldName] = self.__dict__[fldName]
        return hds_dict

    def __getitem__(self, index):
        if type(index) == int:
            return self.__dict__[HEADER_FLD_NAMES[index]]
        else:
            return self.__dict__[index]

    def __setitem__(self, index, value):
        # def setFiled(self, name, value):
        if type(index) == int:
            index = HEADER_FLD_NAMES[index]
        self.__dict__[index] = value
        self.changed = True
        self.changedFields.add(index)

    def save(self):
        """Write the header. An existing one writes only the fields set since it was loaded,
        so a stale copy (e.g. the parts table saving a column width) does not overwrite
        fields changed elsewhere (e.g. 'hidden' in the header edit dialog)."""
        if self.changed:
            if self.id < 0:
                self.id = self.scheme.addHeader(self.getFields())
            else:
                fields = {"id": self.id}
                fields.update({name: self.__dict__[name] for name in self.changedFields if name != "id"})
                if len(fields) > 1:
                    self.scheme.updateHeader(fields)
        self.changed = False
        self.changedFields = set()


class Headers:
    def __init__(self, scheme: DBScheme, type_id: int):
        self.scheme = scheme
        self.type_id: int = type_id
        self.headersAr = {}
        self.index = 0
        self.IterAr = []

        # Resolve each missing column from its nearest configured ancestor.
        # Inherited headers belong to the requested type: editing one inserts a
        # local override instead of updating the ancestor's database row.
        current_id = self.type_id
        visited = set()
        while current_id is not None and current_id not in visited:
            visited.add(current_id)
            for row in self.scheme.loadHeaders(current_id):
                fldName = row[HEADER_FLD_NAMES.index("field_name")]
                if fldName in self.headersAr:
                    continue
                hdr = Header(self.scheme, type_id, fldName)
                hdr.setFields(list(row))
                if current_id != self.type_id:
                    hdr.id = -1
                    hdr.type_id = self.type_id
                self.headersAr[fldName] = hdr
            parent = self.scheme.db.select_params(
                "SELECT parent_id FROM TYPES WHERE id = ?;", (current_id,)).fetchone()
            current_id = parent[0] if parent and parent[0] else None

    def __len__(self):
        return len(self.headersAr.keys())

    def __iter__(self):
        self.index = 0
        self.IterAr = []
        for item in self.headersAr.keys():
            self.IterAr.append(self.headersAr[item])
        return self

    def __next__(self) -> Header:
        if self.index < len(self.IterAr):
            res = self.IterAr[self.index]
            self.index += 1
            return res
        else:
            self.IterAr = []
            raise StopIteration

    def __getitem__(self, field_name) -> Header:
        try:
            hdr = self.headersAr[field_name]
            return hdr

        except KeyError as e:
            if field_name not in ELEMENT_FLD_NAMES:
                raise e

            hdr = Header(self.scheme, self.type_id, field_name)
            if hdr["display"] == "":
                hdr["display"] = ELEMENT_FIELDS_DISPLAY[field_name]

            self.headersAr[field_name] = hdr
            return hdr

    def save(self):
        for hdrName in self.headersAr.keys():
            self.headersAr[hdrName].save()


def extToDocType(ext: str):
    if ext.lower() == "pdf":
        return DOC_TYPE_PDF
    elif ext.lower() == "jpg":
        return DOC_TYPE_JPG
    elif ext.lower() == "jpeg":
        return DOC_TYPE_JPG
    elif ext.lower() == "png":
        return DOC_TYPE_PNG
    elif ext.lower() == "text":
        return DOC_TYPE_TEXT
    elif ext.lower() == "txt":
        return DOC_TYPE_TEXT
    elif ext.lower() == "html":
        return DOC_TYPE_URL
    elif ext.lower() == "htm":
        return DOC_TYPE_URL
    return DOC_TYPE_DEFAULT


def getExt(filename) -> str:
    file_name, file_extension = os.path.splitext(filename)
    return str(file_extension)[1:]


def getTypeByExt(filename):
    ext = getExt(filename).lower()
    if ext == "pdf":
        return DOC_TYPE_PDF
    elif ext == "jpg":
        return DOC_TYPE_JPG
    elif ext == "jpeg":
        return DOC_TYPE_JPG
    elif ext == "png":
        return DOC_TYPE_PNG
    elif ext == "txt":
        return DOC_TYPE_TEXT
    elif ext == "text":
        return DOC_TYPE_TEXT
    else:
        return DOC_TYPE_DEFAULT


class Document:
    def __init__(self, scheme: DBScheme, parentPart):
        self.scheme: DBScheme = scheme
        self.id = -1
        self.type = None
        self.link = None
        self.parentId = None
        self.parent = parentPart    # Part object
        if self.parent is not None:
            self.parentId = parentPart.id

    def load(self, parent):
        self.parent = parent

    def getLink(self):
        return self.link

    def setLink(self, link):
        self.link = link

    def getType(self):
        return self.type

    def setType(self, type):
        self.type = type

    def getLinkExt(self):
        filename, file_extension = os.path.splitext(self.link)
        return file_extension[1:]

    def save(self):
        # TODO add save
        pass


class Documents:

    def __init__(self, scheme: DBScheme, parent):
        self.scheme: DBScheme = scheme
        self.parent = parent
        self.parentId = parent.id
        self.documentsAr = []

    def load(self, parentPart = None):
        parentObj = self.parent if parentPart is None else parentPart

        for doc in self.scheme.loadDocuments(parentObj.id):
            docObj = Document(self.scheme, parentObj)
            docObj.id = doc[0]
            docObj.parentId = doc[1]
            docObj.type = doc[2]
            docObj.link = doc[3]
            self.documentsAr.append(docObj)

    def __getitem__(self, id):
        for theDoc in self.documentsAr:
            if theDoc.id == id:
                return theDoc
        raise IndexError("Not found document with id {} attached to part {}".format(id, self.parent["part_num"]))

    def append(self, theDoc: Document):
        id = self.scheme.addDocument(theDoc.parentId,theDoc.type,theDoc.link)
        theDoc.id = id
        self.documentsAr.append(theDoc)
        return theDoc

    def delete(self, theDoc: Document):
        for doc in self.documentsAr:
            if doc.id == theDoc.id:
                self.documentsAr.remove(theDoc)
                self.scheme.delDocument(theDoc.id)
                return
        raise IndexError("Not found document with id {} attached to part {}".format(id, self.parent["part_num"]))


class Part:
    """
    -------------------------------------------------------------------
        Class Part. Represent main catalogs element - Electronic Part
    -------------------------------------------------------------------
    """
    def __init__(self, scheme: DBScheme, recId: int = -1):
        self.id = recId
        self.scheme = scheme
        for key in ELEMENT_FIELDS.keys():
            if key != "id":
                self.__dict__[key] = ""
        self.changed = False
        self.documents = None

    def getType(self):
        typeId = self.__getitem__("type_id")

    def loadDatas(self):
        if self.id <= 0:
            raise RuntimeError("Unknown parts ID. Cannot load data.")

        el = self.scheme.loadPart(self.id)
        f_names = list(ELEMENT_FIELDS)

        for pos in range(0, len(el)):
            self.__setattr__(f_names[int(pos)], el[pos])

    def copyData(self, fl: dict):
        allow_field = ELEMENT_FIELDS.keys()
        for key in fl.keys():
            if key in allow_field:
                self.__dict__[key] = fl[key]
            else:
                logger.warning("Try to assign undefined parts field %", key)

    def __getitem__(self, index):
        return self.__dict__[index]

    def __setitem__(self, key, value):
        if ELEMENT_FIELDS[key].strip() == "BOOLEAN" and type(value) == bool:
            self.__dict__[key] = value
        elif ELEMENT_FIELDS[key].strip() == "INTEGER" and type(value) == int:
            self.__dict__[key] = value
        elif ELEMENT_FIELDS[key].strip() == "TEXT" and type(value) == str:
            self.__dict__[key] = value
        elif ELEMENT_FIELDS[key].strip() == "REAL" and (type(value) == int or type(value) == float):
            self.__dict__[key] = value
        else:
            raise ValueError("Incorrect parameter type for {}. got type {}".format(key, type(value)))
        self.changed = True

    def save(self):
        if self.changed:
            els = {}
            for key in ELEMENT_FIELDS.keys():
                els[key] = self.__dict__[key]
            self.scheme.updatePart(els)

    def getID(self) -> int:
        return self.id

    def getDocuments(self) -> Documents:
        if self.documents is None:
            self.documents = Documents(self.scheme, self)
            self.documents.load()
        return self.documents

    def addDocument(self, file, type = DOC_TYPE_DEFAULT) -> Document:
        # filename, file_extension = os.path.splitext(file)
        # extToDocType(file_extension)
        # docType: int = type if type != DOC_TYPE_DEFAULT else extToDocType(file)
        theDoc = Document(self.scheme, self)
        theDoc.type = type if type != DOC_TYPE_DEFAULT else extToDocType(file)
        theDoc.link = file
        theDoc = self.documents.append(theDoc)
        # DocId = self.scheme.addDocument(self.id, docType, str(file))
        # # self.documents.load()
        # # self.documents[DocId]
        # self.documents
        return theDoc

    def removeDocument(self, theDoc: Document):
        if theDoc.parentId == self.id:
            self.scheme.delDocument(theDoc.id)
        else:
            raise RuntimeError("Document id %s not found for current part %s ".format(theDoc.id,self.id))


class Parts:
    def __init__(self, scheme: DBScheme):
        self.scheme = scheme
        self.partsAr = []
        self.IterAr = []

    def append(self, thePart: Part):
        self.partsAr.append(thePart)

    def __len__(self):
        return len(self.partsAr)

    def __iter__(self):
        self.index = 0
        self.IterAr = []
        for item in self.partsAr:
            self.IterAr.append(item)
        return self

    def __next__(self) -> Part:
        if self.index < len(self.IterAr):
            res = self.IterAr[self.index]
            self.index += 1
            return res
        else:
            self.IterAr = []
            raise StopIteration

    def __getitem__(self, index):
        if type(index) == int:
            return self.partsAr[index]
        else:
            for thePart in self.partsAr:
                if thePart.part_num == index:
                    return thePart
            raise IndexError

    # def sort(self, fieldName: str, sortOrder: bool):
    #
    #     def sort_func(Item):
    #         retval = Item[fieldName]
    #         if retval is None:
    #             retval = ""
    #         else:
    #             retval = str(retval)
    #
    #         if self.cover_el.headers.get_header(column+1).is_num():
    #             if retval == "":
    #                 retval = 0
    #             else:
    #                 retval = retval.replace(",", ".")
    #                 # print("Sort as value |{}|".format(retval))
    #                 retval = float(retval)
    #
    #         return retval
    #
    #     self.partsAr.sort(reverse=sortOrder,
    #                       key = lambda partFld: partFld[fieldName].strip() if partFld[fieldName] is not None else "" )

    def getByID(self, idx) -> Part:
        for thePart in self.partsAr:
            if thePart.getID() == idx:
                return thePart
        raise IndexError


class DBFactory:

    def __init__(self, db_file: str, data_path: str = None):
        self.rootTypes = None
        self.db_file = db_file
        # Data folder: base for relative paths stored in the DB (icons). Defaults to the DB's folder.
        self.dataPath = os.path.abspath(data_path) if data_path else os.path.dirname(os.path.abspath(db_file))
        self.scheme: DBScheme = DBScheme(self.db_file)
        self.idPos = ELEMENT_FLD_NAMES.index("id")

        try:
            if not self.isDB():
                self.scheme.connect()
                self.scheme.createTables()
                self.scheme.db.commit()
            else:
                self.scheme.connect()
                self.scheme.migrate()
        except Exception:
            if self.scheme.db.isConnect():
                self.scheme.disconnect()
            raise

    def isDB(self) -> bool:
        return True if os.path.exists(self.db_file) else False

    def getIconsDir(self, create: bool = True) -> str:
        """Absolute icons folder: ENVIRONMENT.icons_path relative to the data folder.

        An empty setting is replaced with DEFAULT_ICONS_DIR and saved; the folder is created if missing.
        """
        iconsPath = self.scheme.getEnvironment(ENV_ICONS_PATH)
        if not iconsPath:
            iconsPath = DEFAULT_ICONS_DIR
            self.scheme.setEnvironment(ENV_ICONS_PATH, iconsPath)
            logger.info("Set ENVIRONMENT.%s = '%s'", ENV_ICONS_PATH, iconsPath)
        iconsPath = os.path.expanduser(iconsPath)
        if not os.path.isabs(iconsPath):
            iconsPath = os.path.join(self.dataPath, iconsPath)
        iconsPath = os.path.normpath(iconsPath)
        if create and not os.path.isdir(iconsPath):
            logger.info("Create icons folder %s", iconsPath)
            os.makedirs(iconsPath, exist_ok=True)
        return iconsPath

    def resolveIconPath(self, icon: str) -> str:
        """Full path of a part's icon: PARTS.icon is relative to the icons folder (absolute is kept)."""
        if not icon:
            return ""
        icon = os.path.expanduser(str(icon).strip())
        return icon if os.path.isabs(icon) else os.path.join(self.getIconsDir(create=False), icon)

    def getRootTypes(self):
        if self.rootTypes is None:
            self.rootTypes = Types(self.scheme)
        return self.rootTypes

    def appendType(self, name, parent: Type) -> Type:
        typesList: Types = parent.getChildren() if parent is not None else self.getRootTypes()
        return typesList.addNode(name)

    def createTypeByPath(self, path):
        pathAr = path.split()
        typesList: Types = self.getRootTypes()
        theType: Type = None

        for level in range(0, len(pathAr)):
            token = pathAr[level]

            try:
                theType = typesList[token]
            except IndexError:
                theType = typesList.addNode(token)
            typesList = theType.getChildren()

            # theType = typesList.getByName(token) if typesList is not None else None
            # if theType is None:
            #     theType = typesList.addNode(token)
            # typesList = theType.getChilds()

        return theType

    def getTypeByID(self, typeId: int) -> Type:
        """
        Scan types tree for the type with requested ID.

        :param typeId: type id for type we are looking for
        :return: the Type object
        """
        typesList: Types = self.getRootTypes()
        return self._getTypeByID(typesList, typeId)

    def _getTypeByID(self, typesList: Types, typeId: int) -> Type:
        for theType in typesList:
            if theType.recId == typeId:
                return theType
            if theType.isChildren():
                try:
                    return self._getTypeByID(theType.getChildren(), typeId)
                except RuntimeError:
                    pass

        raise RuntimeError("Type id {} not found".format(typeId))

    def getTypeByPath(self, path) -> Type:
        pathAr = path.split()
        typesList: Types = self.getRootTypes()
        theType: Type = None

        for token in pathAr:
            theType = typesList[token]
            if theType is None:
                raise ValueError
            else:
                typesList = theType.getChildren()

        return theType

    def getHeadersByType(self, typeId):
        headers = Headers(self.scheme, typeId)
        return headers

    def loadPartsByType(self, theType: Type, withChild = False) -> Parts:
        parts = Parts(self.scheme)
        parts = self._scanChildTypes(parts, theType)
        return parts

    def _scanChildTypes(self, parts: Parts, theType: Type ) -> Parts:
        rows = self.scheme.loadPartsByType(theType.recId)
        parts = self._loadParts(parts, rows)

        for childType in theType.getChildren():
            parts = self._scanChildTypes(parts, childType)
        return parts

    def _loadParts(self, parts: Parts, rows) -> Parts:
        # rows = self.scheme.loadPartsByType(theType.recId)
        for row in rows:
            part = Part(self.scheme, row[self.idPos])
            count = 0
            for fldName in ELEMENT_FLD_NAMES:
                part.__dict__[fldName] = row[count]
                count += 1
            parts.append(part)
        return parts

    def loadElementById(self, elId):
        thePart: Part = Part(self.scheme, elId)
        thePart.loadDatas()
        return thePart

    def createPart(self, theType: Type, el: dict) -> Part:
        logger.debug("Create part : {}".format(', '.join(map(str, el.values()))))
        el_id = self.scheme.addPart(theType.recId, el)
        part = Part(self.scheme, el_id)
        part.loadDatas()
        return part

    def search(self, searchStr):
        partsList: Parts = Parts(self.scheme)
        rows = self.scheme.partSearch(searchStr)
        parts = self._loadParts(partsList, rows)
        return parts

    def deletePart(self, thePart: Part):
        logger.debug("Delete part : {}".format(', '.join(map(str, thePart.__dict__.values()))))
        self.scheme.ensurePartNotInProjects(thePart.id)
        icon = self._partIconToDelete(thePart)
        self.scheme.delPart(thePart.id)
        if icon is not None:
            try:
                os.remove(icon)
            except FileNotFoundError:
                pass
            except OSError:
                logger.exception("Part deleted, but couldn't remove icon %s", icon)
                return icon
        return None

    def _partIconToDelete(self, part: Part):
        """Program-created icons have unique names; remove this part's icon, never a document."""
        iconsDir = os.path.realpath(self.getIconsDir(create=False))

        def localPath(value, base):
            if not value:
                return None
            value = str(value)
            url = urllib.parse.urlsplit(value)
            if url.scheme == "file" and url.netloc in ("", "localhost"):
                value = urllib.parse.unquote(url.path)
            elif url.scheme or value.startswith(":"):
                return None
            return os.path.realpath(os.path.join(base, os.path.expanduser(value)))

        icon = localPath(part["icon"], iconsDir)
        if icon is None or os.path.commonpath([iconsDir, icon]) != iconsDir or icon == iconsDir:
            return None
        # A file used as a document must survive, even when it is also this part's icon.
        rows = self.scheme.db.execute("SELECT uri FROM DATASHEETS;")
        if any(localPath(row[0], self.dataPath) == icon for row in rows):
            return None
        return icon

    def getSearch(self, searchStr):
        self.scheme.partSearch(searchStr)

    def disconnect(self):
        self.scheme.disconnect()

