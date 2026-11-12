"""Unit tests for every ElDBScheme.DBScheme method.

Each test gets its own temporary SQLite file. Special attention to the
HEADERS.position change: schema, migration of old DBs, defaults, save/load.

Run from the project root:
    python -m unittest tests.test_DBScheme -v
"""
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ElDBScheme
from ElDBScheme import (DBScheme, DBFactory, Type, Header, Headers, HEADER_FIELDS, HEADER_FLD_NAMES,
                        ELEMENT_FLD_NAMES, ICON_COLUMN_POSITION, defaultColumnOrder, defaultHeaderPosition,
                        DOC_TYPE_PDF, DOC_TYPE_PNG)

# HEADERS as it was before the "position" column was added
OLD_HEADER_TABLE_SQL = (
    "CREATE TABLE HEADERS (id INTEGER PRIMARY KEY AUTOINCREMENT, type_id INTEGER NOT NULL, "
    "field_name TEXT NOT NULL, label TEXT, align TEXT, hidden BOOLEAN, sort BOOLEAN, display TEXT, "
    "width INTEGER, CONSTRAINT fk_header_types FOREIGN KEY(type_id) REFERENCES TYPES(id) ON DELETE CASCADE );")


class SchemeTestCase(unittest.TestCase):
    """Fresh DB with all tables created."""

    def setUp(self):
        self.tmpDir = tempfile.mkdtemp(prefix="partsdb-scheme-")
        self.dbFile = os.path.join(self.tmpDir, "test.sqlite")
        self.scheme = DBScheme(self.dbFile)
        self.scheme.connect()
        self.scheme.createTables()

    def tearDown(self):
        if self.scheme.db.isConnect():
            self.scheme.disconnect()
        shutil.rmtree(self.tmpDir, ignore_errors=True)

    # ---- helpers ----
    def raw(self, sql, params=()):
        """Read straight from the file with a separate connection."""
        conn = sqlite3.connect(self.dbFile)
        try:
            return conn.execute(sql, params).fetchall()
        finally:
            conn.close()

    def columns(self, table):
        return [row[1] for row in self.raw("PRAGMA table_info(%s);" % table)]

    def addType(self, name, parent: Type = None, path=None) -> Type:
        return self.scheme.addType(Type(self.scheme, 0, name, path if path is not None else name, parent))

    def addPart(self, typeId, partNum, **fields) -> int:
        return self.scheme.addPart(typeId, dict(part_num=partNum, **fields))

    def headerDict(self, typeId, fieldName, **fields) -> dict:
        hdr = Header(self.scheme, typeId, fieldName)
        hdr.id = -1
        data = hdr.getFields()
        data.update(fields)
        return data


# ---------------------------------------------------------------- connection / schema

class TestConnectionAndTables(SchemeTestCase):
    def test_connect_is_idempotent(self):
        conn = self.scheme.db.conn
        self.scheme.connect()
        self.assertIs(self.scheme.db.conn, conn)

    def test_createTables_creates_all_tables(self):
        tables = {row[0] for row in self.raw("SELECT name FROM sqlite_master WHERE type='table';")}
        for table in ("TYPES", "HEADERS", "PARTS", "DATASHEETS", "PROJECTS", "EL_BY_PROJECT", "ENVIRONMENT"):
            self.assertIn(table, tables)

    def test_createTables_is_idempotent(self):
        self.scheme.createTables()  # CREATE TABLE IF NOT EXISTS: no error, no duplicates
        self.assertEqual(self.columns("HEADERS"), HEADER_FLD_NAMES)

    def test_parts_columns_match_element_fields(self):
        self.assertEqual(self.columns("PARTS"), ELEMENT_FLD_NAMES)

    def test_new_db_headers_has_position(self):
        self.assertEqual(self.columns("HEADERS"), HEADER_FLD_NAMES)
        self.assertEqual(HEADER_FLD_NAMES[-1], "position")

    def test_disconnect_closes_connection(self):
        self.scheme.disconnect()
        with self.assertRaises(sqlite3.ProgrammingError):
            self.scheme.db.conn.execute("SELECT 1;")


