"""Read modern KiCad schematics without KiCad, Qt or database dependencies."""
import json
import re
from decimal import Decimal
from pathlib import Path
from urllib.parse import unquote, urlsplit

from ElPartsPluginApi.importers import (
    ImportedComponent, ImportedProject, ImportFormat, InvalidSourceError,
    MissingSourceError, Nominal, PluginError, ProbeResult, ProjectImporter,
    UnsupportedFormatError,
)
from ElPartsPluginApi import PLUGIN_TYPE_IMPORT
from ElPartsPluginApi.importers import ImportContext
from .sexpr import children, first, parse, properties, value


def _local_path(source_uri):
    uri = urlsplit(source_uri)
    if uri.scheme and uri.scheme != 'file':
        raise UnsupportedFormatError('KiCad importer supports local files and file: URIs')
    if uri.scheme == 'file' and (uri.netloc not in ('', 'localhost') or uri.query or uri.fragment):
        raise UnsupportedFormatError('Expected a local file URI without query or fragment')
    path = Path(unquote(uri.path) if uri.scheme else source_uri).expanduser().resolve()
    if path.suffix.lower() not in ('.kicad_pro', '.kicad_sch'):
        raise UnsupportedFormatError('Expected .kicad_pro or .kicad_sch')
    return path


def _read(path):
    try:
        return path.read_text(encoding='utf-8-sig')
    except FileNotFoundError as exc:
        raise MissingSourceError(f'Missing KiCad source: {path}') from exc
    except (OSError, UnicodeError) as exc:
        raise InvalidSourceError(f'Cannot read {path}: {exc}') from exc


def _schematic(path):
    document = parse(_read(path))
    if document[0] != 'kicad_sch':
        raise UnsupportedFormatError(f'Expected a modern KiCad schematic: {path}')
    if not value(document, 'uuid') or not value(document, 'version'):
        raise InvalidSourceError(f'Missing schematic version or UUID: {path}')
    return document


def _kind(symbol_id, reference):
    library, _, name = symbol_id.partition(':')
    if library == 'Device':
        if name in ('R', 'R_Small', 'R_US', 'R_Variable', 'R_Potentiometer'):
            return 'resistor'
        if name in ('C', 'C_Small', 'C_Polarized', 'C_Polarized_Small', 'CP', 'CP1'):
            return 'capacitor'
        if name in ('L', 'L_Small', 'L_Ferrite'):
            return 'inductor'
        if name.startswith('LED'):
            return 'led'
    if library == 'Device' and name.startswith('D'):
        return 'diode'
    if library == 'Jumper' or (library == 'Device' and name == 'Varistor'):
        return 'other'
    if name in ('TestPoint', 'TestPoint_Small'):
        return 'test_point'
    if library.startswith('Connector'):
        return 'connector'
    if library.startswith('Transistor'):
        return 'transistor'
    if library.startswith('Diode'):
        return 'diode'
    if library.startswith('Relay'):
        return 'relay'
    if library.startswith('Switch'):
        return 'switch'
    if library in ('RF_Module', 'Module') or library.startswith('MCU_Module'):
        return 'module'
    if library == 'Mechanical' and name.startswith('MountingHole'):
        return 'mounting_hole'
    # References are a fallback: preserve the source library for later matching.
    prefix = re.sub(r'[\d?].*', '', reference).upper()
    return {'R': 'resistor', 'C': 'capacitor', 'L': 'inductor', 'D': 'diode',
            'Q': 'transistor', 'U': 'ic', 'J': 'connector', 'P': 'connector',
            'K': 'relay', 'SW': 'switch', 'F': 'fuse', 'Y': 'crystal',
            'TP': 'test_point', 'H': 'mounting_hole'}.get(prefix, 'unknown')


def _nominal(raw, kind):
    unit = {'resistor': 'ohm', 'capacitor': 'F', 'inductor': 'H'}.get(kind)
    if not unit:
        return None
    text = raw.strip().replace(',', '.').replace('µ', 'u').replace('μ', 'u')
    # RKM notation, e.g. 4k7, 2R2, 4n7.
    embedded = re.fullmatch(r'(\d+)([RrKkMmunp])(\d+)', text)
    if embedded:
        text = embedded[1] + '.' + embedded[3] + embedded[2]
    suffix = {'ohm': r'(?:ohms?|Ω|[Rr])?', 'F': r'[Ff]?', 'H': r'[Hh]?'}[unit]
    match = re.fullmatch(r'(\d+(?:\.\d+)?|\.\d+)\s*([RrKkMmunp]?)\s*' + suffix, text)
    if not match:
        return None
    prefix = match[2]
    if prefix in ('R', 'r') and kind != 'resistor':
        return None
    # Unitless capacitor/inductor values are ambiguous.
    if kind != 'resistor' and not prefix and not re.search(r'[FfHh]$', text):
        return None
    multiplier = {'': '1', 'R': '1', 'r': '1', 'K': '1e3', 'k': '1e3',
                  'M': '1e6', 'm': '1e-3', 'u': '1e-6', 'n': '1e-9', 'p': '1e-12'}[prefix]
    number = format(Decimal(match[1]) * Decimal(multiplier), 'f')
    if '.' in number:
        number = number.rstrip('0').rstrip('.')
    return Nominal(number, unit)


