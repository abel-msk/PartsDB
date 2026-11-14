# Image drag-and-drop: crash workaround and event handling

Two independent problems affected pictures dragged from a web browser onto a
part's icon cell: a native crash while saving the PNG, and a drop target that
became active only after moving over the types tree.

## 1. Native crash while saving a browser image

The browser supplied both an image URL and a ready-made `QImage` carrying an ICC
color profile. The application selected the image data directly.

The logs established that:

- Reading and scaling the pixels succeeded.
- Saving the image crashed inside Qt's `QImage.save()` / `QImageWriter::write()`.
- Diagnostic code subsequently crashed while reading
  `image.colorSpace().iccProfile()` itself.

This isolated the color profile as the problematic data. The likely explanation
is that the profile retained a reference to native macOS drag memory that was
released after the drag. Memory ownership was not conclusively proven, but the
crash location and the successful workaround support this explanation.

The first attempted fix, `QImage.copy()`, did not solve the problem. Copying the
pixels did not remove the problematic color profile.

### Workaround in `ElIconDrop.py`

1. At drop time, rebuild the color space from its parameters without reading the
   original ICC bytes. Standard sRGB and Display P3 spaces can be reconstructed;
   unsupported custom profiles are discarded.
2. Before saving, convert the image to sRGB.
3. Build a fresh ARGB32 image containing only the pixels, without the original
   color profile or metadata.
4. Save this clean image as PNG.

The relevant helpers are `safeColorSpace()`, `ownedImage()`, and `plainImage()`.
This bypasses the problematic profile-handling path; it does not fix Qt itself.
The user confirmed that browser image drops worked after this change.

## 2. Drop target activated only after hovering over the types tree

Originally, the table accepted `DragEnter` only when the cursor entered directly
over the icon column. Entering over another column caused the event to be
ignored.

Qt does not deliver subsequent `DragMove` events to a widget that rejected
`DragEnter`. Consequently, moving from another column onto the icon cell within
the table was never detected. Moving over the types tree and returning created a
new entry, this time through the leftmost icon column, which was accepted.

### Fix in `ElPartsTable.py`

The table now accepts an external picture drag entering over any column so it
continues receiving movement events. Outside the icon column, the action remains
`IgnoreAction`; over a valid icon cell, it becomes `CopyAction` and the cell is
highlighted. The actual drop is allowed only on an icon cell.

## Why the original tests missed these problems

The original tests used ordinary images created in Python, which did not reproduce
the native browser color-profile issue. They also started the drag directly over
the icon cell, missing the rejected-entry route through another column.

Additional tests cover safe color-space handling and the sequence of entering
over another column, moving onto an icon cell, and dropping. These verify the
workaround's behavior, but do not reproduce or prove the suspected native memory
ownership bug. Real browser dragging was checked by the user. The final test run
passed all 207 tests.
