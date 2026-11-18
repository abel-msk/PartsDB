"""Importer regression tests use isolated schematic files and never open a DB."""
import json
import os
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'ElPartsPluginSrc' / 'kicad'))

from ElPartsPluginApi.importers import InvalidSourceError, MissingSourceError, UnsupportedFormatError
from partsdb_kicad import KiCadImporter
from partsdb_kicad.plugin import _nominal
from partsdb_kicad.sexpr import parse


FIXTURE = (Path(__file__).resolve().parents[1] / 'input'
           / 'SMHome_UniversalRound_ESP32_C3_Mini_v4')
PROJECT = FIXTURE / 'SMHome_UniversalRound_ESP32_C3_Mini_v4.kicad_pro'


def symbol(uuid='r-uuid', reference='R1', unit=1, instances='', extra='', lib='Device:R', raw='4k7'):
    return f'''(symbol (lib_id "{lib}") (uuid "{uuid}") (unit {unit})
      (property "Reference" "{reference}") (property "Value" "{raw}")
      (property "Footprint" "Resistor_SMD:R_0805_2012Metric")
      {extra} {instances})'''


def schematic(uuid, body):
    return f'(kicad_sch (version 20250114) (uuid "{uuid}") {body})'


class KiCadPluginTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.project = self.folder / 'Test project.kicad_pro'
        self.project.write_text('{}')
        self.root = self.project.with_suffix('.kicad_sch')
        self.importer = KiCadImporter()

    def write_root(self, body):
        self.root.write_text(schematic('root', body))

    def test_components_flags_properties_and_library_templates(self):
        self.write_root('''(lib_symbols (symbol "Device:R" (property "Reference" "TEMPLATE")))'''
                        + symbol(extra='(in_bom no) (on_board no) (dnp yes) (property "Tolerance" "1%")')
                        + symbol(uuid='power', reference='#PWR01', lib='power:GND'))
        parts = self.importer.get_components(self.project.as_uri())
        self.assertEqual(len(parts), 1)
        part = parts[0]
        self.assertEqual((part.reference, part.external_id), ('R1', '/root/r-uuid'))
        self.assertEqual((part.nominal.value, part.nominal.unit), ('4700', 'ohm'))
        self.assertEqual(part.value_raw, '4k7')
        self.assertEqual(part.properties['Tolerance'], '1%')
        self.assertEqual((part.in_bom, part.on_board, part.dnp), (False, False, True))
        self.assertTrue(self.importer.probe(self.project.as_uri()).supported)
        self.assertEqual(self.importer.get_components(str(self.root)), parts)
        self.assertEqual(self.importer.import_project(str(self.project)).external_id, 'root')

    def test_repeated_sheet_instances_and_old_project_names(self):
        self.write_root('''(sheet (uuid "a") (property "Sheetfile" "child.kicad_sch"))
                          (sheet (uuid "b") (property "Sheetfile" "child.kicad_sch"))''')
        instances = '''(instances (project "Old project"
            (path "/root/a" (reference "R1") (unit 1))
            (path "/root/b" (reference "R2") (unit 1))))'''
        (self.folder / 'child.kicad_sch').write_text(schematic('child', symbol(instances=instances)))
        parts = self.importer.get_components(str(self.project))
        self.assertEqual([p.reference for p in parts], ['R1', 'R2'])
        self.assertEqual([p.external_id for p in parts], ['/root/a/r-uuid', '/root/b/r-uuid'])

    def test_current_project_instance_takes_precedence(self):
        instances = '''(instances (project "old" (path "/root" (reference "R99")))
                         (project "Test project" (path "/root" (reference "R3"))))'''
        self.write_root(symbol(instances=instances))
        self.assertEqual(self.importer.get_components(str(self.project))[0].reference, 'R3')

    def test_multiple_units_form_one_physical_position(self):
        self.write_root(symbol(uuid='b', reference='U1', unit=2, lib='Amplifier:Opamp', raw='LM358')
                        + symbol(uuid='a', reference='U1', unit=1, lib='Amplifier:Opamp', raw='LM358'))
        parts = self.importer.get_components(str(self.project))
        self.assertEqual(len(parts), 1)
        self.assertEqual(parts[0].external_id, '/root/a')
        self.assertEqual(parts[0].properties['kicad_symbol_uuids'], ['a', 'b'])

    def test_missing_child_fails_instead_of_returning_partial_list(self):
        self.write_root(symbol() + '(sheet (uuid "a") (property "Sheetfile" "missing.kicad_sch"))')
        with self.assertRaises(MissingSourceError):
            self.importer.get_components(str(self.project))

    def test_cycles_fail(self):
        self.write_root('(sheet (uuid "a") (property "Sheetfile" "Test project.kicad_sch"))')
        with self.assertRaises(InvalidSourceError):
            self.importer.get_components(str(self.project))

    def test_duplicate_and_unannotated_references_fail(self):
        for body in (symbol() + symbol(uuid='other'), symbol(reference='R?')):
            with self.subTest(body=body):
                self.write_root(body)
                with self.assertRaises(InvalidSourceError):
                    self.importer.get_components(str(self.project))

    def test_bad_project_json_and_unsupported_source(self):
        self.project.write_text('[]')
        with self.assertRaises(InvalidSourceError):
            self.importer.get_components(str(self.project))
        self.assertFalse(self.importer.probe(str(self.project)).supported)
        for uri in ('https://example.org/project.kicad_pro', 'file://server/project.kicad_pro', 'old.sch'):
            with self.subTest(uri=uri), self.assertRaises(UnsupportedFormatError):
                self.importer.get_components(uri)

    def test_malformed_sexpressions(self):
        for text in ('', '(', '(root))', '(root) (root)', '(root "unterminated)'):
            with self.subTest(text=text), self.assertRaises(InvalidSourceError):
                parse(text)
        self.assertEqual(parse(r'(root "a\"b" "C:\\parts")'), ['root', 'a"b', 'C:\\parts'])

    def test_nominals_preserve_case_and_decimal_units(self):
        for raw, kind, expected in [('10K', 'resistor', '10000'), ('1M', 'resistor', '1000000'),
                                    ('1m', 'resistor', '0.001'), ('0,002R', 'resistor', '0.002'),
                                    ('100nf', 'capacitor', '0.0000001'),
                                    ('4,7uF', 'capacitor', '0.0000047'),
                                    ('4n7', 'capacitor', '0.0000000047'),
                                    ('10µH', 'inductor', '0.00001')]:
            with self.subTest(raw=raw):
                self.assertEqual(_nominal(raw, kind).value, expected)
        self.assertIsNone(_nominal('100', 'capacitor'))
        self.assertIsNone(_nominal('DONE', 'led'))
        self.assertIsNone(_nominal('10k 1%', 'resistor'))

    def test_real_project_matches_kicad_netlist(self):
        cli = os.environ.get('KICAD_CLI') or shutil.which('kicad-cli')
        if not cli:
            self.skipTest('Set KICAD_CLI or add kicad-cli to PATH')
        copied = self.folder / FIXTURE.name
        shutil.copytree(FIXTURE, copied)
        source = copied / PROJECT.name
        output = self.folder / 'netlist.xml'
        subprocess.run([cli, 'sch', 'export', 'netlist', '--format', 'kicadxml',
                        '-o', str(output), str(source.with_suffix('.kicad_sch'))],
                       check=True, capture_output=True, text=True, timeout=60)
        expected = {c.attrib['ref']: (c.findtext('value') or '', c.findtext('footprint') or '')
                    for c in ET.parse(output).findall('.//components/comp')}
        parts = self.importer.get_components(str(source))
        actual = {c.reference: (c.value_raw, c.footprint or '') for c in parts}
        self.assertEqual(len(actual), len(parts))
        self.assertEqual(actual, expected)


