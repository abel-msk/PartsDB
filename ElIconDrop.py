"""Make a part icon from an image dropped on the parts table.

The image may come from the desktop (a local file), from a web browser (image data,
an image URL or an HTML fragment with <img src=...>). It is converted to PNG and saved
in the icons folder under a new name, so pictures of other parts are never overwritten.
"""
import base64
import os
import re
import urllib.parse
import urllib.request

from PyQt6.QtCore import QMimeData, QUrl, Qt
from PyQt6.QtGui import QImage, QImageReader, QPixmap, QColorSpace

import ElLogger

logger = ElLogger.setLogger(__name__)

MAX_ICON_SIDE = 512  # px: larger pictures are scaled down, smaller ones are kept as is
DOWNLOAD_TIMEOUT = 15  # s
DOWNLOAD_LIMIT = 20 * 1024 * 1024  # bytes
USER_AGENT = "Mozilla/5.0 (Macintosh) ElPartsCatalog"

IMG_SRC_RE = re.compile(r"""<img\b[^>]*?\bsrc\s*=\s*(["'])(.*?)\1""", re.IGNORECASE | re.DOTALL)
UNSAFE_NAME_RE = re.compile(r'[^\w.\-+]+', re.UNICODE)


def canProvideImage(mime: QMimeData) -> bool:
    """Quick check for drag enter: does the drag carry something that may be a picture."""
    if mime is None:
        return False
    if mime.hasImage():
        return True
    for url in mime.urls():
        if url.isLocalFile():
            if isImageFile(url.toLocalFile()):  # a PDF or a folder is refused right on drag enter
                return True
        elif _isUsableUrl(url):
            return True  # web content is known only after downloading
    if mime.hasHtml() and IMG_SRC_RE.search(mime.html() or ""):
        return True
    return False


def safeColorSpace(cs: QColorSpace) -> QColorSpace:
    """A colour space that owns all its data, built from the parameters of `cs` (invalid if it can't be).

    On macOS the colour space of a picture dragged from a browser wraps the ICC profile bytes of
    CoreGraphics without copying them; they are freed after the drag, and reading the profile
    (QImage.save writes it into the PNG) crashes with SIGSEGV. Never call iccProfile() on it.
    """
    if not cs.isValid():
        return QColorSpace()
    primaries, transfer = cs.primaries(), cs.transferFunction()
    if primaries == QColorSpace.Primaries.Custom or transfer == QColorSpace.TransferFunction.Custom:
        logger.debug("Drop a custom colour space: %s", cs.description())
        return QColorSpace()  # can't rebuild without the profile; an icon doesn't need exact colours
    return QColorSpace(primaries, transfer, cs.gamma())


def ownedImage(value) -> QImage | None:
    """Deep copy of a QImage / QPixmap that shares nothing with the drag (pixels, colour space), or None."""
    if isinstance(value, QPixmap):
        value = value.toImage()
    if isinstance(value, QImage) and not value.isNull():
        img = value.copy()
        img.setColorSpace(safeColorSpace(value.colorSpace()))
        return img
    return None


def imageInfo(img) -> str:
    """Short description of a QImage for the log."""
    if not isinstance(img, QImage):
        return repr(type(img).__name__)
    if img.isNull():
        return "null image"
    cs = img.colorSpace()  # never touch cs.iccProfile(): see safeColorSpace()
    return "{}x{} {} bpl={} bytes={} depth={} dpr={} colorspace={} text={}".format(
        img.width(), img.height(), img.format().name, img.bytesPerLine(), img.sizeInBytes(), img.depth(),
        img.devicePixelRatio(), (cs.description() or cs.colorModel().name) if cs.isValid() else "none",
        {k: len(img.text(k)) for k in img.textKeys()})


def plainImage(img: QImage) -> QImage:
    """Pixels only: a new ARGB32 image without the colour profile, text and other attributes.

    A picture dragged from a browser on macOS comes with CoreGraphics attributes (ICC profile, metadata);
    Qt's PNG writer crashed on such an image (SIGSEGV in QImage.save). An icon needs just the pixels.
    """
    cs = img.colorSpace()
    if cs.isValid() and cs != QColorSpace(QColorSpace.NamedColorSpace.SRgb):
        img = img.convertedToColorSpace(QColorSpace(QColorSpace.NamedColorSpace.SRgb))  # PNG without profile = sRGB
    src = img.convertToFormat(QImage.Format.Format_ARGB32)
    w, h, bpl = src.width(), src.height(), src.bytesPerLine()
    bits = src.constBits()
    bits.setsize(bpl * h)
    data = bytes(bits)  # Python owns these bytes
    return QImage(data, w, h, bpl, QImage.Format.Format_ARGB32).copy()  # copy(): QImage owns its buffer


def describeMime(mime: QMimeData) -> str:
    """What a drag carries, for the log: formats with sizes, URLs, image."""
    if mime is None:
        return "no mime data"
    parts = ["{}({})".format(fmt, len(mime.data(fmt))) for fmt in mime.formats()]
    lines = ["formats: " + ", ".join(parts)]
    if mime.hasUrls():
        lines.append("urls: " + " | ".join(u.toString()[:200] for u in mime.urls()))
    if mime.hasHtml():
        lines.append("html: " + (mime.html() or "")[:300].replace("\n", " "))
    if mime.hasImage():
        lines.append("image: " + imageInfo(mime.imageData()))
    return "; ".join(lines)