# ---------------------------------------------------------------- migrate (HEADERS.position)

class TestMigrate(unittest.TestCase):
    def setUp(self):
        self.tmpDir = tempfile.mkdtemp(prefix="partsdb-migrate-")
        self.dbFile = os.path.join(self.tmpDir, "old.sqlite")
        conn = sqlite3.connect(self.dbFile)
        conn.execute(ElDBScheme.TYPES_TABLE_SQL)
        conn.execute(OLD_HEADER_TABLE_SQL)
        conn.execute("INSERT INTO TYPES (id, name, path, parent_id) VALUES (1, 'R', 'R', 0);")
        conn.execute("INSERT INTO TYPES (id, name, path, parent_id) VALUES (2, 'C', 'C', 0);")
        for typeId in (1, 2):
            for field in ("part_num", "value", "description", "icon"):
                conn.execute("INSERT INTO HEADERS (type_id, field_name, display, hidden, width) VALUES (?,?,?,?,?);",
                             (typeId, field, field.upper(), 0, 77))
        conn.commit()
        conn.close()

    def tearDown(self):
        shutil.rmtree(self.tmpDir, ignore_errors=True)

    def openScheme(self) -> DBScheme:
        scheme = DBScheme(self.dbFile)
        scheme.connect()
        self.addCleanup(scheme.disconnect)
        return scheme

    def rows(self, sql):
        conn = sqlite3.connect(self.dbFile)
        try:
            return conn.execute(sql).fetchall()
        finally:
            conn.close()

    def test_adds_position_column(self):
        self.openScheme().migrate()
        columns = [r[1] for r in self.rows("PRAGMA table_info(HEADERS);")]
        self.assertEqual(columns, HEADER_FLD_NAMES)

    def test_fills_default_positions_for_all_types(self):
        self.openScheme().migrate()
        for field_name, position in self.rows("SELECT field_name, position FROM HEADERS;"):
            self.assertEqual(position, defaultHeaderPosition(field_name), field_name)
        self.assertEqual(self.rows("SELECT count(*) FROM HEADERS WHERE position IS NULL;"), [(0,)])

    def test_icon_moved_to_icon_position(self):
        self.openScheme().migrate()
        self.assertEqual(self.rows("SELECT DISTINCT position FROM HEADERS WHERE field_name='icon';"),
                         [(ICON_COLUMN_POSITION,)])

    def test_keeps_other_header_data(self):
        self.openScheme().migrate()
        self.assertEqual(self.rows("SELECT count(*) FROM HEADERS WHERE width=77 AND display=upper(field_name);"),
                         [(8,)])

    def test_is_idempotent_and_keeps_user_positions(self):
        scheme = self.openScheme()
        scheme.migrate()
        scheme.db.exec("UPDATE HEADERS SET position = 42 WHERE field_name = 'value';")
        scheme.migrate()  # second run must not reset positions
        self.assertEqual(self.rows("SELECT DISTINCT position FROM HEADERS WHERE field_name='value';"), [(42,)])

    def test_without_headers_table_does_nothing(self):
        conn = sqlite3.connect(self.dbFile)
        conn.execute("DROP TABLE HEADERS;")
        conn.commit()
        conn.close()
        self.openScheme().migrate()  # must not raise
        self.assertEqual(self.rows("SELECT name FROM sqlite_master WHERE name='HEADERS';"), [])

    def test_not_connected_does_nothing(self):
        DBScheme(self.dbFile).migrate()  # never connected: must not raise or change anything
        self.assertNotIn("position", [r[1] for r in self.rows("PRAGMA table_info(HEADERS);")])

    def test_DBFactory_migrates_existing_db(self):
        factory = DBFactory(self.dbFile)
        try:
            headers = factory.getHeadersByType(1)
            self.assertEqual(headers["icon"]["position"], ICON_COLUMN_POSITION)
            self.assertEqual(headers["part_num"]["position"], defaultHeaderPosition("part_num"))
        finally:
            factory.disconnect()


