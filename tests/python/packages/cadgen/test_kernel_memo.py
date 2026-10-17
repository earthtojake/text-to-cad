"""The kernel memo (README law 18), the construction keys it gives, and the trace that
names what a run made (README law 20, STORE.md §3).

The contract: inside a run, every kernel construction the model's code calls is
a feature; a second run of the same code hands back the SAME live objects the
first run made, restored to the state the operation returned them in, and ends
with the bytes a cold run ends with -- the kernel's own changes to its inputs
replayed on a hit and undone when the operation is gone; two identical
constructions in one run are two objects; an input that changed, by geometry,
placement or attribute, misses, and so does everything downstream of a miss;
a shape no operation of this process made runs its call uncached; and with
the memo off every call still runs and is still a feature. A component is
named by the construction that made it, the same in every process, and its
elements by the features that made them. Small geometry, in process, no store.
"""

from __future__ import annotations

import contextlib
import io
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_repo_path
from tests.python.support.tmp_root import generated_cad_directory

add_repo_path("packages/cadgen/src")

from cadgen._internal import kernel_memo, kernel_trace  # noqa: E402
from cadgen._internal.component_package import _shape_brep_bytes as _bytes  # noqa: E402

COUNTS = ("hits", "misses", "unkeyable", "unreplayable", "errors")


def _delta(before: dict, after: dict) -> dict:
    return {name: after[name] - before[name] for name in COUNTS}


def _run(function, *args):
    """``(result, stats delta, run)`` of calling ``function`` inside a run."""
    before = kernel_memo.stats()
    with kernel_memo.run(None) as run:
        result = function(*args)
    return result, _delta(before, kernel_memo.stats()), run


def _bored_plate(radius=3.0):
    from build123d import Solid

    box = Solid.make_box(20, 20, 8)
    tool = Solid.make_cylinder(radius, 30)
    return box, tool, box.cut(tool)


def _junction_fillets():
    """The sequential-fillet pattern law 18 names: hold a boss's junction edges,
    re-find each one in the CURRENT solid by ``is_same``, fillet it. Returns
    (fillets applied, the result)."""
    from build123d import Box, Pos

    shape = Box(10, 10, 10).fuse(Pos(5, 0, 0) * Box(10, 6, 6))
    roots = [e for e in shape.edges() if 4 < e.length < 6.5]
    roots.sort(key=lambda e: tuple(round(v, 5) for v in e.center()))
    applied = 0
    for edge in roots:
        current = next((c for c in shape.edges() if edge.is_same(c)), None)
        if current is None:
            continue
        shape = shape.fillet(0.5, [current])
        applied += 1
    return applied, shape


class KernelMemoCase(unittest.TestCase):
    def setUp(self) -> None:
        kernel_memo.install()
        kernel_memo.clear()
        self.addCleanup(kernel_memo.clear)
        patch = mock.patch.dict(os.environ)
        patch.start()
        self.addCleanup(patch.stop)
        os.environ.pop("CADGEN_KERNEL_MEMO", None)


class InstallTest(KernelMemoCase):
    def test_install_is_idempotent_and_uninstall_restores(self) -> None:
        from build123d.topology import Face, Mixin3D, Shape, Solid

        self.assertFalse(kernel_memo.install())
        self.assertTrue(getattr(Solid.make_box.__func__, "__kernel_memo__", False))
        self.assertTrue(getattr(Mixin3D.fillet, "__kernel_memo__", False))
        self.assertTrue(getattr(Shape.is_valid.fget, "__kernel_memo__", False))
        self.assertTrue(getattr(Face.__init__, "__kernel_memo__", False))
        self.addCleanup(kernel_memo.install)
        self.assertTrue(kernel_memo.uninstall())
        self.assertFalse(kernel_memo.uninstall())
        self.assertFalse(getattr(Solid.make_box.__func__, "__kernel_memo__", False))
        self.assertFalse(getattr(Mixin3D.fillet, "__kernel_memo__", False))
        self.assertFalse(getattr(Shape.is_valid.fget, "__kernel_memo__", False))

    def test_outside_a_run_nothing_is_memoized_or_traced(self) -> None:
        before = kernel_memo.stats()
        _bored_plate()
        self.assertEqual(_delta(before, kernel_memo.stats()), dict.fromkeys(COUNTS, 0))