def copyMimeData(src: QMimeData) -> QMimeData:
    """Copy of the drag data that stays valid after the drop event returns."""
    mime = QMimeData()
    for fmt in src.formats():
        mime.setData(fmt, src.data(fmt))  # QByteArray copies
    if src.hasImage():
        img = ownedImage(src.imageData())
        if img is not None:
            mime.setImageData(img)
    return mime


def _isUsableUrl(url: QUrl) -> bool:
    return url.isLocalFile() or url.scheme() in ("http", "https", "data")


NOT_ICON_FORMATS = {"pdf"}  # Qt on macOS reads PDF as an image (first page): a datasheet is not an icon


def isImageFile(path: str) -> bool:
    """A readable picture file (checked by its header, not by the extension)."""
    if not os.path.isfile(path):
        return False
    fmt = bytes(QImageReader.imageFormat(path)).decode().lower()
    return bool(fmt) and fmt not in NOT_ICON_FORMATS


def imageFromMime(mime: QMimeData) -> QImage | None:
    """Image carried by the drag, or None. May download it from the web (blocking)."""
    if mime is None:
        return None
    # 1. Local files (Finder, desktop)
    for url in mime.urls():
        if url.isLocalFile():
            img = QImage(url.toLocalFile()) if isImageFile(url.toLocalFile()) else QImage()
            if not img.isNull():
                logger.info("Icon from local file %s: %s", url.toLocalFile(), imageInfo(img))
                return img
            logger.debug("Not an image: %s", url.toLocalFile())
    # 2. Image data put on the drag by the browser (Safari)
    if mime.hasImage():
        img = ownedImage(mime.imageData())
        if img is not None:
            logger.info("Icon from drag image data: %s", imageInfo(img))
            return img
    # 3. Web URLs, then <img src> from the HTML fragment (Chrome, Firefox)
    candidates = [u.toString() for u in mime.urls() if not u.isLocalFile()]
    if mime.hasHtml():
        candidates += [m.group(2) for m in IMG_SRC_RE.finditer(mime.html() or "")]
    if mime.hasText():
        text = (mime.text() or "").strip()
        if re.match(r"^(https?|data):", text, re.IGNORECASE) and "\n" not in text:
            candidates.append(text)
    seen = set()
    for src in candidates:
        src = src.strip().replace("&amp;", "&")
        if not src or src in seen:
            continue
        seen.add(src)
        img = imageFromUrl(src)
        if img is not None:
            logger.info("Icon from %s: %s", src[:200], imageInfo(img))
            return img
    return None


def imageFromUrl(src: str) -> QImage | None:
    """Load an image from a data:, file:// or http(s):// URL; None if it isn't an image."""
    try:
        if src.startswith("data:"):
            header, _, payload = src.partition(",")
            data = base64.b64decode(payload) if ";base64" in header else urllib.parse.unquote_to_bytes(payload)
        elif src.startswith("file:"):
            img = QImage(QUrl(src).toLocalFile())
            return None if img.isNull() else img
        elif src.startswith(("http://", "https://")):
            request = urllib.request.Request(src, headers={"User-Agent": USER_AGENT, "Accept": "image/*,*/*;q=0.5"})
            with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT) as response:
                data = response.read(DOWNLOAD_LIMIT + 1)
            if len(data) > DOWNLOAD_LIMIT:
                logger.warning("Image too large: %s", src)
                return None
        else:
            return None
    except Exception as e:  # network errors, bad base64 ...
        logger.warning("Can't load image %s: %s", src[:200], e)
        return None
    img = QImage()
    if not img.loadFromData(data):
        logger.debug("Not an image: %s", src[:200])
        return None
    return img


def makeIcon(img: QImage, maxSide: int = MAX_ICON_SIDE) -> QImage:
    """Scale down (never up) to fit maxSide, keeping the aspect ratio."""
    if max(img.width(), img.height()) > maxSide:
        img = img.scaled(maxSide, maxSide, Qt.AspectRatioMode.KeepAspectRatio,
                         Qt.TransformationMode.SmoothTransformation)
    return img


def iconFileName(base: str) -> str:
    """Safe file name stem from a part number."""
    name = UNSAFE_NAME_RE.sub("_", (base or "").strip()).strip("._")
    return name or "icon"


def uniquePath(folder: str, stem: str, ext: str = ".png") -> str:
    path = os.path.join(folder, stem + ext)
    n = 2
    while os.path.exists(path):
        path = os.path.join(folder, "{}-{}{}".format(stem, n, ext))
        n += 1
    return path


def saveIcon(img: QImage, iconsDir: str, partName: str) -> str:
    """Save as PNG in iconsDir; return the file name (relative to iconsDir, as stored in PARTS.icon)."""
    os.makedirs(iconsDir, exist_ok=True)
    path = uniquePath(iconsDir, iconFileName(partName))
    icon = plainImage(makeIcon(img))
    logger.info("Save icon %s: %s", path, imageInfo(icon))
    for handler in logger.handlers:  # the log must be on disk if saving crashes
        handler.flush()
    if not icon.save(path, "PNG"):
        raise OSError("Can't write {}".format(path))
    logger.info("Saved icon %s", path)
    return os.path.basename(path)