# ---------------------------------------------------------------- column order defaults

class TestDBVersion(TestMigrate):
    """DB version in ENVIRONMENT and step-by-step upgrades."""

    def version(self):
        rows = self.rows("SELECT value FROM ENVIRONMENT WHERE name='%s';" % ElDBScheme.ENV_DB_VERSION)
        return [r[0] for r in rows]

    def test_old_db_without_version_is_base_version(self):
        scheme = self.openScheme()
        scheme.db.exec(ElDBScheme.ENVIRONMENT_TABLE_SQL)
        self.assertEqual(scheme.getDBVersion(), ElDBScheme.BASE_DB_VERSION)

    def test_migrate_saves_current_version_once(self):
        self.openScheme().migrate()
        self.assertEqual(self.version(), [str(ElDBScheme.DB_VERSION)])

    def test_migrate_creates_environment_defaults(self):
        self.openScheme().migrate()
        names = {r[0] for r in self.rows("SELECT name FROM ENVIRONMENT;")}
        self.assertEqual(names, set(ElDBScheme.ENVIRONMENT_DEFAULTS))

    def test_every_version_has_a_step(self):
        for version in range(ElDBScheme.BASE_DB_VERSION + 1, ElDBScheme.DB_VERSION + 1):
            self.assertIn(version, ElDBScheme.MIGRATIONS)

    def test_current_db_is_not_migrated_again(self):
        scheme = self.openScheme()
        scheme.migrate()
        calls = []
        with mock.patch.dict(ElDBScheme.MIGRATIONS, {v: (lambda s, v=v: calls.append(v))
                                                     for v in ElDBScheme.MIGRATIONS}):
            scheme.migrate()
        self.assertEqual(calls, [])

    def test_steps_run_in_order_from_db_version(self):
        calls = []

        def step(n):
            return lambda scheme: calls.append((n, scheme.getDBVersion()))

        scheme = self.openScheme()
        scheme.db.exec(ElDBScheme.ENVIRONMENT_TABLE_SQL)
        scheme.setEnvironment(ElDBScheme.ENV_DB_VERSION, 2)
        with mock.patch.object(ElDBScheme, "DB_VERSION", 5), \
                mock.patch.dict(ElDBScheme.MIGRATIONS, {3: step(3), 4: step(4), 5: step(5)}):
            scheme.migrate()
        # each step sees the version saved by the previous one
        self.assertEqual(calls, [(3, 2), (4, 3), (5, 4)])
        self.assertEqual(self.version(), ["5"])

    def test_old_db_runs_all_steps_up_to_current(self):
        calls = []
        with mock.patch.object(ElDBScheme, "DB_VERSION", 3), \
                mock.patch.dict(ElDBScheme.MIGRATIONS, {3: lambda s: calls.append(3)}):
            self.openScheme().migrate()  # base version 1 -> real step 2 -> fake step 3
        self.assertEqual(calls, [3])
        self.assertIn("position", [r[1] for r in self.rows("PRAGMA table_info(HEADERS);")])
        self.assertEqual(self.version(), ["3"])

    def test_failed_step_keeps_last_completed_version(self):
        def broken(scheme):
            raise RuntimeError("step 3 failed")

        scheme = self.openScheme()
        with mock.patch.object(ElDBScheme, "DB_VERSION", 4), \
                mock.patch.dict(ElDBScheme.MIGRATIONS, {3: broken, 4: lambda s: None}):
            with self.assertRaises(RuntimeError):
                scheme.migrate()
        self.assertEqual(self.version(), ["2"])

    def test_missing_step_raises(self):
        scheme = self.openScheme()
        scheme.migrate()
        with mock.patch.object(ElDBScheme, "DB_VERSION", ElDBScheme.DB_VERSION + 1):
            with self.assertRaises(RuntimeError):
                scheme.migrate()
        self.assertEqual(self.version(), [str(ElDBScheme.DB_VERSION)])

    def test_newer_db_is_left_untouched(self):
        scheme = self.openScheme()
        scheme.db.exec(ElDBScheme.ENVIRONMENT_TABLE_SQL)
        scheme.setEnvironment(ElDBScheme.ENV_DB_VERSION, ElDBScheme.DB_VERSION + 10)
        scheme.migrate()
        self.assertEqual(self.version(), [str(ElDBScheme.DB_VERSION + 10)])
        self.assertNotIn("position", [r[1] for r in self.rows("PRAGMA table_info(HEADERS);")])

    def test_bad_version_value_is_base_version(self):
        scheme = self.openScheme()
        scheme.db.exec(ElDBScheme.ENVIRONMENT_TABLE_SQL)
        scheme.setEnvironment(ElDBScheme.ENV_DB_VERSION, "abc")
        self.assertEqual(scheme.getDBVersion(), ElDBScheme.BASE_DB_VERSION)
        scheme.migrate()
        self.assertEqual(self.version(), [str(ElDBScheme.DB_VERSION)])

    def test_step2_is_safe_on_db_that_already_has_position(self):
        # DBs migrated by the earlier, unversioned code: position exists, version row does not
        scheme = self.openScheme()
        scheme.db.exec("ALTER TABLE HEADERS ADD COLUMN position INTEGER;")
        scheme.db.exec("UPDATE HEADERS SET position = 9;")
        scheme.migrate()
        self.assertEqual(self.rows("SELECT DISTINCT position FROM HEADERS;"), [(9,)])
        self.assertEqual(self.version(), [str(ElDBScheme.DB_VERSION)])

    def test_new_db_gets_current_version(self):
        newFile = os.path.join(self.tmpDir, "new.sqlite")
        factory = DBFactory(newFile)
        try:
            self.assertEqual(factory.scheme.getDBVersion(), ElDBScheme.DB_VERSION)
        finally:
            factory.disconnect()

    def test_DBFactory_upgrades_and_saves_version(self):
        DBFactory(self.dbFile).disconnect()
        self.assertEqual(self.version(), [str(ElDBScheme.DB_VERSION)])


