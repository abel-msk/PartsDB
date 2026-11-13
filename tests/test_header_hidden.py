"""Unit tests: 'hidden' set in the header edit dialog survives a stale copy saving the column width.

Run from the project root:
    python -m unittest tests.test_header_hidden -v
"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ElDBScheme import DBFactory


class TestHeaderPartialSave(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="partsdb-hdrhidden-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.factory = DBFactory(os.path.join(self.tmp, "t.sqlite"))
        self.addCleanup(self.factory.disconnect)
        self.theType = self.factory.appendType("Индуктивность", None)
        hdr = self.factory.getHeadersByType(self.theType.recId)["reduced_val"]
        hdr["hidden"] = True
        hdr["width"] = 0
        hdr.save()

    def stored(self, field="reduced_val"):
        return self.factory.getHeadersByType(self.theType.recId)[field]

    def test_stale_width_save_keeps_hidden_from_dialog(self):
        tableCopy = self.theType.getHeaders()["reduced_val"]  # parts table cache, hidden=True
        dialogCopy = self.factory.getHeadersByType(self.theType.recId)["reduced_val"]
        dialogCopy["hidden"] = False
        dialogCopy.save()
        tableCopy["width"] = 100  # column shown -> resize -> width saved from the stale copy
        tableCopy.save()
        self.assertFalse(self.stored()["hidden"])
        self.assertEqual(self.stored()["width"], 100)

    def test_save_writes_only_changed_fields(self):
        hdr = self.stored()
        hdr["display"] = "Reduced"
        hdr.save()
        self.assertEqual(self.stored()["display"], "Reduced")
        self.assertTrue(self.stored()["hidden"])

    def test_save_without_changes_is_noop(self):
        hdr = self.stored()
        hdr.save()
        self.assertTrue(self.stored()["hidden"])

    def test_refresh_headers_sees_dialog_change(self):
        self.theType.getHeaders()
        dialogCopy = self.factory.getHeadersByType(self.theType.recId)["reduced_val_units"]
        dialogCopy["hidden"] = True
        dialogCopy.save()
        self.assertTrue(self.theType.refreshHeaders()["reduced_val_units"]["hidden"])


if __name__ == "__main__":
    unittest.main()
