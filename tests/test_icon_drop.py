"""Unit tests: picture dropped on the icon cell becomes the part's PNG icon.

Run from the project root:
    python -m unittest tests.test_icon_drop -v
"""
import base64
import ctypes
import os
import shutil
import sys
import tempfile
import threading
import unittest
from unittest import mock
from functools import partial
from http.server import HTTPServer, SimpleHTTPRequestHandler

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import sip
from PyQt6.QtCore import QMimeData, QUrl, QBuffer, QIODevice
from PyQt6.QtGui import QImage, QColor, QPixmap, QColorSpace
from PyQt6.QtWidgets import QApplication

import ElIconDrop

app = QApplication.instance() or QApplication(sys.argv)


def makeImage(w=40, h=20, color="red") -> QImage:
    img = QImage(w, h, QImage.Format.Format_ARGB32)
    img.fill(QColor(color))
    return img


class TestIconDrop(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.src = os.path.join(self.tmp, "src")
        self.icons = os.path.join(self.tmp, "icons")
        os.makedirs(self.src)
        self.jpg = os.path.join(self.src, "photo.jpg")
        makeImage().save(self.jpg, "JPG")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_local_file(self):
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(self.jpg)])
        self.assertTrue(ElIconDrop.canProvideImage(mime))
        img = ElIconDrop.imageFromMime(mime)
        self.assertEqual((img.width(), img.height()), (40, 20))

    def test_not_an_image(self):
        txt = os.path.join(self.src, "a.txt")
        with open(txt, "w") as f:
            f.write("hello")
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(txt)])
        self.assertIsNone(ElIconDrop.imageFromMime(mime))
        self.assertFalse(ElIconDrop.canProvideImage(QMimeData()))

    def test_pdf_is_not_an_icon(self):
        # Qt on macOS can render a PDF page as an image; a datasheet must not become an icon
        pdf = os.path.join(self.src, "ds.pdf")
        with open(pdf, "wb") as f:
            f.write(b"%PDF-1.4\n%fake\n")
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(pdf)])
        self.assertFalse(ElIconDrop.canProvideImage(mime))
        self.assertIsNone(ElIconDrop.imageFromMime(mime))
        self.assertFalse(ElIconDrop.isImageFile(self.src))  # a folder

    def test_copy_mime_data_owns_the_image(self):
        """macOS: a browser drag's image points into pasteboard memory freed after the drop (SIGSEGV on save)."""
        w, h = 8, 4
        buf = ctypes.create_string_buffer(b"\x00\x00\xff\xff" * (w * h))  # red, BGRA
        foreign = QImage(sip.voidptr(ctypes.addressof(buf)), w, h, w * 4, QImage.Format.Format_ARGB32)
        src = QMimeData()
        src.setImageData(foreign)
        src.setHtml('<img src="https://example.invalid/a.png">')
        src.setUrls([QUrl("https://example.invalid/page")])
        mime = ElIconDrop.copyMimeData(src)
        ctypes.memset(buf, 0x55, w * h * 4)  # the drag is over: its memory is reused
        self.assertEqual(foreign.pixelColor(0, 0).name(), "#555555")  # the original really shares the buffer
        img = ElIconDrop.imageFromMime(mime)
        self.assertEqual(img.pixelColor(0, 0).name(), "#ff0000")
        self.assertEqual(mime.html(), src.html())
        self.assertEqual([u.toString() for u in mime.urls()], ["https://example.invalid/page"])
        name = ElIconDrop.saveIcon(img, self.icons, "MMBT2222A")
        self.assertEqual(QImage(os.path.join(self.icons, name)).pixelColor(0, 0).name(), "#ff0000")

    def test_plain_image_keeps_only_pixels(self):
        """Browser pictures on macOS carry a colour profile and metadata; Qt's PNG writer crashed on them."""
        img = QImage(6, 4, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(QColor(255, 0, 0, 128))  # translucent: premultiplied values differ from the stored ones
        img.setColorSpace(QColorSpace(QColorSpace.NamedColorSpace.DisplayP3))
        img.setText("Description", "x" * 100)
        img.setDevicePixelRatio(2.0)
        plain = ElIconDrop.plainImage(img)
        self.assertEqual((plain.width(), plain.height()), (6, 4))
        self.assertEqual(plain.format(), QImage.Format.Format_ARGB32)
        self.assertFalse(plain.colorSpace().isValid())
        self.assertEqual(plain.textKeys(), [])
        self.assertEqual(plain.devicePixelRatio(), 1.0)
        c = plain.pixelColor(5, 3)
        self.assertEqual((c.red(), c.green(), c.blue()), (255, 0, 0))
        self.assertAlmostEqual(c.alpha(), 128, delta=1)
        img.fill(QColor("blue"))  # the result does not share memory with the source
        self.assertEqual(plain.pixelColor(0, 0).red(), 255)
        name = ElIconDrop.saveIcon(img, self.icons, "P3")
        saved = QImage(os.path.join(self.icons, name))
        self.assertFalse(saved.colorSpace().isValid())
        self.assertEqual(saved.pixelColor(0, 0).blue(), 255)

    # ----- colour profile of browser pictures (macOS) -----

    SYSTEM_PROFILES = "/System/Library/ColorSync/Profiles"

    def profile(self, name: str) -> QColorSpace:
        path = os.path.join(self.SYSTEM_PROFILES, name)
        if not os.path.isfile(path):
            self.skipTest("no macOS profile " + name)
        with open(path, "rb") as f:
            return QColorSpace.fromIccProfile(f.read())

    def test_safe_color_space_rebuilds_standard_profiles(self):
        for name, primaries in (("sRGB Profile.icc", QColorSpace.Primaries.SRgb),
                                ("Display P3.icc", QColorSpace.Primaries.DciP3D65)):
            safe = ElIconDrop.safeColorSpace(self.profile(name))
            self.assertTrue(safe.isValid(), name)
            self.assertEqual(safe.primaries(), primaries, name)
            self.assertEqual(safe.transferFunction(), QColorSpace.TransferFunction.SRgb, name)

    def test_safe_color_space_drops_custom_profiles(self):
        self.assertFalse(ElIconDrop.safeColorSpace(self.profile("Generic RGB Profile.icc")).isValid())
        self.assertFalse(ElIconDrop.safeColorSpace(QColorSpace()).isValid())

    def test_owned_image_never_reads_the_dragged_profile(self):
        """Crash 2026-11-13: the ICC bytes of a dragged picture are freed after the drop; reading them crashes."""
        img = QImage(10, 6, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(QColor("red"))
        img.setColorSpace(self.profile("sRGB Profile.icc"))
        mime = QMimeData()
        mime.setImageData(img)
        with mock.patch.object(QColorSpace, "iccProfile", side_effect=AssertionError("profile bytes read")):
            copied = ElIconDrop.copyMimeData(mime)
            owned = ElIconDrop.imageFromMime(copied)
            ElIconDrop.imageInfo(owned)
        self.assertEqual(owned.colorSpace().primaries(), QColorSpace.Primaries.SRgb)
        self.assertIsNot(owned.colorSpace(), img.colorSpace())
        name = ElIconDrop.saveIcon(owned, self.icons, "MMBT2222A")
        self.assertEqual(QImage(os.path.join(self.icons, name)).pixelColor(0, 0).name(), "#ff0000")

    def test_plain_image_converts_to_srgb(self):
        img = QImage(4, 4, QImage.Format.Format_ARGB32)
        img.fill(QColor(128, 128, 128))
        img.setColorSpace(QColorSpace(QColorSpace.NamedColorSpace.SRgbLinear))
        plain = ElIconDrop.plainImage(img)
        self.assertFalse(plain.colorSpace().isValid())
        self.assertGreater(plain.pixelColor(0, 0).red(), 160)  # linear 0.5 is brighter in sRGB

    def test_owned_image(self):
        pm = QPixmap(5, 3)
        pm.fill(QColor("green"))
        self.assertEqual(ElIconDrop.ownedImage(pm).size().width(), 5)
        self.assertIsNone(ElIconDrop.ownedImage(QImage()))
        self.assertIsNone(ElIconDrop.ownedImage("not an image"))

    def test_image_data(self):
        mime = QMimeData()
        mime.setImageData(makeImage(10, 10))
        self.assertTrue(ElIconDrop.canProvideImage(mime))
        self.assertEqual(ElIconDrop.imageFromMime(mime).width(), 10)

    def test_html_data_uri(self):
        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        makeImage(7, 5).save(buf, "PNG")
        uri = "data:image/png;base64," + base64.b64encode(bytes(buf.data())).decode()
        mime = QMimeData()
        mime.setHtml('<meta charset="utf-8"><img alt="x" src="{}">'.format(uri))
        self.assertTrue(ElIconDrop.canProvideImage(mime))
        self.assertEqual(ElIconDrop.imageFromMime(mime).width(), 7)

    def test_http_url(self):
        handler = partial(SimpleHTTPRequestHandler, directory=self.src)
        handler.log_message = lambda *a: None
        server = HTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            url = "http://127.0.0.1:{}/photo.jpg".format(server.server_port)
            mime = QMimeData()
            mime.setUrls([QUrl(url)])
            self.assertEqual(ElIconDrop.imageFromMime(mime).width(), 40)
            # the browser page URL is not a picture, the <img> in the HTML is
            mime = QMimeData()
            mime.setUrls([QUrl("http://127.0.0.1:{}/".format(server.server_port))])
            mime.setHtml('<img src="{}">'.format(url))
            self.assertEqual(ElIconDrop.imageFromMime(mime).height(), 20)
        finally:
            server.shutdown()

    def test_save_png_unique_and_scaled(self):
        big = makeImage(2000, 1000)
        name1 = ElIconDrop.saveIcon(big, self.icons, "IRF 540/N")
        name2 = ElIconDrop.saveIcon(makeImage(), self.icons, "IRF 540/N")
        self.assertEqual(name1, "IRF_540_N.png")
        self.assertEqual(name2, "IRF_540_N-2.png")
        saved = QImage(os.path.join(self.icons, name1))
        self.assertEqual((saved.width(), saved.height()), (512, 256))
        with open(os.path.join(self.icons, name1), "rb") as f:
            self.assertEqual(f.read(8), b"\x89PNG\r\n\x1a\n")
        self.assertEqual(ElIconDrop.saveIcon(makeImage(), self.icons, ""), "icon.png")
        self.assertEqual(ElIconDrop.saveIcon(makeImage(), self.icons, "1N4007"), "1N4007.png")


if __name__ == "__main__":
    unittest.main()
