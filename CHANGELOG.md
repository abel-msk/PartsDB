# Changelog

## Unreleased — 2026-11-19

- Split database access into `ElData/ElDBScheme.py` (application SQL and migrations)
  and `ElData/ElDBConnect.py` (SQLite connection, transactions and system metadata).
  Removed the root `connector.py` and updated import/architecture checks.
- Recorded six project architecture rules in `AGENTS.md`; existing data-class and
  general-constant moves remain separate follow-up actions.

- Added three global plugin types and the common `get_plugin_type()` API.
  Installation checks the method against the manifest; project imports reject other types.
- Schema 6 adds the `PLUGINS` metadata table with a checked `plugin_type` column.
  Migration from v5 preserves projects, components and stock.

- Added the KiCad importer and API 1: local project/schematic reading, recursive sheets,
  one record per physical position, R/C/L nominal normalization and BOM/DNP flags.
- Added wheel installation and updates, same-system replacement, enabled state,
  removal and logs. Imports run in private environments and separate processes
  with progress, cancellation and timeouts.
- Connected the Projects tab to import preview, atomic database persistence,
  repeat import, component tables and confirmed stock matches. Schema 5 stores
  projects, positions and matches while preserving legacy project links on migration.
- Moved plugin sources to `ElPartsPluginSrc`; `./build.sh -p` builds the KiCad wheel
  in `dist/plugins/`. `-tp` tests before building; `-tpb` also builds the application.
- Added the local 49-position KiCad fixture in `tests/input` and plugin tests in
  `tests/kikad_plugin`, independent of the original project directory.
- Successful full test runs remove the scratch DB and test backups; failed runs
  retain the scratch DB and the three newest backups per database. Input fixtures
  and archived databases are preserved.
- Updated Russian/English workflow texts and documentation. The full check on
  2026-11-19 passed 340 tests, including test cleanup and backup rotation.

## 1.3 — 2026-11-15

- Column settings inherit from the nearest ancestor that defines them, falling back to built-in defaults. Editing an inherited setting creates an override for the current section.
- Added an option to propagate column settings to descendant sections.

## 1.2 — 2026-11-14

- Added English and Russian interface translations with language switching without restarting the application.
- Drag a picture from the desktop or a web browser onto a part's icon cell to replace its icon and activate the row. Images are saved as PNG in the icons folder, with unique names and a maximum side of 512 pixels.
- Fixed a macOS crash when saving dragged browser images carrying an ICC color profile, and fixed drag activation when entering the table through another column.
- Added a section selector and a default icon selector to the header editor.
- Fixed hidden-column settings being overwritten when column widths are saved; headers reload after editing.
- Improved icon presentation with rounded frames, shadows and 60-pixel rows.
- Added drag-and-drop regression tests and build script options: `-t` for all tests, `-b` for building, and `-tb` for testing before building. PyInstaller runs through the project's virtual environment.
- Native crashes now write a Python stack trace to the application log. Technical notes: [Image drop workaround](docs/img_drop_hack.md).
- Added the MIT License.
