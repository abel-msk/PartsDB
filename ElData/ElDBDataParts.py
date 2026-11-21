"""Catalog data access for basic component types and matching keys."""
from dataclasses import dataclass

from .ElDBScheme import ELEMENT_FLD_NAMES


def basicTypes(factory):
    """Read available catalog basic types.

    @param factory [DBFactory] Active catalog factory.
    @return [list[tuple]] Rows of basic type ID, name, designator and icon.
    """
    return factory.scheme.loadBasicTypes()


def basicTypeName(factory, section):
    """Read the selected basic type name for a section subtitle.

    @param factory [DBFactory] Active catalog factory.
    @param section [Type] Catalog section with a basic type reference.
    @return [str] Reference name, or empty text for a missing reference.
    """
    return next((row[1] for row in basicTypes(factory) if row[0] == section.basic_type_id), '')


def setBasicType(section, basic_type_id):
    """Persist a basic type choice and refresh the section defaults.

    @param section [Type] Section to update.
    @param basic_type_id [int] Existing basic type reference ID.
    @return [None] Refresh cached headers after saving.
    """
    section.scheme.setBasicTypeId(section.recId, basic_type_id)
    section.basic_type_id = basic_type_id
    section.refreshHeaders()


def keyHeaders(section):
    """Read configured catalog key headers in their visual order.

    @param section [Type] Catalog section with inherited header settings.
    @return [list[Header]] Selected key headers sorted by stored position.
    """
    headers = section.refreshHeaders()
    return sorted((headers[field] for field in ELEMENT_FLD_NAMES[2:] if headers[field]['is_key']),
                  key=lambda header: header['position'])


def createPart(factory, section, values):
    """Create a stock card through the existing catalog factory.

    @param factory [DBFactory] Active catalog factory.
    @param section [Type] Destination section.
    @param values [dict[str, object]] Catalog field names and entered values.
    @return [Part] Newly persisted catalog card.
    """
    return factory.createPart(section, values)


@dataclass(frozen=True)
class CatalogMatch:
    """Describe an automatically found catalog candidate without confirming a stock link.

    @attr part_id [int] Internal catalog card ID; retained in models, never rendered.
    @attr type_id [int] Internal section ID containing the card.
    @attr key_text [str] Text of the first matching visible key column in configured order.
    @attr matched_fields [tuple[str]] Matching key field names in configured order.
    """
    part_id: int
    type_id: int
    key_text: str
    matched_fields: tuple[str, ...]


def matchingCatalog(factory, basic_type_ids):
    """Read matching cards through the application schema layer.

    @param factory [DBFactory] Connected catalog factory.
    @param basic_type_ids [list[int], tuple[int]] Basic type IDs and aliases; descendants are included.
    @return [list[dict]] Catalog cards and visible key metadata, ordered by catalog ID.
    """
    return factory.scheme.loadMatchingCatalog(basic_type_ids)


def matchingPart(factory, part_id):
    """Read key text and metadata for an already confirmed catalog link.

    @param factory [DBFactory] Connected catalog factory.
    @param part_id [int] Internal catalog ID.
    @return [dict, None] Card with ordered keys; None when the card no longer exists.
    """
    return factory.scheme.loadMatchingPart(part_id)