class TestEnvironment(SchemeTestCase):
    def test_get_missing_returns_None(self):
        self.assertIsNone(self.scheme.getEnvironment("no_such_name"))

    def test_set_inserts_then_updates_single_row(self):
        self.scheme.setEnvironment("x", 1)
        self.scheme.setEnvironment("x", "two")
        self.assertEqual(self.scheme.getEnvironment("x"), "two")
        self.assertEqual(self.raw("SELECT count(*) FROM ENVIRONMENT WHERE name='x';"), [(1,)])

    def test_ensureEnvironment_keeps_existing_values(self):
        self.scheme.setEnvironment(ElDBScheme.ENV_ICONS_PATH, "/icons")
        self.scheme.ensureEnvironment()
        self.assertEqual(self.scheme.getEnvironment(ElDBScheme.ENV_ICONS_PATH), "/icons")

    def test_createTables_writes_defaults(self):
        for name, value in ElDBScheme.ENVIRONMENT_DEFAULTS.items():
            self.assertEqual(self.scheme.getEnvironment(name), value)


class TestColumnOrderDefaults(unittest.TestCase):
    def test_icon_at_constant_position(self):
        self.assertEqual(defaultColumnOrder()[ICON_COLUMN_POSITION], "icon")
        self.assertEqual(defaultHeaderPosition("icon"), ICON_COLUMN_POSITION)

    def test_order_has_every_table_field_once(self):
        order = defaultColumnOrder()
        self.assertEqual(sorted(order), sorted(ELEMENT_FLD_NAMES[2:]))  # without id, type_id
        self.assertEqual(len(order), len(set(order)))

    def test_other_fields_keep_relative_order(self):
        order = [f for f in defaultColumnOrder() if f != "icon"]
        self.assertEqual(order, [f for f in ELEMENT_FLD_NAMES[2:] if f != "icon"])

    def test_positions_are_unique_and_gap_free(self):
        positions = [defaultHeaderPosition(f) for f in defaultColumnOrder()]
        self.assertEqual(positions, list(range(len(positions))))

    def test_unknown_field_goes_last(self):
        self.assertEqual(defaultHeaderPosition("no_such_field"), len(defaultColumnOrder()))

    def test_new_header_object_gets_default_position(self):
        self.assertEqual(Header(None, 1, "icon")["position"], ICON_COLUMN_POSITION)
        self.assertEqual(Header(None, 1, "part_num")["position"], defaultHeaderPosition("part_num"))

    def test_header_row_with_null_position_gets_default(self):
        row = [None] * len(HEADER_FLD_NAMES)
        row[HEADER_FLD_NAMES.index("id")] = 5
        row[HEADER_FLD_NAMES.index("type_id")] = 1
        row[HEADER_FLD_NAMES.index("field_name")] = "icon"
        row[HEADER_FLD_NAMES.index("width")] = 10
        hdr = Header(None, 1, "icon")
        hdr.setFields(row)
        self.assertEqual(hdr["position"], ICON_COLUMN_POSITION)


