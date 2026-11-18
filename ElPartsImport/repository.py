"""Atomic storage of portable importer results; no stock creation or depletion."""
from dataclasses import dataclass
from datetime import datetime, timezone
import json

from ElPartsPluginApi.importers import PluginError
from .protocol import json_text, project_from_dict, project_to_dict

COMPONENT_FIELDS = ('external_id', 'reference', 'kind', 'value_raw', 'nominal_value',
                    'nominal_unit', 'model', 'symbol_id', 'footprint', 'description',
                    'in_bom', 'on_board', 'dnp', 'properties_json')
# Any change in requirements (including custom voltage/tolerance fields) warrants review.
REQUIREMENTS = ('kind', 'value_raw', 'nominal_value', 'nominal_unit', 'model',
                'symbol_id', 'footprint', 'description', 'in_bom', 'on_board', 'dnp')


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


def requirement_properties(properties):
    # Raw standard fields duplicate columns; UUID diagnostics and references aren't requirements.
    return {k: v for k, v in json.loads(properties).items()
            if k not in ('Reference', 'Value', 'Footprint', 'Description', 'Datasheet', 'kicad_symbol_uuids')}


class ProjectRepository:
    def __init__(self, conn):
        self.conn = conn

    def _rows(self, project_id):
        if project_id is None:
            return {}
        cursor = self.conn.execute('SELECT id, ' + ', '.join(COMPONENT_FIELDS) +
                                   ' FROM PROJECT_COMPONENTS WHERE project_id=? ORDER BY id', (project_id,))
        keys = ['id', *COMPONENT_FIELDS]
        return {row[1]: dict(zip(keys, row)) for row in cursor.fetchall()}

    def changes(self, project, project_id=None):
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

    def _ready(self):
        if self.conn.in_transaction:
            raise PluginError('Finish the current database transaction before importing')
        self.conn.execute('PRAGMA foreign_keys=ON')

    def save(self, project, plugin_id, source_uri, project_id=None):
        # Validate and detach from mutable plugin objects before starting any writes.
        project = project_from_dict(project_to_dict(project))
        rows = [component_row(c) for c in project.components]
        self._ready()
        now = datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
        with self.conn:
            previous = self._rows(project_id)
            if project_id is None:
                cursor = self.conn.execute(
                    'INSERT INTO PROJECTS(name, descr, plugin_id, external_id, source_uri, '
                    'last_imported_at, needs_reload, properties_json) VALUES (?, ?, ?, ?, ?, ?, 0, ?)',
                    (project.name, project.description, plugin_id, project.external_id, source_uri,
                     now, json_text(project.properties)))
                project_id = cursor.lastrowid
            else:
                old = self.conn.execute('SELECT plugin_id FROM PROJECTS WHERE id=?', (project_id,)).fetchone()
                if not old:
                    raise PluginError('Project no longer exists')
                if old[0] not in (None, plugin_id):
                    raise PluginError('Switch the project plugin before importing with another plugin')
                self.conn.execute(
                    'UPDATE PROJECTS SET name=?, descr=?, plugin_id=?, external_id=?, source_uri=?, '
                    'last_imported_at=?, needs_reload=0, properties_json=? WHERE id=?',
                    (project.name, project.description, plugin_id, project.external_id, source_uri,
                     now, json_text(project.properties), project_id))
            for row in rows:
                old = previous.pop(row['external_id'], None)
                if old:
                    if (any(row[k] != old[k] for k in REQUIREMENTS) or
                            requirement_properties(row['properties_json']) != requirement_properties(old['properties_json'])):
                        self.conn.execute('UPDATE PROJECT_COMPONENT_MATCHES SET needs_review=1 WHERE component_id=?', (old['id'],))
                    self.conn.execute('UPDATE PROJECT_COMPONENTS SET ' +
                                      ', '.join(k + '=?' for k in COMPONENT_FIELDS) + ' WHERE id=?',
                                      tuple(row[k] for k in COMPONENT_FIELDS) + (old['id'],))
                else:
                    self.conn.execute('INSERT INTO PROJECT_COMPONENTS(project_id, ' +
                                      ', '.join(COMPONENT_FIELDS) + ') VALUES (' +
                                      ', '.join('?' for _ in range(len(COMPONENT_FIELDS) + 1)) + ')',
                                      (project_id,) + tuple(row[k] for k in COMPONENT_FIELDS))
            for removed in previous.values():
                self.conn.execute('DELETE FROM PROJECT_COMPONENTS WHERE id=?', (removed['id'],))
        return project_id

    def delete(self, project_id):
        self._ready()
        with self.conn:
            # EL_BY_PROJECT is the legacy project/stock relation; it has no cascade in old DBs.
            self.conn.execute('DELETE FROM EL_BY_PROJECT WHERE project_id=?', (project_id,))
            self.conn.execute('DELETE FROM PROJECTS WHERE id=?', (project_id,))

    def components(self, project_id):
        return list(self._rows(project_id).values())

    def matches(self, project_id):
        rows = self.conn.execute(
            'SELECT m.component_id,m.part_id,m.needs_review,p.part_num '
            'FROM PROJECT_COMPONENT_MATCHES m JOIN PROJECT_COMPONENTS c ON c.id=m.component_id '
            'JOIN PARTS p ON p.id=m.part_id WHERE c.project_id=?', (project_id,)).fetchall()
        return {row[0]: {'part_id': row[1], 'needs_review': row[2], 'part_num': row[3]} for row in rows}

    def set_match(self, component_id, part_id=None):
        self._ready()
        with self.conn:
            if part_id is None:
                self.conn.execute('DELETE FROM PROJECT_COMPONENT_MATCHES WHERE component_id=?', (component_id,))
            else:
                self.conn.execute(
                    'INSERT INTO PROJECT_COMPONENT_MATCHES(component_id,part_id,needs_review) VALUES (?,?,0) '
                    'ON CONFLICT(component_id) DO UPDATE SET part_id=excluded.part_id,needs_review=0,'
                    "matched_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')", (component_id, part_id))