class HitTest(KernelMemoCase):
    def test_a_hit_hands_back_the_same_objects_restored(self) -> None:
        from build123d import Location

        def model():
            box, tool, body = _bored_plate()
            body.label = "plate"
            body.move(Location((1, 0, 0)))  # mutates the location in place, after the operation returned
            return box, tool, body

        (box, tool, body), cold, _run1 = _run(model)
        (box2, tool2, body2), hot, _run2 = _run(model)
        self.assertEqual(cold["hits"], 0)
        self.assertGreater(cold["misses"], 0)
        self.assertEqual((hot["misses"], hot["unkeyable"], hot["errors"]), (0, 0, 0))
        self.assertEqual(hot["hits"], cold["misses"])
        self.assertIs(box2, box)
        self.assertIs(tool2, tool)
        self.assertIs(body2, body)
        # Restored to the state the cut returned it in, then moved once by this run.
        self.assertEqual(body2.label, "plate")
        self.assertEqual(tuple(round(v, 9) for v in body2.location.position), (1.0, 0.0, 0.0))
        self.assertEqual(_bytes(body2.wrapped), _bytes(body.wrapped))

    def test_plain_cold_and_hot_runs_agree(self) -> None:
        """Law 18's pressure-test: the geometry, and every is_same along the way."""
        plain_count, plain = _junction_fillets()
        (cold_count, cold), cold_stats, _ = _run(_junction_fillets)
        (hot_count, hot), hot_stats, _ = _run(_junction_fillets)
        self.assertEqual((plain_count, cold_count, hot_count), (6, 6, 6))
        self.assertEqual(_bytes(plain.wrapped), _bytes(cold.wrapped))
        self.assertEqual(_bytes(cold.wrapped), _bytes(hot.wrapped))
        self.assertIs(hot, cold)
        self.assertEqual(cold_stats["hits"], 0)
        self.assertEqual(hot_stats["misses"], 0)
        self.assertEqual(hot_stats["hits"], cold_stats["misses"])
        self.assertEqual((cold_stats["unkeyable"], hot_stats["unkeyable"], hot_stats["errors"]), (0, 0, 0))

    def test_identical_constructions_in_one_run_are_two_objects(self) -> None:
        from build123d import Solid

        def model():
            return Solid.make_box(1, 1, 1), Solid.make_box(1, 1, 1)

        (a, b), _, _ = _run(model)
        self.assertIsNot(a, b)
        self.assertFalse(a == b)
        (a2, b2), hot, _ = _run(model)
        self.assertIs(a2, a)
        self.assertIs(b2, b)
        self.assertEqual(hot["hits"], 2)

    def test_sketch_constructors_and_in_place_clean_hit(self) -> None:
        from build123d import BuildSketch, Circle, Solid, Vector

        def model():
            with BuildSketch() as sketch:
                Circle(4)
            profile = sketch.sketch.faces()[0]
            return profile, Solid.extrude(profile, Vector(0, 0, 4))

        (profile, boss), cold, _ = _run(model)
        (profile2, boss2), hot, _ = _run(model)
        self.assertEqual((cold["unkeyable"], hot["misses"], hot["unkeyable"]), (0, 0, 0))
        self.assertGreater(hot["hits"], 0)
        self.assertIs(boss2, boss)
        # The sketch's face is constructed anew each run and wraps the first run's TShape.
        self.assertTrue(profile2.wrapped.IsPartner(profile.wrapped))
        self.assertEqual(_bytes(boss2.wrapped), _bytes(boss.wrapped))

    def test_an_in_place_clean_that_rebuilds_its_shape_hits(self) -> None:
        """``clean()`` leaves its input wrapping a new TShape: the entry must
        remember the input as it was given, or every hot run misses it and
        everything downstream of it."""
        from build123d import Edge, Face, Location, Solid, Vector, Wire

        def model():
            points = [Vector(0, 0, 0), Vector(5, 0, 0), Vector(10, 0, 0), Vector(10, 5, 0), Vector(0, 5, 0)]
            profile = Face(Wire([Edge.make_line(points[i], points[(i + 1) % 5]) for i in range(5)]))
            prism = Solid.extrude(profile, Vector(0, 0, 4))
            extruded = prism.wrapped.TShape()
            prism.clean()  # merges the two side faces on one plane: a new TShape, in place
            return prism.cut(Solid.make_cylinder(1, 30).moved(Location((5, 2.5, -5)))), extruded

        (bored, extruded), cold, _ = _run(model)
        self.assertEqual(len(bored.faces()), 7, "six faces of the cleaned prism and the bore")
        (bored2, extruded2), hot, _ = _run(model)
        self.assertEqual(extruded2, extruded, "the extrusion hit")
        self.assertIs(bored2, bored)
        self.assertEqual((hot["misses"], hot["unkeyable"]), (0, 0))
        self.assertEqual(hot["hits"], cold["misses"])

    def test_split_results_are_sequences_of_the_same_objects(self) -> None:
        from build123d import Keep, Plane, Solid

        def model():
            body = Solid.make_box(10, 10, 10).moved(Plane.XY.offset(-5).location)
            return body.split(Plane.XY, keep=Keep.BOTH)

        (top, bottom), cold, _ = _run(model)
        (top2, bottom2), hot, _ = _run(model)
        self.assertEqual(hot["misses"], 0)
        self.assertIs(top2, top)
        self.assertIs(bottom2, bottom)
        self.assertEqual(_bytes(top2.wrapped), _bytes(top.wrapped))


class MissTest(KernelMemoCase):
    def test_a_changed_input_misses_and_so_does_its_downstream(self) -> None:
        (_box, _tool, body), _, _ = _run(_bored_plate, 3.0)
        plain_box, _plain_tool, plain = _bored_plate(4.0)
        (box2, tool2, body2), stats, _ = _run(_bored_plate, 4.0)
        self.assertEqual(stats["hits"], 1, "the unchanged box hits")
        self.assertEqual(stats["misses"], 2, "the changed cylinder misses, and the cut after it")
        self.assertIsNot(body2, body)
        self.assertEqual(_bytes(body2.wrapped), _bytes(plain.wrapped))

    def test_attributes_and_placement_of_inputs_are_in_the_key(self) -> None:
        from build123d import Location, Solid

        def labelled(label):
            box = Solid.make_box(20, 20, 8)
            box.label = label
            return box.cut(Solid.make_cylinder(3, 30))

        _run(labelled, "a")
        second, stats, _ = _run(labelled, "b")
        self.assertEqual(second.label, "b")
        self.assertEqual(stats["misses"], 1, "the cut misses on the relabelled base; its inputs hit")

        def placed(offset):
            box = Solid.make_box(20, 20, 8)
            box.move(Location((offset, 0, 0)))
            return box.cut(Solid.make_cylinder(3, 30))

        far, _, _ = _run(placed, 0.0)
        near, stats, _ = _run(placed, 5.0)
        self.assertEqual(stats["misses"], 1)
        self.assertNotEqual(_bytes(far.wrapped), _bytes(near.wrapped))
        self.assertEqual(_bytes(near.wrapped), _bytes(placed(5.0).wrapped))

    def test_a_generator_argument_runs_uncached_but_correct(self) -> None:
        from build123d import Solid

        def model():
            box = Solid.make_box(20, 20, 8)
            return box, box.fillet(1.0, (edge for edge in box.edges()[:2]))

        (box, filleted), stats, _ = _run(model)
        self.assertEqual(stats["unkeyable"], 1)
        self.assertLess(filleted.volume, box.volume)
        (_box2, filleted2), hot, _ = _run(model)
        self.assertEqual(hot["unkeyable"], 1)
        self.assertIsNot(filleted2, filleted)
        self.assertEqual(_bytes(filleted2.wrapped), _bytes(filleted.wrapped))

    def test_a_foreign_shape_makes_its_call_run_uncached(self) -> None:
        from build123d import Solid

        foreign = Solid.make_box(20, 20, 8)  # made outside any run

        def model():
            return foreign.cut(Solid.make_cylinder(3, 30))

        _, stats, run = _run(model)
        self.assertEqual((stats["misses"], stats["unkeyable"]), (1, 1))
        cut = run.trace.features[-1]
        self.assertEqual(cut.op, "cut")
        self.assertEqual(cut.inputs, [None, None, 0], "the foreign base has no feature; the cylinder does")
        _, again, _ = _run(model)
        self.assertEqual(again["hits"], 1, "the cylinder hits; the cut on the foreign base runs again")
        self.assertEqual(again["unkeyable"], 1)


