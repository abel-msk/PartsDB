"""SQLite driver: connections, execution, transactions and SQLite system metadata."""
from contextlib import contextmanager
import sqlite3
from sqlite3 import Cursor

import ElLogger

logger = ElLogger.setLogger(__name__)


class DBError(Exception):
    """Report a database lifecycle/transaction error; stores a diagnostic string."""

    def __init__(self, err_str: str):
        """Store a diagnostic str; keyword err_str is supported for existing callers."""
        super().__init__(err_str)


class DBSyntax(Exception):
    """Report invalid or rejected SQL; stores the execution diagnostic string."""

    def __init__(self, err_str: str):
        """Store a diagnostic str explaining the invalid statement."""
        super().__init__(err_str)


class SQLiteConnector:
    """Wrap a SQLite connection and its path; contains no application table definitions."""

    def __init__(self, db_path: str, create: bool = True):
        """Store a filesystem path or ':memory:'; bool create is kept for compatibility."""
        self.dbPath = db_path
        self.conn = None

    @classmethod
    def from_connection(cls, connection) -> 'SQLiteConnector':
        """Borrow an existing sqlite3.Connection without opening or copying a database."""
        if not isinstance(connection, sqlite3.Connection):
            raise TypeError('Expected sqlite3.Connection')
        instance = cls('')
        instance.conn = connection
        return instance

    def connect(self):
        """Open the stored SQLite path once; repeated calls return the existing connection."""
        if self.isConnect():
            return self.conn
        self.conn = sqlite3.connect(self.dbPath)
        logger.debug('Connect DB : %s', self.dbPath)
        return self.conn

    def isConnect(self) -> bool:
        """Return whether a connection has been assigned; does not execute a query."""
        return self.conn is not None

    def disconnect(self):
        """Close the current handle; keep it available for existing lifecycle diagnostics."""
        logger.debug('SQLite close connection')
        self.conn.close()

    @property
    def in_transaction(self) -> bool:
        """Return SQLite's transaction state for the assigned connection."""
        return self.conn.in_transaction

    def execute(self, sql_str: str, values=()) -> Cursor:
        """Execute one SQL statement with bound sequence/mapping values; never commit."""
        return self.conn.execute(sql_str, values)

    def executemany(self, sql_str: str, values) -> Cursor:
        """Execute one statement for an iterable of parameter sequences; never commit."""
        return self.conn.executemany(sql_str, values)

    def select_all(self, sql_str: str) -> list:
        """Execute a complete SQL str, return all tuples and close the result cursor."""
        cursor = self.select(sql_str)
        try:
            return cursor.fetchall()
        finally:
            cursor.close()

    def select(self, sql_str: str) -> Cursor:
        """Execute a complete SQL str; the caller owns and closes the returned cursor."""
        if not sqlite3.complete_statement(sql_str):
            raise DBSyntax('SQLite get: Incorrect SQL syntax {}'.format(sql_str))
        logger.debug('SQLite select: %s', sql_str)
        return self.execute(sql_str)

    def select_params(self, sql_str: str, values) -> Cursor:
        """Execute complete SQL with bound sequence/mapping values and return its cursor."""
        if not sqlite3.complete_statement(sql_str):
            raise DBSyntax('SQLite get: Incorrect SQL syntax {}'.format(sql_str))
        logger.debug('SQLite select: %s', sql_str)
        return self.execute(sql_str, values)

    def exec(self, sql_str: str) -> int:
        """Execute a complete SQL str, commit it and return the last inserted ID."""
        return self.exec_insert(sql_str, ())

    def exec_insert(self, sql_str: str, values) -> int:
        """Execute complete SQL with bound values, commit it and return the last ID."""
        if not sqlite3.complete_statement(sql_str):
            raise DBSyntax('SQLite get: Incorrect SQL syntax {}'.format(sql_str))
        try:
            logger.debug('SQLite execute: %s', sql_str)
            cursor = self.execute(sql_str, values)
            self.commit()
            return cursor.lastrowid
        except sqlite3.OperationalError as exc:
            raise DBSyntax('SQLite OperationalError: {} >>> SQL:{}'.format(exc, sql_str)) from exc

    def commit(self):
        """Commit pending work if a connection exists; does not close the handle."""
        if self.isConnect():
            self.conn.commit()

    def rollback(self):
        """Roll back pending work if a connection exists; does not close the handle."""
        if self.isConnect():
            self.conn.rollback()

    def begin(self, immediate: bool = False):
        """Begin a transaction; immediate=True requests SQLite's immediate write lock."""
        self.execute('BEGIN IMMEDIATE' if immediate else 'BEGIN')

    @contextmanager
    def transaction(self, require_idle: bool = False, foreign_keys=None, immediate: bool = False):
        """Commit success or roll back an exception, without closing the connection.

        require_idle (bool) rejects existing work when True. foreign_keys is None
        to preserve the setting or bool to set it before starting. immediate=True
        starts BEGIN IMMEDIATE when there is no active transaction.
        """
        if require_idle and self.in_transaction:
            raise DBError('Finish the current database transaction before changing data')
        if foreign_keys is not None:
            if self.in_transaction:
                raise DBError('Set foreign key mode before starting a transaction')
            self.set_foreign_keys(foreign_keys)
        with self.conn:
            if immediate and not self.in_transaction:
                self.begin(immediate=True)
            yield self

    def get_foreign_keys(self) -> bool:
        """Return the current PRAGMA foreign_keys setting as bool."""
        return bool(self.execute('PRAGMA foreign_keys').fetchone()[0])

    def set_foreign_keys(self, enabled: bool):
        """Set PRAGMA foreign_keys to bool enabled; caller must have no active transaction."""
        if self.in_transaction:
            raise DBError('Set foreign key mode before starting a transaction')
        self.execute('PRAGMA foreign_keys=' + str(int(bool(enabled))))

    def foreign_key_violations(self) -> set:
        """Return PRAGMA foreign_key_check rows as a set for migration comparison."""
        return set(self.execute('PRAGMA foreign_key_check').fetchall())

    @staticmethod
    def _identifier(name: str) -> str:
        """Quote a SQLite identifier str, including embedded double quotes."""
        return '"' + name.replace('"', '""') + '"'

    def table_info(self, table: str) -> list:
        """Return SQLite PRAGMA table_info tuples for a table name str."""
        return self.execute('PRAGMA table_info(' + self._identifier(table) + ')').fetchall()

    def table_definition(self, table: str):
        """Return CREATE SQL for a table name str, or None when it does not exist."""
        row = self.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
        return row[0] if row else None

    def schema_objects(self, table: str) -> list:
        """Return non-NULL index/trigger CREATE statements for a table name str."""
        rows = self.execute("SELECT sql FROM sqlite_master WHERE tbl_name=? "
                            "AND type IN ('index','trigger') AND sql IS NOT NULL", (table,)).fetchall()
        return [row[0] for row in rows]

    def sequence_value(self, table: str):
        """Return a table's sqlite_sequence int, or None when no sequence exists."""
        if self.table_definition('sqlite_sequence') is None:
            return None
        row = self.execute('SELECT seq FROM sqlite_sequence WHERE name=?', (table,)).fetchone()
        return row[0] if row else None

    def preserve_sequence(self, table: str, minimum: int):
        """Keep an existing AUTOINCREMENT sequence at least minimum (int); never commit."""
        self.execute('UPDATE sqlite_sequence SET seq=MAX(seq,?) WHERE name=?', (minimum, table))
