"""Common rendering of catalog sections and project rows."""
from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPalette
from PyQt6.QtWidgets import QApplication, QStyledItemDelegate, QStyle, QStyleOptionViewItem
from ElConstants import (SUBTITLE_ROLE, TWO_LINE_MARGIN, TWO_LINE_GAP,
                         LIST_FONT_SECTION, LIST_FONT_DEFAULTS)


def fontSettings(config):
    """Read shared font preferences and record missing defaults. @param config [ElConfig, None]."""
    settings = dict(LIST_FONT_DEFAULTS)
    if config is not None:
        for key, default in settings.items():
            value = config.get_value(key, LIST_FONT_SECTION)
            if key.endswith('_size'):
                value = value if isinstance(value, int) and value > 0 else default
            elif value != 'palette' and (not isinstance(value, str) or not QColor(value).isValid()):
                value = default
            settings[key] = value
            config.set_value(key, value, LIST_FONT_SECTION)
    return settings


class TwoLineDelegate(QStyledItemDelegate):
    """Draw a title and subtitle with shared config fonts; holds the application's config."""

    def __init__(self, parent=None, config=None):
        """Use the owning view and config. @param parent [QWidget, None]; config [ElConfig, None]."""
        super().__init__(parent)
        self.config = config
        fontSettings(config)

    def fonts(self, option):
        """Return configured title/subtitle fonts. @param option [QStyleOptionViewItem]."""
        settings = fontSettings(self.config)
        title, subtitle = QFont(option.font), QFont(option.font)
        title.setPixelSize(settings['title_size'])
        subtitle.setPixelSize(settings['subtitle_size'])
        return title, subtitle

    def sizeHint(self, option, index):
        """Reserve both lines and margins. @param option [QStyleOptionViewItem]; index [QModelIndex]."""
        title, subtitle = self.fonts(option)
        width = max(QFontMetrics(title).horizontalAdvance(index.data() or ''),
                    QFontMetrics(subtitle).horizontalAdvance(index.data(SUBTITLE_ROLE) or ''))
        return QSize(width + 2 * TWO_LINE_MARGIN,
                     QFontMetrics(title).height() + QFontMetrics(subtitle).height()
                     + TWO_LINE_GAP + 2 * TWO_LINE_MARGIN)

    def paint(self, painter, option, index):
        """Draw row text and selection. @param painter [QPainter]; option [QStyleOptionViewItem]; index [QModelIndex]."""
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ''
        style = opt.widget.style() if opt.widget else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)
        title, subtitle = self.fonts(opt)
        settings = fontSettings(self.config)
        rect = opt.rect.adjusted(TWO_LINE_MARGIN, TWO_LINE_MARGIN, -TWO_LINE_MARGIN, -TWO_LINE_MARGIN)
        painter.save()
        painter.setClipRect(opt.rect)
        for name, font, text in [('title', title, index.data()),
                                 ('subtitle', subtitle, index.data(SUBTITLE_ROLE))]:
            painter.setFont(font)
            color = settings[name + '_color']
            selected = bool(opt.state & QStyle.StateFlag.State_Selected)
            painter.setPen(opt.palette.color(QPalette.ColorRole.HighlightedText) if selected else
                           opt.palette.color(QPalette.ColorRole.Text) if color == 'palette' else QColor(color))
            line = rect.adjusted(0, 0, 0, 0)
            line.setHeight(QFontMetrics(font).height())
            painter.drawText(line, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                             QFontMetrics(font).elidedText(text or '', Qt.TextElideMode.ElideRight, rect.width()))
            rect.setTop(rect.top() + line.height() + TWO_LINE_GAP)
        painter.restore()
