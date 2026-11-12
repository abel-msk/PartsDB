"""Unit tests: default part icons from Qt resources for parts without a picture.

Run from the project root:
    python -m unittest tests.test_default_icons -v
"""
import os
import shutil
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtCore import QFile, Qt
from PyQt6.QtGui import QStandardItemModel, QStandardItem
from PyQt6.QtWidgets import QApplication

from ElDBScheme import DBFactory
from ElDefaultIcons import DefaultPartIcons, SECTION_ICONS, RESOURCE_TEMPLATE, mountingOf, SMD, THT
from ElIconDelegate import IconCellDelegate

app = QApplication.instance() or QApplication(sys.argv)


class TestMountingOf(unittest.TestCase):
    def test_smd_packages(self):
        # values that occur in the parts DB
        for package in ("SMD", "SMD_0603", "SMD_1206", "SMD_2512", "SMT", "SND_0805", "SVD_1206", "SMD-0805",
                        "SOD-123", "SOD-123FL", "SOD-323", "SOD_123", "SMA", "SMB", "DO-214AA", "SLP1610",
                        "SOT-23", "sot-23-5", "sot-223", "SOP-8", "SO-8", "TO-252", "TypeA/3216", "0805", "1206"):
            self.assertEqual(mountingOf(package), SMD, package)

    def test_tht_packages(self):
        for package in ("THT", "ТНТ", "DO-41", "TO-92", "ТО-92", "TO-220AB", "TO-220F", "DIP-8"):
            self.assertEqual(mountingOf(package), THT, package)

    def test_unknown_packages(self):
        for package in (None, "", "module", "MBS", "14мм", "3296W"):
            self.assertEqual(mountingOf(package), "", package)


class TestResources(unittest.TestCase):
    def test_every_family_has_its_default_mounting_or_fallback(self):
        for section, family in SECTION_ICONS.items():
            if family is None:
                continue
            name, mount = family
            paths = [RESOURCE_TEMPLATE.format(family=name, mount=m) for m in (SMD, THT)]
            self.assertTrue(any(QFile.exists(p) for p in paths), "no resource icon for %s" % (section,))


class TestDefaultPartIcons(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="partsdb-deficons-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.factory = DBFactory(os.path.join(self.tmp, "t.sqlite"))
        self.addCleanup(self.factory.disconnect)
        self.icons = DefaultPartIcons(self.factory)

    def section(self, *names):
        parent = None
        for name in names:
            parent = self.factory.appendType(name, parent)
        return parent

    def part(self, theType, package=""):
        return self.factory.createPart(theType, {"part_num": "X", "package": package})

    def icon(self, *names, package=""):
        return self.icons.iconPath(self.part(self.section(*names), package))

    def test_section_path_from_root(self):
        child = self.section("Диод", "Шотки")
        self.assertEqual(self.icons.sectionPath(child.recId), ("Диод", "Шотки"))

    def test_resistor_by_package(self):
        self.assertEqual(self.icon("Резистор", package="SMD_0805"), ":/parts/icons/resistor_smd.png")
        self.assertEqual(self.icon("Резистор", package="THT"), ":/parts/icons/resistor_tht.png")
        self.assertEqual(self.icon("Резистор"), ":/parts/icons/resistor_smd.png")  # family default

    def test_subsection_inherits_family(self):
        self.assertEqual(self.icon("Диод", "Шотки", package="SOD-123"), ":/parts/icons/diode_smd.png")
        self.assertEqual(self.icon("Диод", "Зенера", package="DO-41"), ":/parts/icons/diode_tht.png")

    def test_longest_prefix_wins_and_None_disables(self):
        self.assertEqual(self.icon("Резистор", "переменный", package="3296W"), "")

    def test_capacitors(self):
        self.assertEqual(self.icon("Конденсатор", "Керамический", package="SMD_0603"),
                         ":/parts/icons/capacitor_ceramic_smd.png")
        self.assertEqual(self.icon("Конденсатор", "Электролитический"),
                         ":/parts/icons/capacitor_electrolytic_tht.png")
        self.assertEqual(self.icon("Конденсатор", "Электролитический", package="SMD"),
                         ":/parts/icons/capacitor_electrolytic_smd.png")
        self.assertEqual(self.icon("Конденсатор", "Танталовый", package="TypeA/3216"),
                         ":/parts/icons/capacitor_tantalum_smd.png")

    def test_missing_variant_falls_back_to_other_mounting(self):
        # there is no ceramic THT picture: use the SMD one
        self.assertEqual(self.icon("Конденсатор", "Керамический", package="THT"),
                         ":/parts/icons/capacitor_ceramic_smd.png")

    def test_section_without_default(self):
        self.assertEqual(self.icon("Дисплей"), "")
        self.assertEqual(self.icon("Конденсатор"), "")  # only subsections have pictures

    def test_type_added_after_first_lookup(self):
        self.icon("Дисплей")  # loads TYPES
        self.assertEqual(self.icon("Резистор", package="SMD"), ":/parts/icons/resistor_smd.png")

    def test_no_part(self):
        self.assertEqual(self.icons.iconPath(None), "")


class TestDelegateDefault(TestDefaultPartIcons):
    def index(self, part, icon=""):
        model = QStandardItemModel(1, 1)
        item = QStandardItem(icon)
        item.setData(part, Qt.ItemDataRole.UserRole)
        model.setItem(0, 0, item)
        self._model = model  # keep alive
        return model.index(0, 0)

    def test_default_used_when_no_picture(self):
        delegate = IconCellDelegate(iconsDir=self.tmp, defaultIcons=self.icons)
        index = self.index(self.part(self.section("Резистор"), "SMD"))
        self.assertEqual(delegate.imagePath(index), "")
        self.assertEqual(delegate.defaultIconPath(index), ":/parts/icons/resistor_smd.png")

    def test_resource_pixmap_loads(self):
        delegate = IconCellDelegate()
        from PyQt6.QtCore import QSize
        pm = delegate.pixmap(":/parts/icons/resistor_smd.png", QSize(40, 40))
        self.assertIsNotNone(pm)
        self.assertFalse(pm.isNull())
        self.assertIsNone(delegate.pixmap(":/parts/icons/no_such.png", QSize(40, 40)))

    def test_without_default_icons(self):
        delegate = IconCellDelegate()
        self.assertEqual(delegate.defaultIconPath(self.index(self.part(self.section("Резистор")))), "")


if __name__ == "__main__":
    unittest.main()
