"""Source outlines are inspection only; source must never be executed."""
import tempfile
import unittest
from pathlib import Path

from cadgen.viewer.design_outline import parse_design_outline, read_design_outline


class DesignOutlineTests(unittest.TestCase):
    def test_helper_dimensions_and_nested_sketch(self):
        result = parse_design_outline('''
W = 70.6
WALL = 1.8
def rounded(w, h, r, depth):
    return bd.extrude(bd.RectangleRounded(w, h, r), amount=depth)
@step
def case():
    body = rounded(W + 2 * WALL, 150, 12, 10)
    body -= rounded(W, 146, 10, 8)
    return body
''')
        body, cut = result['features']
        self.assertEqual(body['type'], 'extrude')
        self.assertAlmostEqual(body['parameters'][0]['value'], 74.2)
        self.assertAlmostEqual(body['children'][0]['parameters'][0]['value'], 74.2)
        self.assertTrue(cut['label'].startswith('Cut Extrude'))

    def test_builder_sketch_is_nested_under_extrusion(self):
        result = parse_design_outline('''
with BuildPart() as part:
    with BuildSketch():
        Circle(3)
    extrude(amount=5)
''')
        self.assertEqual(len(result['features']), 1)
        self.assertEqual(result['features'][0]['children'][0]['type'], 'sketch')

    def test_controls_are_not_unrolled_or_treated_as_evaluated_values(self):
        result = parse_design_outline('''
x = 9
@step
def case():
    for x in range(3):
        Cylinder(x, 4)
    Cylinder(x, 5)
''')
        repeat, cylinder = result['features']
        self.assertEqual(repeat['label'], 'Repeat')
        self.assertEqual(len(repeat['children']), 1)
        self.assertIsNone(repeat['children'][0]['parameters'][0]['value'])
        self.assertIsNone(cylinder['parameters'][0]['value'])

    def test_dynamic_and_nonfinite_values_stay_expressions(self):
        result = parse_design_outline('''
x = 1e999
@step
def case():
    Cylinder(dangerous(), x)
''')
        self.assertEqual(result['parameters'], [])
        self.assertTrue(all(p['value'] is None for p in result['features'][0]['parameters']))

    def test_multiple_models_need_a_matching_name(self):
        source = '@step\ndef one():\n    Box(1,2,3)\n@step\ndef two():\n    Cylinder(4,5)\n'
        self.assertEqual(parse_design_outline(source)['status'], 'ambiguous')
        self.assertEqual(parse_design_outline(source, 'two')['features'][0]['type'], 'cylinder')

    def test_read_is_contained_and_never_runs_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp, 'models'); root.mkdir()
            step = root / 'case.step'; step.write_text('fixture')
            source = root / 'case.py'
            marker = root / 'executed'
            source.write_text(f"open({str(marker)!r}, 'w').write('bad')\n@step\ndef case():\n    Box(1,2,3)\n")
            before = (source.read_bytes(), step.read_bytes())
            result = read_design_outline(str(root), 'case.step')
            self.assertEqual(result['status'], 'ready')
            self.assertEqual(result['source'], 'case.py')
            self.assertFalse(marker.exists())
            self.assertEqual(before, (source.read_bytes(), step.read_bytes()))
            source.unlink()
            self.assertEqual(read_design_outline(str(root), 'case.step')['status'], 'unavailable')
            outside = Path(tmp, 'outside.py'); outside.write_text('Box(1,2,3)')
            source.symlink_to(outside)
            with self.assertRaises(Exception):
                read_design_outline(str(root), 'case.step')
            with self.assertRaises(Exception):
                read_design_outline(str(root), '../outside.step')

    def test_ambiguous_sources_and_oversize_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp, 'models'); root.mkdir()
            (root / 'case.step').write_text('fixture')
            (root / 'case.py').write_text('Box(1,2,3)')
            alternate = root / 'case.step.py'; alternate.write_text('Cylinder(1,2)')
            self.assertEqual(read_design_outline(str(root), 'case.step')['status'], 'ambiguous')
            alternate.unlink()
            (root / 'case.py').write_bytes(b'#' * (512 * 1024 + 1))
            with self.assertRaisesRegex(ValueError, '512 KB'):
                read_design_outline(str(root), 'case.step')