class EffectTest(KernelMemoCase):
    """The kernel's changes to its inputs: an extrusion clears its profile's ``Free``
    flag and appends representations to the profile's edges (a boolean, run
    non-destructive, changes none: ``BooleanTest``)."""

    def test_effects_on_inputs_are_replayed_on_a_hit_and_undone_when_the_operation_is_gone(self) -> None:
        from build123d import Face, Solid, Vector, Wire

        pristine = _bytes(Face(Wire.make_circle(4)).wrapped)

        def with_boss():
            profile = Face(Wire.make_circle(4))
            return profile, Solid.extrude(profile, Vector(0, 0, 4))

        def without_boss():
            return Face(Wire.make_circle(4))

        (profile, boss), cold, _ = _run(with_boss)
        mutated = _bytes(profile.wrapped)
        self.assertNotEqual(mutated, pristine, "the extrusion changed its profile")
        (profile2, boss2), hot, _ = _run(with_boss)
        self.assertIs(boss2, boss)
        self.assertTrue(profile2.wrapped.IsPartner(profile.wrapped), "constructed anew, around the first run's TShape")
        self.assertEqual(hot["misses"], 0)
        self.assertEqual(_bytes(profile2.wrapped), mutated, "a hit leaves the profile as the extrusion left it")
        self.assertEqual(_bytes(boss2.wrapped), _bytes(boss.wrapped))
        profile3, edited, _ = _run(without_boss)
        self.assertTrue(profile3.wrapped.IsPartner(profile.wrapped))
        self.assertEqual(edited["hits"], 2)
        self.assertEqual(_bytes(profile3.wrapped), pristine, "with the extrusion edited out, the profile is as it was made")
        self.assertEqual((cold["unreplayable"], hot["unreplayable"], edited["unreplayable"]), (0, 0, 0))

    def test_an_extruded_profile_ends_as_a_cold_run_leaves_it(self) -> None:
        from build123d import Face, Solid, Vector, Wire

        def model():
            profile = Face(Wire.make_circle(4))
            boss = Solid.extrude(profile, Vector(0, 0, 4))
            return profile, boss

        plain_profile, plain_boss = model()
        (profile, boss), cold, _ = _run(model)
        (profile2, boss2), hot, _ = _run(model)
        self.assertEqual(cold["unkeyable"], 0)
        self.assertEqual(hot["misses"], 0)
        self.assertEqual(_bytes(profile2.wrapped), _bytes(plain_profile.wrapped))
        self.assertEqual(_bytes(boss2.wrapped), _bytes(plain_boss.wrapped))
        self.assertEqual(_bytes(boss2.wrapped), _bytes(boss.wrapped))


class CapacityTest(KernelMemoCase):
    def test_the_memo_is_bounded_and_a_rerun_past_the_bound_is_still_right(self) -> None:
        from build123d import Solid

        def model():
            body = Solid.make_box(20, 20, 8)
            for index in range(4):
                body = body.cut(Solid.make_cylinder(1, 30).translate((3 + 4 * index, 10, -5)))
            return body

        plain = _bytes(model().wrapped)
        with mock.patch.object(kernel_memo, "CAPACITY", 5):
            first, _, _ = _run(model)
            self.assertLessEqual(kernel_memo.stats()["entries"], 5)
            second, _, _ = _run(model)
        self.assertEqual(_bytes(first.wrapped), plain)
        self.assertEqual(_bytes(second.wrapped), plain)


class KillSwitchTest(KernelMemoCase):
    def test_the_kill_switch_turns_hits_off_and_nothing_else(self) -> None:
        """``CADGEN_KERNEL_MEMO=0`` computes every call again: the trace, the keys
        and the names are the ones the memo gives, so identity is the same either way."""
        (_box, _tool, body), _, run = _run(_bored_plate)
        # A build names its components before the worker runs anything else.
        identity = run.identify(body)
        self.assertRegex(identity[0], r"^[0-9a-f]{64}$")
        kernel_memo.clear()
        os.environ["CADGEN_KERNEL_MEMO"] = "0"
        (_box, _tool, body), first, run1 = _run(_bored_plate)
        self.assertEqual(run1.identify(body), identity)
        (_box2, _tool2, body2), second, run2 = _run(_bored_plate)
        self.assertEqual(run2.identify(body2), identity)
        self.assertEqual((first["hits"], second["hits"], second["misses"]), (0, 0, 3))
        self.assertIsNot(body2, body)
        self.assertEqual(run1.trace.feature_rows(), run2.trace.feature_rows())
        self.assertEqual([feature.op for feature in run2.trace.features], ["Solid.make_box", "Solid.make_cylinder", "cut"])
        self.assertEqual(run2.trace.features[-1].inputs, [0, 0, 1])


