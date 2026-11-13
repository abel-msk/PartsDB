"""Table cell delegate that shows a part's picture as an icon.

The cell value (DisplayRole) is a path to an image file. The delegate draws the
image scaled to fit the cell, keeping its aspect ratio, and shows a larger
preview in the tooltip. Editing still goes through the default text editor,
so the path can be changed in place.
"""
import os
from html import escape

from PyQt6.QtCore import Qt, QSize, QRect, QRectF, QModelIndex, QUrl, QFile
from PyQt6.QtGui import QPixmap, QPainter, QHelpEvent, QPainterPath, QColor, QPen
from PyQt6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem, QStyle, QApplication, QToolTip, \
    QAbstractItemView

import ElLogger

logger = ElLogger.setLogger(__name__)


class IconCellDelegate(QStyledItemDelegate):
    PADDING = 2  # px between the image and the cell border
    PREVIEW_SIZE = 256  # max side of the tooltip preview, px
    CACHE_LIMIT = 500  # scaled pixmaps kept in memory

    DEFAULT_ICON_OPACITY = 0.6  # default (resource) icons are drawn paler than the parts' own pictures

    FRAME_RADIUS = 5.0  # corner radius of the frame around the icon, pt (logical px)
    FRAME_WIDTH = 1.0  # frame line width
    FRAME_PADDING = 5  # px between the frame and the picture inside it
    FRAME_BACKGROUND = QColor(255, 255, 255)  # fill inside the frame
    SHADOW_OFFSET = 2  # shadow shift down, px
    SHADOW_BLUR = 3  # shadow softness: number of 1px layers around the shape
    SHADOW_ALPHA = 60  # opacity of the darkest shadow layer, 0..255

    def __init__(self, parent=None, iconSize: QSize = QSize(60, 60), iconsDir: str = "", defaultIcons=None):
        super().__init__(parent)
        self.iconSize = iconSize
        self.iconsDir = iconsDir  # base folder for relative icon paths
        self.defaultIcons = defaultIcons  # ElDefaultIcons.DefaultPartIcons: icon for parts without a picture
        self._cache: dict = {}  # (path, mtime, w, h, dpr) -> QPixmap

    # ---------- image loading ----------

    def imagePath(self, index: QModelIndex) -> str:
        """Full image path for the cell: relative values are taken inside iconsDir."""
        value = index.data(Qt.ItemDataRole.DisplayRole)
        if value is None:
            return ""
        path = str(value).strip()
        if not path:
            return ""
        if path.startswith("file://"):
            path = QUrl(path).toLocalFile()
        path = os.path.expanduser(path)
        if not os.path.isabs(path) and self.iconsDir:
            path = os.path.join(self.iconsDir, path)
        return path

    def defaultIconPath(self, index: QModelIndex) -> str:
        """Qt resource path of the default icon for the cell's part, or ''."""
        if self.defaultIcons is None:
            return ""
        return self.defaultIcons.iconPath(index.data(Qt.ItemDataRole.UserRole))

    def pixmap(self, path: str, size: QSize, dpr: float = 1.0, fill: bool = False) -> QPixmap | None:
        """Return the image scaled to fit `size` (logical px), or None if it can't be loaded.

        With `fill` the image covers the whole `size` keeping its aspect ratio, and the overflow
        is cropped evenly from both sides, so the result is exactly `size`.

        `path` is a file on disk or a Qt resource (":/...").
        """
        if not path:
            return None
        if path.startswith(":"):
            if not QFile.exists(path):
                return None
            mtime = 0  # resources are built into the program and never change
        elif os.path.isfile(path):
            mtime = os.path.getmtime(path)
        else:
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
        return pm

    def clearCache(self):
        self._cache.clear()

    # ---------- painting ----------

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
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

    def paintFramed(self, painter: QPainter, square: QRect, pm: QPixmap | None, target: QRect | None,
                    opt: QStyleOptionViewItem):
        """Draw a rounded frame with a soft shadow under it and the pixmap inside (\"?\" if there is none)."""
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
        return QSize(self.iconSize.width() + 2 * self.PADDING, self.iconSize.height() + 2 * self.PADDING)

    # ---------- tooltip preview ----------

    def helpEvent(self, event: QHelpEvent, view: QAbstractItemView, option: QStyleOptionViewItem,
                  index: QModelIndex) -> bool:
        if event is None or event.type() != event.Type.ToolTip:
            return super().helpEvent(event, view, option, index)
        path = self.imagePath(index)
        if not path:
            if self.defaultIconPath(index):
                QToolTip.showText(event.globalPos(), "No picture: default icon for the section", view)
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
            html = f"Image not found:<br>{escape(path)}"
        QToolTip.showText(event.globalPos(), html, view)
        return True
