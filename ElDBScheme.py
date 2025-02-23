import logging
import sqlite3
import sys
import os
import bisect
from sqlite3 import Cursor

# from numpy import *

DB_FACTORY = None

from connector import SQLiteConnector, DBError

logger = logging.getLogger(__name__)
logger.setLevel(level=logging.DEBUG)
handler = logging.StreamHandler(stream=sys.stderr)
# handler.setFormatter(Formatter(fmt='[%(levelname)s] %(name)s: %(message)s'))
handler.setFormatter(logging.Formatter(fmt='[%(levelname)s] %(module)s/%(funcName)s: %(message)s'))
logger.addHandler(handler)

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
    "currency": "TXT",      # Валюта
    "shop": "TEXT",  # URL Магазина
    "local_location": "TEXT",  # Где лежит у меня
    "icon": "TEXT"  # Иконка
}

ELEMENT_FIELDS_DISPLAY = {
    "id": "id",
    "type_id": "type_id",
    "part_num": "PartNum",
    "device_code": "Code",
    "value": "Nominal",
    "units": "Unit",
    "reduced_val": "Reduced Value",
    "reduced_val_units": "Reduced Unit",
    "chip_code": "Chip code",
    "max_current": "Current",
    "max_voltage": "Voltage",
    "max_desumption": "Dissipation",
    "description": "Description",
    "package": "Package",
    "present": "Is Present",
    "quantity": "Quantity",
    "price": "Price",
    "currency": "Currency",
    "shop": "Shop link",
    "local_location": "Location",
    "icon": "Icon Link"
}


ELEMENT_FLD_NAMES = list(ELEMENT_FIELDS.keys())
#  DataSheet
#  Image
#  Project

TYPES_TABLE_NAME = "TYPES"
HEADER_TABLE_NAME = "HEADERS"
PARTS_TABLE_NAME = "PARTS"
DATASHEETS_TABLE_NAME = "DATASHEETS"
PROJECTS_TABLE = "PROJECTS"
EL_BY_PROJECT_TABLE = "EL_BY_PROJECT"
ENVIRONMENT_TABLE = "ENVIRONMENT"

TYPES_TABLE_SQL = "CREATE TABLE IF NOT EXISTS " + TYPES_TABLE_NAME + " (" \
                                                                     "id INTEGER PRIMARY KEY AUTOINCREMENT," \
                                                                     "name TEXT NOT NULL," \
                                                                     "path TEXT," \
                                                                     "parent_id INTEGER DEFAULT 0" \
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
    "width": "INTEGER"
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

PROJECTS_TABLE_SQL = "CREATE TABLE IF NOT EXISTS " + PROJECTS_TABLE + " (" \
                  "id INTEGER PRIMARY KEY AUTOINCREMENT," \
                  "name  TEXT," \
                  "descr TEXT," \
                  "schematic_path TEXT" \
                  ");"

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


class DBScheme:
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
            self.db.exec(PROJECTS_TABLE_SQL)
            self.db.exec(EL_BY_PROJECT_TABLE_SQL)
            self.db.exec(ENVIRONMENT_TABLE_SQL)
            self.db.commit()

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
        sql = ""
        for key in els.keys():
            try:
                if key in allow_fields:
                    if key != "id":
                        sql += key + " = '"
                        sql += str(els[key]) if els[key] is not None else ""
                        sql += "',"
                else:
                    raise AttributeError("Try to assign undefined parts field {}".format(key))
            except AttributeError:
                logger.warning("Try to assign undefined parts field %", key)

        #   Remove trail comas
        sql = sql[:-1]
        sql = "UPDATE " + PARTS_TABLE_NAME + "  SET " + sql + " WHERE id=" + str(els['id']) + ";"
        recId = self.db.exec(sql)
        self.db.commit()
        return recId

    def delPart(self, partId):
        sql = "DELETE FROM " + PARTS_TABLE_NAME + " WHERE id='" + str(partId) + "';"
        self.db.exec(sql)
        self.db.commit()

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
        sql = "Select "+ get_parts_fld_str() + " FROM " + PARTS_TABLE_NAME +\
              " WHERE part_num like '%" + searchStr + "%' OR" \
              " device_code like '%" + searchStr + "%' OR" \
              " description like '%" + searchStr + "%'" \
                                                        ";"
        curr = self.db.select(sql)
        return curr.fetchall()

    def disconnect(self):
        self.db.disconnect()


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
        self.type_id = type_id
        self.field_name = field_name

    def setFields(self, el):
        for fldName in HEADER_FLD_NAMES:
            value = el[int(HEADER_FLD_NAMES.index(fldName))]
            if HEADER_FIELDS[fldName] == "BOOLEAN":
                self.__dict__[fldName] = True if value == 1 else False
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
        self.__dict__[index] = value
        self.changed = True

    def save(self):
        if self.changed:
            if self.id < 0:
                self.id = self.scheme.addHeader(self.getFields())
            else:
                self.scheme.updateHeader(self.getFields())
        self.changed = False


class Headers:
    def __init__(self, scheme: DBScheme, type_id: int):
        self.scheme = scheme
        self.type_id: int = type_id
        self.headersAr = {}
        self.index = 0
        self.IterAr = []

        for row in self.scheme.loadHeaders(str(self.type_id)):
            # id, type_id, field_name, name, align, hidden, sort, display
            count = 0
            fldList: list = list(HEADER_FIELDS.keys())
            fldName = row[int(HEADER_FLD_NAMES.index("field_name"))]
            hdr = Header(self.scheme, type_id, fldName)
            hdr.setFields(list(row))
            self.headersAr[fldName] = hdr

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

    def __init__(self, db_file: str):
        self.rootTypes = None
        self.db_file = db_file
        self.scheme: DBScheme = DBScheme(self.db_file)
        self.idPos = ELEMENT_FLD_NAMES.index("id")

        if not self.isDB():
            self.scheme.connect()
            self.scheme.createTables()
            self.scheme.db.conn.commit()
        else:
            self.scheme.connect()

    def isDB(self) -> bool:
        return True if os.path.exists(self.db_file) else False

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
        self.scheme.delPart(thePart.id)

    def getSearch(self, searchStr):
        self.scheme.partSearch(searchStr)

    def disconnect(self):
        self.scheme.disconnect()

