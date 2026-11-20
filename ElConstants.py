gt"""Shared presentation and interaction defaults for catalog and projects."""
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