# ---------------------------------------------------------------- TYPES

class TestTypes(SchemeTestCase):
    def test_addType_sets_recId(self):
        theType = self.addType("Резистор")
        self.assertGreater(theType.recId, 0)
        self.assertEqual(self.raw("SELECT name, path, parent_id FROM TYPES WHERE id=?;", (theType.recId,)),
                         [("Резистор", "Резистор", 0)])

    def test_addType_child_stores_parent(self):
        parent = self.addType("Диод")
        child = self.addType("Шоттки", parent, "Диод Шоттки")
        self.assertEqual(self.raw("SELECT parent_id FROM TYPES WHERE id=?;", (child.recId,)), [(parent.recId,)])

    def test_loadTypes_filters_by_parent_and_sorts_by_name(self):
        b = self.addType("B")
        self.addType("A")
        self.addType("c-child", b)
        self.assertEqual([r[1] for r in self.scheme.loadTypes()], ["A", "B"])
        self.assertEqual([r[1] for r in self.scheme.loadTypes(b.recId)], ["c-child"])
        self.assertEqual(self.scheme.loadTypes(9999), [])

    def test_loadTypes_row_layout(self):
        theType = self.addType("X", path="P")
        self.assertEqual(self.scheme.loadTypes(), [(theType.recId, "X", "P", 0)])

    def test_updateType_name_only_keeps_path(self):
        theType = self.addType("Old", path="old/path")
        self.scheme.updateType(theType.recId, "New")
        self.assertEqual(self.raw("SELECT name, path FROM TYPES WHERE id=?;", (theType.recId,)),
                         [("New", "old/path")])

    def test_updateType_name_and_path(self):
        theType = self.addType("Old")
        self.scheme.updateType(theType.recId, "New", "new/path")
        self.assertEqual(self.raw("SELECT name, path FROM TYPES WHERE id=?;", (theType.recId,)),
                         [("New", "new/path")])

    def test_updateType_rejects_empty_name_or_id(self):
        theType = self.addType("Keep")
        with self.assertRaises(ValueError):
            self.scheme.updateType(theType.recId, "")
        with self.assertRaises(ValueError):
            self.scheme.updateType(None, "Name")
        self.assertEqual(self.raw("SELECT name FROM TYPES WHERE id=?;", (theType.recId,)), [("Keep",)])

    def test_delType_removes_only_that_type(self):
        keep = self.addType("Keep")
        gone = self.addType("Gone")
        self.scheme.delType(gone.recId)
        self.assertEqual([r[0] for r in self.raw("SELECT id FROM TYPES;")], [keep.recId])


# ---------------------------------------------------------------- HEADERS

