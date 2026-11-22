"""Shared logging, owned image transfer, PNG storage and application data paths."""
from __future__ import annotations
import base64
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path
import logging
import sys


# loafFileHandler = None
loggers = {}
handlers = []

handler = logging.StreamHandler(stream=sys.stderr)
handler.setFormatter(logging.Formatter(fmt='[%(levelname)s] %(module)s/%(funcName)s: %(message)s'))
handlers.append(handler)

def_level = None

def setLogger(modName):
    """Register a module logger using the current configured level and output handlers.

    @param modName [str] Module name used in log records.
    @return [logging.Logger] Logger sharing console and configured file handlers.
    """
    logger = logging.getLogger(modName)
    logger.setLevel(logging.ERROR if def_level is None else def_level)
    loggers[modName] = logger
    for hdl in handlers:
        logger.addHandler(hdl)
    return logger


def setLevel(level):
    """Apply and retain the logging level for existing and subsequently registered modules.

    @param level [int, str] Standard logging severity accepted by Logger.setLevel.
    @return [None] Update all registered loggers and the registration default.
    """
    global def_level
    def_level = level
    for logger in loggers.values():
        logger.setLevel(level=level)


def setLogFile(FN):
    """Attach a timestamped UTF-8 log file to existing and future module loggers.

    @param FN [str] Destination log filename.
    @return [None] Register the file handler and report its location.
    """
    handler = logging.FileHandler(FN, mode='a', encoding="UTF-8", delay=False, errors=None)
    handler.setFormatter(logging.Formatter(fmt='%(asctime)s: [%(levelname)s] %(module)s/%(funcName)s: %(message)s'))
    handlers.append(handler)

    print("Create log file {}".format(FN))
    for key, logger in loggers.items():
            logger.addHandler(handler)


logger = setLogger(__name__)


def canProvideImage(mime: QMimeData) -> bool:
    """Quick check for drag enter: does the drag carry something that may be a picture.

    @param mime [QMimeData] mime used by image transfer or PNG conversion.
    @return [bool] Requested image, metadata or path; None means no usable image."""
    from PyQt6.QtCore import QMimeData
    from ElConstants import IMG_SRC_RE
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

    @param cs [QColorSpace] cs used by image transfer or PNG conversion.
    @return [QColorSpace] Requested image, metadata or path; None means no usable image."""
    from PyQt6.QtGui import QColorSpace
    if not cs.isValid():
        return QColorSpace()
    primaries, transfer = cs.primaries(), cs.transferFunction()
    if primaries == QColorSpace.Primaries.Custom or transfer == QColorSpace.TransferFunction.Custom:
        logger.debug("Drop a custom colour space: %s", cs.description())
        return QColorSpace()  # can't rebuild without the profile; an icon doesn't need exact colours
    return QColorSpace(primaries, transfer, cs.gamma())


def ownedImage(value) -> QImage | None:
    """Deep copy of a QImage / QPixmap that shares nothing with the drag (pixels, colour space), or None.

    @param value [QImage, QPixmap, object] value used by image transfer or PNG conversion.
    @return [QImage, None] Requested image, metadata or path; None means no usable image."""
    from PyQt6.QtGui import QImage, QPixmap
    if isinstance(value, QPixmap):
        value = value.toImage()
    if isinstance(value, QImage) and not value.isNull():
        img = value.copy()
        img.setColorSpace(safeColorSpace(value.colorSpace()))
        return img
    return None


def imageInfo(img) -> str:
    """Short description of a QImage for the log.

    @param img [QImage] img used by image transfer or PNG conversion.
    @return [str] Requested image, metadata or path; None means no usable image."""
    from PyQt6.QtGui import QImage
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

    @param img [QImage] img used by image transfer or PNG conversion.
    @return [QImage] Requested image, metadata or path; None means no usable image."""
    from PyQt6.QtGui import QColorSpace, QImage
    cs = img.colorSpace()
    if cs.isValid() and cs != QColorSpace(QColorSpace.NamedColorSpace.SRgb):
        img = img.convertedToColorSpace(QColorSpace(QColorSpace.NamedColorSpace.SRgb))  # PNG without profile = sRGB
    src = img.convertToFormat(QImage.Format.Format_ARGB32)
    w, h, bpl = src.width(), src.height(), src.bytesPerLine()
    bits = src.constBits()
    bits.setsize(bpl * h)
    data = bytes(bits)  # Python owns these bytes
    return QImage(data, w, h, bpl, QImage.Format.Format_ARGB32).copy()


