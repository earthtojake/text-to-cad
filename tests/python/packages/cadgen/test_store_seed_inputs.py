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

    def test_seeding_geometry_a_hint_and_its_parts_never_imports_native_modules(self):
        document = self.root / "part.step"; document.write_bytes(b"fixture")
        code = '''
import importlib.abc, sys
class NoNative(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'OCP', 'build123d'}:
            raise AssertionError('native import: ' + fullname)
sys.meta_path.insert(0, NoNative())
from tests.python.support.store_fixtures import seed_result, FIXTURE_PRODUCER
from cadgen.store.trees import capture_tree
from cadgen.store.view import descriptor_for_view, stored_parts
from cadgen.store.records import document_entry_for_hash
import hashlib
from pathlib import Path
path=Path(sys.argv[1]); tree=seed_result(path)
flat, objects=capture_tree(tree)
document=hashlib.sha256(path.read_bytes()).hexdigest()
assert document_entry_for_hash(document)['producer']==FIXTURE_PRODUCER
view=descriptor_for_view(tree, document_hash=document)
assert set(stored_parts(view))==set(flat['components'])
assert not any(name.split('.')[0] in {'OCP','build123d'} for name in sys.modules)
print('ok')
'''
        result = subprocess.run([sys.executable, "-c", code, str(document)], env=os.environ.copy(), text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.strip(), "ok")

    def test_seeded_parts_are_what_derivation_makes_of_the_seeded_geometry(self):
        from tests.python.support.store_fixtures import seed_result, FIXTURE_PRODUCER
        from cadgen.store import parts
        from cadgen.store.index import remove_entry
        from cadgen.store.trees import capture_tree
        from cadgen._internal.component_package import decode_geometry_component
        document = self.root / "parts.step"; document.write_bytes(b"fixture")
        tree = seed_result(document, components=("first", "second", "third", "fourth"))
        flat, objects = capture_tree(tree)
        volumes = []
        for entry in flat["components"].values():
            volumes.append(round(decode_geometry_component(entry, objects[entry["brep"]]).volume, 8))
            key = parts.part_key(entry, FIXTURE_PRODUCER)
            seeded = parts.probe(key)
            remove_entry("part", key)
            # The record names both objects by content address: the same record is the same bytes.
            self.assertEqual(parts._derive(entry, key), seeded)
        self.assertEqual(sorted(volumes), [6, 12, 18, 24])
        self.assertEqual(len(flat["occurrences"]), 4)

if __name__ == "__main__": unittest.main()
