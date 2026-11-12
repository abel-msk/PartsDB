"""Default part icons from Qt resources (:/parts/icons/...), for parts without their own picture.

The icon is chosen by the part's section (TYPES tree) and mounting type from its package:
    section  -> icon family  (longest matching section path wins; None = no default icon)
    package  -> "smd" / "tht" (unknown package -> the family's default mounting)
If the family has no icon for that mounting, its other variant is used.
"""
import re

from PyQt6.QtCore import QFile

import ElLogger
import resources  # noqa: F401  registers :/ resources. Do not delete

logger = ElLogger.setLogger(__name__)

RESOURCE_TEMPLATE = ":/parts/icons/{family}_{mount}.png"
SMD = "smd"
THT = "tht"

# Section path (names from the root) -> (icon family, default mounting) or None
SECTION_ICONS = {
    ("Резистор",): ("resistor", SMD),
    ("Резистор", "переменный"): None,
    ("Конденсатор", "Керамический"): ("capacitor_ceramic", SMD),
    ("Конденсатор", "Танталовый"): ("capacitor_tantalum", SMD),
    ("Конденсатор", "Электролитический"): ("capacitor_electrolytic", THT),
    ("Конденсатор", "Твердотельный"): ("capacitor_solid", THT),
    ("Диод",): ("diode", SMD),
}

# Package -> mounting. Checked in order, case-insensitive.
_THT_PACKAGE = re.compile(r"(THT|ТНТ|DIP|DO-?41|DO-?15|DO-?35|TO-?92|ТО-?92|TO-?220|TO-?247|AXIAL|RADIAL)",
                          re.IGNORECASE)
_SMD_PACKAGE = re.compile(r"(SMD|SMT|SND|SVD|SO[DTP]?[-_]|SOIC|SSOP|TSSOP|QFN|QFP|DFN|SMA|SMB|SMC|DO-?214|SLP|"
                          r"TYPE ?[A-E]|\b0[2468]0[1-5]\b|\b1[02]06\b|\b1210\b|\b2512\b|\b3216\b|TO-?252|TO-?263)",
                          re.IGNORECASE)


def mountingOf(package) -> str:
    """'smd', 'tht' or '' (unknown) for a PARTS.package value."""
    if not package:
        return ""
    package = str(package)
    if _THT_PACKAGE.search(package):
        return THT
    if _SMD_PACKAGE.search(package):
        return SMD
    return ""


class DefaultPartIcons:
    def __init__(self, factory):
        self.factory = factory
        self._types = None  # type_id -> (name, parent_id)
        self._sectionCache = {}  # type_id -> section path tuple

    def _loadTypes(self):
        rows = self.factory.scheme.db.select_all("SELECT id, name, parent_id FROM TYPES;")
        self._types = {row[0]: (row[1], row[2]) for row in rows}
        self._sectionCache = {}

    def sectionPath(self, typeId) -> tuple:
        """Section names from the root down to typeId, e.g. ('Диод', 'Шотки')."""
        if typeId in (None, ""):
            return ()
        typeId = int(typeId)
        if typeId in self._sectionCache:
            return self._sectionCache[typeId]
        if self._types is None or typeId not in self._types:
            self._loadTypes()  # a type may have been added since the last load
        names = []
        current, seen = typeId, set()
        while current in self._types and current not in seen:
            seen.add(current)
            name, parent = self._types[current]
            names.insert(0, name)
            current = parent
        path = tuple(names)
        self._sectionCache[typeId] = path
        return path

    @staticmethod
    def familyFor(section: tuple):
        """(family, default mounting) for the longest matching section prefix, or None."""
        for length in range(len(section), 0, -1):
            prefix = section[:length]
            if prefix in SECTION_ICONS:
                return SECTION_ICONS[prefix]
        return None

    def iconPath(self, part) -> str:
        """Resource path of the default icon for the part, or '' if its section has none."""
        if part is None:
            return ""
        family = self.familyFor(self.sectionPath(part["type_id"]))
        if family is None:
            return ""
        name, defaultMount = family
        mount = mountingOf(part["package"]) or defaultMount
        for candidate in (mount, THT if mount == SMD else SMD):
            path = RESOURCE_TEMPLATE.format(family=name, mount=candidate)
            if QFile.exists(path):
                return path
        logger.warning("No default icon resource for %s", name)
        return ""
