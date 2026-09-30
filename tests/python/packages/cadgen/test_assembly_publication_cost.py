"""A parent's document preparation, bounds and read-back pay per prototype, not per
occurrence — and byte-identical outputs prove it changed nothing else."""
from __future__ import annotations

import gc
import hashlib
import importlib
import os
from pathlib import Path
import unittest
from unittest import mock
import weakref

from tests.python.support.paths import add_repo_path
from tests.python.support.tmp_root import generated_cad_directory

add_repo_path("packages/cadgen/src")

from cadgen.store import bounds, build
from cadgen._internal import component_package as cp
from cadgen.store.trees import get_tree

mat = importlib.import_module("cadgen.store.materialize")


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp = generated_cad_directory(prefix="assembly-cost-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = mock.patch.dict(os.environ, {
            "CADGEN_CACHE_DIR": str(self.root / "store"),
            "CADGEN_COMPONENT_WORKERS": "1", "CADGEN_DAEMON": "0",
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        bounds.clear()
        mat.reset_memo()
        self.addCleanup(bounds.clear)
        self.addCleanup(mat.reset_memo)

    @staticmethod
    def prototype(kind):
        import build123d as bd
        if kind == "nurbs":
            from OCP.BRepBuilderAPI import BRepBuilderAPI_NurbsConvert
            return bd.Solid(BRepBuilderAPI_NurbsConvert(bd.Cylinder(3, 7).wrapped, True).Shape())
        if kind == "hole":
            return bd.Box(12, 8, 3) - bd.Cylinder(2, 10)
        return bd.Solid.make_box(3, 5, 7)

    def child_tree(self, kind, repeats=3):
        """A child placing one prototype ``repeats`` times: shared TShape, distinct occurrences."""
        import build123d as bd
        base = self.prototype(kind)
        base.cad_face_ordinal_colors = {1: (1., .2, .1, 1.)}
        children = []
        for index in range(repeats):
            placed = base.moved(bd.Location((index * 20, index * 3, index), (index * 15, 7, index * 40)))
            placed.label = f"{kind}{index}"
            placed.color = (.6, .7, .1 * index, 1.)
            children.append(placed)
        compound = bd.Compound(children=children, label=kind)
        return build.build_tree_from_compound(compound, root_name=kind)[0]

    def parent(self):
        import build123d as bd
        children = []
        for index, kind in enumerate(("box", "hole", "nurbs")):
            child = mat.materialize(self.child_tree(kind)).moved(bd.Location((index * 50, 0, 0), (0, index * 30, 0)))
            child.label = f"link{index}"
            children.append(child)
        return bd.Compound(children=children, label="root")

    def result(self, shape, *, force=False, name="same"):
        path = self.root / f"{name}.step"
        value = build.build_tree_through_step(shape, path, root_name="root", force=force,
                                              _internal_source_publication=True)
        return {"sourceHash": value[0], "sourceTree": value[1], "stepHash": value[3],
                "stepBytesHash": hashlib.sha256(path.read_bytes()).hexdigest(),
                "documentTree": value[2]["documentTree"],
                "documentOccurrenceMap": value[2]["documentOccurrenceMap"],
                "documentNodeMap": value[2]["documentNodeMap"]}


def _plain_state(shape):
    """Everything ``moved()`` carries besides the native shape, deep-compared."""
    return {key: value for key, value in shape.__dict__.items() if key != "_wrapped"}


class PlacementTests(Fixture):
    def test_placed_copy_is_moved_without_the_discarded_geometry_copy(self):
        import build123d as bd
        from build123d import Shape
        location = bd.Location((1, 2, 3), (10, 20, 30))
        for kind in ("box", "hole", "nurbs"):
            entry = cp.prepare_geometry_component(self.prototype(kind), face_colors={1: (1., 0., 0., 1.)})
            base = cp.decode_geometry_component(entry["entry"], entry["payload"])
            expected = base.moved(location)
            with mock.patch.object(Shape, "__deepcopy__", side_effect=AssertionError("geometry deep copy")):
                placed = mat._placed_copy(base, location)
            self.assertIs(type(placed), type(expected))
            self.assertTrue(placed.wrapped.IsEqual(expected.wrapped))
            self.assertEqual(placed.wrapped.TShape(), base.wrapped.TShape())
            self.assertEqual(_plain_state(placed), _plain_state(expected))
            self.assertIsNot(placed.cad_face_ordinal_colors, base.cad_face_ordinal_colors)
            self.assertIsNone(placed.parent)

    def test_attached_or_jointed_bases_keep_the_original_moved(self):
        import build123d as bd
        base = bd.Solid.make_box(1, 2, 3)
        bd.Compound(children=[base])
        with mock.patch.object(bd.Shape, "moved", autospec=True, side_effect=bd.Shape.moved) as moved:
            placed = mat._placed_copy(base, bd.Location((1, 0, 0)))
        self.assertEqual(moved.call_count, 1)
        self.assertEqual(placed.wrapped.TShape(), base.wrapped.TShape())

    def test_materialize_places_occurrences_over_the_shared_prototype(self):
        from build123d import Shape
        tree = self.child_tree("hole", repeats=4)
        with mock.patch.object(Shape, "__deepcopy__", side_effect=AssertionError("geometry deep copy")):
            materialized = mat.materialize(tree)
        leaves = list(materialized.children)
        self.assertEqual(len(leaves), 4)
        self.assertEqual(len({leaf.wrapped.TShape() for leaf in leaves}), 1)
        self.assertEqual([leaf.label for leaf in leaves], [f"hole{i}" for i in range(4)])
        # Still an intact link when a parent packages it.
        import build123d as bd
        from cadgen.coordination import resolve
        walk = build._walk_compound(bd.Compound(children=[materialized], label="p"),
                                    root_name="p", progress=resolve(None))
        self.assertEqual([link["tree"] for link in walk.links], [tree])
        self.assertEqual(walk.components, {})

    def test_parent_outputs_are_byte_identical_with_the_old_placement(self):
        shape = self.parent()
        with mock.patch.object(mat, "_placed_copy", side_effect=lambda base, loc: base.moved(loc)):
            expected = self.result(shape, name="old")
        for state in ("warm", "disk", "force"):
            if state == "disk":
                bounds.clear()
                mat.reset_memo()
            actual = self.result(self.parent(), force=state == "force", name=state)
            self.assertEqual(expected, actual, state)
        tree = get_tree(expected["sourceHash"])
        self.assertEqual(len(tree["links"]), 3)
        self.assertEqual(tree["components"], {})


class BoundsTests(Fixture):
    def test_bbox_digests_each_prototype_once_and_matches_per_leaf_measurement(self):
        import build123d as bd
        from OCP.TopLoc import TopLoc_Location
        from OCP.gp import gp_Vec
        occurrences = []
        for index in range(6):
            base = self.prototype(("box", "hole", "nurbs")[index % 3])
            occurrences.append(base.moved(bd.Location((index * 9, 2, index), (index * 11, 3, 5))))
        # Two more occurrences of the first prototype: same TShape, new placements.
        occurrences.append(occurrences[0].moved(bd.Location((100, 0, 0))))
        occurrences.append(occurrences[0].moved(bd.Location((0, 0, 0), (0, 90, 0))))
        compound = bd.Compound(children=occurrences, label="c").moved(bd.Location((1, 1, 1), (5, 0, 0)))
        expected_boxes = []
        for leaf in cp._world_leaves(compound.wrapped):
            transform = leaf.Location().Transformation()
            translation = tuple(transform.TranslationPart().Coord())
            transform.SetTranslationPart(gp_Vec(0., 0., 0.))
            box = cp.optimal_box(leaf.Located(TopLoc_Location(transform)))
            expected_boxes.append([v + translation[i % 3] for i, v in enumerate(box)])
        expected = {"min": [min(b[a] for b in expected_boxes) for a in range(3)],
                    "max": [max(b[a] for b in expected_boxes) for a in range(3, 6)]}
        # Eight leaves of six prototypes: each call serializes each TShape once
        # for its key, whether the boxes come from a measurement or from RAM.
        with mock.patch.object(cp, "_shape_brep_bytes", wraps=cp._shape_brep_bytes) as serialized:
            self.assertEqual(cp._bbox_from_shape(compound), expected)
            self.assertEqual(cp._bbox_from_shape(compound), expected)
        self.assertEqual(serialized.call_count, 6 * 2)


class ReadbackTests(Fixture):
    def test_readback_reuses_published_prototypes_without_decoding_them_again(self):
        decodes: list[int] = []
        original_walk = build._document_walk

        def counted_walk(*args, **kwargs):
            with mock.patch.object(cp, "_decode_brep", wraps=cp._decode_brep) as decode:
                result = original_walk(*args, **kwargs)
            decodes.append(decode.call_count)
            return result

        with mock.patch.object(build, "_document_walk", side_effect=counted_walk):
            first = self.result(self.parent(), name="first")
            published = get_tree(first["documentTree"])["components"]
            with mock.patch.object(cp, "prepare_published_component",
                                   wraps=cp.prepare_published_component) as fast:
                second = self.result(self.parent(), name="second")
            with mock.patch.object(cp, "prepare_published_component", side_effect=AssertionError("forced")):
                forced = self.result(self.parent(), force=True, name="forced")
        self.assertEqual(first, second)
        self.assertEqual(first, forced)
        for entry in published.values():
            self.assertEqual((entry["kind"], entry["codec"]), ("native", "bintools-v4"))
        # Every written product is prepared (differently coloured occurrences
        # are separate products that dedupe to one cid). The cold read-back
        # decodes each; the second saves nothing new and decodes none; the
        # forced build proves every one again.
        self.assertGreaterEqual(fast.call_count, len(published))
        self.assertEqual(decodes, [fast.call_count, 0, fast.call_count])

    def test_published_component_fast_path_needs_the_exact_native_entry(self):
        from cadgen.store.index import write_entry
        from cadgen.store.objects import put_object
        prototype = self.prototype("hole")
        ordinary = cp.prepare_geometry_component(prototype)
        with mock.patch.object(cp, "_decode_brep", wraps=cp._decode_brep) as decode:
            # Unpublished bytes: the ordinary path, decode included.
            self.assertEqual(cp.prepare_published_component(prototype)["entry"], ordinary["entry"])
            self.assertEqual(decode.call_count, 1)
            # Bytes published, but under a different recipe: still the ordinary path.
            put_object(ordinary["payload"])
            write_entry("component", ordinary["entry"]["contentHash"][:16], {"schemaVersion": 1, **ordinary["entry"]})
            colored = cp.prepare_published_component(prototype, face_colors={1: (1., 0., 0., 1.)})
            self.assertNotEqual(colored["entry"]["contentHash"], ordinary["entry"]["contentHash"])
            self.assertEqual(decode.call_count, 2)
            # The exact published entry: no decode, the prototype stands in.
            fast = cp.prepare_published_component(prototype)
            self.assertEqual(decode.call_count, 2)
        self.assertEqual(fast["entry"], ordinary["entry"])
        self.assertEqual(fast["payload"], ordinary["payload"])
        self.assertEqual(fast["shape"].wrapped.TShape(), prototype.wrapped.TShape())
        self.assertEqual(cp._bbox_from_shape(fast["shape"]), cp._bbox_from_shape(ordinary["shape"]))

    def test_private_document_is_released_before_the_step_is_read_back(self):
        from cadgen._internal import step_scene_loader
        holders = []
        original = mat.materialize_descriptor

        def materialize(*args, **kwargs):
            document = original(*args, **kwargs)
            if kwargs.get("tree_hash") is None:  # the build's private document, not a child pin
                holders.append(weakref.ref(document))
            return document

        alive_at_readback = []
        original_load = step_scene_loader.load_step_scene

        def load(*args, **kwargs):
            gc.collect()
            alive_at_readback.append([ref() is not None for ref in holders])
            return original_load(*args, **kwargs)

        with mock.patch.object(mat, "materialize_descriptor", side_effect=materialize), \
                mock.patch.object(step_scene_loader, "load_step_scene", side_effect=load):
            for force in (False, True):
                self.result(self.parent(), force=force, name=f"release{force}")
        self.assertEqual(len(holders), 2)
        self.assertEqual(alive_at_readback, [[False], [False, False]])


class ReferenceSceneTests(Fixture):
    def test_reference_scene_prototypes_are_released_once_the_edge_policy_is_decided(self):
        import contextlib
        import io
        from cadgen.cli._run_model import run_model_argv
        from cadgen.store.records import read_record, remove_record
        from cadgen._internal import generation, step_scene_mesh

        for name, geometry in (("box", "bd.Solid.make_box(2, 3, 4)"), ("curve", "bd.Solid.make_torus(7, 1)")):
            (self.root / f"{name}.py").write_text(
                f"from cadgen import step, build123d as bd\n@step\ndef {name}():\n    return {geometry}\n",
                encoding="utf-8",
            )
        parent = self.root / "parent.py"
        parent.write_text(
            "from cadgen import step, build123d as bd\nfrom box import box\nfrom curve import curve\n"
            "@step\ndef parent():\n"
            "    return bd.Compound(children=[bd.Pos(5, 0, 0) * box(), bd.Pos(-5, 0, 0) * curve()], label='assembly')\n",
            encoding="utf-8",
        )
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            for name in ("box", "curve"):
                self.assertEqual(run_model_argv([str(self.root / f"{name}.py"), "--json"]), 0, output.getvalue())
        from cadgen._internal import generation_runner
        from cadgen.store import _references

        results = []
        for released in (False, True):
            remove_record(parent)
            scenes, sizes = [], []
            original = generation._selector_options_for_part
            hints = step_scene_mesh._scene_mesh_resolution_hints
            source_scene = _references.source_scene

            def capture(spec, *, scene=None):
                scenes.append(scene)
                return original(spec, scene=scene)

            def counted_hints(scene):
                sizes.append(len(scene.prototype_shapes))
                return hints(scene)

            def retained_scene(*args, **kwargs):
                scene = source_scene(*args, **kwargs)
                scene.disposable_prototypes = released
                return scene

            with mock.patch.object(generation, "_selector_options_for_part", side_effect=capture), \
                    mock.patch.object(step_scene_mesh, "_scene_mesh_resolution_hints", side_effect=counted_hints), \
                    mock.patch.object(_references, "source_scene", side_effect=retained_scene), \
                    mock.patch.object(generation, "_assembly_provenance_manifest",
                                      wraps=generation._assembly_provenance_manifest) as provenance, \
                    contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                self.assertEqual(run_model_argv([str(parent), "--json"]), 0, output.getvalue())
            self.assertEqual(len(scenes), 1)
            self.assertEqual(sizes, [2])  # the policy saw both prototypes
            self.assertEqual(provenance.call_count, 1)
            self.assertEqual(len(scenes[0].prototype_shapes), 0 if released else 2)
            results.append((read_record(parent)["tree"], read_record(parent)["documentTree"],
                            (self.root / "parent.step").read_bytes()))
        self.assertEqual(results[0], results[1])


if __name__ == "__main__":
    unittest.main()