class TestHeaders(SchemeTestCase):
    def setUp(self):
        super().setUp()
        self.typeId = self.addType("T").recId

    def test_addHeader_stores_position(self):
        recId = self.scheme.addHeader(self.headerDict(self.typeId, "icon", width=60))
        self.assertGreater(recId, 0)
        self.assertEqual(self.raw("SELECT field_name, width, position FROM HEADERS WHERE id=?;", (recId,)),
                         [("icon", 60, ICON_COLUMN_POSITION)])

    def test_addHeader_ignores_id(self):
        data = self.headerDict(self.typeId, "part_num")
        data["id"] = 12345
        recId = self.scheme.addHeader(data)
        self.assertNotEqual(recId, 12345)

    def test_loadHeaders_row_layout_matches_HEADER_FIELDS(self):
        recId = self.scheme.addHeader(self.headerDict(self.typeId, "value", display="Номинал", width=90,
                                                      position=3, hidden=True, align="LEFT"))
        rows = self.scheme.loadHeaders(self.typeId)
        self.assertEqual(len(rows), 1)
        row = dict(zip(HEADER_FLD_NAMES, rows[0]))
        self.assertEqual(row["id"], recId)
        self.assertEqual(row["type_id"], self.typeId)
        self.assertEqual(row["display"], "Номинал")
        self.assertEqual(row["width"], 90)
        self.assertEqual(row["position"], 3)
        self.assertEqual(row["hidden"], 1)
        self.assertEqual(row["align"], "LEFT")

    def test_loadHeaders_filters_by_type_and_sorts_by_field_name(self):
        other = self.addType("Other").recId
        for field in ("value", "icon", "part_num"):
            self.scheme.addHeader(self.headerDict(self.typeId, field))
        self.scheme.addHeader(self.headerDict(other, "description"))
        self.assertEqual([r[HEADER_FLD_NAMES.index("field_name")] for r in self.scheme.loadHeaders(self.typeId)],
                         ["icon", "part_num", "value"])
        self.assertEqual(self.scheme.loadHeaders(9999), [])

    def test_updateHeader_changes_position_and_width(self):
        data = self.headerDict(self.typeId, "icon")
        data["id"] = self.scheme.addHeader(data)
        data.update(position=5, width=120, display="Фото")
        self.scheme.updateHeader(data)
        self.assertEqual(self.raw("SELECT position, width, display FROM HEADERS WHERE id=?;", (data["id"],)),
                         [(5, 120, "Фото")])

    def test_updateHeader_touches_only_its_row(self):
        a = self.headerDict(self.typeId, "icon")
        a["id"] = self.scheme.addHeader(a)
        b = self.headerDict(self.typeId, "part_num", width=11)
        b["id"] = self.scheme.addHeader(b)
        a["width"] = 99
        self.scheme.updateHeader(a)
        self.assertEqual(self.raw("SELECT width FROM HEADERS WHERE id=?;", (b["id"],)), [(11,)])

    def test_header_save_roundtrip_through_Headers(self):
        theType = Type(self.scheme, self.typeId, "T", "T", None)
        hdr = theType.getHeaders()["icon"]  # lazy default, not in DB yet
        self.assertEqual(self.scheme.loadHeaders(self.typeId), [])
        hdr["width"] = 64
        hdr.save()  # INSERT
        hdr["position"] = 7
        hdr.save()  # UPDATE
        loaded = Headers(self.scheme, self.typeId)["icon"]
        self.assertEqual((loaded.id, loaded["width"], loaded["position"]), (hdr.id, 64, 7))
        self.assertEqual(len(self.scheme.loadHeaders(self.typeId)), 1)


# ---------------------------------------------------------------- PARTS