class KiCadImporter(ProjectImporter):
    def get_plugin_type(self) -> str:
        return PLUGIN_TYPE_IMPORT

    def get_import_formats(self):
        return [ImportFormat('kicad', 'KiCad project', ['.kicad_pro', '.kicad_sch'])]

    def probe(self, source_uri):
        try:
            path = _local_path(source_uri)
            if path.suffix.lower() == '.kicad_pro':
                self._read_project(path)
                path = path.with_suffix('.kicad_sch')
            _schematic(path)
        except PluginError as exc:
            return ProbeResult(False, str(exc))
        return ProbeResult(True)

    @staticmethod
    def _read_project(path):
        try:
            project = json.loads(_read(path))
        except json.JSONDecodeError as exc:
            raise InvalidSourceError(f'Invalid KiCad project JSON: {path}') from exc
        if not isinstance(project, dict):
            raise InvalidSourceError(f'Expected KiCad project object: {path}')
        return project

    def import_project(self, source_uri):
        context = getattr(self, 'context', None) or ImportContext()
        context.check_cancelled()
        source = _local_path(source_uri)
        if source.suffix.lower() == '.kicad_pro':
            self._read_project(source)
        schematic = source.with_suffix('.kicad_sch')
        root = _schematic(schematic)
        root_uuid = value(root, 'uuid')
        result = ImportedProject(name=source.stem, external_id=root_uuid)
        title = first(root, 'title_block')
        result.description = value(title, 'title') or None
        files = []
        positions = {}

        def visit(path, document, instance_path, ancestors):
            context.check_cancelled()
            context.log('info', f'Reading {path.name}')
            if path in ancestors:
                raise InvalidSourceError(f'Cyclic schematic hierarchy: {path}')
            ancestors = ancestors + (path,)
            if str(path) not in files:
                files.append(str(path))
            libraries = {s[1]: s for s in children(first(document, 'lib_symbols'), 'symbol')}
            symbols = sorted(children(document, 'symbol'), key=lambda s: int(value(s, 'unit', '1')))
            for symbol in symbols:
                context.check_cancelled()
                props = properties(symbol)
                symbol_id = value(symbol, 'lib_id')
                library = libraries.get(symbol_id, [])
                reference = props.get('Reference', '')
                candidates = []
                for project in children(first(symbol, 'instances'), 'project'):
                    for entry in children(project, 'path'):
                        if entry[1].rstrip('/') == instance_path:
                            candidates.append((project[1], value(entry, 'reference')))
                current = [ref for name, ref in candidates if name == source.stem]
                references = set(current or [ref for _, ref in candidates])
                if len(references) > 1:
                    raise InvalidSourceError(f'Ambiguous reference at {instance_path}: {references}')
                if references:
                    reference = references.pop()
                if reference.startswith('#') or first(library, 'power') or symbol_id.startswith('power:'):
                    continue
                if not reference or '?' in reference:
                    raise InvalidSourceError(f'Unannotated component in {path}: {reference}')
                symbol_uuid = value(symbol, 'uuid')
                if not symbol_uuid:
                    raise InvalidSourceError(f'Missing component UUID: {reference}')
                kind = _kind(symbol_id, reference)
                raw = props.get('Value', '')
                nominal = _nominal(raw, kind)
                component = ImportedComponent(
                    external_id=instance_path + '/' + symbol_uuid,
                    reference=reference, kind=kind, value_raw=raw, nominal=nominal,
                    model=(props.get('MPN') or props.get('Manufacturer Part Number')
                           or (raw if kind in ('diode', 'transistor', 'ic', 'module', 'relay') else None)),
                    symbol_id=symbol_id or None, footprint=props.get('Footprint') or None,
                    description=props.get('Description') or properties(library).get('Description') or None,
                    in_bom=value(symbol, 'in_bom', 'yes') == 'yes',
                    on_board=value(symbol, 'on_board', 'yes') == 'yes',
                    dnp=value(symbol, 'dnp', 'no') == 'yes',
                    properties=dict(props, kicad_symbol_uuids=[symbol_uuid]),
                )
                key = (instance_path, reference)
                if key in positions:
                    previous, units = positions[key]
                    unit = value(symbol, 'unit', '1')
                    if unit in units or any(getattr(previous, field) != getattr(component, field)
                                            for field in ('symbol_id', 'value_raw', 'footprint', 'in_bom', 'on_board', 'dnp')):
                        raise InvalidSourceError(f'Conflicting component sections: {reference}')
                    units.add(unit)
                    previous.properties['kicad_symbol_uuids'].append(symbol_uuid)
                else:
                    positions[key] = (component, {value(symbol, 'unit', '1')})
            for sheet in children(document, 'sheet'):
                sheet_props = properties(sheet)
                filename = sheet_props.get('Sheetfile') or sheet_props.get('Sheet file')
                sheet_uuid = value(sheet, 'uuid')
                if not filename or not sheet_uuid:
                    raise InvalidSourceError(f'Missing sheet filename or UUID in {path}')
                filename = filename.replace('${KIPRJMOD}', str(schematic.parent))
                if '${' in filename:
                    raise UnsupportedFormatError(f'Unresolved sheet variable: {filename}')
                child_path = (path.parent / filename).resolve()
                visit(child_path, _schematic(child_path), instance_path + '/' + sheet_uuid, ancestors)

        visit(schematic, root, '/' + root_uuid, ())
        result.components = [item[0] for item in positions.values()]
        result.components.sort(key=lambda c: tuple(int(p) if p.isdigit() else p
                                                  for p in re.split(r'(\d+)', c.reference)))
        references = [c.reference for c in result.components]
        if len(references) != len(set(references)):
            raise InvalidSourceError('Duplicate references across schematic instances')
        result.properties['source_files'] = files
        context.progress(len(result.components), len(result.components), 'Components read')
        return result
