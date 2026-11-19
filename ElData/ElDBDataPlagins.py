"""Plugin database records and access through the application's SQL layer."""
from dataclasses import asdict, dataclass, fields

from .ElDBScheme import DBScheme


@dataclass(frozen=True)
class PluginData:
    """Store a PLUGINS card for the manager UI, independent of the installed runtime."""

    id: str
    plugin_type: str
    name: str
    version: str
    api_version: int
    system_id: str
    system_name: str
    description: str
    author: str
    enabled: bool
    manifest_json: str

    @classmethod
    def from_record(cls, record: dict):
        """Create a card from a validated metadata dict; convert SQLite 0/1 to bool."""
        values = {field.name: record[field.name] for field in fields(cls)}
        return cls(**dict(values, enabled=bool(record['enabled'])))

    def to_record(self) -> dict:
        """Return metadata as a dict with enabled encoded as SQLite integer 0 or 1."""
        return dict(asdict(self), enabled=int(self.enabled))


class PluginDataStore:
    """Read and change plugin cards; hold a DBScheme without owning its connection."""

    def __init__(self, database):
        """Use a DBScheme or borrowed SQLite connection; never open another database."""
        self.scheme = DBScheme.using(database)

    def all(self) -> list[PluginData]:
        """Return saved plugin cards ordered by name and ID; takes no parameters."""
        return [PluginData.from_record(record) for record in self.scheme.loadPluginMetadata()]

    def save(self, plugin: PluginData):
        """Save a PluginData card within the caller's transaction, without committing."""
        self.scheme.storePluginMetadata(plugin.to_record())

    def remove(self, plugin_id: str):
        """Remove metadata for a string plugin ID; retain projects and do not commit."""
        self.scheme.deletePluginMetadata(plugin_id)

    def replace(self, old_id: str, new_id: str):
        """Switch projects between string plugin IDs; flag reload without committing."""
        self.scheme.switchProjectPlugin(old_id, new_id)

    def sync(self, plugins: list[PluginData]):
        """Sync validated cards in the caller's transaction; retain imported projects."""
        self.scheme.syncPluginMetadata([plugin.to_record() for plugin in plugins])
