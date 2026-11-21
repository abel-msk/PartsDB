"""Shared presentation and interaction defaults for catalog and projects."""
from PyQt6.QtCore import Qt

SUBTITLE_ROLE = Qt.ItemDataRole.UserRole + 1
TWO_LINE_MARGIN = 6
TWO_LINE_GAP = 2
LIST_FONT_SECTION = 'list_fonts'
LIST_FONT_DEFAULTS = {
    'title_size': 16, 'subtitle_size': 10,
    'title_color': 'palette', 'subtitle_color': 'gray',
}
PROJECT_TABLE_FIELDS = ('reference', 'kind', 'value_raw', 'footprint', 'in_bom',
                        'on_board', 'dnp', 'stock_part', 'needs_review')
PROJECT_TABLE_DEFAULT_WIDTH = 100
PROJECT_TABLE_ALL = 'project_components'
PROJECT_TABLE_UNMATCHED = 'project_unmatched'

# Reference editor columns and initial SI units; multiply converts to the base unit.
UNIT_FIELDS = ('id', 'name', 'name_ru', 'marker', 'marker_ru', 'multiply', 'base_unit_id')
BASIC_TYPE_FIELDS = ('id', 'name', 'designator', 'icon', 'base_unit_id')
BASIC_TYPE_SI_UNITS = {2: 'Farad', 3: 'Ohm', 7: 'Henry'}
UNIT_REFERENCE_ROLE = Qt.ItemDataRole.UserRole + 2
SI_PREFIXES = (
    ('atto', 'атто', 'a', 'а', 1e-18), ('femto', 'фемто', 'f', 'ф', 1e-15),
    ('pico', 'пико', 'p', 'п', 1e-12), ('nano', 'нано', 'n', 'н', 1e-9),
    ('micro', 'микро', 'u', 'мк', 1e-6), ('milli', 'милли', 'm', 'м', 1e-3),
    ('centi', 'санти', 'c', 'с', 1e-2), ('deci', 'деци', 'd', 'д', 1e-1),
    ('', '', '', '', 1.0), ('deca', 'дека', 'da', 'да', 1e1),
    ('hecto', 'гекто', 'h', 'г', 1e2), ('kilo', 'кило', 'k', 'к', 1e3),
    ('mega', 'мега', 'M', 'М', 1e6), ('giga', 'гига', 'G', 'Г', 1e9),
    ('tera', 'тера', 'T', 'Т', 1e12), ('peta', 'пета', 'P', 'П', 1e15),
    ('exa', 'экса', 'E', 'Э', 1e18), ('zetta', 'зетта', 'Z', 'З', 1e21),
    ('yotta', 'иотта', 'Y', 'И', 1e24), ('ronna', 'ронна', 'R', 'Р', 1e27),
    ('quetta', 'кветта', 'Q', 'Кв', 1e30), ('ronto', 'ронто', 'r', 'р', 1e-27),
    ('quecto', 'квекто', 'q', 'кв', 1e-30), ('yocto', 'иокто', 'y', 'и', 1e-24),
    ('zepto', 'зепто', 'z', 'з', 1e-21),
)
SI_BASE_UNITS = (('farad', 'фарад', 'F', 'Ф'), ('henry', 'генри', 'H', 'Г'),
                 ('ohm', 'ом', 'R', 'Ом'), ('volt', 'вольт', 'V', 'В'),
                 ('ampere', 'ампер', 'A', 'А'))
