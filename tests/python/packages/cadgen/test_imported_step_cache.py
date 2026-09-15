"""Imported STEP reads publish once and always return the canonical tree scene."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_repo_path
from tests.python.support.tmp_root import generated_cad_directory

CADGEN_SRC = add_repo_path("packages/cadgen/src")


_READER = r"""
import json
import sys
from pathlib import Path

import cadgen._internal.step_scene_package as package

if sys.argv[2] == "forbid-text":
    def forbidden(*args, **kwargs):
        raise AssertionError("a canonical cache hit attempted a text STEP parse")
    package._load_step_scene_text = forbidden

from cadgen import load_step_scene
from cadgen.store import closure

document = Path(sys.argv[1]).resolve()
consumed = {}
closure.note_consumed_file_hash = lambda path, digest: consumed.setdefault(str(Path(path).resolve()), digest)
scene = load_step_scene(document)

def node(value):
    return {
        "name": value.name,
        "prototype": value.prototype_key is not None,
        "transform": [round(float(item), 8) for item in value.transform],
        "children": [node(child) for child in value.children],
    }

print(json.dumps({
    "hash": scene.step_hash,
    "consumedHash": consumed[str(document)],
    "roots": [node(root) for root in scene.roots],
    "prototypeNames": sorted(name or "" for name in scene.prototype_names.values()),
    "prototypeColors": sorted(
        [round(float(channel), 6) for channel in color]
        for color in scene.prototype_colors.values()
    ),
    "faceColorCounts": sorted(len(colors) for colors in scene.prototype_face_colors.values()),
}, sort_keys=True))
"""


class ImportedStepCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = generated_cad_directory(prefix="imported-step-cache-")
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name).resolve()
        self.store = self.root / "store"
        self.step_path = self.root / "vendor.step"
        self.sidecar_path = Path(str(self.step_path) + ".json")
        self._environment_patch = mock.patch.dict(
            os.environ,
            {
                "CADGEN_CACHE_DIR": str(self.store),
                "CADGEN_DAEMON": "0",
                "CADGEN_COMPONENT_WORKERS": "1",
            },
        )
        self._environment_patch.start()
        self.addCleanup(self._environment_patch.stop)
        self.environment = dict(os.environ)
        self.environment.update(
            {
                "CADGEN_CACHE_DIR": str(self.store),
                "CADGEN_DAEMON": "0",
                "CADGEN_COMPONENT_WORKERS": "1",
                "PYTHONPATH": str(CADGEN_SRC),
            }
        )

    def _write_fixture(self, path: Path | None = None, *, offset: float = 0.0) -> None:
        import build123d as bd

        from cadgen.step_export import export_build123d_step_file

        first = bd.Box(2, 3, 4)
        first.label = "colored_box"
        first.color = bd.Color(0.2, 0.4, 0.8)
        first.cad_face_ordinal_colors = {
            1: (1.0, 0.0, 0.0, 1.0),
            6: (0.0, 1.0, 0.0, 1.0),
        }
        second = bd.Pos(8 + offset, 2, 1) * bd.Cylinder(1, 5)
        second.label = "placed_pin"
        shape = bd.Compound(children=[first, second], label="vendor_assembly")
        export_build123d_step_file(shape, path or self.step_path)

    def _read_fresh_process(self, *, forbid_text: bool = False) -> dict:
        completed = subprocess.run(
            [
                sys.executable,
                "-c",
                _READER,
                str(self.step_path),
                "forbid-text" if forbid_text else "allow-text",
            ],
            cwd=str(self.root),
            env=self.environment,
            capture_output=True,
            text=True,
            timeout=180,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        return json.loads(completed.stdout)

    def test_fresh_process_hit_skips_text_parse_and_preserves_the_authored_pair(self) -> None:
        from cadgen.store.index import entry_path, model_key

        self._write_fixture()
        self.sidecar_path.write_bytes(b'{"authored":true}\n')
        authored_before = (self.step_path.read_bytes(), self.sidecar_path.read_bytes())

        cold = self._read_fresh_process()
        digest = hashlib.sha256(authored_before[0]).hexdigest()
        self.assertEqual(cold["hash"], digest)
        self.assertEqual(cold["consumedHash"], digest)
        self.assertEqual(len(cold["roots"]), 1)
        self.assertGreaterEqual(sum(cold["faceColorCounts"]), 2)

        # Artifact lookup is independent of the path-keyed producer record.
        entry_path("model", model_key(self.step_path)).unlink()
        warm = self._read_fresh_process(forbid_text=True)
        self.assertEqual(warm, cold)
        self.assertEqual((self.step_path.read_bytes(), self.sidecar_path.read_bytes()), authored_before)
        self.assertEqual(
            sorted(path.name for path in self.root.glob("*.step*")),
            ["vendor.step", "vendor.step.json"],
        )

    def test_an_incomplete_tree_is_recompiled_and_healed(self) -> None:
        from cadgen.store.objects import object_path
        from cadgen.store.records import tree_for_document_hash
        from cadgen.store.trees import get_tree, tree_complete

        self._write_fixture()
        first = self._read_fresh_process()
        tree_hash = tree_for_document_hash(first["hash"])
        self.assertTrue(tree_hash and tree_complete(tree_hash))
        tree = get_tree(tree_hash)
        self.assertIsInstance(tree, dict)
        victim = next(iter(tree["components"].values()))["brep"]
        object_path(victim).unlink()
        self.assertFalse(tree_complete(tree_hash))

        healed = self._read_fresh_process()
        self.assertEqual(healed, first)
        self.assertTrue(tree_complete(tree_hash))

    def test_snapshot_digest_and_closure_follow_the_bytes_parsed_during_replacement(self) -> None:
        from cadgen._internal import step_scene_package as package
        from cadgen.store.closure import ExecutionHashes, note_consumed_file_hash

        replacement = self.root / "replacement.step"
        self._write_fixture()
        self._write_fixture(replacement, offset=11.0)
        consumed = self.step_path.read_bytes()
        replacement_bytes = replacement.read_bytes()
        consumed_hash = hashlib.sha256(consumed).hexdigest()
        replacement_hash = hashlib.sha256(replacement_bytes).hexdigest()
        self.assertNotEqual(consumed_hash, replacement_hash)

        real_loader = package._load_step_scene_text

        def replace_then_parse(snapshot: Path, **kwargs):
            self.step_path.write_bytes(replacement_bytes)
            return real_loader(snapshot, **kwargs)

        with mock.patch.object(package, "_load_step_scene_text", side_effect=replace_then_parse):
            scene = package.load_step_scene_exact(self.step_path)
        self.assertEqual(scene.step_hash, consumed_hash)
        self.assertEqual(hashlib.sha256(self.step_path.read_bytes()).hexdigest(), replacement_hash)

        # The exact-value hook wins over the normal after-body path hash.
        with ExecutionHashes() as hashes:
            note_consumed_file_hash(self.step_path, consumed_hash)
            hashes.note(self.step_path)
        self.assertEqual(hashes.hashes[str(self.step_path)], consumed_hash)

    def test_nested_import_compile_yields_a_single_worker_slot(self) -> None:
        self._write_fixture()
        model = self.root / "wrapper.py"
        model.write_text(
            textwrap.dedent(
                """
                from pathlib import Path
                from cadgen import read_step, step

                @step
                def wrapper():
                    return read_step(Path(__file__).with_name("vendor.step"))

                if __name__ == "__main__":
                    wrapper()
                """
            ).lstrip(),
            encoding="utf-8",
        )
        environment = dict(self.environment)
        environment["CADGEN_JOBS"] = "1"
        completed = subprocess.run(
            [sys.executable, str(model)],
            cwd=str(self.root),
            env=environment,
            capture_output=True,
            text=True,
            timeout=180,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)


if __name__ == "__main__":
    unittest.main()
