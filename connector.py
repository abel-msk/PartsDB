import os
import sys
import sqlite3 # https://docs.python.org/3/library/sqlite3.html
import logging
from sqlite3 import Cursor
from sqlite3 import Error
import ElLogger

# logger = logging.getLogger(__name__)
# logger.setLevel(level=logging.DEBUG)
# handler = logging.StreamHandler(stream=sys.stderr)
# # handler.setFormatter(Formatter(fmt='[%(levelname)s] %(name)s: %(message)s'))
# handler.setFormatter(logging.Formatter(fmt='[%(levelname)s] %(module)s/%(funcName)s: %(message)s'))
# logger.addHandler(handler)

logger = ElLogger.setLogger(__name__)

# logger = logging.getLogger(__name__)
# logger.setLevel(level=logging.DEBUG)
# handler = logging.StreamHandler(stream=sys.stderr)
# handler.setFormatter(logging.Formatter(fmt='%(asctime)s [%(levelname)s] %(module)s/%(funcName)s: %(message)s'))
# logger.addHandler(handler)


class DBError(Exception):
    def __init__(self, err_str: str):
        # Call the base class constructor with the parameters it needs
        super().__init__(err_str)


class DBSyntax(Exception):
    def __init__(self, err_str: str):
        # Call the base class constructor with the parameters it needs
        super().__init__(err_str)


class SQLiteConnector:
    def __init__(self, db_path: str, create: bool = True):
        self.dbPath = db_path
        self.conn = None
        # self.connect(False)

    def connect(self):
        if self.isConnect():
            return self.conn
        self.conn = sqlite3.connect(self.dbPath)
        logger.debug("Connect DB : %s", self.dbPath)
        # sqlite3.connect(database, timeout=5.0, detect_types=0, isolation_level='DEFERRED', check_same_thread=True,
        #                factory=sqlite3.Connection, cached_statements=128, uri=False, *,
        #                autocommit=sqlite3.LEGACY_TRANSACTION_CONTROL)¶

    def isConnect(self):
        return True if self.conn is not None else False

    def disconnect(self):
        logger.debug("SQLite close connection")
        self.conn.close()

    def select_all(self, sql_str):
        if sqlite3.complete_statement(sql_str):
            logger.debug("SQLite execute: %s", sql_str)
            cur = self.conn.cursor()
            cur.execute(sql_str)
            return cur.fetchall()
        else:
            raise DBSyntax("SQLite select_all: Incorrect SQL syntax {}".format(sql_str))

    def select(self, sql_str) -> Cursor:
        if sqlite3.complete_statement(sql_str):
            logger.debug("SQLite select: %s", sql_str)
            cur = self.conn.cursor()
            cur.execute(sql_str)
            return cur
        else:
            raise DBSyntax("SQLite get: Incorrect SQL syntax {}".format(sql_str))

    def exec(self, sql_str) -> int:
        if sqlite3.complete_statement(sql_str):
            try:
                logger.debug("SQLite execute: %s", sql_str)
                curr = self.conn.execute(sql_str)
                recId = curr.lastrowid
                self.conn.commit()
            except sqlite3.OperationalError as e:
                # raise sqlite3.OperationalError
                raise DBSyntax("SQLite OperationalError: {} >>> SQL:{}".format(e, sql_str))
            return recId
        else:
            raise DBSyntax("SQLite get: Incorrect SQL syntax {}".format(sql_str))

    def exec_insert(self, sql_str, values) -> int:
        if sqlite3.complete_statement(sql_str):
            try:
                logger.debug("SQLite execute: %s, values:%s", sql_str, ", ".join(map(str, values)))
                curr = self.conn.execute(sql_str, values)
                recId = curr.lastrowid
                self.conn.commit()
                return recId

            except sqlite3.OperationalError as e:
                # raise sqlite3.OperationalError
                raise DBSyntax("SQLite OperationalError: {} >>> SQL:{}".format(e, sql_str))
        else:
            raise DBSyntax("SQLite get: Incorrect SQL syntax {}".format(sql_str))

    def commit(self):
        if self.isConnect():
            self.conn.commit()

