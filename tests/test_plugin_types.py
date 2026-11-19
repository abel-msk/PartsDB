"""Common plugin types and the v5 -> v6 plugin metadata migration."""
from dataclasses import replace
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest import mock

import constants
from ElData import ElDBScheme as db
from ElPartsPluginApi import (Plugin, PLUGIN_TYPE_IMPORT, PLUGIN_TYPE_PARTS_ORDER,
                             PLUGIN_TYPE_SHIPMENT_TRACKING, PLUGIN_TYPES)
from ElPartsPluginApi.importers import PluginError, ProjectImporter
from ElPartsPluginApi.importers.manifest import PluginManifest
from ElPluginMgr.installer import InstalledPlugin
from ElPluginMgr.manager import store_plugin

ROOT = Path(__file__).resolve().parents[1]
METADATA = json.loads((ROOT / 'ElPartsPluginSrc/kicad/partsdb-plugin.json').read_text())


class PluginTypeContractTests(unittest.TestCase):
    def test_three_global_types_are_shared_by_host_and_sdk(self):
        self.assertEqual(PLUGIN_TYPES, {'project_import', 'parts_order', 'shipment_tracking'})
        for name in ('PLUGIN_TYPE_IMPORT', 'PLUGIN_TYPE_PARTS_ORDER', 'PLUGIN_TYPE_SHIPMENT_TRACKING'):
            self.assertEqual(getattr(constants, name), globals()[name])
        self.assertTrue(issubclass(ProjectImporter, Plugin))
        with self.assertRaises(TypeError):
            Plugin()

    def test_each_known_type_is_declared_in_the_manifest(self):
        for value in PLUGIN_TYPES:
            with self.subTest(value=value):
                manifest = PluginManifest.from_dict(dict(METADATA, plugin_type=value, capabilities=[value]))
                self.assertEqual(manifest.plugin_type, value)
                self.assertEqual(manifest.to_dict()['plugin_type'], value)

    def test_type_is_required_and_capability_must_match(self):
        missing = dict(METADATA)
        missing.pop('plugin_type')
        for metadata in (missing, dict(METADATA, plugin_type='unknown'),
                         dict(METADATA, plugin_type=PLUGIN_TYPE_PARTS_ORDER)):
            with self.subTest(metadata=metadata), self.assertRaises(PluginError):
                PluginManifest.from_dict(metadata)


class PluginTableMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.scheme = db.DBScheme(str(Path(self.temp.name) / 'test.sqlite'))
        self.scheme.connect()
        self.addCleanup(self.scheme.disconnect)
        self.scheme.createTables()
        self.conn = self.scheme.db.conn

    def make_v5(self):
        with self.conn:
            self.conn.execute('DROP TABLE PLUGINS')
            self.conn.execute("UPDATE ENVIRONMENT SET value='5' WHERE name='db_version'")
            self.conn.execute("INSERT INTO PROJECTS(id,name,plugin_id) VALUES (1,'Keep project','org.partsdb.kicad')")
            self.conn.execute("INSERT INTO PROJECT_COMPONENTS(project_id,external_id,reference) VALUES (1,'keep','R1')")

    def test_migration_preserves_projects_and_positions_and_is_repeatable(self):
        self.make_v5()
        self.scheme.migrate()
        self.assertEqual(self.scheme.getDBVersion(), 6)
        self.assertEqual(self.conn.execute('SELECT name FROM PROJECTS').fetchall(), [('Keep project',)])
        self.assertEqual(self.conn.execute('SELECT reference FROM PROJECT_COMPONENTS').fetchall(), [('R1',)])
        self.assertEqual(self.conn.execute('SELECT count(*) FROM PLUGINS').fetchone(), (0,))
        before = list(self.conn.iterdump())
        self.scheme.migrate()
        self.assertEqual(list(self.conn.iterdump()), before)

    def test_failed_migration_is_atomic_and_retryable(self):
        self.make_v5()
        before = list(self.conn.iterdump())
        with mock.patch.object(db, 'PLUGINS_TABLE_SQL', 'INVALID SQL'):
            with self.assertRaises(sqlite3.OperationalError):
                self.scheme.migrate()
        self.assertEqual(self.scheme.getDBVersion(), 5)
        self.assertEqual(list(self.conn.iterdump()), before)
        self.scheme.migrate()
        self.assertEqual(self.scheme.getDBVersion(), 6)

    def test_table_rejects_unknown_type(self):
        manifest = PluginManifest.from_dict(METADATA)
        plugin = InstalledPlugin(replace(manifest, plugin_type='unknown'), Path(self.temp.name))
        with self.assertRaises(sqlite3.IntegrityError), self.conn:
            store_plugin(self.conn, plugin)
        self.assertEqual(self.conn.execute('SELECT count(*) FROM PLUGINS').fetchone(), (0,))
