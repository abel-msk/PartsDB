"""Catalog data access for basic component types and matching keys."""
from .ElDBScheme import ELEMENT_FLD_NAMES


def basicTypes(factory):
    """Return reference tuples. @param factory [DBFactory] current catalog."""
    return factory.scheme.loadBasicTypes()


def basicTypeName(factory, section):
    """Return the English subtitle. @param factory [DBFactory]; section [Type]."""
    return next((row[1] for row in basicTypes(factory) if row[0] == section.basic_type_id), '')


def setBasicType(section, basic_type_id):
    """Persist a section's basic type. @param section [Type]; basic_type_id [int] valid reference ID."""
    section.scheme.setBasicTypeId(section.recId, basic_type_id)
    section.basic_type_id = basic_type_id
    section.refreshHeaders()


def keyHeaders(section):
    """Return configured keys in visual order. @param section [Type] catalog section."""
    headers = section.refreshHeaders()
    return sorted((headers[field] for field in ELEMENT_FLD_NAMES[2:] if headers[field]['is_key']),
                  key=lambda header: header['position'])


def createPart(factory, section, values):
    """Create a catalog card. @param factory [DBFactory]; section [Type]; values [dict[str,str]]."""
    return factory.createPart(section, values)