class SettingsTest(KernelMemoCase):
    """An operation is every setting it runs with: what build123d sets on the OCC
    operation object before the call, the class-wide ``SkipClean``, the font file a
    text reads. A hit that ignored one would hand back another operation's geometry."""

    def test_a_boolean_s_fuzzy_value_and_glue_are_in_its_key(self) -> None:
        from build123d import Box, Pos

        def fused(tol, gap=10.3, glue=False):
            a = Box(10, 10, 10)
            b = Pos(gap, 0, 0) * Box(10, 10, 10)
            return a.fuse(b, tol=tol, glue=glue) if tol or glue else a.fuse(b)

        apart, _, _ = _run(fused, 0)
        merged, stats, _ = _run(fused, 0.5)
        self.assertEqual((len(apart.solids()), len(merged.solids())), (2, 1), "the fuzzy fuse closes the gap")
        self.assertEqual(stats["misses"], 1, "the boxes hit; the fuse is another operation")
        self.assertNotEqual(kernel_memo.construction_key(merged), kernel_memo.construction_key(apart))
        touching, _, _ = _run(fused, 0, 10.0)
        glued, stats, _ = _run(fused, 0, 10.0, True)
        self.assertEqual(stats["misses"], 1)
        self.assertNotEqual(kernel_memo.construction_key(glued), kernel_memo.construction_key(touching))

    def test_skip_clean_is_in_the_key(self) -> None:
        from build123d import Box, Pos, SkipClean

        def joined():
            return Box(10, 10, 10).fuse(Pos(10, 0, 0) * Box(10, 10, 10))

        cleaned, _, _ = _run(joined)
        with SkipClean():
            raw, _, _ = _run(joined)
        self.assertEqual((len(cleaned.faces()), len(raw.faces())), (6, 10), "the fuse ran again, uncleaned")
        self.assertNotEqual(kernel_memo.construction_key(raw), kernel_memo.construction_key(cleaned))

    def test_a_text_is_keyed_by_its_font_file_s_bytes_not_its_path(self) -> None:
        import shutil
        import tempfile

        import build123d
        from build123d import Compound
        from build123d.text import FontManager

        bundled = Path(build123d.__file__).parent / "data" / "fonts" / "reliefsingleline" / "ReliefSingleLineCAD-Regular.ttf"
        # The font manager is the kernel's, process-wide: give the bundled face its file back.
        self.addCleanup(lambda: FontManager().register_font(str(bundled), True, True))
        # The kernel may still hold a font it read open: on Windows that file outlives the test.
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
            first, other, same = (Path(folder) / name for name in ("first.ttf", "other.ttf", "same.ttf"))
            shutil.copyfile(bundled, first)
            other.write_bytes(bundled.read_bytes() + bytes(4))  # the same glyphs, other bytes
            shutil.copyfile(bundled, same)

            def text(path):
                return Compound.make_text("cad", 5, font_path=str(path))

            key = kernel_memo.construction_key(_run(text, first)[0])
            self.assertRegex(key, r"^[0-9a-f]{64}$")
            changed, stats, _ = _run(text, other)
            self.assertEqual(stats["hits"], 0, "a font file of other bytes is another text")
            self.assertNotEqual(kernel_memo.construction_key(changed), key)
            kernel_memo.clear()
            self.assertEqual(kernel_memo.construction_key(_run(text, same)[0]), key,
                             "the same bytes at another path are the same font")


