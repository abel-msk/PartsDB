#!/usr/bin/env python3
"""Clean successful test runs, or rotate backups after a failed run.

Only test_db.sqlite in the repository root and database backups directly in
that root or tests/ are considered. Input fixtures and nested archives are kept.
"""
import argparse
from collections import defaultdict
from pathlib import Path
import re

BACKUP = re.compile(r'(?P<database>.+\.(?:sqlite|sqlite3|db))\.bak(?:$|[-.].*)')
SIDECARS = ('-wal', '-shm', '-journal')


def backup_groups(root):
    groups = defaultdict(dict)
    for directory in (root, root / 'tests'):
        if not directory.is_dir() or directory.is_symlink():
            continue
        for path in directory.iterdir():
            if not path.is_file() and not path.is_symlink():
                continue
            base = path.name
            for suffix in SIDECARS:
                if base.endswith(suffix):
                    base = base[:-len(suffix)]
                    break
            match = BACKUP.fullmatch(base)
            if not match:
                continue
            # The root also contains application files: only the known scratch DB is eligible.
            if directory == root and match['database'] != 'test_db.sqlite':
                continue
            database = directory / match['database']
            groups[database].setdefault(directory / base, []).append(path)
    return groups


def cleanup(root, successful, keep_backups=3):
    if keep_backups < 0:
        raise ValueError('keep_backups must not be negative')
    root = Path(root).resolve()
    removed = []
    for backups in backup_groups(root).values():
        ordered = sorted(backups, key=lambda base: (
            max(path.lstat().st_mtime_ns for path in backups[base]), base.name), reverse=True)
        for base in ordered[0 if successful else keep_backups:]:
            for path in backups[base]:
                path.unlink()
                removed.append(path)
    if successful:
        scratch = root / 'test_db.sqlite'
        for path in (scratch, *(Path(str(scratch) + suffix) for suffix in SIDECARS)):
            if path.is_file() or path.is_symlink():
                path.unlink()
                removed.append(path)
    return removed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    status = parser.add_mutually_exclusive_group(required=True)
    status.add_argument('--success', action='store_true', help='delete scratch DB and test backups')
    status.add_argument('--failed', action='store_true', help='keep scratch DB and rotate backups')
    parser.add_argument('--keep-backups', type=int, default=3, help='backups per database retained on failure (default: 3)')
    args = parser.parse_args()
    if args.keep_backups < 0:
        parser.error('--keep-backups must not be negative')
    root = Path(__file__).resolve().parents[1]
    removed = cleanup(root, successful=args.success, keep_backups=args.keep_backups)
    print(f'Test database cleanup: removed {len(removed)} files')


if __name__ == '__main__':
    main()
