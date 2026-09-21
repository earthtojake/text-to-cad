"""An accepted save owns its exact child revision through publication."""

from __future__ import annotations

import hashlib
import os
import shutil
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_repo_path
from tests.python.support.tmp_root import generated_cad_directory

add_repo_path("packages/cadgen/src")


class RetainedRevisionPublication(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = generated_cad_directory(prefix="retained-revision-")
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name).resolve()
        self.store = self.root / "store"
        self._environment = mock.patch.dict(
            os.environ,
            {
                "CADGEN_CACHE_DIR": str(self.store),
                "CADGEN_COMPONENT_WORKERS": "1",
                "CADGEN_DAEMON": "0",
            },
        )
        self._environment.start()
        self.addCleanup(self._environment.stop)

        from build123d import Box, Cylinder
        from cadgen.store.build import build_tree_from_compound
        from cadgen.store.records import write_record

        self.child_model = self.root / "child.py"
        self.child_model.write_text("# synthetic child identity\n", encoding="utf-8")
        self.old_tree, _tree, _stats = build_tree_from_compound(
            Box(2, 3, 4), root_name="child"
        )
        self.new_tree, _tree, _stats = build_tree_from_compound(
            Cylinder(1, 9), root_name="child"
        )
        write_record(
            self.child_model,
            {"tree": self.old_tree, "closure": {"hash": "", "files": []}, "children": [], "outputs": {}},
        )

    def _publication(self):
        import build123d as bd

        from cadgen._internal.generation_spec import EntrySpec
        from cadgen._internal.step_scene import LoadedStepScene
        from cadgen.metadata import GeneratorMetadata
        from cadgen.step_export import export_build123d_step_file
        from cadgen.store.materialize import materialize

        target = self.root / "parent.step"
        export_build123d_step_file(bd.Sphere(1), target)
        original_pair = (target.read_bytes(), None)
        script = self.root / "parent.py"
        script.write_text("# synthetic parent identity\n", encoding="utf-8")
        metadata = GeneratorMetadata(
            script_path=script,
            display_name="parent",
            generator_names=("parent",),
            format="step",
            mesh_tolerance=None,
            mesh_angular_tolerance=None,
            entry_function="parent",
            is_decorated=True,
        )
        spec = EntrySpec(
            source_ref="parent.py",
            cad_ref="parent.step",
            source_path=script,
            display_name="parent",
            source="generated",
            step_path=target,
            script_path=script,
            generator_metadata=metadata,
        )
        pinned = materialize(self.old_tree, label="child")
        pinned.label = "pinned_child"
        parent = bd.Compound(children=[pinned], label="parent")
        scene = LoadedStepScene(
            step_path=target,
            roots=[],
            prototype_shapes={},
            source_kind="step",
            reemit_source_hash=hashlib.sha256(b"immutable source revision").hexdigest(),
            reemit_annotation_hash=hashlib.sha256(b"no annotation").hexdigest(),
        )
        scene.source_compound = parent
        scene.store_children = [{"model": str(self.child_model), "tree": self.old_tree}]
        return spec, scene, target, original_pair, float(parent.volume)

    def _run_with_preview_fault(self, fault):
        import build123d as bd

        from cadgen._internal import generation
        from cadgen.daemon import executors
        from cadgen.store import build as store_build

        spec, scene, target, original_pair, pinned_volume = self._publication()
        expected_pair = (hashlib.sha256(original_pair[0]).hexdigest(), None)
        real_build = store_build.build_tree_through_step
        observed = {}

        def injecting_build(*args, **kwargs):
            publish = kwargs.get("on_preview")

            def inject(preview_hash, preview_tree):
                if publish is not None:
                    publish(preview_hash, preview_tree)
                fault()

            kwargs["on_preview"] = inject
            result = real_build(*args, **kwargs)
            observed["stagedVolume"] = float(bd.import_step(Path(args[1])).volume)
            observed["tree"] = result[0]
            return result

        executors.set_event_sink(lambda _event: None)
        self.addCleanup(executors.set_event_sink, None)
        with mock.patch.object(store_build, "build_tree_through_step", side_effect=injecting_build):
            result = generation._generate_part_outputs(
                spec,
                entries_by_step_path={target: spec},
                preloaded_scene=scene,
                require_step_file=False,
                force=True,
                expected_document_pair=expected_pair,
            )
        return result, target, original_pair, pinned_volume, observed, spec

    def test_newer_child_record_and_normal_gc_do_not_change_the_pinned_save(self) -> None:
        from cadgen.store.gc import collect
        from cadgen.store.index import model_ref
        from cadgen.store.records import read_record, write_record
        from cadgen.store.trees import get_tree, tree_complete

        gc_reports = []

        def publish_new_child_and_collect():
            record = read_record(self.child_model)
            self.assertIsNotNone(record)
            write_record(self.child_model, {**record, "tree": self.new_tree})
            gc_reports.append(collect())

        _result, target, original_pair, pinned_volume, observed, spec = self._run_with_preview_fault(
            publish_new_child_and_collect
        )

        parent_record = read_record(model_ref(spec.script_path, "parent"))
        self.assertEqual(read_record(self.child_model)["tree"], self.new_tree)
        self.assertEqual(parent_record["children"], [{"model": str(self.child_model), "tree": self.old_tree}])
        self.assertEqual(get_tree(parent_record["tree"])["links"][0]["tree"], self.old_tree)
        self.assertTrue(tree_complete(parent_record["tree"]))
        self.assertEqual(gc_reports[0].removed, 0)
        self.assertAlmostEqual(observed["stagedVolume"], pinned_volume, places=5)
        self.assertNotEqual(target.read_bytes(), original_pair[0])

    def _assert_deletion_fails_before_named_replacement(self, delete):
        from cadgen._internal import generation
        from cadgen.store.records import read_record, write_record

        def replace_child_then_delete():
            record = read_record(self.child_model)
            write_record(self.child_model, {**record, "tree": self.new_tree})
            delete()

        spec, scene, target, original_pair, pinned_volume = self._publication()
        expected_pair = (hashlib.sha256(original_pair[0]).hexdigest(), None)
        from cadgen.daemon import executors
        from cadgen.store import build as store_build
        import build123d as bd

        real_build = store_build.build_tree_through_step
        observed = {}

        def injecting_build(*args, **kwargs):
            publish = kwargs.get("on_preview")

            def inject(preview_hash, preview_tree):
                if publish is not None:
                    publish(preview_hash, preview_tree)
                replace_child_then_delete()

            kwargs["on_preview"] = inject
            result = real_build(*args, **kwargs)
            observed["stagedVolume"] = float(bd.import_step(Path(args[1])).volume)
            return result

        executors.set_event_sink(lambda _event: None)
        self.addCleanup(executors.set_event_sink, None)
        with mock.patch.object(store_build, "build_tree_through_step", side_effect=injecting_build):
            with self.assertRaisesRegex(RuntimeError, "pinned geometry disappeared"):
                generation._generate_part_outputs(
                    spec,
                    entries_by_step_path={target: spec},
                    preloaded_scene=scene,
                    require_step_file=False,
                    force=True,
                    expected_document_pair=expected_pair,
                )

        self.assertAlmostEqual(observed["stagedVolume"], pinned_volume, places=5)
        self.assertEqual(target.read_bytes(), original_pair[0])

    def test_missing_pinned_child_fails_before_replacing_the_saved_document(self) -> None:
        from cadgen.store.objects import object_path

        self._assert_deletion_fails_before_named_replacement(lambda: object_path(self.old_tree).unlink())

    def test_whole_store_deletion_fails_before_replacing_the_saved_document(self) -> None:
        self._assert_deletion_fails_before_named_replacement(lambda: shutil.rmtree(self.store))


if __name__ == "__main__":
    unittest.main()
