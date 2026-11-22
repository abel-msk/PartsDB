"""Find catalog candidates by component value, basic type, SI units and mounting."""
from decimal import Decimal, InvalidOperation
import re

from ElConstants import (MATCHING_KIND_NAMES, MATCHING_NUMBER_PATTERN,
                         MATCHING_QUANTITY_PATTERN, MATCHING_MOUNTING_PATTERN,
                         MATCHING_MOUNTING_TRANSLATION, MATCHING_SYMBOL_TRANSLATION)
from ElData import ElDBDataParts
from ElData.ElDBDataUnits import UnitsDataStore


class PartsMatching:
    """Match project values against visible catalog keys using a read-only snapshot.

    @attr factory [DBFactory] Active catalog factory; this matcher never changes its records.
    @attr basic_types [dict[int, tuple]] Basic type reference rows, including aliases and base units.
    @attr units [dict[int, tuple]] SI reference rows used for suffixes and decimal multipliers.
    @attr unit_aliases [dict[int, tuple[str]]] Persisted alternate spellings from the SI reference.
    @attr aliases [list[tuple[str, int]]] Unit spellings in longest-suffix order.
    @attr unit_index [dict[str, tuple[tuple]]] Uppercase spellings mapped to every matching SI row.
    @attr catalogs [dict[tuple[int], list[dict]]] Cached stock cards per requested kind.
    @attr cards [dict[int, dict]] Cached stock cards for labels of confirmed matches.
    """

    def __init__(self, factory):
        """Load current SI and basic type reference data once for a matching pass.

        @param factory [DBFactory] Factory connected to the catalog being displayed.
        @return [None] Build independent per-pass reference and catalog caches.
        """
        self.factory = factory
        references = UnitsDataStore(factory.scheme)
        self.basic_types = {row[0]: row for row in references.basicTypes()}
        self.units = {row[0]: row for row in references.units()}
        self.unit_aliases = references.aliases()
        self.catalogs = {}
        self.cards = {}
        self.aliases = self._unitAliases()
        unit_ids = {}
        for alias, unit_id in self.aliases:
            unit_ids.setdefault(alias, []).append(unit_id)
        self.unit_index = {alias: tuple(self.units[unit_id] for unit_id in identifiers)
                           for alias, identifiers in unit_ids.items()}

    @staticmethod
    def _text(value):
        """Convert nullable values to trimmed source text without exposing identifiers.

        @param value [object, None] Source component or catalog field value.
        @return [str] Empty for None, otherwise stripped text.
        """
        return '' if value is None else str(value).strip()

    @staticmethod
    def _name(value):
        """Normalize a kind or basic type name for reference lookup.

        @param value [str] Case-insensitive name; spaces, underscores and punctuation are equivalent.
        @return [str] Normalized words separated by single spaces.
        """
        return re.sub(r'[\W_]+', ' ', str(value).casefold()).strip()

    @staticmethod
    def _symbol(value):
        """Normalize alternate micro and ohm glyphs before separate case normalization.

        @param value [str] Unit marker or name.
        @return [str] Stripped spelling with equivalent Unicode glyphs normalized.
        """
        return str(value).strip().translate(str.maketrans(MATCHING_SYMBOL_TRANSLATION))

    def _canonicalType(self, type_id):
        """Resolve a configured alias without looping over invalid references.

        @param type_id [int] Basic type reference ID.
        @return [int, None] Canonical ID; None for an absent target or alias cycle.
        """
        visited = set()
        while type_id in self.basic_types and type_id not in visited:
            visited.add(type_id)
            target = self.basic_types[type_id][5]
            if target is None:
                return type_id
            type_id = target
        return None

    def _kindTypes(self, kind):
        """Resolve the requested kind to basic types and their configured aliases.

        @param kind [str] Imported category such as capacitor, ic, connector or a custom alias name.
        @return [tuple[int]] Deterministically ordered IDs used as recursive section roots.
        """
        normalized = self._name(kind)
        direct = [row[0] for row in self.basic_types.values() if self._name(row[1]) == normalized]
        if not direct:
            names = {self._name(name) for name in MATCHING_KIND_NAMES.get(str(kind).casefold(), ())}
            direct = [row[0] for row in self.basic_types.values() if self._name(row[1]) in names]
        canonical = {self._canonicalType(type_id) for type_id in direct} - {None}
        return tuple(sorted(type_id for type_id in self.basic_types
                            if self._canonicalType(type_id) in canonical))

    def _unitAliases(self):
        """Build uppercase unit spellings and retain collisions between reference multipliers.

        @return [list[tuple[str, int]]] Uppercase markers and all reference IDs, ordered by marker length/name/ID.
        """
        spellings = {}
        for unit in self.units.values():
            names = (*unit[1:5], *self.unit_aliases.get(unit[0], ()))
            for name in names:
                if name:
                    spellings.setdefault(self._symbol(name).upper(), set()).add(unit[0])
        return sorted(((name, unit_id) for name, ids in spellings.items() for unit_id in ids),
                      key=lambda item: (-len(item[0]), item[0], item[1]))

    def _unit(self, value):
        """Look up every reference interpretation of an uppercase standalone unit marker.

        @param value [str] Unit marker, with no numeric portion.
        @return [tuple[tuple]] Matching SI rows, including case collisions; empty for unknown spellings.
        """
        text = self._symbol(value).upper()
        return self.unit_index.get(text, ())

    @staticmethod
    def _number(value):
        """Read a finite decimal without accepting model numbers or partial numeric strings.

        @param value [str, int, float] Numeric key; a comma or dot is accepted as decimal separator.
        @return [Decimal, None] Decimal value, or None for nonnumeric and nonfinite input.
        """
        text = str(value).strip()
        if re.fullmatch(MATCHING_NUMBER_PATTERN, text) is None:
            return None
        try:
            result = Decimal(text.replace(',', '.'))
            return result if result.is_finite() else None
        except InvalidOperation:
            return None

    def _quantity(self, value):
        """Separate a numeric value and a recognized trailing SI marker.

        @param value [str] Complete component value or catalog key, for example 100nF or 4.7k.
        @return [tuple[Decimal, tuple[tuple]], None] Number and all matching SI rows, or None.
        """
        match = re.fullmatch(MATCHING_QUANTITY_PATTERN, self._symbol(value))
        if match is None:
            return None
        number, unit = self._number(match[1]), self._unit(match[2])
        return (number, unit) if number is not None and unit else None

    @staticmethod
    def _equalQuantity(left, right):
        """Compare dimensions separately from decimal values converted to their base unit.

        @param left [tuple[Decimal, tuple[tuple]]] Numeric value and matching SI reference rows.
        @param right [tuple[Decimal, tuple[tuple]]] Candidate numeric value and matching SI reference rows.
        @return [bool] True when an interpretation pair has the same base unit and equal scaled values.
        """
        left_number, left_units = left
        right_number, right_units = right
        return any((left_unit[6] or left_unit[0]) == (right_unit[6] or right_unit[0]) and
                   left_number * Decimal(str(left_unit[5])) == right_number * Decimal(str(right_unit[5]))
                   for left_unit in left_units for right_unit in right_units)

    @staticmethod
    def _mounting(value):
        """Determine declared mounting, defaulting populated strings without a marker to SMD.

        @param value [str, None] Footprint or visible package text; empty text has no mounting constraint.
        @return [set[str]] Explicit SMD/THT variants, default SMD, or an empty set for blank input.
        """
        text = str(value or '').strip().upper().translate(str.maketrans(MATCHING_MOUNTING_TRANSLATION))
        if not text:
            return set()
        markers = {('THT' if match == 'TNT' else match)
                   for match in re.findall(MATCHING_MOUNTING_PATTERN, text)}
        return markers or {'SMD'}

    def _compatibleMounting(self, footprint, package):
        """Apply the final mounting filter only when both strings contain a value.

        @param footprint [str, None] Imported footprint; populated unmarked strings mean SMD.
        @param package [str, None] Visible catalog package; blank packages are not compared.
        @return [bool] Whether the mounting sets intersect or either side is unspecified.
        """
        source, catalog = self._mounting(footprint), self._mounting(package)
        return not source or not catalog or bool(source & catalog)

    @staticmethod
    def _shortestEqual(left, right):
        """Compare nonempty model names up to the length of their shorter value.

        @param left [str] Catalog part_num, trimmed by the caller.
        @param right [str] Imported Value text, trimmed by the caller.
        @return [bool] Case-insensitive prefix equality; empty values never match.
        """
        left, right = left.casefold(), right.casefold()
        length = min(len(left), len(right))
        return bool(length) and left[:length] == right[:length]

    def _matchingFields(self, card, value, quantity, kind_types):
        """Find visible keys matching the component's literal value or SI quantity.

        @param card [dict] Stock values and inherited key configuration from the data layer.
        @param value [str] Original imported value, never the model or normalized nominal field.
        @param quantity [tuple, None] Recognized numeric value and unit, or literal comparison mode.
        @param kind_types [tuple[int]] Basic types selected for the component, including aliases.
        @return [tuple[str]] Matching key names in their configured display order.
        """
        values, keys = card['values'], card['keys']
        if quantity is None:
            number = self._number(value)
            return tuple(field for field in keys if self._text(values[field]) and
                         ((field == 'part_num' and self._shortestEqual(self._text(values[field]), value)) or
                          self._text(values[field]).casefold() == value.casefold() or
                          (number is not None and self._number(values[field]) == number)))
        units = [unit for field in keys for unit in self._unit(self._text(values[field]))]
        units.extend(self._unit(self._text(card['units'])))
        if not units and not self._text(card['units']):
            # A declared basic SI unit supplies the dimension for values stored in base units.
            for type_id in kind_types:
                base_id = self.basic_types[type_id][4]
                if base_id in self.units:
                    units.append(self.units[base_id])
        matched = []
        for field in keys:
            text = self._text(values[field])
            if field == 'part_num' and self._shortestEqual(text, value):
                matched.append(field)
                continue
            with_unit = self._quantity(text)
            if with_unit is not None:
                equal = self._equalQuantity(quantity, with_unit)
            else:
                number = self._number(text)
                equal = number is not None and any(self._equalQuantity(quantity, (number, (unit,))) for unit in units)
            if equal:
                matched.append(field)
        return tuple(matched)

    def findCandidates(self, component):
        """Return all matching stock IDs and the first matching key's display value.

        @param component [dict, ImportedComponent] Component with kind, value/value_raw and footprint.
        @return [list[CatalogMatch]] Candidates in catalog ID order; never writes confirmed links.
        """
        if isinstance(component, dict):
            kind = self._text(component.get('kind'))
            value = self._text(component.get('value', component.get('value_raw')))
            footprint = component.get('footprint')
        else:
            kind = self._text(component.kind)
            value = self._text(getattr(component, 'value', getattr(component, 'value_raw', '')))
            footprint = component.footprint
        kind_types = self._kindTypes(kind)
        if not kind_types or not value:
            return []
        if kind_types not in self.catalogs:
            self.catalogs[kind_types] = ElDBDataParts.matchingCatalog(self.factory, kind_types)
            self.cards.update((card['id'], card) for card in self.catalogs[kind_types])
        quantity = self._quantity(value)
        found = []
        for card in self.catalogs[kind_types]:
            fields = self._matchingFields(card, value, quantity, kind_types)
            if fields and self._compatibleMounting(footprint, card['package']):
                found.append(ElDBDataParts.CatalogMatch(card['id'], card['type_id'],
                             self._text(card['values'][fields[0]]), fields))
        return found

    def keyText(self, part_id):
        """Read the first visible nonempty key of an explicitly confirmed stock card.

        @param part_id [int] Internal catalog ID; never included in the display text.
        @return [str] First key value, or empty text when the stock card or its keys are absent.
        """
        if part_id not in self.cards:
            self.cards[part_id] = ElDBDataParts.matchingPart(self.factory, part_id)
        card = self.cards[part_id]
        if card is None:
            return ''
        return next((self._text(card['values'][field]) for field in card['keys']
                     if self._text(card['values'][field])), '')
