"""Shared viewer fixtures carry valid geometry while seeding without a kernel."""
from __future__ import annotations
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock
from tests.python.support.tmp_root import generated_cad_directory

class SeedInputs(unittest.TestCase):
    def setUp(self):
        self.tmp = generated_cad_directory(prefix="store-seed-inputs-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        patch = mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(self.root / "store")})
        patch.start(); self.addCleanup(patch.stop)

    def test_seeding_geometry_hint_and_ready_surface_never_imports_native_modules(self):
        document = self.root / "part.step"; document.write_bytes(b"fixture")
        code = '''
import importlib.abc, sys
class NoNative(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'OCP', 'build123d'}:
            raise AssertionError('native import: ' + fullname)
sys.meta_path.insert(0, NoNative())
from tests.python.support.store_fixtures import seed_result, FIXTURE_SURFACE_PRODUCER
from cadgen.store.trees import capture_tree
from cadgen.store.surfaces import request_view, lookup
from cadgen.store.records import document_entry_for_hash
import hashlib
from pathlib import Path
path=Path(sys.argv[1]); tree=seed_result(path)
flat, objects=capture_tree(tree)
selected=document_entry_for_hash(hashlib.sha256(path.read_bytes()).hexdigest())
assert selected['surfaceProducer']==FIXTURE_SURFACE_PRODUCER
view=request_view(tree, producer=selected['surfaceProducer'])
assert all(lookup(entry,selected['surfaceProducer']) is not None for entry in flat['components'].values())
assert not any(name.split('.')[0] in {'OCP','build123d'} for name in sys.modules)
print('ok')
'''
        result = subprocess.run([sys.executable, "-c", code, str(document)], env=os.environ.copy(), text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.strip(), "ok")

    def test_seeded_component_and_surface_bytes_are_real_matching_native_inputs(self):
        from tests.python.support.store_fixtures import seed_result, FIXTURE_SURFACE_PRODUCER
        from cadgen.store.trees import capture_tree
        from cadgen.store.surfaces import lookup
        from cadgen.store.objects import read_verified_object
        from cadgen._internal.component_package import decode_geometry_component
        from cadgen._internal.surface_extract import extract_surface_component
        document = self.root / "parts.step"; document.write_bytes(b"fixture")
        tree = seed_result(document, components=("first", "second", "third", "fourth"))
        flat, objects = capture_tree(tree)
        volumes = []
        for entry in flat["components"].values():
            private = decode_geometry_component(entry, objects[entry["brep"]])
            volumes.append(round(private.volume, 8))
            record = lookup(entry, FIXTURE_SURFACE_PRODUCER)
            self.assertEqual(read_verified_object(record["object"]),
                             extract_surface_component(private.wrapped, face_colors={}))
        self.assertEqual(sorted(volumes), [6, 12, 18, 24])
        self.assertEqual(len(flat["occurrences"]), 4)

if __name__ == "__main__": unittest.main()
