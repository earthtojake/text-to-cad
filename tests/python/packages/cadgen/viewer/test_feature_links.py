import hashlib
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from cadgen.feature_links import FeatureTrace, publish_links, read_links

SOURCE = '''from cadgen import build123d as bd

def part():
    body = bd.Box(40, 30, 8)
    tool = bd.Cylinder(3, 20)
    body -= bd.Pos(10, 0, 0) * tool
    for x in (-10, -5):
        body -= bd.Pos(x, 0, 0) * bd.Cylinder(1, 20)
    return body
'''

class FeatureLinksTests(unittest.TestCase):
    def test_translated_tool_repeat_and_geometry_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp, 'models', 'part.py'); source.parent.mkdir(); source.write_text(SOURCE, encoding="utf-8")
            spec = importlib.util.spec_from_file_location('feature_fixture', source)
            module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
            baseline = module.part()
            with FeatureTrace(source, 'part') as trace:
                shape = module.part()
            self.assertIsNone(sys.gettrace())
            self.assertAlmostEqual(shape.volume, baseline.volume)
            links = trace.finish(shape)
            self.assertIsNotNone(links)
            self.assertEqual(len(links['lines']['4']), 6)
            self.assertEqual(len(links['lines']['6']), 1)
            self.assertEqual(links['lines']['5'], links['lines']['6'])
            tool_face = links['faces'][links['lines']['5'][0]]
            self.assertAlmostEqual(tool_face['center'][0], 10)
            self.assertEqual(len(links['lines']['8']), 2)
            self.assertFalse(set(links['lines']['6']) & set(links['lines']['8']))

    def test_cache_requires_exact_source_and_step_bytes(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'CADGEN_CACHE_DIR':tmp}):
            models = Path(tmp, 'models'); models.mkdir()
            source = models / 'part.py'; source.write_text(SOURCE, encoding="utf-8")
            document = models / 'part.step'; document.write_text('test artifact', encoding="utf-8")
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            links = {'schema':1,'sourceHash':digest,'faces':[], 'lines':{}}
            publish_links(source,document,links)
            self.assertEqual(read_links(digest,document),links)
            source.write_text(SOURCE+'\n', encoding="utf-8")
            self.assertIsNone(read_links(hashlib.sha256(source.read_bytes()).hexdigest(),document))
            document.write_text('changed artifact', encoding="utf-8")
            self.assertIsNone(read_links(digest,document))
            publish_links(source,document,links)
            self.assertIsNone(read_links(digest,document))

    def test_mismatched_loaded_source_and_existing_debugger_disable_capture(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp,'part.py'); source.write_text(SOURCE, encoding="utf-8")
            with FeatureTrace(source,'part',source_hash='wrong') as trace:
                self.assertFalse(trace.active)
            previous = sys.gettrace()
            debugger = lambda *_: None
            try:
                sys.settrace(debugger)
                with FeatureTrace(source,'part') as trace:
                    self.assertFalse(trace.active)
                self.assertIs(sys.gettrace(),debugger)
            finally:
                sys.settrace(previous)

    def test_named_assembly_uses_consumed_placements_and_combines_repeats(self):
        source_text = """from cadgen import build123d as bd

def assembly():
    parts = []
    wing = bd.Box(10, 2, 1)
    placed = bd.Pos(20, 0, 0) * wing
    placed.label = 'wing'
    parts.append(placed)
    for x in (-5, 5):
        part = bd.Pos(x, 0, 0) * bd.Box(1, 1, 1)
        part.label = f'part_{x}'
        parts.append(part)
    return bd.Compound(children=parts)
"""
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp, 'models', 'assembly.py'); source.parent.mkdir(); source.write_text(source_text, encoding="utf-8")
            spec = importlib.util.spec_from_file_location('assembly_fixture', source)
            module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
            with FeatureTrace(source, 'assembly') as trace:
                shape = module.assembly()
            links = trace.finish(shape)
            self.assertIsNotNone(links)
            self.assertEqual(len(links['parts']), 3)
            self.assertEqual(links['partLines']['5'], links['partLines']['8'])
            wing = links['parts'][links['partLines']['5'][0]]
            self.assertEqual(wing['name'], 'wing')
            self.assertAlmostEqual(wing['bbox']['min'][0], 15, places=5)
            self.assertEqual(len(links['partLines']['10']), 2)