class TraceTest(KernelMemoCase):
    def test_features_are_named_by_function_operation_and_count(self) -> None:
        """A feature is named among the features its part descends from, in call order:
        a function's calls of one operation count up, wherever they are; a feature the
        part does not descend from counts for nothing; a line is no part of a name."""
        from build123d import Location, Solid
        from OCP.TopLoc import TopLoc_Location

        def model():
            box = Solid.make_box(20, 20, 8)
            Solid.make_box(1, 1, 1)  # a feature no element of the part descends from
            tools = [Solid.make_cylinder(1, 30).moved(Location((5 + 10 * index, 10, -5))) for index in range(2)]
            return box.cut(*tools)

        body, _, run = _run(model)
        features = run.trace.features
        here = Path(__file__).as_posix()  # the trace names a file the same on every OS
        self.assertTrue(all(feature.file == here for feature in features))
        self.assertEqual(features[0].function, "model")
        lineage, names = run.trace.account(body.wrapped.Located(TopLoc_Location()), run.made_by)
        by_index = {index: name for name, index in names.items()}
        self.assertEqual(by_index[0], "model.make_box1")
        self.assertEqual([feature.op for feature in features].count("Solid.make_box"), 2)
        self.assertNotIn("model.make_box2", names, "the run's other box is no feature of the part")
        cylinders = [feature.index for feature in features if feature.op == "Solid.make_cylinder"]
        self.assertEqual([by_index[index] for index in cylinders], ["model.make_cylinder1", "model.make_cylinder2"])
        self.assertEqual(len({features[index].line for index in cylinders}), 1)
        cut = features[-1]
        self.assertEqual((cut.op, lineage["made"], names["model.cut1"]), ("cut", "model.cut1", cut.index))
        moved = [feature.index for feature in features if feature.op == "moved"]
        self.assertEqual(cut.inputs, [0, 0, *moved], "the cut consumed the box and the two placed tools")
        self.assertEqual([by_index[index] for index in moved], ["model.moved1", "model.moved2"])
        row = run.trace.feature_rows()[-1]
        self.assertEqual((row["op"], row["function"], row["inputs"]), ("cut", "model", [0, 0, *moved]))

    def test_elements_are_named_by_the_feature_that_made_them(self) -> None:
        """Unchanged: same surface, same extent, inherited. Modified: same
        surface, another extent, the name kept and the modifier recorded. Made:
        anything else, named by the feature that made it."""
        from build123d import Axis, Location, Solid

        from cadgen._internal.entity_ordinals import entity_map

        def model():
            box = Solid.make_box(20, 20, 8)
            tool = Solid.make_cylinder(3, 30).moved(Location((10, 10, -5)))
            return box.cut(tool)

        body, _, run = _run(model)
        _key, lineage = run.identify(body)
        self.assertEqual(lineage["made"], "model.cut1")
        faces, edges = entity_map(body.wrapped, "face"), entity_map(body.wrapped, "edge")

        def face(shape):
            return lineage["faces"][faces.FindIndex(shape.wrapped) - 1]

        def edge(shape):
            return lineage["edges"][edges.FindIndex(shape.wrapped) - 1]

        bottom = body.faces().sort_by(Axis.Z)[0]
        side = body.faces().sort_by(Axis.X)[0]
        bore = [shape for shape in body.faces() if shape.geom_type.name == "CYLINDER"][0]
        self.assertRegex(face(bottom), r"^f:model\.make_box1\.[1-6]$")
        self.assertEqual(lineage["modified"][face(bottom)], "model.cut1", "the hole changed the bottom face's extent")
        self.assertRegex(face(side), r"^f:model\.make_box1\.[1-6]$")
        self.assertNotIn(face(side), lineage["modified"], "the cut left the side face alone")
        self.assertEqual(face(bore), "f:model.make_cylinder1.1", "the bore wall is the cylinder's face, trimmed")
        self.assertEqual(lineage["modified"][face(bore)], "model.cut1")
        vertical = body.edges().filter_by(Axis.Z).sort_by(Axis.X)[0]
        rims = sorted(edge(shape) for shape in body.edges() if shape.geom_type.name == "CIRCLE")
        self.assertRegex(edge(vertical), r"^e:model\.make_box1\.\d+$", "a box edge the cut never touched")
        self.assertEqual(rims, ["e:model.cut1.1", "e:model.cut1.2"], "the hole's rims are new circles the cut made")
        self.assertEqual(len(set(lineage["faces"])), len(lineage["faces"]))
        self.assertTrue(all(name is not None for plural in ("faces", "edges", "vertices") for name in lineage[plural]))

    def test_each_piece_of_a_split_element_is_numbered(self) -> None:
        from build123d import Axis, Box

        from cadgen._internal.entity_ordinals import entity_map

        def model():
            return Box(30, 20, 10) - Box(4, 30, 20)

        body, _, run = _run(model)
        _key, lineage = run.identify(body)
        faces = entity_map(body.wrapped, "face")
        # The slot cuts the box's top in two: two pieces of one face of the box, numbered.
        top = sorted(lineage["faces"][faces.FindIndex(shape.wrapped) - 1]
                     for shape in body.faces() if abs(shape.center().Z - 5) < 1e-9)
        self.assertEqual(len(top), 2)
        stem = top[0].rsplit(".", 1)[0]
        self.assertRegex(stem, r"^f:model\.make_box1\.[1-6]$")
        self.assertEqual(top, [f"{stem}.1", f"{stem}.2"])
        self.assertEqual(lineage["modified"][top[0]], "model.cut1")
        ends = [lineage["faces"][faces.FindIndex(shape.wrapped) - 1] for shape in body.faces().filter_by(Axis.X)]
        self.assertTrue(all(name.count(".") == 2 for name in ends), "an end the slot does not reach is whole")

    def test_two_places_of_one_shape_are_two_elements_and_an_in_place_operation_is_followed(self) -> None:
        """An extrusion's caps are one TShape at two places: the bottom is the
        profile's face, passed through, and the top is a face the extrusion made.
        The profile reaches the extrusion through an in-place ``clean`` and a
        placement the builder makes outside the patched surface: the lineage
        follows both back to the face the profile made."""
        from build123d import Axis, BuildPart, BuildSketch, Plane, SlotOverall, extrude

        from cadgen._internal.entity_ordinals import entity_map

        def slot():
            with BuildPart() as part:
                with BuildSketch(Plane.XY):
                    SlotOverall(30, 10)
                extrude(amount=5)
            return part.part

        body, _, run = _run(slot)
        _key, lineage = run.identify(body)
        faces = entity_map(body.wrapped, "face")
        bottom, top = (lineage["faces"][faces.FindIndex(shape.wrapped) - 1]
                       for shape in body.faces().filter_by(Axis.Z).sort_by(Axis.Z))
        self.assertEqual((bottom, top), ("f:slot.face1.1", "f:slot.extrude1.5"))
        self.assertTrue(all(name is not None for plural in ("faces", "edges", "vertices") for name in lineage[plural]))
        self.assertEqual(len(set(lineage["edges"])), len(lineage["edges"]), "a top edge is not its bottom twin")

    def test_a_label_pins_the_name_in_what_is_made_of_the_labelled_shape(self) -> None:
        """A shape the model labels and gives another construction names the feature
        that made it -- through build123d's part wrapper and through a placement -- in
        what that construction makes. Placed in an assembly, a labelled shape is an
        occurrence the label names: its own elements keep its construction's names, so
        identical constructions labelled apart are one part, named alike."""
        from build123d import Box, Compound, Cylinder, Pos

        def model():
            pegs = []
            for index in range(2):
                peg = Pos(40 * index, 0, 0) * Cylinder(3, 10)
                peg.label = f"peg:{index}"
                pegs.append(peg)
            boss = Cylinder(2, 4)
            boss.label = "boss"
            plate = Box(20, 20, 2) + Pos(0, 0, 3) * boss
            return Compound(children=[*pegs, plate], label="pair")

        compound, _, run = _run(model)
        first, second, plate = compound.children
        identity = run.identify(first)
        self.assertEqual(run.identify(second), identity, "one construction, labelled apart: one part")
        _key, lineage = identity
        self.assertEqual(lineage["made"], "model.make_cylinder1")
        self.assertEqual(sorted(lineage["faces"]),
                         ["f:model.make_cylinder1.1", "f:model.make_cylinder1.2", "f:model.make_cylinder1.3"])
        _key, plate_lineage = run.identify(plate)
        bosses = [name for name in plate_lineage["faces"] if name.startswith("f:boss.")]
        self.assertTrue(bosses, plate_lineage["faces"])
        self.assertFalse([name for name in plate_lineage["faces"] if "cylinder" in name], plate_lineage["faces"])

    def test_a_label_set_after_a_construction_renames_nothing_it_made(self) -> None:
        """A label pins names only in what is made after it is applied: labelling a shape
        that a construction was already given renames nothing that construction made, and
        the part keeps its key. What is made of the shape after the label is named by it."""
        from build123d import Box, Compound, Cylinder, Pos

        def model(label):
            a = Box(10, 10, 10)
            fused = Pos(30, 0, 0) * (a + Pos(5, 0, 0) * Cylinder(2, 12))
            if label:
                a.label = label
            after = Pos(0, 30, 0) * (a + Pos(5, 0, 0) * Cylinder(1, 12))
            return Compound(children=[a, fused, after])

        found = []
        for label in (None, "lid"):
            compound, _, run = _run(model, label)
            found.append([run.identify(child) for child in compound.children[1:]])
        (plain_fused, plain_after), (fused, after) = found
        self.assertEqual(fused, plain_fused, "made before the label: named and keyed as if there were none")
        self.assertTrue([name for name in fused[1]["faces"] if name.startswith("f:model.make_box1.")], fused[1]["faces"])
        self.assertTrue([name for name in after[1]["faces"] if name.startswith("f:lid.")], after[1]["faces"])
        self.assertNotEqual(after, plain_after, "made after it: the label names the box's feature there")

    def test_a_nested_run_s_features_are_its_own(self) -> None:
        """A child model built inside its parent's body runs in a run of its own:
        its features land in its trace, and the parent's trace goes on without them."""
        from build123d import Solid

        with kernel_memo.run(None) as outer:
            Solid.make_box(1, 1, 1)
            with kernel_memo.run(None) as inner:
                Solid.make_cylinder(1, 2)
            Solid.make_sphere(1)
        self.assertEqual([feature.op for feature in outer.trace.features], ["Solid.make_box", "Solid.make_sphere"])
        self.assertEqual([feature.op for feature in inner.trace.features], ["Solid.make_cylinder"])

    def test_a_shape_no_feature_made_has_no_lineage_even_placed(self) -> None:
        from build123d import Location, Solid

        foreign = Solid.make_box(5, 5, 5)

        def model():
            return foreign.moved(Location((1, 2, 3)))

        placed, _, run = _run(model)
        self.assertEqual([feature.op for feature in run.trace.features], ["moved"])
        self.assertEqual(run.identify(placed), (None, None))

    def test_a_decoded_child_is_made_by_no_feature(self) -> None:
        """A body composes a child as its stored result, decoded (``cadgen.store.materialize``):
        a shape no feature of this run made. The feature that places it has no input
        feature for it, the run names it by nothing, and the parent's own features are
        the same on a hit and on a miss, since the child is decoded on both."""
        from build123d import Compound, Pos, Solid

        from cadgen.store.build import build_tree_from_compound
        from cadgen.store.materialize import materialize

        with mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": tempfile.mkdtemp(prefix="memo-child-")}):
            tree = build_tree_from_compound(Solid.make_box(1, 2, 3), root_name="child")[0]

            def parent():
                child = materialize(tree, label="child")
                return Compound(children=[Pos(5, 0, 0) * child, Solid.make_box(4, 4, 4)])

            assembly, _, run = _run(parent)
        placed, own = assembly.children
        self.assertEqual([feature.op for feature in run.trace.features], ["moved", "Solid.make_box", "Compound"])
        self.assertEqual(run.trace.features[0].inputs, [None], "the child it placed was made by no feature of this run")
        self.assertEqual(run.identify(placed), (None, None), "a decoded child has no construction key and no lineage")
        self.assertIsNotNone(run.identify(own)[0])

    def test_an_element_the_kernel_leaves_unbounded_is_signed_in_a_window(self) -> None:
        """A hyperbola's natural bounds are the kernel's infinity, the finite
        float 2e100, where its Cosh overflows: the signature samples a fixed
        window instead, the same for every trim of the curve or surface."""
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeFace
        from OCP.Geom import Geom_Hyperbola, Geom_SurfaceOfLinearExtrusion
        from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

        def hyperbola(major: float):
            return Geom_Hyperbola(gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)), major, 1.0)

        self.assertEqual(hyperbola(2.0).LastParameter(), 2e100)
        short = kernel_trace.edge_signature(BRepBuilderAPI_MakeEdge(hyperbola(2.0), -1.0, 1.0).Edge())
        long = kernel_trace.edge_signature(BRepBuilderAPI_MakeEdge(hyperbola(2.0), -2.0, 0.5).Edge())
        other = kernel_trace.edge_signature(BRepBuilderAPI_MakeEdge(hyperbola(3.0), -1.0, 1.0).Edge())
        self.assertEqual(short[0], long[0])
        self.assertNotEqual(short[1], long[1])
        self.assertNotEqual(short[0], other[0])

        surface = Geom_SurfaceOfLinearExtrusion(hyperbola(2.0), gp_Dir(0, 0, 1))
        self.assertEqual(surface.Bounds(), (-2e100, 2e100, -2e100, 2e100))
        low = kernel_trace.face_signature(BRepBuilderAPI_MakeFace(surface, -1.0, 1.0, 0.0, 2.0, 1e-6).Face())
        high = kernel_trace.face_signature(BRepBuilderAPI_MakeFace(surface, -0.5, 0.5, 5.0, 9.0, 1e-6).Face())
        self.assertEqual(low[0], high[0])
        self.assertNotEqual(low[1], high[1])

    def test_an_edge_the_kernel_built_without_vertices_is_signed_by_its_curve(self) -> None:
        """A closed edge made straight from its curve has no vertices (a loft or sweep
        leaves such edges, as the hypercar's chassis does): its ends are its curve's, the
        same as the edge with vertices on that curve -- not a null vertex's point, which
        the kernel refuses."""
        from OCP.BRep import BRep_Builder
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
        from OCP.Geom import Geom_Circle
        from OCP.TopoDS import TopoDS_Edge
        from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

        circle = Geom_Circle(gp_Ax2(gp_Pnt(1, 2, 3), gp_Dir(0, 0, 1)), 5.0)
        bare = TopoDS_Edge()
        BRep_Builder().MakeEdge(bare, circle, 1e-7)
        self.assertEqual(kernel_trace.edge_signature(bare),
                         kernel_trace.edge_signature(BRepBuilderAPI_MakeEdge(circle).Edge()))

    def test_an_edit_elsewhere_renames_nothing(self) -> None:
        """A name's ordinal counts among the features the part descends from, never
        across the run: another hole in another part renames nothing in this one."""
        from build123d import Box, Compound, Cylinder, Pos

        def bore(body, x, radius):
            return body - Pos(x, 0, 0) * Cylinder(radius, 30)

        def plate(holes):
            body = Box(40, 10, 2)
            for index in range(holes):
                body = bore(body, -15 + 6 * index, 1.0)
            return body

        def bar():
            return bore(Box(20, 8, 4), 0, 1.5)

        def model(holes):
            part, other = plate(holes), bar()
            Compound(children=[part, other])
            return part, other

        lineages = []
        for holes in (1, 2):
            kernel_memo.clear()
            (part, other), _, run = _run(model, holes)
            lineages.append(run.identify(other)[1])
            plate_lineage = run.identify(part)[1]
        self.assertEqual(lineages[0], lineages[1])
        self.assertEqual(lineages[0]["made"], "bore.cut1")
        self.assertIn("f:bore.make_cylinder1.1", lineages[0]["faces"])
        # The plate's own two bores count among its own features.
        self.assertEqual(sorted(name for name in plate_lineage["faces"] if "make_cylinder" in name),
                         ["f:bore.make_cylinder1.1", "f:bore.make_cylinder2.1"])

    def test_every_element_the_run_produced_is_named_through_a_sub_shape_input(self) -> None:
        """``Solid.extrude(bar.faces()[i])``: the tab's base is the bar's face, its edges and
        vertices the bar's, followed from the face to the bar that owns it."""
        from build123d import Axis, Solid, Vector

        from cadgen._internal.entity_ordinals import entity_map

        def model():
            bar = Solid.make_box(20, 8, 4)
            face = bar.faces().sort_by(Axis.X)[-1]
            return bar, Solid.extrude(face, Vector(5, 0, 0))

        (bar, tab), _, run = _run(model)
        _key, lineage = run.identify(tab)
        self.assertTrue(all(name is not None for plural in ("faces", "edges", "vertices") for name in lineage[plural]),
                        lineage)
        faces = entity_map(tab.wrapped, "face")
        by_x = {round(face.center().X, 6): lineage["faces"][faces.FindIndex(face.wrapped) - 1]
                for face in tab.faces().filter_by(Axis.X)}
        _bar_key, bar_lineage = run.identify(bar)
        bar_faces = entity_map(bar.wrapped, "face")
        end = bar.faces().sort_by(Axis.X)[-1]
        self.assertEqual(by_x[20.0], bar_lineage["faces"][bar_faces.FindIndex(end.wrapped) - 1],
                         "the tab's base is the bar's end face, by the bar's name")
        self.assertRegex(by_x[25.0], r"^f:model\.extrude1\.\d+$", "the cap the extrusion made")

    def test_a_function_named_beyond_ascii_has_a_name_of_its_own(self) -> None:
        """Normalisation is injective: a name that is not an ASCII identifier is its ASCII
        form and a digest of it, never another function's name."""
        namespace: dict = {}
        source = "def \u043a\u043e\u0440\u043f\u0443\u0441(Solid):\n    return Solid.make_box(2, 2, 2)\n"
        exec(compile(source, __file__, "exec"), namespace)  # noqa: S102 - a function of the model's file
        housing = namespace["\u043a\u043e\u0440\u043f\u0443\u0441"]

        def model():
            from build123d import Location, Solid

            return Solid.make_box(2, 2, 2).fuse(housing(Solid).moved(Location((5, 0, 0))))

        from cadgen._internal.component_package import lineage_bytes

        body, _, run = _run(model)
        _key, lineage = run.identify(body)
        lineage_bytes(lineage)  # every name distinct
        features = sorted({name.split(".")[0] for name in lineage["faces"]})
        self.assertEqual(len(features), 2)
        self.assertIn("f:model", features)
        self.assertRegex(next(name for name in features if name != "f:model"), r"^f:_[0-9a-f]{8}$")
        names = {kernel_trace.identifier(text) for text in
                 ("model", "\u043a\u043e\u0440\u043f\u0443\u0441", "<module>", "module", "a:b", "a_b",
                  "a_b_0123abcd", "")}
        self.assertEqual(len(names), 8)
        self.assertTrue(all(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) for name in names))
        self.assertEqual(kernel_trace.identifier("<module>"), "module")
        self.assertEqual(kernel_trace.identifier("bracket"), "bracket")

    def test_names_and_construction_keys_are_the_same_cold_and_hot(self) -> None:
        def model():
            box, tool, body = _bored_plate()
            body.label = "plate"
            return body

        cold, _, run1 = _run(model)
        # A build names its components before the worker runs anything else.
        cold_identity = run1.identify(cold)
        hot, stats, run2 = _run(model)
        self.assertGreater(stats["hits"], 0)
        self.assertEqual(run2.identify(hot), cold_identity)
        self.assertRegex(cold_identity[0], r"^[0-9a-f]{64}$")


