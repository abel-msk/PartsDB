"""Cleanup is limited to generated DBs; failure retains bounded diagnostics."""
import os
from pathlib import Path
import tempfile
import unittest

from tools.cleanup_test_databases import cleanup


class CleanupTestDatabasesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        (self.root / 'tests/input').mkdir(parents=True)
        (self.root / 'tests/archive').mkdir()

    def create(self, name, mtime=1):
        path = self.root / name
        path.write_bytes(b'preserve contents')
        os.utime(path, ns=(mtime, mtime))
        return path

    def test_success_removes_scratch_sidecars_and_backups_but_preserves_fixtures(self):
        generated = [self.create('test_db.sqlite'), self.create('test_db.sqlite-wal'),
                     self.create('test_db.sqlite-shm'), self.create('test_db.sqlite-journal'),
                     self.create('test_db.sqlite.bak-before-test'),
                     self.create('tests/imported.sqlite.bak-before-test'),
                     self.create('tests/other.sqlite3.bak'), self.create('tests/other.db.bak.1')]
        fixtures = [self.create('tests/imported.sqlite'), self.create('tests/test_db.sqlite'),
                    self.create('tests/archive/imported.sqlite.bak-1'),
                    self.create('tests/input/example.sqlite.bak-1'),
                    self.create('working.sqlite.bak-1'), self.create('tests/notes.bak')]
        self.assertEqual(set(cleanup(self.root, True)), set(generated))
        self.assertTrue(all(not path.exists() for path in generated))
        self.assertTrue(all(path.read_bytes() == b'preserve contents' for path in fixtures))
        self.assertEqual(cleanup(self.root, True), [])

    def test_failure_keeps_scratch_and_three_latest_backups_per_database(self):
        scratch = self.create('test_db.sqlite')
        sidecar = self.create('test_db.sqlite-wal')
        for database in ('imported.sqlite', 'other.db'):
            for number in range(5):
                self.create(f'tests/{database}.bak-{number}', mtime=number + 1)
        removed = cleanup(self.root, False)
        self.assertEqual(len(removed), 4)
        self.assertTrue(scratch.exists() and sidecar.exists())
        for database in ('imported.sqlite', 'other.db'):
            self.assertEqual(sorted(p.name for p in (self.root / 'tests').glob(database + '.bak-*')),
                             [database + '.bak-' + str(i) for i in (2, 3, 4)])

    def test_rotated_backups_and_their_sidecars_are_removed_together(self):
        old = self.create('tests/imported.sqlite.bak-old', 1)
        old_wal = self.create('tests/imported.sqlite.bak-old-wal', 2)
        new = self.create('tests/imported.sqlite.bak-new', 3)
        new_wal = self.create('tests/imported.sqlite.bak-new-wal', 4)
        self.assertEqual(set(cleanup(self.root, False, keep_backups=1)), {old, old_wal})
        self.assertTrue(new.exists() and new_wal.exists())

    def test_cleanup_unlinks_backup_symlink_without_changing_its_target(self):
        target = self.create('original.sqlite')
        link = self.root / 'tests/imported.sqlite.bak-linked'
        link.symlink_to(target)
        cleanup(self.root, True)
        self.assertFalse(link.exists())
        self.assertEqual(target.read_bytes(), b'preserve contents')


if __name__ == '__main__':
    unittest.main()
