"""Public project importer contract."""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from .models import ImportedComponent, ImportedProject


@dataclass(frozen=True)
class ImportFormat:
    id: str
    name: str
    extensions: list[str]


@dataclass(frozen=True)
class ProbeResult:
    supported: bool
    reason: Optional[str] = None


class ProjectImporter(ABC):
    @abstractmethod
    def get_import_formats(self) -> list[ImportFormat]:
        raise NotImplementedError

    @abstractmethod
    def probe(self, source_uri: str) -> ProbeResult:
        raise NotImplementedError

    @abstractmethod
    def import_project(self, source_uri: str) -> ImportedProject:
        raise NotImplementedError

    def get_components(self, source_uri: str) -> list[ImportedComponent]:
        """Return one record per physical position, including BOM/DNP flags."""
        return self.import_project(source_uri).components
