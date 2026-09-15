"""Reference composition preserves eager bytes, native semantics, and pins."""

from __future__ import annotations

import copy
import contextlib
import importlib
import io
import os
import pickle
import subprocess
import sys
from pathlib import Path
import unittest
from unittest import mock

from tests.python.support.tmp_root import generated_cad_directory

import build123d as bd
from cadgen.authoring import building
from cadgen.store import _references
from cadgen.store.build import build_tree_from_compound, build_tree_through_step
from cadgen.store.lazy import ChildBuildError, LazyCompound
from cadgen.store.materialize import materialize, reset_memo
from cadgen.store.objects import object_path, put_object
from cadgen.store.trees import get_tree

lazy_module = importlib.import_module("cadgen.store.lazy")


class Job:
    result_ready = True

    def __init__(self, tree, callback=None, failure=None):
        self.tree, self.callback, self.failure = tree, callback, failure
        self.calls = 0

    def wait_result(self):
        self.calls += 1
        if self.callback:
            self.callback()
        if self.failure:
            raise RuntimeError(self.failure)
        return self.tree


class ReferenceAssemblies(unittest.TestCase):
    def setUp(self):
        self.scratch = generated_cad_directory(prefix="reference-assembly-")
        self.addCleanup(self.scratch.cleanup)
        self.root = Path(self.scratch.name)
        patch = mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(self.root / "store"),
                                            "CADGEN_DAEMON": "0", "CADGEN_JOBS": "1"})
        patch.start()
        self.addCleanup(patch.stop)
        reset_memo()
        self.addCleanup(reset_memo)
        self._box_tree = None
        self._curved_tree = None

    @property
    def box_tree(self):
        if self._box_tree is None:
            self._box_tree = build_tree_from_compound(
                bd.Solid.make_box(2, 3, 4), root_name="box"
            )[0]
        return self._box_tree

    @property
    def curved_tree(self):
        if self._curved_tree is not None:
            return self._curved_tree
        placed = bd.Solid.make_torus(7, 1).moved(bd.Location((2, 3, 5), (13, 27, 39)))
        placed.color = "red"
        self._curved_tree = build_tree_from_compound(
            placed,
            root_name="curved",
            materials={
                "definitions": {"finish": {"name": "Finish", "roughness": 0.3}},
                "assignments": [{"targets": ["#o1"], "material": "finish"}],
            },
        )[0]
        return self._curved_tree

    def child(self, frame, index, tree=None, job=None):
        return LazyCompound(self.root / f"child{index}.py", job, frame=frame,
                            label=f"child{index}", tree=tree if job is None else None)

    def assembly(self, frame, *, varied=False):
        a = self.child(frame, 1, self.curved_tree if varied else self.box_tree)
        b = self.child(frame, 2, self.box_tree)
        a = a.moved(bd.Location((7, 11, 13), (17, 31, 43)))
        b = b.moved(bd.Location((-7, 2, 8), (5, 19, 37)))
        a.label = ""
        result = bd.Compound(children=[a, b], label="assembly", color="blue")
        return result, (a, b)

    def test_constructor_and_publication_avoid_child_native_materialization(self):
        with building(None) as frame, mock.patch.object(
            lazy_module, "_materialize_tree", wraps=lazy_module._materialize_tree
        ) as reconstruct:
            result, children = self.assembly(frame)
            self.assertIs(type(result), _references._ReferenceCompound)
            self.assertTrue(all(child.parent is result for child in children))
            self.assertTrue(all(not child._forced for child in children))
            tree, descriptor, _, _ = build_tree_through_step(
                result, self.root / "assembly.step", root_name="assembly",
                _internal_source_publication=True,
            )
            self.assertEqual(reconstruct.call_count, 0)
            self.assertEqual(len(descriptor["links"]), 2)
            self.assertAlmostEqual(materialize(tree).volume, 48)

    def test_cold_warm_disabled_and_forced_save_have_identical_tree_and_step_bytes(self):
        results = []
        for mode in ("cold", "warm", "disabled", "forced"):
            if mode in ("cold", "disabled"):
                reset_memo()
            with self.subTest(mode=mode), mock.patch.object(_references, "_ENABLED", mode != "disabled"):
                with building(None) as frame:
                    shape, _ = self.assembly(frame, varied=True)
                    out = self.root / "assembly.step"
                    tree, descriptor, _, _ = build_tree_through_step(
                        shape, out, root_name="assembly", force=mode == "forced",
                        _internal_source_publication=True,
                    )
                    results.append((tree, descriptor, out.read_bytes()))
        for result in results[1:]:
            self.assertEqual(result, results[0])

    def test_parent_color_edit_keeps_color_inherited_at_attachment(self):
        rows = []
        for enabled in (False, True):
            with mock.patch.object(_references, "_ENABLED", enabled), building(None) as frame:
                shape, children = self.assembly(frame, varied=True)
                shape.color = "green"
                rows.append(build_tree_from_compound(shape, root_name="assembly")[1])
                self.assertEqual(tuple(children[0].color), tuple(bd.Color("blue")))
        self.assertEqual(rows[0], rows[1])

    def test_mutating_original_location_after_attachment_does_not_move_child(self):
        rows = []
        for enabled in (False, True):
            with mock.patch.object(_references, "_ENABLED", enabled), building(None) as frame:
                location = bd.Location((7, 11, 13), (17, 31, 43))
                a = self.child(frame, 1, self.curved_tree).moved(location)
                b = self.child(frame, 2, self.box_tree)
                shape = bd.Compound(children=[a, b])
                location.wrapped.Clear()
                rows.append(build_tree_from_compound(shape, root_name="assembly")[1])
        self.assertEqual(rows[0], rows[1])

    def test_native_reads_and_copies_promote_to_ordinary_compound(self):
        for name, read in (
            ("wrapped", lambda shape: shape.wrapped),
            ("private_wrapped", lambda shape: shape._wrapped),
            ("truth", bool),
            ("faces", lambda shape: shape.faces()),
            ("bbox", lambda shape: shape.bounding_box()),
            ("copy", copy.copy),
            ("deepcopy", copy.deepcopy),
            ("move", lambda shape: shape.moved(bd.Location((1, 2, 3)))),
        ):
            with self.subTest(name=name), building(None) as frame:
                result, children = self.assembly(frame)
                read(result)
                self.assertIs(type(result), bd.Compound)
                self.assertTrue(all(child._forced for child in children))
                self.assertAlmostEqual(result.volume, 48)
        with building(None) as frame:
            result, _ = self.assembly(frame)
            try:
                pickle.dumps(result)
            except (TypeError, pickle.PicklingError):
                pass  # ordinary OCCT wrappers are not picklable
            self.assertIs(type(result), bd.Compound)

    def test_native_assignment_never_keeps_reference_identity(self):
        for name in ("wrapped", "_wrapped"):
            with self.subTest(name=name), building(None) as frame:
                result, _ = self.assembly(frame)
                replacement = bd.Compound([bd.Solid.make_box(1, 1, 1)])
                setattr(result, name, replacement.wrapped)
                self.assertIs(type(result), bd.Compound)
                self.assertIsNone(_references.links(result))
                self.assertAlmostEqual(result.volume, 1)

    def test_child_move_after_attachment_preserves_shared_native_mutation(self):
        from OCP.BRep import BRep_Builder
        from OCP.gp import gp_Pnt

        with building(None) as frame:
            _, children = self.assembly(frame)
            original = children[0]
            moved = original.moved(bd.Location())
            self.assertTrue(original._forced)
            self.assertTrue(original.wrapped.IsPartner(moved.wrapped))
            point = original.vertices()[0]
            BRep_Builder().UpdateVertex(point.wrapped, gp_Pnt(123, 456, 789), 1e-7)
            self.assertEqual(tuple(moved.vertices()[0].center()), tuple(point.center()))

    def test_child_native_replacement_and_location_keep_captured_parent_geometry(self):
        for change in ("wrapped", "_wrapped", "location", "children", "plain_parent"):
            rows = []
            for enabled in (False, True):
                with self.subTest(change=change, enabled=enabled), \
                        mock.patch.object(_references, "_ENABLED", enabled), building(None) as frame:
                    result, children = self.assembly(frame)
                    child = children[0]
                    if change in ("wrapped", "_wrapped"):
                        setattr(child, change, bd.Compound([bd.Solid.make_box(1, 1, 1)]).wrapped)
                    elif change == "location":
                        child.wrapped.Location(bd.Location((100, 200, 300)).wrapped)
                    elif change == "children":
                        child.children = [bd.Solid.make_box(1, 1, 1)]
                    else:
                        bd.Solid.make_box(1, 1, 1).parent = child
                    self.assertIs(type(result), bd.Compound)
                    bounds = result.bounding_box()
                    rows.append((result.volume, tuple(bounds.min), tuple(bounds.max), child.volume,
                                 tuple(item.volume for item in child.children)))
            self.assertEqual(rows[0], rows[1])

    def test_malicious_native_vertex_and_container_changes_do_not_reuse_pins(self):
        from OCP.BRep import BRep_Builder
        from OCP.gp import gp_Pnt

        with building(None) as frame:
            result, children = self.assembly(frame)
            vertex = children[0].vertices()[0]
            BRep_Builder().UpdateVertex(vertex.wrapped, gp_Pnt(123, 456, 789), 1e-7)
            self.assertIsNone(_references.links(result))
            from cadgen.store.build import _tagged_intact
            self.assertIsNone(_tagged_intact(children[0]))
            clean = materialize(self.box_tree)
            self.assertAlmostEqual(clean.volume, 24)
        with building(None) as frame:
            result, children = self.assembly(frame)
            native = result.wrapped
            BRep_Builder().Remove(native, children[0].wrapped)
            self.assertIsNone(_references.links(result))
            self.assertAlmostEqual(result.volume, 24)

    def test_hierarchy_edits_preserve_ordinary_child_ownership(self):
        for action in ("replace", "delete", "detach", "reparent"):
            with self.subTest(action=action), building(None) as frame:
                result, children = self.assembly(frame)
                if action == "replace":
                    result.children = [children[0]]
                elif action == "delete":
                    del result.children
                elif action == "detach":
                    children[0].parent = None
                else:
                    children[0].parent = bd.Compound()
                self.assertIs(type(result), bd.Compound)
                self.assertIsNone(_references.links(result))

    def test_material_overrides_and_forced_children_use_ordinary_construction(self):
        for mode in ("material", "faces", "forced"):
            with self.subTest(mode=mode), building(None) as frame:
                a, b = self.child(frame, 1, self.box_tree), self.child(frame, 2, self.box_tree)
                if mode == "material":
                    # Private restored metadata mutation still forces ordinary
                    # construction; public authors use @step(materials=...).
                    a._cadgen_material = {"name": "Override", "roughness": 0.7}
                    a._cadgen_material_id = "override"
                elif mode == "faces":
                    a.cad_face_ordinal_colors = {1: (1, 0, 0, 1)}
                else:
                    a.faces()
                shape = bd.Compound(children=[a, b])
                self.assertIs(type(shape), bd.Compound)
                self.assertTrue(a._forced and b._forced)

    def test_exact_pins_survive_source_edit_and_later_job_variant(self):
        with building(None) as frame:
            first = self.child(frame, 1, job=Job(self.box_tree))
            later = self.child(frame, 1, job=Job(self.curved_tree))
            first = first.moved(bd.Location((5, 0, 0)))
            later = later.moved(bd.Location((-5, 0, 0)))
            shape = bd.Compound(children=[first, later])
            (self.root / "child1.py").write_text("raise RuntimeError('new source')\n", encoding="utf-8")
            with mock.patch("cadgen.store.records.read_record", side_effect=AssertionError("latest record")):
                _, descriptor, _ = build_tree_from_compound(shape, root_name="assembly")
            self.assertEqual([row["tree"] for row in descriptor["links"]], [self.box_tree] * 2)

    def test_missing_and_corrupt_entries_are_not_hidden_and_repair_recovers(self):
        digest = next(iter(get_tree(self.box_tree)["components"].values()))["brep"]
        target = object_path(digest)
        payload = target.read_bytes()
        for corrupt in (False, True):
            with self.subTest(corrupt=corrupt), building(None) as frame:
                shape, _ = self.assembly(frame)
                target.write_bytes(b"corrupt") if corrupt else target.unlink()
                with self.assertRaisesRegex(ChildBuildError, "disappeared"):
                    build_tree_from_compound(shape, root_name="assembly")
                put_object(payload, repair=True)
                tree = build_tree_from_compound(shape, root_name="assembly")[0]
                self.assertAlmostEqual(materialize(tree).volume, 48)

    def test_failed_child_is_reported_in_original_attach_order(self):
        for enabled in (False, True):
            with self.subTest(enabled=enabled), mock.patch.object(_references, "_ENABLED", enabled), building(None) as frame:
                calls = []
                first = self.child(frame, 1, job=Job(self.box_tree, lambda: calls.append("first"), "failure"))
                later = self.child(frame, 2, job=Job(self.curved_tree, lambda: calls.append("later")))
                with self.assertRaisesRegex(ChildBuildError, "failure"):
                    bd.Compound(children=[first, later])
                self.assertEqual(calls, ["first"])

    def test_repeated_face_color_variants_remain_distinct(self):
        entries = []
        for color in ((1, 0, 0, 1), (0, 0, 1, 1)):
            solid = bd.Solid.make_box(2, 3, 4)
            solid.cad_face_ordinal_colors = {1: color}
            entries.append(build_tree_from_compound(solid, root_name="box")[0])
        results = []
        for enabled in (False, True):
            with mock.patch.object(_references, "_ENABLED", enabled), building(None) as frame:
                children = [self.child(frame, index, tree) for index, tree in enumerate(entries)]
                children[1] = children[1].moved(bd.Location((8, 0, 0)))
                shape = bd.Compound(children=children, label="variants")
                out = self.root / "variants.step"
                result = build_tree_through_step(shape, out, root_name="variants", _internal_source_publication=True)
                results.append((result[0], result[1], out.read_bytes()))
        self.assertEqual(results[0], results[1])

    def test_direct_plain_shape_parent_edit_keeps_native_and_wrapper_semantics(self):
        results = []
        for enabled in (False, True):
            with mock.patch.object(_references, "_ENABLED", enabled), building(None) as frame:
                shape, _ = self.assembly(frame)
                extra = bd.Solid.make_box(1, 1, 1)
                extra.parent = shape
                self.assertIsNone(_references.links(shape))
                volume = shape.volume
                results.append((volume, build_tree_from_compound(shape, root_name="assembly")[1]))
        self.assertEqual(results[0], results[1])

    def test_source_scene_matches_eager_adaptive_hints_and_nested_appearance(self):
        from cadgen.step_export import build_build123d_step_scene
        from cadgen._internal.step_scene_mesh import _scene_mesh_resolution_hints, scene_leaf_occurrences

        red, blue = bd.Solid.make_box(3, 4, 5), bd.Solid.make_torus(7, 1)
        red.label, red.color = "red", "red"
        blue.label, blue.color = "blue", "blue"
        nested_tree = build_tree_from_compound(bd.Compound(children=[
            bd.Compound(children=[red], label="group"),
            blue.moved(bd.Location((20, 0, 0), (13, 21, 34))),
        ], label="nested"), root_name="nested")[0]
        with building(None) as frame:
            children = [self.child(frame, i, nested_tree).moved(bd.Location((i * 30, 0, 0), (5, 9, 17)))
                        for i in range(3)]
            shape = bd.Compound(children=children, label="nested", color="green")
        fast = _references.source_scene(shape, self.root / "nested.step")
        self.assertIsNotNone(fast)
        self.assertTrue(all(not child._forced for child in children))
        eager = build_build123d_step_scene(shape, self.root / "nested.step")
        self.assertEqual(_scene_mesh_resolution_hints(fast), _scene_mesh_resolution_hints(eager))

        def rows(scene):
            return [(node.path, node.name, tuple(round(v, 12) for v in node.transform), node.color)
                    for node in scene_leaf_occurrences(scene)]
        self.assertEqual(rows(fast), rows(eager))

    def test_reference_scene_opt_in_does_not_change_native_generator_reader(self):
        from cadgen._internal.generation_runner import _write_shape_step_payload
        from cadgen.cli_logging import CliLogger

        script = self.root / "assembly.py"
        script.write_text("# source identity\n", encoding="utf-8")
        for enabled in (False, True):
            with self.subTest(enabled=enabled), building(None) as frame:
                shape, children = self.assembly(frame)
            scene = _write_shape_step_payload({"shape": shape}, output_path=self.root / "assembly.step",
                                              script_path=script, logger=CliLogger("test"),
                                              defer_reference_scene=enabled)
            self.assertTrue(scene.roots and scene.prototype_shapes)
            self.assertEqual(all(not child._forced for child in children), enabled)
            self.assertEqual(scene.source_kind, "python")

    def test_queued_child_resolution_keeps_order_and_yields_without_native_work(self):
        first_job, second_job = Job(self.box_tree), Job(self.curved_tree)
        first_job.result_ready = second_job.result_ready = False
        events = []
        first_job.callback, second_job.callback = lambda: events.append(1), lambda: events.append(2)
        with building(None) as frame, mock.patch("cadgen.daemon.broker.yielded", return_value=contextlib.nullcontext()) as yields:
            children = [self.child(frame, 1, job=first_job), self.child(frame, 2, job=second_job)]
            shape = bd.Compound(children=children)
            self.assertIs(type(shape), _references._ReferenceCompound)
            self.assertEqual(events, [1, 2])
            self.assertEqual(yields.call_count, 2)
            self.assertTrue(all(not child._forced for child in children))

    def test_public_decorated_builds_and_fresh_worker_keep_exact_outputs(self):
        from cadgen.cli._run_model import run_model_argv
        from cadgen.store.records import read_record, remove_record
        from cadgen._internal import generation_runner

        for name, geometry in (("box", "bd.Solid.make_box(2, 3, 4)"),
                               ("curve", "bd.Solid.make_torus(7, 1)")):
            (self.root / f"{name}.py").write_text(
                "from cadgen import step, build123d as bd\n"
                "@step(materials={'definitions': {'finish': {'name': 'Finish', 'roughness': .3}}, "
                "'assignments': [{'targets': ['#o1'], 'material': 'finish'}]})\n"
                f"def {name}():\n    return {geometry}\n",
                encoding="utf-8",
            )
        parent = self.root / "parent.py"
        parent.write_text(
            "from cadgen import step, build123d as bd\nfrom box import box\nfrom curve import curve\n"
            "@step(mesh_tolerance=.001, mesh_angular_tolerance=.07)\ndef parent():\n"
            "    return bd.Compound(children=[bd.Pos(5, 0, 0) * box(), bd.Pos(-5, 0, 0) * curve()], label='assembly')\n",
            encoding="utf-8",
        )
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            for name in ("box", "curve"):
                self.assertEqual(run_model_argv([str(self.root / f"{name}.py"), "--json"]), 0, output.getvalue())
        results = []
        for enabled in (False, True):
            remove_record(parent)
            with mock.patch.object(_references, "_ENABLED", enabled), \
                    mock.patch.object(generation_runner, "build_build123d_step_scene", wraps=generation_runner.build_build123d_step_scene) as xcaf, \
                    mock.patch.object(lazy_module, "_materialize_tree", wraps=lazy_module._materialize_tree) as reconstructed, \
                    contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                self.assertEqual(run_model_argv([str(parent), "--json"]), 0, output.getvalue())
                self.assertEqual(xcaf.call_count, 0 if enabled else 1)
                self.assertEqual(reconstructed.call_count, 0 if enabled else 2)
            results.append((read_record(parent)["tree"], (self.root / "parent.step").read_bytes(),
                            (self.root / "parent.step.json").read_bytes()))
        self.assertEqual(results[0], results[1])
        remove_record(parent)
        command = ("from cadgen.cli._run_model import run_model_argv; import sys; "
                   "raise SystemExit(run_model_argv([sys.argv[1], '--json']))")
        finished = subprocess.run([sys.executable, "-c", command, str(parent)],
                                  capture_output=True, text=True, timeout=30)
        self.assertEqual(finished.returncode, 0, finished.stderr + finished.stdout)
        restarted = (read_record(parent)["tree"], (self.root / "parent.step").read_bytes(),
                     (self.root / "parent.step.json").read_bytes())
        self.assertEqual(restarted, results[0])


if __name__ == "__main__":
    unittest.main()
