"""Plugin database records and access through the application's SQL layer."""
from dataclasses import asdict, dataclass, fields

from .ElDBScheme import DBScheme


@dataclass(frozen=True)
class PluginData:
    """Immutable plugin card used by the manager and project application launcher.

    @attr id [str] Stable plugin identifier.
    @attr plugin_type [str] Functional type declared by the plugin API.
    @attr name [str] Display name.
    @attr version [str] Installed plugin version.
    @attr api_version [int] Supported host API version.
    @attr system_id [str] External system ID.
    @attr system_name [str] External system display name.
    @attr description [str] Plugin description.
    @attr author [str] Plugin author.
    @attr enabled [bool] Whether the installation is enabled.
    @attr manifest_json [str] Validated plugin manifest encoded as JSON.
    @attr app_path [str] External executable or macOS application bundle path; empty when unset.
    @attr app_params [str] Argument template with optional {file} placeholders."""

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
    app_path: str = ''
    app_params: str = ''

    @classmethod
    def from_record(cls, record: dict):
        """Build a card from validated database or installation metadata.

        @param record [dict] Required manifest fields and enabled flag; launch fields default to empty strings.
        @return [PluginData] Immutable card with enabled converted to bool."""
        values = {field.name: record.get(field.name, '') if field.name in ('app_path', 'app_params')
                  else record[field.name] for field in fields(cls)}
        return cls(**dict(values, enabled=bool(record['enabled'])))

    def to_record(self) -> dict:
        """Serialize the card for database-layer operations.

        @return [dict] Card fields with enabled encoded as integer 0 or 1."""
        return dict(asdict(self), enabled=int(self.enabled))


class PluginDataStore:
    """Read and update plugin records through the application SQL layer.

    @attr scheme [DBScheme] Borrowed scheme; this store does not own the connection."""

    def __init__(self, database):
        """Borrow an existing database for plugin data access.

        @param database [DBScheme, sqlite3.Connection] Connected scheme or borrowed SQLite handle.
        @return [None] No value is returned."""
        self.scheme = DBScheme.using(database)

    def all(self) -> list[PluginData]:
        """Read all saved plugin cards ordered by name and ID.

        @return [list[PluginData]] Saved metadata and launch settings."""
        return [PluginData.from_record(record) for record in self.scheme.loadPluginMetadata()]

    def save(self, plugin: PluginData):
        """Store plugin metadata without committing or changing launch settings.

        @param plugin [PluginData] Validated metadata card; caller owns the transaction.
        @return [None] No value is returned."""
        self.scheme.storePluginMetadata(plugin.to_record())

    def remove(self, plugin_id: str):
        """Delete plugin metadata while retaining projects; do not commit.

        @param plugin_id [str] Stable plugin ID to remove.
        @return [None] No value is returned."""
        self.scheme.deletePluginMetadata(plugin_id)

    def replace(self, old_id: str, new_id: str):
        """Switch projects to another plugin and flag them for reimport; do not commit.

        @param old_id [str] Replaced plugin ID.
        @param new_id [str] Replacement plugin ID.
        @return [None] No value is returned."""
        self.scheme.switchProjectPlugin(old_id, new_id)

    def sync(self, plugins: list[PluginData]):
        """Synchronize installation metadata in the caller transaction, retaining launch settings.

        @param plugins [list[PluginData]] Validated cards for all currently installed plugins.
        @return [None] No value is returned."""
        self.scheme.syncPluginMetadata([plugin.to_record() for plugin in plugins])

    def application(self, plugin_id):
        """Find the saved plugin card used for launching a project.

        @param plugin_id [str, None] Plugin ID from the selected project.
        @return [PluginData, None] Matching card, or None when the plugin is missing."""
        return next((plugin for plugin in self.all() if plugin.id == plugin_id), None)

    def saveApplications(self, settings):
        """Commit application settings for the specified plugins atomically.

        @param settings [dict[str, tuple[str, str]]] Plugin IDs mapped to executable paths and argument templates.
        @return [None] No value is returned."""
        self.scheme.savePluginApplications(settings)