class ConstructionKeyTest(KernelMemoCase):
    def test_a_construction_key_follows_the_construction(self) -> None:
        (_box, _tool, body), _, _run1 = _run(_bored_plate)
        key = kernel_memo.construction_key(body)
        kernel_memo.clear()
        (_box, _tool, again), _, _run2 = _run(_bored_plate)
        self.assertEqual(kernel_memo.construction_key(again), key, "the same construction, made again")
        (_box, _tool, wider), _, _run3 = _run(_bored_plate, 4.0)
        self.assertNotEqual(kernel_memo.construction_key(wider), key, "another parameter")
        from build123d import Solid

        self.assertIsNone(kernel_memo.construction_key(Solid.make_box(1, 1, 1)), "made outside a run")

    def test_each_output_of_one_construction_is_its_own_construction(self) -> None:
        """A split kept both ways is one call with two outputs: each output is a
        construction of its own, and so is what is made from each."""
        from build123d import Keep, Plane, Solid

        def halves():
            return Solid.make_torus(10, 2).split(Plane.XZ, keep=Keep.BOTH)

        pieces, _, _ = _run(halves)
        self.assertEqual(len(pieces), 2)
        keys = [kernel_memo.construction_key(piece) for piece in pieces]
        self.assertTrue(all(re.fullmatch(r"[0-9a-f]{64}", key or "") for key in keys))
        self.assertNotEqual(keys[0], keys[1])

        def scaled(which):
            return halves()[which].scale(2.0)

        made = []
        for which in (0, 1):
            kernel_memo.clear()
            made.append(kernel_memo.construction_key(_run(scaled, which)[0]))
        self.assertNotEqual(made[0], made[1], "the same operation on the other output")

    def test_a_construction_key_is_the_construction_s_whatever_ran_before(self) -> None:
        """A warm worker's earlier runs leave sub-shapes registered and effects undone:
        none of it is in a key. A, then B, then A gives A the key a cold run gives."""
        from build123d import Axis, Solid, Vector

        def bracket(face_index):
            box = Solid.make_box(10, 10, 10)
            face = box.faces().sort_by(Axis.Z)[face_index]
            Solid.extrude(face, Vector(0, 0, 2 if face_index == -1 else -2))
            return box

        cold = kernel_memo.construction_key(_run(bracket, -1)[0])
        self.assertRegex(cold, r"^[0-9a-f]{64}$")
        _run(bracket, 0)  # an edit extrudes the other face
        warm = kernel_memo.construction_key(_run(bracket, -1)[0])
        self.assertEqual(warm, cold)

    def test_identical_constructions_are_one_construction_whatever_ran_before(self) -> None:
        """Two identical constructions in one run are two objects (HitTest) but one
        construction: the memo tells the calls apart by how many identical ones the run
        made before, and that count -- grown by any part's calls -- is in no key."""
        from build123d import Pos, Solid

        def screws(earlier):
            if earlier:
                Solid.make_cylinder(0.5, 2)  # an identical call another part made first
            return [Pos(4 * index, 0, 0) * Solid.make_cylinder(0.5, 2).fuse(Pos(0, 0, 2) * Solid.make_cylinder(1, 0.5))
                    for index in range(2)]

        first, second = _run(screws, False)[0]
        self.assertFalse(first.wrapped.IsPartner(second.wrapped), "two objects, two bodies")
        key = kernel_memo.construction_key(first)
        self.assertRegex(key or "", r"^[0-9a-f]{64}$")
        self.assertEqual(kernel_memo.construction_key(second), key)
        kernel_memo.clear()
        self.assertEqual([kernel_memo.construction_key(screw) for screw in _run(screws, True)[0]], [key, key])

    def test_a_construction_key_is_the_same_in_another_process(self) -> None:
        import subprocess
        import sys
        import tempfile

        script = (
            "from cadgen._internal import kernel_memo\n"
            "from build123d import Solid\n"
            "with kernel_memo.run(None):\n"
            "    body = Solid.make_box(20, 20, 8).cut(Solid.make_cylinder(3.0, 30))\n"
            "print(kernel_memo.construction_key(body))\n"
        )
        with tempfile.TemporaryDirectory() as folder:
            # The model's own code is a file of its own: a feature needs a first-party frame.
            path = Path(folder) / "model.py"
            path.write_text(script, encoding="utf-8")
            env = {**os.environ, "PYTHONPATH": str(Path(kernel_memo.__file__).resolve().parents[2])}
            there = subprocess.run([sys.executable, str(path)], env=env, capture_output=True, text=True, check=True)
        (_box, _tool, body), _, _run1 = _run(_bored_plate)
        self.assertRegex(there.stdout.strip(), r"^[0-9a-f]{64}$")
        self.assertEqual(there.stdout.strip(), kernel_memo.construction_key(body))


