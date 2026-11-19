"""Validate imported data and delegate all database access to ElDBScheme."""
from dataclasses import dataclass
import json

from ElData.ElDBScheme import COMPONENT_FIELDS, DBError, DBScheme
from ElPartsPluginApi.importers import PluginError
from .protocol import json_text, project_from_dict, project_to_dict


@dataclass(frozen=True)
class ImportChanges:
    added: tuple
    changed: tuple
    removed: tuple
    unchanged: tuple


def component_row(component):
    return dict(external_id=component.external_id, reference=component.reference,
                kind=component.kind, value_raw=component.value_raw,
                nominal_value=component.nominal.value if component.nominal else None,
                nominal_unit=component.nominal.unit if component.nominal else None,
                model=component.model, symbol_id=component.symbol_id, footprint=component.footprint,
                description=component.description, in_bom=int(component.in_bom),
                on_board=int(component.on_board), dnp=int(component.dnp),
                properties_json=json_text(component.properties))


class ProjectRepository:
    """Coordinate imported project data and deltas; holds a DBScheme, not SQL queries."""

    def __init__(self, conn):
        """Use a DBScheme (application) or borrowed sqlite3.Connection (compatibility/tests)."""
        self.scheme = DBScheme.using(conn)

    def _rows(self, project_id):
        """Get component dictionaries for an int project ID or an empty map for None."""
        return self.scheme.loadProjectComponents(project_id)

    def changes(self, project, project_id=None):
        """Compare an ImportedProject to an existing int ID; None means a new project."""
        project_to_dict(project)
        previous = self._rows(project_id)
        added, changed, unchanged = [], [], []
        for component in project.components:
            row = component_row(component)
            old = previous.pop(component.external_id, None)
            if old is None:
                added.append(component.reference)
            elif (any(row[key] != old[key] for key in COMPONENT_FIELDS if key != 'properties_json')
                  or json.loads(row['properties_json']) != json.loads(old['properties_json'])):
                changed.append(component.reference)
            else:
                unchanged.append(component.reference)
        return ImportChanges(tuple(added), tuple(changed),
                             tuple(row['reference'] for row in previous.values()), tuple(unchanged))

    def save(self, project, plugin_id, source_uri, project_id=None):
        """Validate ImportedProject, delegate atomic save and return its int database ID.

        plugin_id/source_uri are strings; project_id is int or None for a new card.
        """
        project = project_from_dict(project_to_dict(project))
        rows = [component_row(component) for component in project.components]
        metadata = dict(name=project.name, descr=project.description, external_id=project.external_id,
                        properties_json=json_text(project.properties))
        try:
            return self.scheme.saveImportedProject(metadata, rows, plugin_id, source_uri, project_id)
        except DBError as exc:
            raise PluginError(str(exc)) from exc

    def delete(self, project_id):
        """Delegate deletion of an int project ID; stock cards are retained."""
        try:
            self.scheme.deleteImportedProject(project_id)
        except DBError as exc:
            raise PluginError(str(exc)) from exc

    def components(self, project_id):
        """Return component dictionaries for an int project ID."""
        return list(self._rows(project_id).values())

    def matches(self, project_id):
        """Return confirmed matches keyed by component ID for an int project ID."""
        return self.scheme.loadProjectMatches(project_id)

    def set_match(self, component_id, part_id=None):
        """Confirm int component/stock IDs; part_id=None removes the selected match."""
        try:
            self.scheme.setProjectMatch(component_id, part_id)
        except DBError as exc:
            raise PluginError(str(exc)) from exc
