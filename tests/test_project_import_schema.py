"""Project importer schema and migration checks using temporary SQLite databases."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ElData import ElDBScheme as db


class TestProjectImportSchema(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='partsdb-import-')
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / 'test.sqlite'
        self.scheme = db.DBScheme(str(self.path))
        self.scheme.connect()
        self.addCleanup(self.scheme.disconnect)
        self.scheme.createTables()
        self.conn = self.scheme.db.conn
        self.conn.execute('PRAGMA foreign_keys=ON')

    def columns(self, table):
        return [r[1] for r in self.conn.execute('PRAGMA table_info(' + table + ')')]

    def tables(self):
        return {r[0] for r in self.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}

    def seed(self):
        with self.conn:
            self.conn.execute("INSERT INTO TYPES(id, name) VALUES (1, 'R')")
            self.conn.execute("INSERT INTO PARTS(id, type_id) VALUES (1, 1)")
            self.conn.execute("INSERT INTO PROJECTS(id, name, plugin_id, source_uri) "
                              "VALUES (1, 'Power', 'org.partsdb.kicad', 'https://example.org/project')")
            self.conn.execute("INSERT INTO PROJECT_COMPONENTS(id, project_id, external_id, reference) "
                              "VALUES (1, 1, 'uuid-1', 'R1')")
            self.conn.execute('INSERT INTO PROJECT_COMPONENT_MATCHES(component_id, part_id) VALUES (1, 1)')

    def make_v4(self):
        with self.conn:
            self.conn.execute('DROP TABLE PROJECT_COMPONENT_MATCHES')
            self.conn.execute('DROP TABLE PROJECT_COMPONENTS')
            self.conn.execute('DROP TABLE PROJECTS')
            self.conn.execute('CREATE TABLE PROJECTS(id INTEGER PRIMARY KEY AUTOINCREMENT, '
                              'name TEXT, descr TEXT, schematic_path TEXT)')
            self.conn.execute("UPDATE ENVIRONMENT SET value='4' WHERE name='db_version'")

    def test_new_schema_and_idempotent_creation(self):
        self.scheme.createTables()
        self.assertEqual(self.columns('PROJECTS'), ['id', 'name', 'descr', 'plugin_id', 'external_id',
                         'source_uri', 'last_imported_at', 'needs_reload', 'properties_json'])
        self.assertTrue({'PROJECT_COMPONENTS', 'PROJECT_COMPONENT_MATCHES'} <= self.tables())
        self.assertTrue({'PROJECT_SOURCES', 'PROJECT_IMPORTS'}.isdisjoint(self.tables()))
        self.assertNotIn('sheet_path', self.columns('PROJECT_COMPONENTS'))
        self.assertEqual(self.scheme.getDBVersion(), db.DB_VERSION)

    def test_defaults_unknown_fields_and_exact_nominal(self):
        self.seed()
        self.assertEqual(self.conn.execute('SELECT last_imported_at, needs_reload, properties_json '
                                          'FROM PROJECTS').fetchone(), (None, 1, '{}'))
        self.conn.execute("UPDATE PROJECT_COMPONENTS SET nominal_value='0.002', nominal_unit='ohm'")
        self.assertEqual(self.conn.execute('SELECT kind, nominal_value, quantity, on_board, dnp '
                                          'FROM PROJECT_COMPONENTS').fetchone(), ('unknown', '0.002', 1, 1, 0))
        self.assertTrue(self.conn.execute('SELECT matched_at FROM PROJECT_COMPONENT_MATCHES').fetchone()[0].endswith('Z'))

    def test_component_unique_within_project(self):
        self.seed()
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("INSERT INTO PROJECT_COMPONENTS(project_id, external_id, reference) VALUES (1, 'uuid-1', 'R2')")
        self.conn.execute("INSERT INTO PROJECTS(id, name) VALUES (2, 'Second')")
        self.conn.execute("INSERT INTO PROJECT_COMPONENTS(project_id, external_id, reference) VALUES (2, 'uuid-1', 'R1')")

    def test_constraints(self):
        self.seed()
        for table, field in [('PROJECTS', 'needs_reload'),
                             ('PROJECT_COMPONENTS', 'on_board'), ('PROJECT_COMPONENTS', 'dnp'),
                             ('PROJECT_COMPONENT_MATCHES', 'needs_review')]:
            with self.subTest(table=table, field=field), self.assertRaises(sqlite3.IntegrityError):
                self.conn.execute('UPDATE ' + table + ' SET ' + field + '=2')
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute('UPDATE PROJECT_COMPONENTS SET project_id=999')
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute('UPDATE PROJECT_COMPONENT_MATCHES SET part_id=999')

    def test_delete_project_cascades_and_preserves_stock(self):
        self.seed()
        self.conn.execute('DELETE FROM PROJECTS WHERE id=1')
        self.assertEqual(self.conn.execute('SELECT count(*) FROM PROJECT_COMPONENTS').fetchone()[0], 0)
        self.assertEqual(self.conn.execute('SELECT count(*) FROM PROJECT_COMPONENT_MATCHES').fetchone()[0], 0)
        self.assertEqual(self.conn.execute('SELECT count(*) FROM PARTS').fetchone()[0], 1)

    def test_delete_stock_unlinks_but_keeps_component(self):
        self.seed()
        self.conn.execute('PRAGMA foreign_keys=OFF')
        self.scheme.delPart(1)
        self.assertEqual(self.scheme.countProjectComponentMatches(1), 0)
        self.assertEqual(self.conn.execute('SELECT reference FROM PROJECT_COMPONENTS').fetchall(), [('R1',)])

    def test_failed_stock_delete_rolls_back_matches(self):
        self.seed()
        self.conn.execute("CREATE TRIGGER stop_delete BEFORE DELETE ON PARTS "
                          "BEGIN SELECT RAISE(ABORT, 'blocked'); END;")
        with self.assertRaises(sqlite3.IntegrityError):
            self.scheme.delPart(1)
        self.assertEqual(self.scheme.countProjectComponentMatches(1), 1)

    def test_migrate_v4_preserves_cards_links_uris_and_sequences(self):
        self.make_v4()
        with self.conn:
            self.conn.execute("INSERT INTO TYPES(id, name) VALUES (1, 'R')")
            self.conn.execute('INSERT INTO PARTS(id, type_id) VALUES (1, 1)')
            self.conn.execute("INSERT INTO PROJECTS VALUES (7, 'Имя', 'Описание', 'folder/my board.kicad_pro')")
            self.conn.execute("INSERT INTO PROJECTS VALUES (8, 'Web', NULL, 'https://example.org/a%20b?q=1')")
            self.conn.execute("INSERT INTO PROJECTS VALUES (9, 'Empty', NULL, NULL)")
            self.conn.execute("INSERT INTO PROJECTS VALUES (100, 'Deleted', NULL, NULL)")
            self.conn.execute('DELETE FROM PROJECTS WHERE id=100')
            self.conn.execute('INSERT INTO EL_BY_PROJECT(project_id, part_id, quantity) VALUES (7, 1, 2)')
            self.conn.execute('CREATE INDEX custom_project_name ON PROJECTS(name)')
        self.scheme.migrate()
        self.assertEqual(self.conn.execute('SELECT id, name, descr, source_uri FROM PROJECTS WHERE id=7').fetchone(),
                         (7, 'Имя', 'Описание', (self.path.parent / 'folder/my board.kicad_pro').as_uri()))
        self.assertEqual(self.conn.execute('SELECT source_uri FROM PROJECTS WHERE id=8').fetchone()[0],
                         'https://example.org/a%20b?q=1')
        self.assertIsNone(self.conn.execute('SELECT source_uri FROM PROJECTS WHERE id=9').fetchone()[0])
        self.assertEqual(self.conn.execute('SELECT project_id, part_id, quantity FROM EL_BY_PROJECT').fetchall(), [(7, 1, 2)])
        self.assertEqual(self.conn.execute('PRAGMA foreign_keys').fetchone()[0], 1)
        before = list(self.conn.iterdump())
        db._migrate_to_5(self.scheme)
        self.scheme.migrate()
        self.assertEqual(list(self.conn.iterdump()), before)
        self.assertGreater(self.conn.execute("INSERT INTO PROJECTS(name) VALUES ('New')").lastrowid, 100)
        self.assertNotIn('schematic_path', self.columns('PROJECTS'))

    def test_failed_migration_is_atomic_and_retryable(self):
        self.make_v4()
        with self.conn:
            self.conn.execute("INSERT INTO PROJECTS VALUES (1, 'Old', NULL, '/tmp/board.sch')")
        before = list(self.conn.iterdump())
        with mock.patch.object(db, 'PROJECT_IMPORT_SCHEMA_SQL', db.PROJECT_IMPORT_SCHEMA_SQL + ('INVALID SQL;',)):
            with self.assertRaises(sqlite3.OperationalError):
                self.scheme.migrate()
        self.assertEqual(self.scheme.getDBVersion(), 4)
        self.assertEqual(list(self.conn.iterdump()), before)
        self.assertEqual(self.conn.execute('PRAGMA foreign_keys').fetchone()[0], 1)
        self.scheme.migrate()
        self.assertEqual(self.scheme.getDBVersion(), db.DB_VERSION)


if __name__ == '__main__':
    unittest.main()
