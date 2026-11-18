"""Version 1 JSON-lines protocol and strict portable result validation."""
from dataclasses import asdict
from decimal import Decimal, InvalidOperation
import json

from ElPartsPluginApi.importers import (
    ImportedComponent, ImportedProject, ImportWarning, Nominal, PluginError,
)

PROTOCOL_VERSION = 1
MAX_MESSAGE_BYTES = 16 * 1024 * 1024


def json_text(value):
    try:
        return json.dumps(value, ensure_ascii=False, allow_nan=False)
    except (ValueError, TypeError, RecursionError) as exc:
        raise PluginError(f'Invalid JSON data: {exc}') from exc


def _string(value, field, optional=False, nonempty=False):
    if value is None and optional:
        return
    if not isinstance(value, str) or (nonempty and not value.strip()):
        raise PluginError(f'Invalid result field: {field}')


def _object(data, model):
    if not isinstance(data, dict) or set(data) != set(model.__dataclass_fields__):
        raise PluginError(f'Invalid {model.__name__} fields')


def project_from_dict(data):
    _object(data, ImportedProject)
    _string(data['name'], 'name', nonempty=True)
    for key in ('description', 'external_id'):
        _string(data[key], key, optional=True)
    if not isinstance(data['properties'], dict) or not isinstance(data['components'], list) or not isinstance(data['warnings'], list):
        raise PluginError('Invalid project collections')
    components = []
    seen = set()
    references = set()
    for item in data['components']:
        _object(item, ImportedComponent)
        for key in ('external_id', 'reference', 'kind', 'value_raw'):
            _string(item[key], key, nonempty=key != 'value_raw')
        for key in ('model', 'symbol_id', 'footprint', 'description'):
            _string(item[key], key, optional=True)
        for key in ('in_bom', 'on_board', 'dnp'):
            if type(item[key]) is not bool:
                raise PluginError(f'Expected a boolean: {key}')
        if not isinstance(item['properties'], dict):
            raise PluginError('Component properties must be an object')
        if item['external_id'] in seen or item['reference'] in references:
            raise PluginError('Duplicate component ID or reference')
        seen.add(item['external_id'])
        references.add(item['reference'])
        values = dict(item)
        if item['nominal'] is not None:
            _object(item['nominal'], Nominal)
            for key in ('value', 'unit'):
                _string(item['nominal'][key], 'nominal.' + key, nonempty=True)
            try:
                if not Decimal(item['nominal']['value']).is_finite():
                    raise InvalidOperation
            except InvalidOperation as exc:
                raise PluginError('Nominal must be a finite decimal string') from exc
            values['nominal'] = Nominal(**item['nominal'])
        components.append(ImportedComponent(**values))
    warnings = []
    for warning in data['warnings']:
        _object(warning, ImportWarning)
        for key in ('code', 'message'):
            _string(warning[key], key, nonempty=True)
        for key in ('component_id', 'source_file'):
            _string(warning[key], key, optional=True)
        warnings.append(ImportWarning(**warning))
    json_text(data)
    return ImportedProject(**dict(data, components=components, warnings=warnings))


def project_to_dict(project):
    if not isinstance(project, ImportedProject):
        raise PluginError('Importer must return ImportedProject')
    data = asdict(project)
    project_from_dict(data)
    return data


def validate_formats(formats):
    if not isinstance(formats, list) or not formats:
        raise PluginError('Importer must declare supported formats')
    for item in formats:
        if not isinstance(item, dict) or set(item) != {'id', 'name', 'extensions'}:
            raise PluginError('Invalid import format')
        for key in ('id', 'name'):
            _string(item[key], key, nonempty=True)
        if not isinstance(item['extensions'], list) or not item['extensions']:
            raise PluginError('Invalid file extensions')
        for extension in item['extensions']:
            if not isinstance(extension, str) or not extension.startswith('.') or any(c in extension for c in ' /\\*?;()'):
                raise PluginError('Invalid file extension')
    return formats
