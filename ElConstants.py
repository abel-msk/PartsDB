"""Shared presentation and interaction defaults for catalog and projects."""
import re
from PyQt6.QtCore import Qt

SUBTITLE_ROLE = Qt.ItemDataRole.UserRole + 1
TWO_LINE_MARGIN = 6
TWO_LINE_GAP = 2
LIST_FONT_SECTION = 'list_fonts'
LIST_FONT_DEFAULTS = {
    'title_size': 16, 'subtitle_size': 10,
    'title_color': 'palette', 'subtitle_color': 'gray',
}
PROJECT_TABLE_FIELDS = ('reference', 'kind', 'value_raw', 'footprint', 'quantity',
                        'on_board', 'dnp', 'stock_part', 'needs_review')
PROJECT_TABLE_DEFAULT_WIDTH = 100
PROJECT_TABLE_ALL = 'project_components'
PROJECT_TABLE_UNMATCHED = 'project_unmatched'

# Reference editor columns and initial SI units; multiply converts to the base unit.
UNIT_FIELDS = ('id', 'name', 'name_ru', 'marker', 'marker_ru', 'multiply', 'base_unit_id')
BASIC_TYPE_FIELDS = ('id', 'name', 'designator', 'icon', 'base_unit_id', 'alias_of_id')
BASIC_TYPE_SI_UNITS = {2: 'Farad', 3: 'Ohm', 7: 'Henry'}
UNIT_REFERENCE_ROLE = Qt.ItemDataRole.UserRole + 2
SI_PREFIXES = (
    ('pico', 'пико', 'p', 'п', 1e-12),
    ('nano', 'нано', 'n', 'н', 1e-9),
    ('micro', 'микро', 'u', 'мк', 1e-6),
    ('milli', 'милли', 'm', 'м', 1e-3),
    ('', '', '', '', 1.0),
    ('kilo', 'кило', 'k', 'к', 1e3),
    ('mega', 'мега', 'M', 'М', 1e6),
)
SI_BASE_UNITS = (('farad', 'фарад', 'F', 'Ф'), ('henry', 'генри', 'H', 'Г'),
                 ('ohm', 'ом', 'R', 'Ом'), ('volt', 'вольт', 'V', 'В'),
                 ('ampere', 'ампер', 'A', 'А'))


# Candidate matching uses database basic types and SI references rather than section names.
MATCHING_CANDIDATES_ROLE = Qt.ItemDataRole.UserRole + 3
MATCHING_KIND_NAMES = {
    'ic': ('Integrated circuit',), 'connector': ('Jack', 'Plug'),
    'led': ('LED', 'Diode'), 'module': ('Sub-assembly or module',),
    'crystal': ('Crystal or oscillator',), 'mounting_hole': ('Hardware',),
    'other': ('Miscellaneous',),
}
MATCHING_NUMBER_PATTERN = r'[+-]?(?:\d+(?:[.,]\d*)?|[.,]\d+)(?:[eE][+-]?\d+)?'
MATCHING_QUANTITY_PATTERN = r'\s*(' + MATCHING_NUMBER_PATTERN + r')\s*(\S(?:.*\S)?)\s*'
MATCHING_MOUNTING_PATTERN = r'(SMD|THT|TNT)'
SI_OHM_UNIT_NAMES = ('ohm', 'ом')
SI_OHM_ALIAS_SUFFIXES = ('R', 'Ω', 'Ohm', 'Ом')
UNIT_ALIAS_COLUMN = len(UNIT_FIELDS)
MATCHING_KEY_METADATA = ('units', 'package')
MATCHING_MOUNTING_TRANSLATION = {'Т': 'T', 'Н': 'H', 'С': 'S', 'М': 'M', 'Д': 'D'}
MATCHING_SYMBOL_TRANSLATION = {'µ': 'u', 'μ': 'u', 'Ω': 'Ω'}


PROJECT_MATCH_STATUS_COLUMN = PROJECT_TABLE_FIELDS.index('stock_part')
MATCHING_STATUS_ROLE = Qt.ItemDataRole.UserRole + 4
MATCHING_LABEL_ROLE = Qt.ItemDataRole.UserRole + 5
PROJECT_MATCHED_COLOR = '#008000'
PROJECT_UNMATCHED_COLOR = '#d32f2f'
PROJECT_MATCH_BUTTON_STYLE = 'QPushButton {{ color: {}; padding: 0px 3px; }}'

# Import aggregation preserves exact electrical identity and assembly flags.
COMPONENT_GROUP_FIELDS = ('kind', 'value_raw', 'footprint', 'model', 'symbol_id', 'on_board', 'dnp')
COMPONENT_MEMBER_IDS = 'source_external_ids'
COMPONENT_MEMBER_REFERENCES = 'source_references'
BASIC_TYPE_ICONS_DIR = 'el_icons'
BASIC_TYPE_ICON_COLUMN = BASIC_TYPE_FIELDS.index('icon')
BASIC_TYPE_ICON_NAMES = {
    'Capacitor': 'capasitor.png', 'Resistor': 'resistor.png', 'Transistor': 'transistor.png',
    'Diode': 'diode.png', 'Integrated circuit': 'integrated circuit.png', 'Inductor': 'Inductor.png',
    'Transformer': 'transformer.png', 'Relay': 'relay.png', 'Switch': 'switch.png',
    'Jack': 'jack.png', 'Plug': 'jack.png', 'Fuse': 'fuse.png', 'Ferrite bead': 'FerriteBead.png',
    'Jumper': 'jumper.png', 'Resistor network': 'resistor.png', 'Thermistor': 'resistor.png',
    'Varistor': 'varistor.png', 'Zener diode': 'diode zenner.png', 'LED': 'LED.png',
    'MOSFET': 'transistor FET.png', 'Potentiometer': 'Potentiometer2.png'}

# Historical stock spelling: Russian мОм means megaohm in this inventory.
CATALOG_UNIT_SPELLINGS = {'мОм': 'МОм'}


# Image-drop conversion and transport limits.
MAX_ICON_SIDE = 512
DOWNLOAD_TIMEOUT = 15
DOWNLOAD_LIMIT = 20 * 1024 * 1024
USER_AGENT = "Mozilla/5.0 (Macintosh) ElPartsCatalog"
IMG_SRC_RE = re.compile(r"""<img\b[^>]*?\bsrc\s*=\s*(["'])(.*?)\1""", re.IGNORECASE | re.DOTALL)
UNSAFE_NAME_RE = re.compile(r'[^\w.\-+]+', re.UNICODE)
NOT_ICON_FORMATS = {"pdf"}


# Shared icon-cell drawing and pixmap cache settings.
ICON_CELL_PADDING = 2
ICON_CELL_PREVIEW_SIZE = 256
ICON_CELL_CACHE_LIMIT = 500
ICON_CELL_DEFAULT_ICON_OPACITY = 0.6
ICON_CELL_FRAME_RADIUS = 5.0
ICON_CELL_FRAME_WIDTH = 1.0
ICON_CELL_FRAME_PADDING = 5
ICON_CELL_FRAME_BACKGROUND = (255, 255, 255)
ICON_CELL_SHADOW_OFFSET = 2
ICON_CELL_SHADOW_BLUR = 3
ICON_CELL_SHADOW_ALPHA = 60
ICON_CELL_USE_SHADOW = False
# Default project matching sidebar width in logical pixels.
PROJECT_RIGHT_DEFAULT_WIDTH = 100