class TestParts(SchemeTestCase):
    def setUp(self):
        super().setUp()
        self.typeId = self.addType("T").recId

    def part(self, recId) -> dict:
        row = self.scheme.loadPart(recId)
        return dict(zip(ELEMENT_FLD_NAMES, row)) if row else None

    def test_addPart_returns_id_and_stores_fields(self):
        recId = self.addPart(self.typeId, "1N4007", device_code="M7", description="Диод", quantity=10, price=1.5)
        part = self.part(recId)
        self.assertEqual(part["id"], recId)
        self.assertEqual(part["type_id"], self.typeId)
        self.assertEqual((part["part_num"], part["device_code"], part["description"]), ("1N4007", "M7", "Диод"))
        self.assertEqual((part["quantity"], part["price"]), (10, 1.5))

    def test_addPart_is_committed(self):
        recId = self.addPart(self.typeId, "X1")
        self.assertEqual(self.raw("SELECT part_num FROM PARTS WHERE id=?;", (recId,)), [("X1",)])

    def test_addPart_requires_part_num(self):
        with self.assertRaises(RuntimeError):
            self.scheme.addPart(self.typeId, {"description": "no part number"})

    def test_addPart_ignores_unknown_fields(self):
        recId = self.scheme.addPart(self.typeId, {"part_num": "X", "no_such_field": "junk"})
        self.assertEqual(self.part(recId)["part_num"], "X")

    def test_addPart_keeps_quotes(self):
        recId = self.addPart(self.typeId, "O'Neil \"quoted\"")
        self.assertEqual(self.part(recId)["part_num"], "O'Neil \"quoted\"")

    def test_loadPart_missing_returns_None(self):
        self.assertIsNone(self.scheme.loadPart(9999))

    def test_loadPartsByType_filters_and_sorts_by_part_num(self):
        other = self.addType("Other").recId
        self.addPart(self.typeId, "B")
        self.addPart(self.typeId, "A")
        self.addPart(other, "C")
        rows = self.scheme.loadPartsByType(self.typeId)
        self.assertEqual([r[ELEMENT_FLD_NAMES.index("part_num")] for r in rows], ["A", "B"])
        self.assertEqual(self.scheme.loadPartsByType(9999), [])

    def test_updatePart_changes_fields(self):
        recId = self.addPart(self.typeId, "OLD", description="old")
        data = self.part(recId)
        data.update(part_num="NEW", description="new", local_location="Box 3")
        self.scheme.updatePart(data)
        part = self.part(recId)
        self.assertEqual((part["part_num"], part["description"], part["local_location"]), ("NEW", "new", "Box 3"))

    def test_updatePart_touches_only_its_row(self):
        a = self.addPart(self.typeId, "A")
        b = self.addPart(self.typeId, "B")
        data = self.part(a)
        data["part_num"] = "A2"
        self.scheme.updatePart(data)
        self.assertEqual(self.part(b)["part_num"], "B")

    def test_updatePart_ignores_unknown_fields(self):
        recId = self.addPart(self.typeId, "A")
        data = self.part(recId)
        data["no_such_field"] = "junk"
        data["part_num"] = "A2"
        self.scheme.updatePart(data)
        self.assertEqual(self.part(recId)["part_num"], "A2")

    def test_updatePart_keeps_quotes(self):
        # A description like: 2.8" display, O'Reilly book ref
        recId = self.addPart(self.typeId, "A")
        data = self.part(recId)
        data["description"] = "2.8\" IPS, Schottky's diode"
        self.scheme.updatePart(data)
        self.assertEqual(self.part(recId)["description"], "2.8\" IPS, Schottky's diode")

    def test_updatePart_keeps_icon_path(self):
        recId = self.addPart(self.typeId, "A")
        data = self.part(recId)
        data["icon"] = "/Users/me/Documents/Электроника/images/1N4007.png"
        self.scheme.updatePart(data)
        self.assertEqual(self.part(recId)["icon"], data["icon"])

    def test_updatePart_present_false_reads_back_falsy(self):
        # The table shows the check box from bool(present); 'False' as text would read as checked
        recId = self.addPart(self.typeId, "A", present=True)
        data = self.part(recId)
        data["present"] = False
        self.scheme.updatePart(data)
        self.assertFalse(self.part(recId)["present"])
        data["present"] = True
        self.scheme.updatePart(data)
        self.assertTrue(self.part(recId)["present"])

    def test_updatePart_None_stored_as_NULL(self):
        recId = self.addPart(self.typeId, "A", description="text")
        data = self.part(recId)
        data["description"] = None
        self.scheme.updatePart(data)
        self.assertEqual(self.raw("SELECT description IS NULL FROM PARTS WHERE id=?;", (recId,)), [(1,)])

    def test_delPart(self):
        a = self.addPart(self.typeId, "A")
        b = self.addPart(self.typeId, "B")
        self.scheme.delPart(a)
        self.assertIsNone(self.scheme.loadPart(a))
        self.assertIsNotNone(self.scheme.loadPart(b))

    def test_chPartsType_moves_part(self):
        other = self.addType("Other").recId
        recId = self.addPart(self.typeId, "A")
        self.assertEqual(self.scheme.chPartsType(recId, other), recId)
        self.assertEqual(self.part(recId)["type_id"], other)
        self.assertEqual(self.scheme.loadPartsByType(self.typeId), [])


