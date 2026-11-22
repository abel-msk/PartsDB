"""Group accepted BOM positions and migrate legacy imports using disposable databases."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from ElData import ElDBScheme as db
from ElPluginMgr.repository import ProjectRepository
from ElPartsPluginApi.importers import ImportedComponent, ImportedProject


class ProjectQuantityTests(unittest.TestCase):
    """Verify grouping, stable links and transactional v12 schema replacement.

    @attr factory [DBFactory] Disposable catalog.
    @attr repo [ProjectRepository] Import persistence boundary.
    """

    def setUp(self):
        """Prepare an isolated catalog and connection.

        @return [None] Register connection and directory cleanup.
        """
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.factory = db.DBFactory(str(Path(folder.name)/'catalog.sqlite'))
        self.addCleanup(self.factory.disconnect)
        self.repo = ProjectRepository(self.factory.scheme)
        self.conn = self.factory.scheme.db.conn

    def test_aggregate_dnp_separately_exclude_non_bom_and_preserve_surviving_group(self):
        """Count duplicate parts including DNP while retaining each assembly state's identities.

        @return [None] Verify exclusion, idempotence, quantity changes and stable confirmed links.
        """
        components = [ImportedComponent('a', 'R1', kind='resistor', value_raw='1K'),
                      ImportedComponent('b', 'R2', kind='resistor', value_raw='1K'),
                      ImportedComponent('c', 'R3', kind='resistor', value_raw='1K', dnp=True),
                      ImportedComponent('d', 'R4', kind='resistor', value_raw='1K', dnp=True),
                      ImportedComponent('e', 'R5', kind='resistor', value_raw='1K', in_bom=False)]
        project = ImportedProject('Groups', components=components)
        identity = self.repo.save(project, 'test', 'file:///tmp/group')
        rows = self.repo.components(identity)
        self.assertEqual([(row['reference'], row['quantity'], row['dnp']) for row in rows],
                         [('R1, R2', 2, 0), ('R3, R4', 2, 1)])
        self.assertNotIn('in_bom', rows[0])
        self.assertEqual(json.loads(rows[0]['properties_json'])['source_external_ids'], ['a','b'])
        self.repo.save(project, 'test', 'file:///tmp/group', identity)
        self.assertEqual(self.repo.components(identity), rows)
        section = self.factory.appendType('R', None, 3)
        stock = self.factory.createPart(section, {'part_num':'test'})
        self.repo.set_match(rows[0]['id'], stock.id)
        project.components.pop(0)
        self.assertEqual(self.repo.changes(project, identity).added, ())
        self.repo.save(project, 'test', 'file:///tmp/group', identity)
        updated = self.repo.components(identity)[0]
        self.assertEqual((updated['id'],updated['reference'],updated['quantity']), (rows[0]['id'],'R2',1))
        self.assertEqual(self.repo.matches(identity)[rows[0]['id']]['needs_review'], 1)

    def legacy(self):
        """Build a v11 component fixture containing duplicates and an excluded BOM row.

        @return [None] Commit a legacy schema without modifying external fixtures.
        """
        with self.conn:
            self.conn.execute('DROP TABLE PROJECT_COMPONENT_MATCHES')
            self.conn.execute('DROP TABLE PROJECT_COMPONENTS')
            sql=db.PROJECT_COMPONENTS_TABLE_SQL.replace('quantity INTEGER NOT NULL DEFAULT 1 CHECK (quantity > 0)',
                'in_bom INTEGER NOT NULL DEFAULT 1 CHECK (in_bom IN (0,1))')
            self.conn.execute(sql)
            self.conn.execute(db.PROJECT_COMPONENT_MATCHES_TABLE_SQL)
            self.conn.execute("INSERT INTO PROJECTS(id,name) VALUES(1,'Legacy')")
            for number, bom in ((1,1),(2,1),(3,0)):
                self.conn.execute('INSERT INTO PROJECT_COMPONENTS(id,project_id,external_id,reference,kind,value_raw,in_bom) VALUES(?,1,?,?,?,?,?)',
                                  (number,str(number),'R'+str(number),'resistor','1K',bom))
            self.conn.execute("UPDATE ENVIRONMENT SET value='11' WHERE name='db_version'")

    def test_migration_merges_rows_retains_links_and_rejects_zero_quantity(self):
        """Migrate grouped quantities while preserving an existing match from a merged-away row.

        @return [None] Verify schema, FK checks, sequence, constraints and repeatable migration.
        """
        self.legacy()
        section=self.factory.appendType('R',None,3)
        stock=self.factory.createPart(section,{'part_num':'test'})
        with self.conn:
            self.conn.execute('INSERT INTO PROJECT_COMPONENT_MATCHES(component_id,part_id) VALUES(2,?)',(stock.id,))
        self.factory.scheme.migrate()
        rows=self.repo.components(1)
        self.assertEqual([(row['reference'],row['quantity']) for row in rows],[('R1, R2',2)])
        self.assertEqual(self.repo.matches(1)[rows[0]['id']]['part_id'], stock.id)
        self.assertEqual(self.conn.execute('PRAGMA foreign_key_check').fetchall(),[])
        self.assertNotIn('in_bom',[row[1] for row in self.conn.execute('PRAGMA table_info(PROJECT_COMPONENTS)')])
        with self.assertRaises(Exception):
            self.conn.execute('UPDATE PROJECT_COMPONENTS SET quantity=0')
        self.conn.rollback()
        before=list(self.conn.iterdump())
        self.factory.scheme.migrate()
        self.assertEqual(list(self.conn.iterdump()),before)
        with self.conn:
            cursor=self.conn.execute("INSERT INTO PROJECT_COMPONENTS(project_id,external_id,reference) VALUES(1,'new','R9')")
        self.assertGreater(cursor.lastrowid,3)

    def test_migration_failure_restores_schema_rows_links_and_version(self):
        """Inject failure after legacy table renaming to check transactional DDL rollback.

        @return [None] Preserve the complete database dump and foreign key setting.
        """
        self.legacy()
        before=list(self.conn.iterdump())
        with mock.patch('ElData.ElDBDataProj.groupedComponents',side_effect=RuntimeError('injected')):
            with self.assertRaisesRegex(RuntimeError,'injected'):
                self.factory.scheme.migrate()
        self.assertEqual(list(self.conn.iterdump()),before)
        self.assertEqual(self.factory.scheme.getDBVersion(),11)
