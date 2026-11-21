"""Reference data for the units and basic component type editor."""
import math

from .ElDBScheme import DBScheme


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

        @return [list[tuple]] Rows: id, name, designator, icon, base_unit_id."""
        return self.scheme.loadUnitBasicTypes()

    def save(self, units, basic_types):
        """Validate and commit both edited reference lists atomically.

        English unit names and markers must be ASCII. Decimal multipliers may use a dot
        or comma. Invalid values raise ValueError; database failures leave both tables unchanged.

        @param units [list[tuple]] Rows of id, nonempty English/Russian names and markers, positive finite multiplier and optional base unit ID.
        @param basic_types [list[tuple]] Rows of id, nonempty name, designator, optional icon and optional base unit ID; new IDs are None.
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
        for record_id, name, designator, icon, base_unit_id in basic_types:
            if not name.strip():
                raise ValueError('Basic type names must not be empty')
            cleaned_types.append((record_id, name.strip(), designator.strip(), icon or None, base_unit_id))
        bases = {row[0] for row in cleaned_units if row[0] is not None and row[5] == 1 and row[6] is None}
        for record_id, *_, factor, base_unit_id in cleaned_units:
            if factor == 1:
                if base_unit_id is not None:
                    raise ValueError('A base unit must not reference another unit')
            elif base_unit_id not in bases:
                raise ValueError('Select an existing base unit with multiplier 1 for each prefixed unit')
        for *_, base_unit_id in cleaned_types:
            if base_unit_id is not None and base_unit_id not in bases:
                raise ValueError('A basic type may reference only a base unit with multiplier 1')
        self.scheme.saveUnitReferences(cleaned_units, cleaned_types)