# ---------------------------------------------------------------- search

class TestPartSearch(SchemeTestCase):
    def setUp(self):
        super().setUp()
        typeId = self.addType("T").recId
        self.byPartNum = self.addPart(typeId, "MP2315", device_code="", description="")
        self.byCode = self.addPart(typeId, "X1", device_code="AO3401", description="")
        self.byDescr = self.addPart(typeId, "X2", device_code="", description="Step-down DC/DC converter")
        self.addPart(typeId, "unrelated", device_code="", description="")

    def ids(self, text):
        return sorted(r[0] for r in self.scheme.partSearch(text))

    def test_matches_part_num_device_code_description(self):
        self.assertEqual(self.ids("MP23"), [self.byPartNum])
        self.assertEqual(self.ids("3401"), [self.byCode])
        self.assertEqual(self.ids("DC/DC"), [self.byDescr])

    def test_is_case_insensitive_for_latin(self):
        self.assertEqual(self.ids("step-DOWN"), [self.byDescr])

    def test_no_match(self):
        self.assertEqual(self.ids("zzz-nothing"), [])

    def test_search_text_with_quote(self):
        self.assertEqual(self.ids("O'Reilly"), [])  # must not break the SQL


# ---------------------------------------------------------------- DATASHEETS

class TestDocuments(SchemeTestCase):
    def setUp(self):
        super().setUp()
        typeId = self.addType("T").recId
        self.partId = self.addPart(typeId, "A")
        self.otherPartId = self.addPart(typeId, "B")

    def test_addDocument_and_loadDocuments(self):
        docId = self.scheme.addDocument(self.partId, DOC_TYPE_PDF, "/docs/a.pdf")
        self.assertGreater(docId, 0)
        self.assertEqual(self.scheme.loadDocuments(self.partId), [(docId, self.partId, DOC_TYPE_PDF, "/docs/a.pdf")])

    def test_loadDocuments_filters_by_part(self):
        a = self.scheme.addDocument(self.partId, DOC_TYPE_PDF, "/docs/a.pdf")
        b = self.scheme.addDocument(self.partId, DOC_TYPE_PNG, "/docs/a.png")
        self.scheme.addDocument(self.otherPartId, DOC_TYPE_PDF, "/docs/b.pdf")
        self.assertEqual(sorted(r[0] for r in self.scheme.loadDocuments(self.partId)), [a, b])
        self.assertEqual(self.scheme.loadDocuments(9999), [])

    def test_delDocument(self):
        a = self.scheme.addDocument(self.partId, DOC_TYPE_PDF, "/docs/a.pdf")
        b = self.scheme.addDocument(self.partId, DOC_TYPE_PNG, "/docs/a.png")
        self.scheme.delDocument(a)
        self.assertEqual([r[0] for r in self.scheme.loadDocuments(self.partId)], [b])

    def test_addDocument_keeps_quotes_and_unicode(self):
        uri = "/Users/me/Documents/Электроника/O'Brien datasheet.pdf"
        self.scheme.addDocument(self.partId, DOC_TYPE_PDF, uri)
        self.assertEqual(self.scheme.loadDocuments(self.partId)[0][3], uri)


if __name__ == "__main__":
    unittest.main()
