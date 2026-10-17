"""Native document operations read geometry, never display data: an inspection derives
nothing, and a compile or a re-emit -- a build -- derives its parts' display data once,
before it reports done."""
from __future__ import annotations

import builtins
import contextlib
import io
import os
from pathlib import Path
import shutil
import unittest
from unittest import mock

from tests.python.support.tmp_root import generated_cad_directory


class NativeDocumentDoors(unittest.TestCase):
    def setUp(self):
        temporary = generated_cad_directory(prefix="native-doors-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.store = self.root / "store"
        self.enterContext(mock.patch.dict(os.environ, {
            "CADGEN_CACHE_DIR": str(self.store), "CADGEN_DAEMON": "0",
            "CADGEN_COMPONENT_WORKERS": "1",
        }))
        from build123d import Solid
        from cadgen import step
        from cadgen.step_export import export_build123d_step_file

        self.document = self.root / "box.step"
        box = Solid.make_box(2, 3, 4)
        box.label = "colored box"
        box.cad_face_ordinal_colors = {1: (0.2, 0.4, 0.8, 1.0)}
        export_build123d_step_file(box, self.document)
        self.original = self.document.read_bytes()
        self.tree = step.compile(self.document).tree
        self.source = self.root / "unrelated.py"
        self.source.write_text("from cadgen import step\n@step\ndef unrelated():\n    raise AssertionError('never run')\n", encoding="utf-8")

    @contextlib.contextmanager
    def native_only(self):
        attempts = []
        original_open, original_io_open = builtins.open, io.open

        def guard(opener):
            def read(path, *args, **kwargs):
                if isinstance(path, (str, bytes, os.PathLike)) and os.fsdecode(path) == str(self.source):
                    attempts.append(str(path))
                    raise AssertionError("unrelated source read")
                return opener(path, *args, **kwargs)
            return read

        derived = sorted(path.name for path in (self.store / "index/part").glob("*"))
        from cadgen.daemon import artifacts

        def files_only(real, name):
            # A build's file is an export of its result, verified by a parse: pool jobs
            # that derive no display data.
            def call(request, **kwargs):
                if request.get("kind") not in ("export", "verify"):
                    raise AssertionError(f"native-only operation invoked {name}")
                return real(request, **kwargs)
            return call

        with contextlib.ExitStack() as stack:
            for name in ("submit_artifact", "resolve_artifact"):
                stack.enter_context(mock.patch.object(artifacts, name, side_effect=files_only(
                    getattr(artifacts, name), f"cadgen.daemon.artifacts.{name}")))
            for name in ("cadgen.store.parts._derive", "cadgen._internal.topology_extract.extract_topology_facts",
                         "cadgen.catalog.result_view_dir", "cadgen.store.view.export_view"):
                stack.enter_context(mock.patch(name, side_effect=AssertionError(f"native-only operation invoked {name}")))
            stack.enter_context(mock.patch("builtins.open", side_effect=guard(original_open)))
            stack.enter_context(mock.patch("io.open", side_effect=guard(original_io_open)))
            yield
        self.assertEqual(attempts, [], "a source scan swallowed the forbidden read")
        self.assertEqual(sorted(path.name for path in (self.store / "index/part").glob("*")), derived)
        self.assertEqual(self.document.read_bytes(), self.original)

    def test_the_compile_derived_the_display_data_of_every_part(self):
        import hashlib

        from cadgen.store import parts
        from cadgen.store.records import document_entry_for_hash
        from cadgen.store.trees import capture_tree

        producer = document_entry_for_hash(hashlib.sha256(self.original).hexdigest())["producer"]
        components = capture_tree(self.tree, retain_payloads=False)[0]["components"]
        self.assertTrue(components)
        for entry in components.values():
            self.assertIsNotNone(parts.probe(parts.part_key(entry, producer)))

    def test_scene_selectors_skip_display_and_unrelated_source(self):
        from cadgen import read_scene
        # An inspection never derives display data, even where the store has none.
        shutil.rmtree(self.store / "index/part")
        with self.native_only():
            scene = read_scene(self.document)
            self.assertAlmostEqual(scene.roots[0].shape().volume, 24)
            self.assertEqual(len(list(scene.roots[0].entities("face"))), 6)

    def test_compile_native_inspections_and_reemit_skip_display_and_unrelated_source(self):
        from cadgen import read_step, step
        from cadgen.geometry import topology_errors, overlap_volume
        from cadgen.store.trees import capture_tree

        closure = capture_tree(self.tree)[1]
        destination = self.root / "reemit.step"
        with self.native_only():
            self.assertEqual(step.compile(self.document, force=True).tree, self.tree)
            self.assertEqual(capture_tree(self.tree)[1], closure)
            self.assertAlmostEqual(read_step(self.document).volume, 24.0)
            body = read_step(self.document).solids()[0]
            self.assertEqual(topology_errors(body), ())
            self.assertAlmostEqual(overlap_volume(body, body), 24)
            first = step.build(self.document, destination)
            self.assertTrue(first.ok)
            output = destination.read_bytes()
            self.assertTrue(step.build(self.document, destination).skipped)
            self.assertTrue(step.build(self.document, destination, force=True).ok)
            self.assertEqual(destination.read_bytes(), output)
            self.assertEqual(capture_tree(self.tree)[1], closure)


if __name__ == "__main__":
    unittest.main()
