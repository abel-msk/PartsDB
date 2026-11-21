# Changelog

## 2.0 — 2026-11-21

- Added the KiCad importer and API 1: recursive project/schematic reading, one row per physical
  position, R/C/L normalization and BOM/DNP flags. Imports run in isolated environments and
  processes with progress, cancellation and timeouts.
- Added plugin wheel installation, updates, same-system replacement, enable/disable, removal
  and logs. Saved plugin cards declare `project_import`, `parts_order` or `shipment_tracking`;
  only importers are offered for project import.
- Connected the Projects tab to preview, atomic persistence, repeat imports and stock matches.
  Importing preserves inventory quantities; changed requirements mark existing matches for review.
- Added basic component types, inherited matching keys, shared two-line list presentation and
  saved widths for project tables. Main window tab and panel settings persist across launches.
- Added the SI unit and basic type editor under Setup. The initial 125 units cover farads,
  henries, ohms, volts and amperes with SI prefixes. Prefixed units and component types link
  to base units through `base_unit_id`; types without a unit retain NULL.
- Reference editing supports confirmed deletion, validation, atomic Save and Cancel. Base units
  still referenced by remaining rows cannot be deleted. Reference cells use named selectors;
  fixed text overlap while editing them.
- Added per-plugin application paths and argument templates, saved on closing the manager.
  Projects can launch the configured executable or macOS .app independently of PartsDB;
  `{file}` substitution preserves paths containing spaces.
- Database schema 9 includes project/import tables, plugin metadata, catalog references and SI
  unit links. Migrations 8 and 9 are atomic and preserve existing inventory and project data.
- Centralized application SQL in `ElData/ElDBScheme.py` and SQLite infrastructure in
  `ElData/ElDBConnect.py`; added data modules and documented classes and methods with YARD tags.
- Added `./build.sh -p` for the KiCad wheel, local importer fixtures and regression coverage.
  Full test success cleans scratch databases and test backups; failure retains diagnostic data.
- Updated English/Russian interface catalogs, README and workflow/schema documentation.

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
