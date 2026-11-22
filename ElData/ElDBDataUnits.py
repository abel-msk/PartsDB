"""Reference data for the units and basic component type editor."""
import ElCommon
import math

from .ElDBScheme import DBScheme


logger = ElCommon.setLogger(__name__)


class UnitsDataStore:
    """Read and validate reference data for the units and basic type editor.

    @attr scheme [DBScheme] Borrowed active scheme; this store does not own its connection."""

    def __init__(self, database):
        """Borrow the active database schema without opening another connection.

        @param database [DBScheme, sqlite3.Connection] Connected database scheme or borrowed SQLite handle.
        @return [None] No value is returned."""
        self.scheme = DBScheme.using(database)

    def units(self):
        """Read persisted units ordered by ID.

        @return [list[tuple]] Rows: id, name, name_ru, marker, marker_ru, multiply, base_unit_id."""
        return self.scheme.loadSiUnits()

    def basicTypes(self):
        """Read persisted basic component types ordered by ID.

        @return [list[tuple]] Rows: id, name, designator, icon, base_unit_id, alias_of_id."""
        return self.scheme.loadUnitBasicTypes()

    def aliases(self):
        """Read alternate SI spellings without duplicating dimension or multiplier data.

        @return [dict[int, tuple[str]]] Unit IDs mapped to editable aliases.
        """
        return self.scheme.loadSiUnitAliases()

    def save(self, units, basic_types, aliases=None):
        """Validate and commit both edited reference lists atomically.

        English unit names and markers must be ASCII. Decimal multipliers may use a dot
        or comma. Invalid values raise ValueError; database failures leave both tables unchanged.

        @param units [list[tuple]] Rows of id, nonempty English/Russian names and markers, positive finite multiplier and optional base unit ID.
        @param aliases [dict[int, list[str]], None] Alternate unit spellings; None preserves the saved list.
        @param basic_types [list[tuple]] Rows of id, nonempty name, designator, optional icon, base unit ID and alias target ID; new IDs are None or negative. Five-field legacy rows imply no alias.
        @return [None] No value is returned."""
        cleaned_units = []
        for record_id, name, name_ru, marker, marker_ru, multiply, base_unit_id in units:
            values = tuple(str(value).strip() for value in (name, name_ru, marker, marker_ru))
            if not all(values):
                raise ValueError('Unit names and markers must not be empty')
            if not values[0].isascii() or not values[2].isascii():
                raise ValueError('English unit names and markers must use ASCII characters')
            try:
                factor = float(str(multiply).replace(',', '.'))
            except ValueError as exc:
                raise ValueError('The multiplier must be a finite number greater than zero') from exc
            if not math.isfinite(factor) or factor <= 0:
                raise ValueError('The multiplier must be a finite number greater than zero')
            cleaned_units.append((record_id, *values, factor, base_unit_id))
        cleaned_types = []
        for record in basic_types:
            record_id, name, designator, icon, base_unit_id, alias_of_id = (*record, None) if len(record) == 5 else record
            if not name.strip():
                raise ValueError('Basic type names must not be empty')
            cleaned_types.append((record_id, name.strip(), designator.strip(), icon or None, base_unit_id, alias_of_id))
        bases = {row[0] for row in cleaned_units if row[0] is not None and row[5] == 1 and row[6] is None}
        for record_id, *_, factor, base_unit_id in cleaned_units:
            if factor == 1:
                if base_unit_id is not None:
                    raise ValueError('A base unit must not reference another unit')
            elif base_unit_id not in bases:
                raise ValueError('Select an existing base unit with multiplier 1 for each prefixed unit')
        canonical_ids = {row[0] for row in cleaned_types if row[0] is not None and row[5] is None}
        for record_id, _, _, _, base_unit_id, alias_of_id in cleaned_types:
            if alias_of_id is not None and (alias_of_id == record_id or alias_of_id not in canonical_ids):
                raise ValueError('An alias must reference another existing non-alias type')
            if base_unit_id is not None and base_unit_id not in bases:
                raise ValueError('A basic type may reference only a base unit with multiplier 1')
        cleaned_aliases = None
        if aliases is not None:
            identifiers = {row[0] for row in cleaned_units if row[0] is not None}
            if not set(aliases) <= identifiers:
                raise ValueError('An SI alias must reference an existing or pending unit')
            cleaned_aliases = {}
            for unit_id, markers in aliases.items():
                if not isinstance(markers, (list, tuple)) or any(not isinstance(marker, str) for marker in markers):
                    raise ValueError('SI aliases must be a list of nonempty spellings')
                stripped = tuple(marker.strip() for marker in markers)
                if any(not marker for marker in stripped):
                    raise ValueError('SI aliases must be a list of nonempty spellings')
                cleaned_aliases[unit_id] = tuple(dict.fromkeys(stripped))
        self.scheme.saveUnitReferences(cleaned_units, cleaned_types, cleaned_aliases)

    def sectionUnits(self, type_id):
        """Resolve a section's canonical basic type to its SI dimension and scaled units.

        @param type_id [int] Catalog section ID.
        @return [tuple[tuple, list[tuple]]] Base SI row and related rows, or (None, []).
        """
        types = {row[0]: row for row in self.basicTypes()}
        basic_id = self.scheme.getBasicTypeId(type_id)
        seen = set()
        while basic_id in types and basic_id not in seen:
            seen.add(basic_id)
            basic = types[basic_id]
            if basic[5] is None:
                break
            basic_id = basic[5]
        else:
            return None, []
        units = self.units()
        base = next((row for row in units if row[0] == basic[4]), None)
        return (base, [row for row in units if row[0] == base[0] or row[6] == base[0]]) if base else (None, [])

    def normalizePart(self, values):
        """Calculate reduced nominal fields from a complete stock card's value and unit.

        @param values [dict] Card fields including type_id, value and units.
        @return [dict] Copy with base-unit reduced_val/reduced_val_units for configured SI types.
        """
        from decimal import Decimal, InvalidOperation
        result = dict(values)
        base, units = self.sectionUnits(values['type_id'])
        if base is None:
            return result
        result['reduced_val_units'] = base[3]
        result['reduced_val'] = None
        from ElConstants import CATALOG_UNIT_SPELLINGS
        marker = str(values.get('units') or '').strip()
        marker = CATALOG_UNIT_SPELLINGS.get(marker, marker)
        aliases = self.aliases()
        choices = [unit for unit in units if marker and marker in (*unit[1:5], *aliases.get(unit[0], ()))]
        if not choices:
            choices = [unit for unit in units if marker and marker.upper() in
                       [str(text).upper() for text in (*unit[1:5], *aliases.get(unit[0], ()))]]
        if len({unit[5] for unit in choices}) != 1 or values.get('value') in (None, ''):
            logger.debug('Reduced nominal cleared: part=%s value=%r units=%r interpretations=%s',
                         values.get('id'), values.get('value'), values.get('units'), len(choices))
            return result
        try:
            number = Decimal(str(values['value']).replace(',', '.'))
            reduced = number * Decimal(str(choices[0][5]))
            if reduced.is_finite():
                result['reduced_val'] = float(reduced)
        except (InvalidOperation, ValueError, OverflowError):
            logger.debug('Cannot normalize nominal: part=%s value=%r units=%r',
                         values.get('id'), values.get('value'), values.get('units'), exc_info=True)
        logger.debug('Normalized nominal: part=%s value=%r units=%r reduced_val=%r reduced_unit=%s',
                     values.get('id'), values.get('value'), values.get('units'),
                     result['reduced_val'], result['reduced_val_units'])
        return result

    def assignDefaultIcons(self, icon_paths):
        """Explicitly assign installed PNG paths to known existing basic type names.

        @param icon_paths [dict[str, str]] Source icon filenames mapped to installed absolute PNG paths.
        @return [int] Updated type count; missing images and unknown types remain unchanged.
        """
        from ElConstants import BASIC_TYPE_ICON_NAMES
        assignments = [(icon_paths[BASIC_TYPE_ICON_NAMES[row[1]]], row[0])
                       for row in self.scheme.loadBasicTypes() if row[1] in BASIC_TYPE_ICON_NAMES
                       and BASIC_TYPE_ICON_NAMES[row[1]] in icon_paths]
        self.scheme.assignBasicTypeIcons(assignments)
        logger.debug('Assigned basic type PNG paths: types=%s', len(assignments))
        return len(assignments)