def describeMime(mime: QMimeData) -> str:
    """What a drag carries, for the log: formats with sizes, URLs, image.

    @param mime [QMimeData] mime used by image transfer or PNG conversion.
    @return [str] Requested image, metadata or path; None means no usable image."""
    from PyQt6.QtCore import QMimeData
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
    """Copy of the drag data that stays valid after the drop event returns.

    @param src [QMimeData] src used by image transfer or PNG conversion.
    @return [QMimeData] Requested image, metadata or path; None means no usable image."""
    from PyQt6.QtCore import QMimeData
    mime = QMimeData()
    for fmt in src.formats():
        mime.setData(fmt, src.data(fmt))  # QByteArray copies
    if src.hasImage():
        img = ownedImage(src.imageData())
        if img is not None:
            mime.setImageData(img)
    return mime


def _isUsableUrl(url: QUrl) -> bool:
    """Determine whether the URL is supported for image transfer.

    @param url [QUrl] url used by image transfer or PNG conversion.
    @return [bool] Requested image, metadata or path; None means no usable image."""
    from PyQt6.QtCore import QUrl
    return url.isLocalFile() or url.scheme() in ("http", "https", "data")


def isImageFile(path: str) -> bool:
    """A readable picture file (checked by its header, not by the extension).

    @param path [str] path used by image transfer or PNG conversion.
    @return [bool] Requested image, metadata or path; None means no usable image."""
    from PyQt6.QtGui import QImageReader
    from ElConstants import NOT_ICON_FORMATS
    if not os.path.isfile(path):
        return False
    fmt = bytes(QImageReader.imageFormat(path)).decode().lower()
    return bool(fmt) and fmt not in NOT_ICON_FORMATS


def imageFromMime(mime: QMimeData) -> QImage | None:
    """Image carried by the drag, or None. May download it from the web (blocking).

    @param mime [QMimeData] mime used by image transfer or PNG conversion.
    @return [QImage, None] Requested image, metadata or path; None means no usable image."""
    from PyQt6.QtCore import QMimeData
    from PyQt6.QtGui import QImage
    from ElConstants import IMG_SRC_RE
    if mime is None:
        return None
    logger.debug('Decoding dropped image: formats=%s', mime.formats())
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
    """Load an image from a data:, file:// or http(s):// URL; None if it isn't an image.

    @param src [str] src used by image transfer or PNG conversion.
    @return [QImage, None] Requested image, metadata or path; None means no usable image."""
    from PyQt6.QtCore import QUrl
    from PyQt6.QtGui import QImage
    from ElConstants import DOWNLOAD_LIMIT, DOWNLOAD_TIMEOUT, USER_AGENT
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
        logger.debug('Image download/decoding failed: source=%s', src[:200], exc_info=True)
        logger.warning("Can't load image %s: %s", src[:200], e)
        return None
    img = QImage()
    if not img.loadFromData(data):
        logger.debug("Not an image: %s", src[:200])
        return None
    return img


