"""Portable values returned by project importers (no Qt or database access)."""
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class Nominal:
    value: str
    unit: str


@dataclass
class ImportedComponent:
    external_id: str
    reference: str
    kind: str = 'unknown'
    value_raw: str = ''
    nominal: Optional[Nominal] = None
    model: Optional[str] = None
    symbol_id: Optional[str] = None
    footprint: Optional[str] = None
    description: Optional[str] = None
    in_bom: bool = True
    on_board: bool = True
    dnp: bool = False
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ImportWarning:
    code: str
    message: str
    component_id: Optional[str] = None
    source_file: Optional[str] = None


@dataclass
class ImportedProject:
    name: str
    description: Optional[str] = None
    external_id: Optional[str] = None
    properties: dict[str, Any] = field(default_factory=dict)
    components: list[ImportedComponent] = field(default_factory=list)
    warnings: list[ImportWarning] = field(default_factory=list)