class KiCadProjectFixtureTests(unittest.TestCase):
    """Always run against the committed project; KiCad itself is not required."""

    def setUp(self):
        self.importer = KiCadImporter()

    def test_project_matches_saved_kicad_export(self):
        expected = json.loads((FIXTURE / 'components.expected.json').read_text())
        project = self.importer.import_project(PROJECT.as_uri())
        actual = {c.reference: {'value': c.value_raw, 'footprint': c.footprint or ''}
                  for c in project.components}
        self.assertEqual(len(project.components), 49)
        self.assertEqual(len(actual), len(project.components))
        self.assertEqual(actual, expected)
        self.assertEqual(project.name, PROJECT.stem)
        self.assertEqual({Path(p).name for p in project.properties['source_files']},
                         {PROJECT.with_suffix('.kicad_sch').name,
                          'ExtConnectors.kicad_sch', 'PowerSupply.kicad_sch'})
        self.assertTrue(all(c.in_bom and c.on_board and not c.dnp for c in project.components))

    def test_project_nominals_and_kinds(self):
        parts = {c.reference: c for c in self.importer.get_components(str(PROJECT))}
        self.assertEqual((parts['C1'].nominal.value, parts['C1'].nominal.unit),
                         ('0.0000001', 'F'))
        self.assertEqual((parts['C2'].nominal.value, parts['C2'].nominal.unit),
                         ('0.0000047', 'F'))
        self.assertEqual(parts['C2'].value_raw, '4,7uF')
        self.assertEqual(parts['U1'].kind, 'module')
        self.assertEqual(parts['DB1'].kind, 'diode')

    def test_project_is_portable_and_identifiers_remain_stable(self):
        with tempfile.TemporaryDirectory() as folder:
            copied = Path(folder) / FIXTURE.name
            shutil.copytree(FIXTURE, copied)
            original = self.importer.get_components(str(PROJECT))
            relocated = self.importer.get_components((copied / PROJECT.name).as_uri())
            self.assertEqual(relocated, original)

    def test_missing_project_sheet_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            copied = Path(folder) / FIXTURE.name
            shutil.copytree(FIXTURE, copied)
            (copied / 'PowerSupply.kicad_sch').unlink()
            with self.assertRaises(MissingSourceError):
                self.importer.get_components(str(copied / PROJECT.name))


if __name__ == '__main__':
    unittest.main()
