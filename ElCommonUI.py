"""Shared Qt rendering, icon cells, image-drop handling and catalog dialogs."""
import os
from html import escape
from PyQt6 import sip
from PyQt6.QtCore import (QSize, Qt, QRect, QRectF, QModelIndex, QUrl, QFile,
                          QEvent, QTimer, QPersistentModelIndex, pyqtSignal)
from PyQt6.QtGui import (QColor, QFont, QFontMetrics, QPalette, QPixmap,
                         QPainter, QHelpEvent, QPainterPath, QPen)
from PyQt6.QtWidgets import (QApplication, QStyledItemDelegate, QStyle, QStyleOptionViewItem,
                             QToolTip, QAbstractItemView, QDialog, QDialogButtonBox,
                             QFormLayout, QLineEdit, QComboBox, QLabel)
from ElConstants import (SUBTITLE_ROLE, TWO_LINE_MARGIN, TWO_LINE_GAP,
                         LIST_FONT_SECTION, LIST_FONT_DEFAULTS,
                         ICON_CELL_PADDING, ICON_CELL_PREVIEW_SIZE, ICON_CELL_CACHE_LIMIT,
                         ICON_CELL_DEFAULT_ICON_OPACITY, ICON_CELL_FRAME_RADIUS, ICON_CELL_FRAME_WIDTH,
                         ICON_CELL_FRAME_PADDING, ICON_CELL_FRAME_BACKGROUND, ICON_CELL_SHADOW_OFFSET,
                         ICON_CELL_SHADOW_BLUR, ICON_CELL_SHADOW_ALPHA)
import ElCommon
from ElTranslations import TranslatedDialogMixin
from ElWindowTexts import (sectionDialogTexts, partValuesDialogTexts,
                           iconDefaultTooltipText, iconMissingTooltipText)

logger = ElCommon.setLogger(__name__)


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




class ElTreeEditDlg(TranslatedDialogMixin, QDialog):
    """Edit a section name and basic type while retaining user input across language changes.

    @attr ui [ElTreeEditDlg] Self-reference for translation events.
    @attr nameEdit [QLineEdit] Pending section name.
    @attr typeCombo [QComboBox] Basic type names and persistent IDs.
    @attr buttons [QDialogButtonBox] Acceptance/cancellation controls."""

    def __init__(self, parent, basic_types, name='', basic_type_id=1):
        """Build editors from a section name and available basic type records.

        @param parent [QWidget, QObject, None] Qt owner of the created object.
        @param basic_types [list[tuple]] Basic type records: ID, name, designator and optional icon.
        @param name [str] Initial section name, preserved as user data.
        @param basic_type_id [int] Initial basic type ID; unknown IDs fall back to the first choice.
        @return [None] Update the owned UI or state without returning a value."""
        super().__init__(parent)
        self.ui = self
        self.nameEdit = QLineEdit(name, self)
        self.typeCombo = QComboBox(self)
        for key, title, designator, _ in basic_types:
            self.typeCombo.addItem(title, key)
        self.typeCombo.setCurrentIndex(max(0, self.typeCombo.findData(basic_type_id)))
        self.nameLabel = QLabel(self)
        self.typeLabel = QLabel(self)
        form = QFormLayout(self)
        form.addRow(self.nameLabel, self.nameEdit)
        form.addRow(self.typeLabel, self.typeCombo)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        form.addRow(self.buttons)
        self.nameEdit.textChanged.connect(self.validate)
        self.validate()
        self.retranslate()

    def validate(self):
        """Enable acceptance only when the pending name is nonempty.

        @return [None] Update the owned UI or state without returning a value."""
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(bool(self.nameEdit.text().strip()))

    def retranslate(self):
        """Refresh section captions without changing reference names or input.

        @return [None] Update the owned UI or state without returning a value."""
        sectionDialogTexts(self)


