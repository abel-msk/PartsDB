# Changelog

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
- Native crashes now write a Python stack trace to the application log. Technical notes: [Image drop workaround](dev_nodes/img_drop_hack.md).
- Added the MIT License.
