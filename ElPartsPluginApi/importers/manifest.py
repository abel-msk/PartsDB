"""Declarative importer metadata, checked before executing plugin code."""
from dataclasses import asdict, dataclass
import re

from .errors import PluginError

API_VERSION = 1


@dataclass(frozen=True)
class PluginManifest:
    id: str
    name: str
    version: str
    api_version: int
    description: str
    author: str
    system_id: str
    system_name: str
    capabilities: list[str]
    entry_point: str

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            raise PluginError('Plugin manifest must be an object')
        fields = cls.__dataclass_fields__
        if set(data) != set(fields):
            raise PluginError('Plugin manifest has missing or unknown fields')
        for key in fields:
            if key not in ('api_version', 'capabilities') and (
                    not isinstance(data[key], str) or not data[key].strip()):
                raise PluginError(f'Invalid manifest field: {key}')
        if type(data['api_version']) is not int or data['api_version'] != API_VERSION:
            raise PluginError(f'Unsupported plugin API version: {data["api_version"]}')
        for key in ('id', 'system_id'):
            if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}', data[key]):
                raise PluginError(f'Invalid manifest field: {key}')
        if data['capabilities'] != ['project_import']:
            raise PluginError('Expected project_import capability')
        if not re.fullmatch(r'[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*:[A-Za-z_]\w*', data['entry_point']):
            raise PluginError('Invalid plugin entry point')
        return cls(**data)

    def to_dict(self):
        return asdict(self)
