# Matching project components to the catalog

[Русская версия](parts-matching.md)

Updated: November 24, 2026. The algorithm is implemented in
[ElPartsMatching.py](../ElPartsMatching.py), class `PartsMatching`.

For step-by-step comparisons and tables of accepted and rejected matches, see
[algorithm examples (Russian)](parts-matching-algorithm-examples.md).

## Using automatic matching

Automatic matching finds PartsDB catalog cards for schematic components returned
by an importer plugin. For example, a KiCad resistor `R1` with the value `10K`
can match a resistor card whose keys are `value=10` and `units=кОм`, provided
the mounting types are compatible.

### Preparation

- Install and enable an importer through **Setup → Plugins... → Install from file**.
  Select its `.whl` package; see [installation details (Russian)](plugins-ui.md#менеджер-плагинов).
- On the **Projects** tab, add a project using the installed importer, review
  the preview, and save the components imported from the schematic.
- Populate the catalog. Assign a suitable basic type to each section and choose
  its key columns in the header editor. Matching uses visible keys; for resistors,
  these can be the nominal value and unit. See
  [key columns and basic types (Russian)](catalog-keys-and-layout.md).

### Searching and saving

1. Select an imported project on the **Projects** tab.
2. Click **Link Part**. Importing or opening a project does not start matching.
   The log shows progress and candidates, or **No match**, for each component group.
3. Wait for completion and review the results. `YES` in a project table means
   candidates were found or a confirmed link already exists. It does not by
   itself mean that a candidate has been saved to the database.
4. Click **Save** in the log. Only unique matches for components without an
   existing confirmed link are saved. If several candidates were found, none
   is selected automatically. Existing links are preserved. The log closes
   after a successful save.
5. Use [manual selection in the right panel](#manual-matching-in-the-right-panel)
   for the remaining components. **Unmatched parts** contains only components
   with neither candidates nor a confirmed link. Components with several
   candidates appear in **Used Parts**, rather than in the unmatched list.

**Cancel** closes the log without saving links and stops the search if it is
still running. Candidates remain in memory; unsaved results are lost when the
application closes or the database changes. Links confirmed with **Save** or
**Link** persist in the database and remain available after a restart.

Matching includes catalog cards regardless of stock availability and does not
check whether enough parts are in stock. Importing and matching do not change
stock quantities. If no candidates are found, check the original schematic
Value, the section's basic type, visible key columns, units and package.
After correcting the catalog or reimporting an edited schematic, click **Link Part** again.
See [comparison examples (Russian)](parts-matching-algorithm-examples.md) and
[log controls](#running-a-pass-and-using-the-log).

## Input data and search scope

Matching uses the component's original `Value`: `value` in an input dictionary
or `value_raw` in an imported component. Neither `model` nor the normalized
`nominal` replaces this original value.

`kind` is resolved against basic type names in `BASIC_TYPES` and their aliases.
Standard categories have mappings such as `ic` → Integrated circuit,
`connector` → Jack/Plug, and `module` → Sub-assembly or module.
A recursive CTE builds the section list from the corresponding basic types.
Child sections are included regardless of their own basic type. A section's
name does not determine its category. An unknown `kind` without a matching
type or alias does not trigger a search across the entire catalog.

Comparison uses columns marked `is_key`, respecting inherited settings and
column order. Hidden columns are excluded. Stock availability does not limit
the search: a result identifies a matching catalog card.

## Values with SI units

Numbers with recognized units or prefixes are parsed using `SI_UNITS` and
`SI_UNIT_ALIASES`: English and Russian symbols, multipliers and base-unit
references. Decimal points and commas are supported, as are the micro symbols
`u`, `µ`, `μ` and common resistance suffixes `R`, `Ω`, `k`, `K`, `M`.

Both the source suffix and reference unit symbols are converted to uppercase
before comparison. Full Russian resistance suffixes `кОм` and `МОм` are also
supported. If this makes units with different multipliers share a symbol
(for example, `mR` and `MR`), all interpretations and corresponding candidates
are retained. No confirmed link is chosen automatically. Additional symbols
are edited in the **Aliases** column of the SI unit dialog. Saving refreshes
candidates for the open project without reimporting it. The matcher does not
generate resistance suffixes such as `кОм` or `kR` in its own code.

Each key column can contain:

- A number and unit together, such as `100nF`.
- A number, with the unit in a separate key column.
- A number, with the unit in the visible `units` column.
- A number expressed in the basic type's base unit, when no separate unit
  is populated and no unit can be obtained from the keys.

Dimensions are compared separately, and decimal arithmetic converts values
to their base units. Thus `100nF`, `0.1uF` and a catalog value of `100` + `нФ`
match, whereas `100` + `мкФ` or `100` + `V` do not. Editing the references
changes the next matching pass; there is no hardcoded list of nominal values.

## Values without a recognized unit

Within suitable sections, the original value is compared with each visible key.
For `part_num`, both strings are truncated to the length of the shorter one
and compared without regard to case. Empty strings do not match. Other keys
are compared in full. Leading and trailing whitespace is ignored.

Entirely numeric values are compared as numbers: `0,3` equals `0.3`.
`AMS1117-3.3` matches `AMS1117-3.3-extra` in `part_num`;
`AMS1117` also matches `AMS1117-3.3`. These are candidate matches, not a guarantee
of electrical interchangeability.

## Mounting type

The final step in both numeric and text matching checks `Footprint` against
the catalog card's visible `package` field:

| Text | Interpretation |
|---|---|
| Contains SMD | SMD |
| Contains THT; ТНТ/TNT are also supported | THT |
| Populated without explicit SMD/THT, such as `0805` or `SOT-23` | SMD |
| Empty `package` | Skip the package check |
| Empty `Footprint` | No mounting restriction from the source |

For example, `Capacitor_THT:...` does not match a card with `package=0805`,
whereas `Capacitor_SMD:...` does. This rule applies to both fields. Packages
without a marker are treated as SMD; their geometry is not analyzed.

## Results and project tables

`findCandidates(component)` returns all matching `CatalogMatch` objects in
catalog card ID order. The data class is defined in
[ElData/ElDBDataParts.py](../ElData/ElDBDataParts.py):

- `part_id`: catalog card reference.
- `type_id`: the card's section reference.
- `key_text`: the first matching key column's text in configured order.
- `matched_fields`: names of the matching key columns.

The **Matching status** column in `prj_parts_all` (**Used Parts**) and
`no_matched_tbl` contains a green `YES` button when candidates or a confirmed
link exist, and a red `NO` otherwise. `no_matched_tbl` includes only `NO` rows.
Clicking the button selects the component and updates the right panel through
`ProjWindow.matchingRequested(component_id)`; it does not change the database.

The first candidate's or confirmed card's `key_text` is available in the button
tooltip and `MATCHING_LABEL_ROLE`. Component IDs are stored in `Qt.UserRole`,
candidate IDs in `MATCHING_CANDIDATES_ROLE`, and status in `MATCHING_STATUS_ROLE`.
Complete results are available in `ProjWindow.matchingCandidates`.

Automatic results stay in memory until **Save** is clicked in the log.
Save confirms only unique matches; see [saving rules](#running-a-pass-and-using-the-log).
Existing confirmed links are not replaced automatically. Searching does not
change cards, stock quantities or link tables. SQL is implemented only in
`ElData/ElDBScheme.py`, with search access through functions in
`ElData/ElDBDataParts.py`. No new table or migration is required.

## Manual matching in the right panel

Manual linking is available on the **Projects** tab without switching to the
catalog. **Link Part** starts automatic candidate matching; **Link** in the
right panel saves the card chosen by the user. An automatic pass is not
required before choosing a card manually.

1. Select a project, then a component row in **Used Parts** (`prj_parts_all`)
   or **Unmatched parts** (`no_matched_tbl`). Select any cell in the row,
   or click its `YES` or `NO` button.
2. Choose **Sections** (`section_list`) in the right panel. Sections display
   their full paths, such as `Resistors / SMD`. **Parts** (`parts_list`) lists
   catalog cards from that section and its child sections.
3. Select a card. Its label joins the values of visible key columns with spaces,
   in configured order. For example, nominal value and unit keys can produce
   `10 кОм`. Cards are listed regardless of stock availability.
4. Check **Properties** (`prop_list`). Each visible column appears as one
   standard list row in the format `Heading: value`. Hidden columns and internal
   IDs are excluded. Names and order follow the selected card's section settings.
5. Click **Link**. If the component already has a confirmed link or automatic
   candidates, confirm replacement in the dialog. **No** preserves the previous match.

If no project component or catalog card is selected, the application warns:
**First select a project component and a catalog part.** No link is saved.

Selecting another project row synchronizes all selectors in the right panel:

- If a confirmed link exists, its catalog card is displayed.
- Otherwise, the first candidate is displayed when candidates exist.
- If neither a link nor candidates exist, the section selection and both lists
  are cleared.

Displaying a candidate does not confirm the link. Clicking **Link** writes the
link to `PROJECT_COMPONENT_MATCHES`, clears the review flag, updates both tables,
and selects the component in the main table. It disappears from the unmatched
list. The catalog card and its stock quantity remain unchanged.
Manual selection can link a card that the automatic algorithm did not find;
clicking **Link** does not repeat Value, Kind or mounting checks.

Drag the splitter to resize the right panel. Its width is saved on window close
as `window.project_right_width` and restored when the Projects tab opens.
Switching databases clears the selected component and the right panel lists.

To remove a link, use **Clear stock match** in the main table row's context menu.
The earlier linking workflow is also available: select a card on the catalog tab,
then choose **Link selected stock part** in the project component's context menu.

## Verification

```sh
python -m unittest tests.test_parts_matching tests.test_project_selector -v
./build.sh -t
```

Tests use temporary catalogs to cover SI units and prefixes, separate keys,
hidden columns, aliases, child sections, model comparisons, SMD/THT and table
model references. `tests/test_project_selector.py` checks manual linking,
replacement confirmation, missing selections, selector synchronization,
database changes, cancellation of a section change in the header editor,
and panel width persistence.

After a successful full run, `build.sh` performs the standard cleanup of the
temporary database and test backups. Failed runs retain diagnostic data and
rotate backups.

## Resistor mismatch correction

In the configured test database, resistors use `value` and `units` as keys,
for example `1` + `кОм`. Previously, aliases included `k`, `kR` and `kΩ`, but not
the full `кОм` suffix, so these cards failed unit checks. The Russian `Ом`
suffix was added for prefixes, along with uppercase comparison.

On a temporary copy of the test database, after migration 10 → 11, all 11
resistors in `SMHome_UniversalRound_ESP32_C3_Mini_v4` received candidates.
In another previously imported project, `51k` and `0,002R` remained unmatched
because those values were absent from the test catalog. This was a missing
nominal value, rather than a package-check error.

## Running a pass and using the log

Automatic matching runs only when **Link Part** is clicked. Loading, importing,
switching projects and repainting tables do not start a search.
`ElLogWnd` shows progress over `PROJECT_COMPONENTS` groups and one line per group:
references, Value, quantity, matching keys or **No match**.

After the pass finishes, the log provides **Cancel** and **Save**:

- **Save** writes only results with exactly one candidate and no existing
  confirmed link to `PROJECT_COMPONENT_MATCHES`. New links receive
  `needs_review=0`. Existing confirmed links and their review flags remain
  unchanged. Ambiguous results and components without candidates are skipped;
  use the right panel to select them manually. After a successful save,
  the project tables refresh and the log closes.
- **Cancel** closes the log without saving links. If matching is still running,
  it stops. Computed candidates remain in memory until the database changes
  or the application closes; individual cards can still be confirmed manually.

**Save** is disabled while matching is running and after a failed or interrupted
pass. Saving uses a single transaction: on failure, no new links are written,
the log stays open, and an error message appears. If project components or the
active database changed after the search, stale results cannot be saved;
run matching again.

Starting another pass searches the catalog again. Changing databases clears
in-memory results. After editing units, click **Link Part** again.
Searching alone does not create confirmed links: use **Save** in the log or
**Link** for a selected card in the right panel.
