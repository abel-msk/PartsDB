"""Enforce domain SQL and SQLite-driver boundaries after the package move."""
import ast
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import unittest
from unittest import mock

from ElData import ElDBConnect, ElDBScheme

def production_paths():
    """Yield maintained Python sources, respecting ignored local exports and build trees."""
    root = Path(__file__).resolve().parents[1]
    if (root / '.git').exists():
        names = subprocess.check_output(
            ['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'], cwd=root).decode().split('\0')
        for name in sorted(set(names)):
            path = root / name
            if name.endswith('.py') and not name.startswith('tests/') and path.is_file():
                yield path
        return
    # Source archives contain the same application directories without Git metadata.
    for folder, directories, files in os.walk(root):
        directories[:] = [name for name in directories
                          if not name.startswith('.') and name not in
                          ('tests', 'venv', 'build', 'dist', '__pycache__')
                          and not name.endswith('.egg-info')]
        for name in files:
            if name.endswith('.py'):
                yield Path(folder) / name


class DatabaseAccessBoundaryTests(unittest.TestCase):
    """Inspect production sources for misplaced DB operations; stores no database records."""

    def test_sql_imports_and_execution_are_centralized(self):
        """Require SQL execution to stay inside the schema/driver pair in ElData."""
        root = Path(__file__).resolve().parents[1]
        violations = []
        sql = re.compile(r'^\s*(SELECT|INSERT|UPDATE|DELETE|PRAGMA|CREATE|ALTER|DROP|BEGIN|COMMIT|ROLLBACK)\b')
        execution = {'execute', 'executemany', 'executescript', 'cursor', 'commit',
                     'rollback', 'fetchone', 'fetchall', 'select_params', 'select_all', 'exec_insert'}
        for path in production_paths():
            if path in (root / 'ElData/ElDBScheme.py', root / 'ElData/ElDBConnect.py'):
                continue
            tree = ast.parse(path.read_text(encoding='utf-8'))
            docstrings = {id(node.body[0].value) for node in ast.walk(tree)
                          if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
                          and node.body and isinstance(node.body[0], ast.Expr)
                          and isinstance(node.body[0].value, ast.Constant)
                          and isinstance(node.body[0].value.value, str)}
            for node in ast.walk(tree):
                reason = None
                if isinstance(node, ast.Import) and any(alias.name == 'sqlite3' for alias in node.names):
                    reason = 'SQLite import'
                elif isinstance(node, ast.ImportFrom) and node.module == 'sqlite3':
                    reason = 'SQLite import'
                elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in execution:
                    reason = 'database/cursor operation'
                elif isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings and sql.match(node.value):
                    reason = 'SQL statement or fragment'
                if reason:
                    violations.append(f'{path.relative_to(root)}:{node.lineno}: {reason}')
        self.assertEqual(violations, [])

    def test_sqlite_imports_and_system_queries_are_driver_only(self):
        """Keep SQLite APIs, PRAGMA and system tables out of domain schema methods."""
        root = Path(__file__).resolve().parents[1]
        schema = (root / 'ElData/ElDBScheme.py').read_text()
        tree = ast.parse(schema)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                self.assertFalse(any(alias.name == 'sqlite3' for alias in node.names))
            elif isinstance(node, ast.ImportFrom):
                self.assertNotEqual(node.module, 'sqlite3')
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                self.assertNotRegex(node.value, r'(?i)sqlite_master|sqlite_sequence|^\s*PRAGMA\b')
        self.assertIs(ElDBScheme.SQLiteConnector, ElDBConnect.SQLiteConnector)
        self.assertIs(ElDBScheme.DBError, ElDBConnect.DBError)
        self.assertIs(ElDBScheme.DBSyntax, ElDBConnect.DBSyntax)
        self.assertFalse((root / 'connector.py').exists())

    def test_borrowed_connection_is_not_reopened_and_pending_work_is_preserved(self):
        """Wrap an existing SQLite handle; reject nested transactions without committing it."""
        conn = sqlite3.connect(':memory:')
        self.addCleanup(conn.close)
        with mock.patch('ElData.ElDBConnect.sqlite3.connect') as connect:
            scheme = ElDBScheme.DBScheme.using(conn)
            self.assertIs(ElDBScheme.DBScheme.using(scheme), scheme)
            connect.assert_not_called()
        conn.execute('CREATE TABLE scratch(value TEXT)')
        conn.execute("INSERT INTO scratch VALUES ('pending')")
        with self.assertRaises(ElDBScheme.DBError):
            with scheme.transaction():
                self.fail('A nested transaction must not start')
        self.assertTrue(conn.in_transaction)
        conn.rollback()
        self.assertEqual(conn.execute('SELECT * FROM scratch').fetchall(), [])


if __name__ == '__main__':
    unittest.main()