class PartValuesDialog(TranslatedDialogMixin, QDialog):
    """Collect configured key values for a new part.

    @attr headers [list[Header]] Ordered key metadata.
    @attr editors [dict[str, QLineEdit]] Pending values by field name.
    @attr labels [dict[str, QLabel]] Localized field labels.
    @attr buttons [QDialogButtonBox] Acceptance/cancellation controls."""

    def __init__(self, parent, headers):
        """Build one editor for each configured key field.

        @param parent [QWidget, QObject, None] Qt owner of the created object.
        @param headers [list[Header]] Ordered metadata for the required key fields.
        @return [None] Update the owned UI or state without returning a value."""
        super().__init__(parent)
        self.ui = self
        self.headers = headers
        self.editors = {}
        self.labels = {}
        form = QFormLayout(self)
        self.prompt = QLabel(self)
        form.addRow(self.prompt)
        for header in headers:
            field = header['field_name']
            editor = QLineEdit(self)
            self.editors[field] = editor
            self.labels[field] = QLabel(self)
            form.addRow(self.labels[field], editor)
            editor.textChanged.connect(self.validate)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        form.addRow(self.buttons)
        self.validate()
        self.retranslate()

    def values(self):
        """Read all pending key values with surrounding whitespace removed.

        @return [dict[str, str]] Trimmed pending key values."""
        return {field: editor.text().strip() for field, editor in self.editors.items()}

    def validate(self):
        """Enable acceptance only when every key field contains a value.

        @return [None] Update the owned UI or state without returning a value."""
        valid = bool(self.editors) and all(self.values().values())
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(valid)

    def retranslate(self):
        """Refresh the prompt and field captions while preserving values.

        @return [None] Update the owned UI or state without returning a value."""
        partValuesDialogTexts(self)