def makeIcon(img: QImage, maxSide: int | None = None) -> QImage:
    """Scale down (never up) to fit maxSide, keeping the aspect ratio.

    @param img [QImage] img used by image transfer or PNG conversion.
    @param maxSide [int] maxSide used by image transfer or PNG conversion.
    @return [QImage] Requested image, metadata or path; None means no usable image."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QImage
    from ElConstants import MAX_ICON_SIDE
    if maxSide is None:
        maxSide = MAX_ICON_SIDE
    if max(img.width(), img.height()) > maxSide:
        logger.debug('Scaling icon: source=%sx%s maximum=%s', img.width(), img.height(), maxSide)
        img = img.scaled(maxSide, maxSide, Qt.AspectRatioMode.KeepAspectRatio,
                         Qt.TransformationMode.SmoothTransformation)
    return img


def iconFileName(base: str) -> str:
    """Safe file name stem from a part number.

    @param base [str] base used by image transfer or PNG conversion.
    @return [str] Requested image, metadata or path; None means no usable image."""
    from ElConstants import UNSAFE_NAME_RE
    name = UNSAFE_NAME_RE.sub("_", (base or "").strip()).strip("._")
    return name or "icon"


def uniquePath(folder: str, stem: str, ext: str = ".png") -> str:
    """Select a non-existing image destination without overwriting files.

    @param folder [str] folder used by image transfer or PNG conversion.
    @param stem [str] stem used by image transfer or PNG conversion.
    @param ext [str] ext used by image transfer or PNG conversion.
    @return [str] Requested image, metadata or path; None means no usable image."""
    path = os.path.join(folder, stem + ext)
    n = 2
    while os.path.exists(path):
        path = os.path.join(folder, "{}-{}{}".format(stem, n, ext))
        n += 1
    return path


def saveIcon(img: QImage, iconsDir: str, partName: str) -> str:
    """Save as PNG in iconsDir; return the file name (relative to iconsDir, as stored in PARTS.icon).

    @param img [QImage] img used by image transfer or PNG conversion.
    @param iconsDir [str] iconsDir used by image transfer or PNG conversion.
    @param partName [str] partName used by image transfer or PNG conversion.
    @return [str] Requested image, metadata or path; None means no usable image."""
    from PyQt6.QtGui import QImage
    logger.debug('Preparing PNG icon: folder=%s name=%r image=%s', iconsDir, partName, imageInfo(img))
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


def configuredDataPath(config=None, fallback=''):
    """Resolve the configured data directory using the configuration file's location.

    @param config [ElConfig, None] Settings containing main.data_path and optional filename.
    @param fallback [str] Active factory's resolved data directory, or the database folder.
    @return [str] Absolute expanded data directory; no files are created.
    """
    from constants import CONFIG_DATA_PATH
    value = config.get_value(CONFIG_DATA_PATH) if config is not None else None
    if not value:
        path = Path(fallback or Path.cwd()).expanduser()
    else:
        path = Path(str(value)).expanduser()
        if not path.is_absolute():
            filename = getattr(config, 'filename', '')
            base = Path(filename).expanduser().resolve().parent if filename else Path(fallback or Path.cwd())
            path = base / path
    result = str(path.resolve())
    logger.debug('Resolved data directory: configured=%r fallback=%r result=%s', value, fallback, result)
    return result


def basicTypeIconsDir(dataPath, create=False):
    """Locate PNG icons for basic component types inside the application's data directory.

    @param dataPath [str] Resolved main.data_path directory.
    @param create [bool] True creates the folder when preparing an image write.
    @return [str] Absolute el_icons folder path.
    """
    from ElConstants import BASIC_TYPE_ICONS_DIR
    folder = Path(dataPath).expanduser().resolve() / BASIC_TYPE_ICONS_DIR
    if create:
        folder.mkdir(parents=True, exist_ok=True)
    logger.debug('Basic type icon directory: path=%s create=%s', folder, create)
    return str(folder)


def installBasicTypeIcons(dataPath, sourceDir):
    """Copy supplied PNG icons to el_icons without overwriting existing user images.

    @param dataPath [str] Resolved application data directory.
    @param sourceDir [str] Source directory containing the initial PNG files.
    @return [dict[str, str]] Source filenames mapped to installed absolute PNG paths.
    """
    folder = Path(basicTypeIconsDir(dataPath, create=True))
    installed = {}
    for source in sorted(Path(sourceDir).glob('*.png')):
        if not isImageFile(str(source)):
            raise ValueError('Invalid PNG icon: ' + str(source))
        content = source.read_bytes()
        target = folder / source.name
        if target.exists() and target.read_bytes() != content:
            matching = next((candidate for candidate in folder.glob(source.stem + '-*' + source.suffix)
                             if candidate.is_file() and candidate.read_bytes() == content), None)
            target = matching or Path(uniquePath(str(folder), source.stem, source.suffix))
        if not target.exists():
            with target.open('xb') as output:
                output.write(content)
            logger.debug('Installed basic type PNG: source=%s destination=%s', source, target)
        else:
            logger.debug('Reusing installed basic type PNG: path=%s', target)
        installed[source.name] = str(target)
    logger.debug('Basic type PNG installation completed: count=%s folder=%s', len(installed), folder)
    return installed
