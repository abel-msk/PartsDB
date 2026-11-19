"""Exercise the standalone SQLite driver on in-memory databases."""
from pathlib import Path
import sqlite3
import subprocess
import sys
import unittest

from ElData.ElDBConnect import DBError, DBSyntax, SQLiteConnector


class SQLiteConnectorTests(unittest.TestCase):
    """Check SQLite lifecycle, transaction and metadata operations; stores a memory driver."""

    def setUp(self):
        """Create one isolated in-memory driver; no parameters or filesystem database."""
        self.db = SQLiteConnector(':memory:')
        self.db.connect()
        self.addCleanup(self.db.disconnect)

    def test_connection_is_idempotent_and_close_releases_handle(self):
        """Repeated connect returns one handle; disconnect makes further execution fail."""
        self.assertIs(self.db.connect(), self.db.conn)
        self.assertTrue(self.db.isConnect())
        self.db.disconnect()
        with self.assertRaises(sqlite3.ProgrammingError):
            self.db.execute('SELECT 1')

    def test_borrowing_a_connection_does_not_close_it_at_transaction_exit(self):
        """Borrow the existing SQLite handle; a successful transaction leaves it usable."""
        borrowed = SQLiteConnector.from_connection(self.db.conn)
        self.assertIs(borrowed.conn, self.db.conn)
        with borrowed.transaction(require_idle=True):
            borrowed.execute('CREATE TABLE borrowed(value TEXT)')
            borrowed.execute('INSERT INTO borrowed VALUES (?)', ('kept',))
        self.assertEqual(self.db.select_all('SELECT value FROM borrowed;'), [('kept',)])
        with self.assertRaises(TypeError):
            SQLiteConnector.from_connection(object())

    def test_transaction_commits_or_rolls_back_all_changes(self):
        """Bound values are literal data; immediate transactions commit success and roll back failures."""
        self.db.exec('CREATE TABLE values_table(value TEXT);')
        text = "quote'; DROP TABLE values_table;--"
        with self.db.transaction(require_idle=True, immediate=True):
            self.assertTrue(self.db.in_transaction)
            self.db.execute('INSERT INTO values_table VALUES (?)', (text,))
            self.db.executemany('INSERT INTO values_table VALUES (?)', [('second',), ('third',)])
        self.assertFalse(self.db.in_transaction)
        before = self.db.select_all('SELECT value FROM values_table;')
        with self.assertRaises(RuntimeError):
            with self.db.transaction(require_idle=True):
                self.db.execute('DELETE FROM values_table')
                raise RuntimeError('test rollback')
        self.assertEqual(self.db.select_all('SELECT value FROM values_table;'), before)
        self.assertEqual(before, [(text,), ('second',), ('third',)])

    def test_complete_statement_validation_and_bound_selection(self):
        """Reject incomplete SQL; preserve bound-value selection and wrapped DDL errors."""
        self.db.exec('CREATE TABLE selected(id INTEGER PRIMARY KEY,value TEXT);')
        record_id = self.db.exec_insert('INSERT INTO selected(value) VALUES (?);', ('quoted value',))
        cursor = self.db.select_params('SELECT value FROM selected WHERE id=?;', (record_id,))
        try:
            self.assertEqual(cursor.fetchone(), ('quoted value',))
        finally:
            cursor.close()
        for operation in (self.db.select, self.db.exec):
            with self.subTest(operation=operation), self.assertRaises(DBSyntax):
                operation('SELECT 1')
        with self.assertRaises(DBSyntax):
            self.db.exec('INVALID SQL;')

    def test_foreign_key_mode_and_violations(self):
        """Foreign-key PRAGMA changes require idle state; orphan detection works independently."""
        self.db.set_foreign_keys(False)
        self.db.exec('CREATE TABLE parent(id INTEGER PRIMARY KEY);')
        self.db.exec('CREATE TABLE child(parent_id INTEGER REFERENCES parent(id));')
        self.db.execute('INSERT INTO child VALUES (99)')
        with self.assertRaises(DBError):
            self.db.set_foreign_keys(True)
        self.assertFalse(self.db.get_foreign_keys())
        self.db.commit()
        violations = self.db.foreign_key_violations()
        self.assertEqual({row[0] for row in violations}, {'child'})
        self.db.exec('INSERT INTO parent VALUES (99);')
        self.assertEqual(self.db.foreign_key_violations(), set())
        with self.db.transaction(require_idle=True, foreign_keys=True):
            self.assertTrue(self.db.get_foreign_keys())
        self.assertTrue(self.db.get_foreign_keys())

    def test_table_metadata_quotes_identifiers_and_lists_schema_objects(self):
        """Read columns/DDL/indexes/triggers safely for a table whose name contains quotes."""
        self.db.exec('CREATE TABLE "odd ""table"""(id INTEGER PRIMARY KEY,value TEXT);')
        self.db.exec('CREATE INDEX odd_index ON "odd ""table"""(value);')
        self.db.exec('CREATE TRIGGER odd_trigger AFTER INSERT ON "odd ""table""" BEGIN SELECT 1; END;')
        table = 'odd "table"'
        self.assertEqual([row[1] for row in self.db.table_info(table)], ['id', 'value'])
        self.assertIn('CREATE TABLE', self.db.table_definition(table))
        objects = self.db.schema_objects(table)
        self.assertEqual(len(objects), 2)
        self.assertTrue(any(text.startswith('CREATE INDEX') for text in objects))
        self.assertTrue(any(text.startswith('CREATE TRIGGER') for text in objects))
        self.assertEqual(self.db.table_info('absent"; DROP TABLE parent;--'), [])
        self.assertIsNone(self.db.table_definition('absent'))
        self.assertEqual(self.db.sequence_value(table), None)

    def test_autoincrement_sequence_is_preserved_without_decreasing_it(self):
        """Preserve a deleted maximum ID across rebuilds; a smaller minimum cannot lower it."""
        self.db.exec('CREATE TABLE seq_test(id INTEGER PRIMARY KEY AUTOINCREMENT,value TEXT);')
        self.db.exec("INSERT INTO seq_test(id,value) VALUES (100,'deleted');")
        self.db.exec('DELETE FROM seq_test;')
        self.assertEqual(self.db.sequence_value('seq_test'), 100)
        self.db.preserve_sequence('seq_test', 200)
        self.db.commit()
        self.assertEqual(self.db.exec_insert('INSERT INTO seq_test(value) VALUES (?);', ('new',)), 201)
        self.db.preserve_sequence('seq_test', 50)
        self.assertEqual(self.db.sequence_value('seq_test'), 201)
        self.assertIsNone(self.db.sequence_value('absent'))

    def test_driver_import_does_not_load_qt_or_application_schema(self):
        """Import this module in a clean process using only the standard library and logging."""
        root = Path(__file__).resolve().parents[1]
        code = (f'import sys; sys.path.insert(0, {str(root)!r}); '
                'from ElData.ElDBConnect import SQLiteConnector; '
                'assert "PyQt6" not in sys.modules; '
                'assert "ElData.ElDBScheme" not in sys.modules')
        subprocess.run([sys.executable, '-I', '-c', code], check=True, capture_output=True, timeout=10)


if __name__ == '__main__':
    unittest.main()
