#!/usr/bin/env python3
"""Install PNG files and assign basic-type icon paths after a backup; do not run migrations."""
import argparse
import logging
from datetime import date
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ElData.ElDBScheme import DBScheme
from ElData.ElDBDataUnits import UnitsDataStore
import ElCommon


def main():
    """Back up the selected existing catalog, then assign icons by canonical type name.

    @return [None] Print the backup path and updated type count; propagate errors.
    """
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('database',type=Path)
    parser.add_argument('--debug', action='store_true', help='Show DEBUG diagnostics')
    parser.add_argument('--backup-dir', type=Path, help='Directory for a protected manual backup')
    parser.add_argument('--data-path', type=Path, help='Resolved data_path from the application config')
    parser.add_argument('--backup-date', default=date.today().isoformat(), help='Backup date in YYYY-MM-DD format')
    args=parser.parse_args()
    date.fromisoformat(args.backup_date)
    if args.debug:
        ElCommon.setLevel(logging.DEBUG)
    path=args.database.expanduser().resolve(strict=True)
    backup_dir = args.backup_dir.expanduser().resolve() if args.backup_dir else path.parent
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / (path.name+'.bak-before-basic-type-icon-files-'+args.backup_date)
    if backup.exists():
        raise FileExistsError('Backup already exists: '+str(backup))
    scheme=DBScheme(str(path))
    scheme.connect()
    try:
        scheme.db.backupTo(str(backup))
        data_path = args.data_path.expanduser().resolve() if args.data_path else path.parent
        installed = ElCommon.installBasicTypeIcons(str(data_path), str(Path(__file__).resolve().parents[1]/'qt'/'el_icons'))
        count=UnitsDataStore(scheme).assignDefaultIcons(installed)
        print('Backup: '+str(backup))
        print('Assigned basic type icons: '+str(count))
    finally:
        scheme.disconnect()


if __name__=='__main__':
    main()