class IconCellDelegate(QStyledItemDelegate):
    """Render optional file icons and handle safe external image drops when configured.

    @attr iconsDir [str] Base folder for relative stored icon paths.
    @attr defaultIcons [object, None] Optional catalog fallback resolver; None leaves empty cells blank.
    @attr dropColumn [int, None] Column accepting images; None disables drop handling.
    @attr onDrop [callable, None] Callback receiving a persistent cell index and an owned QImage.
    @attr _cache [dict] Scaled pixmaps keyed by path, timestamp and target size.
    @attr dropFailed [pyqtBoundSignal] Reports image decoding or saving failures to the owning form.
    """
    dropFailed = pyqtSignal(str)
    PADDING = ICON_CELL_PADDING  # px between the image and the cell border
    PREVIEW_SIZE = ICON_CELL_PREVIEW_SIZE  # max side of the tooltip preview, px
    CACHE_LIMIT = ICON_CELL_CACHE_LIMIT  # scaled pixmaps kept in memory

    DEFAULT_ICON_OPACITY = ICON_CELL_DEFAULT_ICON_OPACITY  # default (resource) icons are drawn paler than the parts' own pictures

    FRAME_RADIUS = ICON_CELL_FRAME_RADIUS  # corner radius of the frame around the icon, pt (logical px)
    FRAME_WIDTH = ICON_CELL_FRAME_WIDTH  # frame line width
    FRAME_PADDING = ICON_CELL_FRAME_PADDING  # px between the frame and the picture inside it
    FRAME_BACKGROUND = QColor(*ICON_CELL_FRAME_BACKGROUND)  # fill inside the frame
    SHADOW_OFFSET = ICON_CELL_SHADOW_OFFSET  # shadow shift down, px
    SHADOW_BLUR = ICON_CELL_SHADOW_BLUR  # shadow softness: number of 1px layers around the shape
    SHADOW_ALPHA = ICON_CELL_SHADOW_ALPHA  # opacity of the darkest shadow layer, 0..255

    def __init__(self, parent=None, iconSize: QSize = QSize(60, 60), iconsDir: str = "",
                 defaultIcons=None, dropColumn=None, onDrop=None):
        """Configure icon sizing, optional catalog fallback and external cell-drop handling.

        @param parent [QWidget, None] parent supplied by the owning view or caller.
        @param iconSize [QSize] iconSize supplied by the owning view or caller.
        @param iconsDir [str] iconsDir supplied by the owning view or caller.
        @param defaultIcons [object, None] defaultIcons supplied by the owning view or caller.
        @param dropColumn [int, None] dropColumn supplied by the owning view or caller.
        @param onDrop [callable, None] onDrop supplied by the owning view or caller.
        @return [None] Result of the documented icon-cell operation."""
        super().__init__(parent)
        self.iconSize = iconSize
        self.iconsDir = iconsDir  # base folder for relative icon paths
        self.defaultIcons = defaultIcons  # ElDefaultIcons.DefaultPartIcons: icon for parts without a picture
        self._cache: dict = {}  # (path, mtime, w, h, dpr) -> QPixmap
        self.dropRow = -1  # row under a picture being dragged onto the table: its frame is highlighted
        self.dropColumn = dropColumn
        self.onDrop = onDrop
        self._missingPaths = set()
        if dropColumn is not None and onDrop is not None:
            parent.setAcceptDrops(True)
            parent.viewport().setAcceptDrops(True)
            parent.viewport().installEventFilter(self)
        logger.debug('Icon delegate initialized: folder=%s fallback=%s drop_column=%s',
                     iconsDir, defaultIcons is not None, dropColumn)

    # ---------- image loading ----------

    def imagePath(self, index: QModelIndex) -> str:
        """Full image path for the cell: relative values are taken inside iconsDir.

        @param index [QModelIndex] index supplied by the owning view or caller.
        @return [str] Result of the documented icon-cell operation."""
        value = index.data(Qt.ItemDataRole.DisplayRole)
        if value is None:
            return ""
        path = str(value).strip()
        if not path:
            return ""
        if path.startswith("file://"):
            path = QUrl(path).toLocalFile()
        if path.startswith(':/'):
            return path
        path = os.path.expanduser(path)
        if not os.path.isabs(path) and self.iconsDir:
            path = os.path.join(self.iconsDir, path)
        return path

    def defaultIconPath(self, index: QModelIndex) -> str:
        """Qt resource path of the default icon for the cell's part, or ''.

        @param index [QModelIndex] index supplied by the owning view or caller.
        @return [str] Result of the documented icon-cell operation."""
        if self.defaultIcons is None:
            return ""
        return self.defaultIcons.iconPath(index.data(Qt.ItemDataRole.UserRole))

    def pixmap(self, path: str, size: QSize, dpr: float = 1.0, fill: bool = False) -> QPixmap | None:
        """Return the image scaled to fit `size` (logical px), or None if it can't be loaded.

        With `fill` the image covers the whole `size` keeping its aspect ratio, and the overflow
        is cropped evenly from both sides, so the result is exactly `size`.

        `path` is a file on disk or a Qt resource (":/...").

        @param path [str] path supplied by the owning view or caller.
        @param size [QSize] size supplied by the owning view or caller.
        @param dpr [float] dpr supplied by the owning view or caller.
        @param fill [bool] fill supplied by the owning view or caller.
        @return [QPixmap, None] Result of the documented icon-cell operation."""
        if not path:
            return None
        if path.startswith(":"):
            if not QFile.exists(path):
                return None
            mtime = 0  # resources are built into the program and never change
        elif os.path.isfile(path):
            mtime = os.path.getmtime(path)
        else:
            if path not in self._missingPaths:
                logger.debug('Icon file is missing: path=%s', path)
                self._missingPaths.add(path)
            return None
        key = (path, mtime, size.width(), size.height(), dpr, fill)
        pm = self._cache.get(key)
        if pm is None:
            src = QPixmap(path)
            if src.isNull():
                logger.debug("Can't load image %s", path)
                return None
            devSize = QSize(int(size.width() * dpr), int(size.height() * dpr))
            mode = Qt.AspectRatioMode.KeepAspectRatioByExpanding if fill else Qt.AspectRatioMode.KeepAspectRatio
            pm = src.scaled(devSize, mode, Qt.TransformationMode.SmoothTransformation)
            if fill:  # crop the centre
                pm = pm.copy((pm.width() - devSize.width()) // 2, (pm.height() - devSize.height()) // 2,
                             devSize.width(), devSize.height())
            pm.setDevicePixelRatio(dpr)
            if len(self._cache) >= self.CACHE_LIMIT:
                self._cache.clear()
            self._cache[key] = pm
            logger.debug('Icon pixmap cached: path=%s target=%sx%s dpr=%s',
                         path, size.width(), size.height(), dpr)
        return pm

    def clearCache(self):
        """Clear both scaled pixmaps and remembered missing file diagnostics.

        @return [None] Result of the documented icon-cell operation."""
        logger.debug('Clearing icon cache: pixmaps=%s missing_paths=%s', len(self._cache), len(self._missingPaths))
        self._cache.clear()
        self._missingPaths.clear()

    # ---------- painting ----------

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        """Draw the cell background, optional image and current drop-target highlight.

        @param painter [QPainter] painter supplied by the owning view or caller.
        @param option [QStyleOptionViewItem] option supplied by the owning view or caller.
        @param index [QModelIndex] index supplied by the owning view or caller.
        @return [None] Result of the documented icon-cell operation."""
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        path = self.imagePath(index)
        opt.text = ""  # draw background / selection / focus only, without the path text
        style = opt.widget.style() if opt.widget else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)

        isDefault = False
        if not path:
            path = self.defaultIconPath(index)  # part has no picture: icon for its section
            isDefault = True
            if not path:
                if index.row() == self.dropRow:
                    side = min(opt.rect.width(), opt.rect.height()) - 2 * self.PADDING
                    square = QRect(0, 0, side, side)
                    square.moveCenter(opt.rect.center())
                    self.paintDropMark(painter, square, opt)
                return

        rect = opt.rect.adjusted(self.PADDING, self.PADDING, -self.PADDING, -self.PADDING)
        # Leave room for the shadow: it spreads SHADOW_BLUR-1 px around the frame and is shifted down
        spread = self.SHADOW_BLUR - 1
        rect = rect.adjusted(spread, max(0, spread - self.SHADOW_OFFSET), -spread, -(spread + self.SHADOW_OFFSET))
        if rect.width() <= 0 or rect.height() <= 0:
            return

        # Square frame; the whole picture fits inside it with FRAME_PADDING, aspect ratio kept
        side = min(rect.width(), rect.height())
        square = QRect(0, 0, side, side)
        square.moveCenter(rect.center())
        inner = square.adjusted(self.FRAME_PADDING, self.FRAME_PADDING, -self.FRAME_PADDING, -self.FRAME_PADDING)
        if inner.width() <= 0 or inner.height() <= 0:
            return

        dpr = painter.device().devicePixelRatioF() if painter.device() else 1.0
        pm = self.pixmap(path, inner.size(), dpr)
        painter.save()
        if isDefault:
            painter.setOpacity(self.DEFAULT_ICON_OPACITY)
        target = None
        if pm is not None:
            w = round(pm.width() / pm.devicePixelRatio())
            h = round(pm.height() / pm.devicePixelRatio())
            target = QRect(0, 0, w, h)
            target.moveCenter(inner.center())
        self.paintFramed(painter, square, pm, target, opt)
        painter.restore()
        if index.row() == self.dropRow:
            self.paintDropMark(painter, square, opt)

    def paintDropMark(self, painter: QPainter, square: QRect, opt: QStyleOptionViewItem):
        """Highlighted frame: a dropped picture will become this part's icon.

        @param painter [QPainter] painter supplied by the owning view or caller.
        @param square [QRect] square supplied by the owning view or caller.
        @param opt [QStyleOptionViewItem] opt supplied by the owning view or caller.
        @return [None] Result of the documented icon-cell operation."""
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(opt.palette.color(opt.palette.ColorRole.Highlight), 3))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(QRectF(square).adjusted(1.5, 1.5, -1.5, -1.5), self.FRAME_RADIUS, self.FRAME_RADIUS)
        painter.restore()

    def paintFramed(self, painter: QPainter, square: QRect, pm: QPixmap | None, target: QRect | None,
                    opt: QStyleOptionViewItem):
        """Draw a rounded frame with a soft shadow under it and the pixmap inside ("?" if there is none).

        @param painter [QPainter] painter supplied by the owning view or caller.
        @param square [QRect] square supplied by the owning view or caller.
        @param pm [QPixmap, None] pm supplied by the owning view or caller.
        @param target [QRect, None] target supplied by the owning view or caller.
        @param opt [QStyleOptionViewItem] opt supplied by the owning view or caller.
        @return [None] Result of the documented icon-cell operation."""
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        frame = QRectF(square).adjusted(0.5, 0.5, -0.5, -0.5)
        r = self.FRAME_RADIUS

        # Shadow: layered rounded rects, shifted down, fading outwards
        painter.setPen(Qt.PenStyle.NoPen)
        for i in range(self.SHADOW_BLUR, 0, -1):
            alpha = int(self.SHADOW_ALPHA * (self.SHADOW_BLUR - i + 1) / (self.SHADOW_BLUR + 1))
            painter.setBrush(QColor(0, 0, 0, alpha))
            painter.drawRoundedRect(frame.translated(0, self.SHADOW_OFFSET).adjusted(-i + 1, -i + 1, i - 1, i - 1),
                                    r + i - 1, r + i - 1)

        # White card (also hides the shadow behind transparent pictures) and the picture, clipped to the frame
        path = QPainterPath()
        path.addRoundedRect(frame, r, r)
        painter.save()
        painter.setClipPath(path)
        painter.fillRect(frame, self.FRAME_BACKGROUND)
        if pm is not None:
            painter.drawPixmap(target, pm)
        else:
            # Path is set but the file is missing or unreadable
            painter.setPen(QColor(128, 128, 128))
            painter.drawText(square, Qt.AlignmentFlag.AlignCenter, "?")
        painter.restore()

        # Frame line
        pen = QPen(opt.palette.color(opt.palette.ColorRole.Mid), self.FRAME_WIDTH)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(frame, r, r)

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        """Return the configured icon dimensions plus cell padding.

        @param option [QStyleOptionViewItem] option supplied by the owning view or caller.
        @param index [QModelIndex] index supplied by the owning view or caller.
        @return [QSize] Result of the documented icon-cell operation."""
        return QSize(self.iconSize.width() + 2 * self.PADDING, self.iconSize.height() + 2 * self.PADDING)

    # ---------- tooltip preview ----------

    def helpEvent(self, event: QHelpEvent, view: QAbstractItemView, option: QStyleOptionViewItem,
                  index: QModelIndex) -> bool:
        """Show a preview tooltip or hide it for an empty cell without a fallback.

        @param event [QHelpEvent] event supplied by the owning view or caller.
        @param view [QAbstractItemView] view supplied by the owning view or caller.
        @param option [QStyleOptionViewItem] option supplied by the owning view or caller.
        @param index [QModelIndex] index supplied by the owning view or caller.
        @return [bool] Result of the documented icon-cell operation."""
        if event is None or event.type() != event.Type.ToolTip:
            return super().helpEvent(event, view, option, index)
        path = self.imagePath(index)
        if not path:
            if self.defaultIconPath(index):
                QToolTip.showText(event.globalPos(), iconDefaultTooltipText(), view)
            else:
                QToolTip.hideText()
            return True
        if os.path.isfile(path) and not QPixmap(path).isNull():
            src = QPixmap(path)
            scale = min(1.0, self.PREVIEW_SIZE / max(src.width(), src.height()))
            html = (f'<img src="{escape(QUrl.fromLocalFile(path).toString())}" '
                    f'width="{int(src.width() * scale)}" height="{int(src.height() * scale)}"><br>'
                    f'{escape(os.path.basename(path))}')
        else:
            html = iconMissingTooltipText(path)
        QToolTip.showText(event.globalPos(), html, view)
        return True


    def _setDropRow(self, row):
        """Highlight a pending image target without changing row selection.

        @param row [int] Target row, or -1 to clear the drop marker.
        @return [None] Repaint only when the target changes.
        """
        if self.dropRow != row:
            self.dropRow = row
            view = self.parent()
            if isinstance(view, QAbstractItemView) and not sip.isdeleted(view):
                view.viewport().update()

    def eventFilter(self, watched, event):
        """Accept external images only in the configured column and retain owned drag data.

        @param watched [QObject] View viewport receiving drag/drop events.
        @param event [QEvent] Drag enter, move, leave or drop event.
        @return [bool] True consumes a handled drag event; unrelated events remain unchanged.
        """
        view = self.parent()
        if (self.dropColumn is None or self.onDrop is None or not isinstance(view, QAbstractItemView)
                or sip.isdeleted(view) or watched is not view.viewport()):
            return super().eventFilter(watched, event)
        kind = event.type()
        if kind == QEvent.Type.DragLeave:
            self._setDropRow(-1)
            return False
        if kind not in (QEvent.Type.DragEnter, QEvent.Type.DragMove, QEvent.Type.Drop):
            return super().eventFilter(watched, event)
        external_image = event.source() is None and ElCommon.canProvideImage(event.mimeData())
        index = view.indexAt(event.position().toPoint())
        valid = external_image and index.isValid() and index.column() == self.dropColumn
        if kind == QEvent.Type.DragEnter:
            logger.debug('Icon drag entered: valid_cell=%s row=%s column=%s formats=%s',
                         valid, index.row(), index.column(), event.mimeData().formats())
        if not valid:
            self._setDropRow(-1)
            event.setDropAction(Qt.DropAction.IgnoreAction)
            if kind == QEvent.Type.DragEnter and external_image:
                event.accept()  # Continue receiving moves when entering over a neighbouring column.
            else:
                event.ignore()
            return True
        event.setDropAction(Qt.DropAction.CopyAction)
        event.accept()
        if kind != QEvent.Type.Drop:
            self._setDropRow(index.row())
            return True
        self._setDropRow(-1)
        logger.debug('Image dropped into icon cell: row=%s column=%s %s',
                     index.row(), index.column(), ElCommon.describeMime(event.mimeData()))
        pending = QPersistentModelIndex(index)
        mime = ElCommon.copyMimeData(event.mimeData())
        QTimer.singleShot(0, lambda: self._applyDroppedMime(pending, mime))
        return True

    def _applyDroppedMime(self, index, mime):
        """Decode a retained drop after the native event and update its original persistent cell.

        @param index [QPersistentModelIndex] Target cell; deleted rows are ignored.
        @param mime [QMimeData] Deep-owned image and transfer metadata.
        @return [None] Call onDrop or report failure without modifying other rows.
        """
        if sip.isdeleted(self):
            return
        view = self.parent()
        if not isinstance(view, QAbstractItemView) or sip.isdeleted(view) or not index.isValid():
            logger.debug('Discarding icon drop: view or target row was removed')
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        error = None
        try:
            image = ElCommon.imageFromMime(mime)
            if image is None:
                raise ValueError('The dropped object is not a picture or it cannot be downloaded')
            accepted = self.onDrop(QModelIndex(index), image)
            logger.debug('Icon drop callback finished: row=%s accepted=%s', index.row(), accepted)
            if accepted:
                self.clearCache()
                self.parent().viewport().update()
        except Exception as exc:
            logger.exception('Icon drop failed: row=%s column=%s', index.row(), index.column())
            error = str(exc)
        finally:
            QApplication.restoreOverrideCursor()
        if error is not None:
            self.dropFailed.emit(error)
