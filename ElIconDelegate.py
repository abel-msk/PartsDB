"""Table cell delegate that shows a part's picture as an icon.

The cell value (DisplayRole) is a path to an image file. The delegate draws the
image scaled to fit the cell, keeping its aspect ratio, and shows a larger
preview in the tooltip. Editing still goes through the default text editor,
so the path can be changed in place.
"""
import os
from html import escape

from PyQt6.QtCore import Qt, QSize, QRect, QModelIndex, QUrl, QFile
from PyQt6.QtGui import QPixmap, QPainter, QHelpEvent
from PyQt6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem, QStyle, QApplication, QToolTip, \
    QAbstractItemView

import ElLogger

logger = ElLogger.setLogger(__name__)


class IconCellDelegate(QStyledItemDelegate):
    PADDING = 2  # px between the image and the cell border
    PREVIEW_SIZE = 256  # max side of the tooltip preview, px
    CACHE_LIMIT = 500  # scaled pixmaps kept in memory

    DEFAULT_ICON_OPACITY = 0.6  # default (resource) icons are drawn paler than the parts' own pictures

    def __init__(self, parent=None, iconSize: QSize = QSize(48, 48), iconsDir: str = "", defaultIcons=None):
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

    def pixmap(self, path: str, size: QSize, dpr: float = 1.0) -> QPixmap | None:
        """Return the image scaled to fit `size` (logical px), or None if it can't be loaded.

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
        key = (path, mtime, size.width(), size.height(), dpr)
        pm = self._cache.get(key)
        if pm is None:
            src = QPixmap(path)
            if src.isNull():
                logger.debug("Can't load image %s", path)
                return None
            pm = src.scaled(QSize(int(size.width() * dpr), int(size.height() * dpr)),
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation)
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
        if rect.width() <= 0 or rect.height() <= 0:
            return

        dpr = painter.device().devicePixelRatioF() if painter.device() else 1.0
        pm = self.pixmap(path, rect.size(), dpr)
        painter.save()
        if isDefault:
            painter.setOpacity(self.DEFAULT_ICON_OPACITY)
        if pm is None:
            # Path is set but the file is missing or unreadable
            painter.setPen(opt.palette.color(opt.palette.ColorRole.PlaceholderText))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "?")
        else:
            w = round(pm.width() / pm.devicePixelRatio())
            h = round(pm.height() / pm.devicePixelRatio())
            target = QRect(0, 0, w, h)
            target.moveCenter(rect.center())
            painter.drawPixmap(target, pm)
        painter.restore()

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
