"""Data access for persisted project table layout preferences."""
import ElCommon


logger = ElCommon.setLogger(__name__)


def columnWidths(factory, table_name):
    """Read saved minimum widths. @param factory [DBFactory]; table_name [str] table identifier."""
    return factory.scheme.loadProjectColumnWidths(table_name)


def saveColumnWidths(factory, table_name, widths):
    """Save user widths. @param factory [DBFactory]; table_name [str]; widths [dict[str,int]] positive pixels."""
    factory.scheme.saveProjectColumnWidths(table_name, widths)


def groupedComponents(rows):
    """Aggregate accepted import rows without losing their source identities.

    @param rows [list[dict]] Raw component rows; missing in_bom means already accepted.
    @return [list[dict]] One row per exact identity and assembly state, with quantity and member lists.
    """
    import json
    from ElConstants import COMPONENT_GROUP_FIELDS, COMPONENT_MEMBER_IDS, COMPONENT_MEMBER_REFERENCES
    groups = {}
    for source in sorted(rows, key=lambda row: row['external_id']):
        if not source.get('in_bom', True):
            logger.debug('Skipping component outside BOM: reference=%s', source['reference'])
            continue
        key = tuple(source.get(field) or '' for field in COMPONENT_GROUP_FIELDS)
        properties = json.loads(source['properties_json'])
        identifiers = properties.get(COMPONENT_MEMBER_IDS, [source['external_id']])
        references = properties.get(COMPONENT_MEMBER_REFERENCES, [source['reference']])
        if key not in groups:
            row = dict(source)
            row.pop('in_bom', None)
            row['quantity'] = 0
            groups[key] = row, properties, [], []
        row, merged, ids, refs = groups[key]
        row['quantity'] += source.get('quantity', 1)
        ids.extend(identifiers)
        refs.extend(references)
    result = []
    for row, properties, ids, refs in groups.values():
        properties[COMPONENT_MEMBER_IDS] = sorted(set(ids))
        properties[COMPONENT_MEMBER_REFERENCES] = sorted(set(refs))
        row['reference'] = ', '.join(properties[COMPONENT_MEMBER_REFERENCES])
        row['properties_json'] = json.dumps(properties, ensure_ascii=False, sort_keys=True)
        result.append(row)
        logger.debug('Import group: reference=%s quantity=%s dnp=%s',
                     row['reference'], row['quantity'], row['dnp'])
    logger.debug('Import grouping completed: input_rows=%s groups=%s quantity=%s',
                 len(rows), len(result), sum(row['quantity'] for row in result))
    return result


def takePreviousComponent(previous, row):
    """Remove the existing group sharing an anchor or a surviving source member.

    @param previous [dict[str, dict]] Mutable rows keyed by representative external ID.
    @param row [dict] Incoming grouped row containing source member metadata.
    @return [dict, None] Existing row, removed exactly once from the supplied mapping.
    """
    import json
    from ElConstants import COMPONENT_MEMBER_IDS
    old = previous.pop(row['external_id'], None)
    if old is not None:
        return old
    members = set(json.loads(row['properties_json']).get(COMPONENT_MEMBER_IDS, []))
    key = next((key for key, existing in previous.items()
                if members.intersection(json.loads(existing['properties_json']).get(
                    COMPONENT_MEMBER_IDS, [existing['external_id']]))), None)
    return previous.pop(key, None)