class BooleanTest(KernelMemoCase):
    """Every boolean the layer sees runs non-destructive (``BOPAlgo_Options``): the kernel
    copies the sub-shapes it changes and shares the rest, so a boolean's inputs are left as
    they were given, and lineage by identity (``kernel_trace``) follows what it left alone."""

    def test_a_boolean_leaves_its_inputs_as_given_and_shares_what_it_leaves_alone(self) -> None:
        from build123d import Axis, Solid

        pristine = _bytes(Solid.make_cylinder(3, 30).wrapped)
        (box, tool, body), stats, _ = _run(_bored_plate)
        self.assertEqual(stats["unreplayable"], 0)
        self.assertEqual(_bytes(tool.wrapped), pristine, "the cut left its tool as it was given")
        side = box.faces().sort_by(Axis.X)[-1]
        bottom = box.faces().sort_by(Axis.Z)[0]
        self.assertTrue(any(face.wrapped.IsSame(side.wrapped) for face in body.faces()),
                        "a face the cut leaves alone keeps its TShape in the result")
        self.assertFalse(any(face.wrapped.IsPartner(bottom.wrapped) for face in body.faces()),
                         "a face the cut modifies is a new one")


class BuildAgreementTest(unittest.TestCase):
    """A model built cold, then hot in one process (``--force`` runs the body again, every
    construction a hit), stores one tree of one set of component bytes when its body reuses
    an input an operation changed: a boolean's tool after the boolean, a profile face after
    an extrusion (README law 18's pressure-test, at the store)."""

    TOOL_REUSED = """\
from cadgen import step
from cadgen import build123d as bd


@step
def plate():
    body = bd.Solid.make_box(20, 20, 8)
    tool = bd.Solid.make_cylinder(3, 30)
    bored = body.cut(tool)
    bored.label = "bored"
    peg = bd.Pos(30, 0, 0) * tool  # the tool again, after the cut
    peg.label = "peg"
    return bd.Compound(children=[bored, peg], label="plate")
"""

    PROFILE_REUSED = """\
from cadgen import step
from cadgen import build123d as bd


@step
def boss():
    profile = bd.Face(bd.Wire.make_circle(4))
    body = bd.Solid.extrude(profile, bd.Vector(0, 0, 4))
    body.label = "body"
    lid = bd.Solid.extrude(profile, bd.Vector(0, 0, -1))  # the profile again, after the extrusion
    lid.label = "lid"
    return bd.Compound(children=[body, bd.Pos(0, 0, -2) * lid], label="boss")
"""

    def setUp(self) -> None:
        temporary = generated_cad_directory(prefix="memo-build-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        env = mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(self.root / "store"), "CADGEN_DAEMON": "0"})
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("CADGEN_KERNEL_MEMO", None)
        kernel_memo.install()
        kernel_memo.clear()
        self.addCleanup(kernel_memo.clear)

    def build(self, script: Path, *flags: str) -> tuple[dict, dict]:
        """``(record, memo stats delta)`` of ``python script.py flags``, run in this process."""
        from cadgen.cli._run_model import run_model_argv
        from cadgen.store.records import read_record

        before = kernel_memo.stats()
        err = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            code = run_model_argv([str(script), *flags])
        self.assertEqual(code, 0, err.getvalue())
        record = read_record(script)
        self.assertIsNotNone(record, f"{script.name} has no record")
        return record, _delta(before, kernel_memo.stats())

    def components(self, record: dict) -> dict[str, bytes]:
        """Each component of the record's tree, by cid: its encoded BREP."""
        from cadgen.store.objects import read_object
        from cadgen.store.trees import get_tree

        return {cid: read_object(entry["brep"]) for cid, entry in get_tree(record["tree"])["components"].items()}

    def assert_cold_and_hot_agree(self, name: str, source: str) -> None:
        script = self.root / f"{name}.py"
        script.write_text(source, encoding="utf-8")
        cold, cold_stats = self.build(script)
        cold_components = self.components(cold)
        self.assertEqual(len(cold_components), 2)
        self.assertEqual((cold_stats["hits"], cold_stats["unreplayable"], cold_stats["errors"]), (0, 0, 0))
        hot, hot_stats = self.build(script, "--force")
        self.assertEqual((hot_stats["misses"], hot_stats["unreplayable"], hot_stats["errors"]), (0, 0, 0))
        self.assertEqual(hot_stats["hits"], cold_stats["misses"], "every construction of the cold run hit")
        self.assertEqual((hot["tree"], hot["key"]), (cold["tree"], cold["key"]))
        self.assertEqual(self.components(hot), cold_components)

    def test_a_tool_reused_after_its_boolean_builds_the_same_cold_and_hot(self) -> None:
        self.assert_cold_and_hot_agree("plate", self.TOOL_REUSED)

    def test_a_profile_reused_after_its_extrusion_builds_the_same_cold_and_hot(self) -> None:
        self.assert_cold_and_hot_agree("boss", self.PROFILE_REUSED)


if __name__ == "__main__":
    unittest.main()
