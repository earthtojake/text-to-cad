"""A GSL concept as a part of an assembly: ``cad.gsl.concept`` and ``cad.gsl.baked``, what the document keeps of
them, what refuses a part with no shape, and ``fit`` and ``bake`` given the assembly alone.

Declaring a concept and carrying it through a document need the kernel and no omega. The assembly's checks score
points with omega's evaluator (the omega-core wheel: requirements-dev.txt installs it on macOS and Linux) and skip,
by name, where it is absent. An assembly is given to them as the plan ``cad.omega._fit.as_plan`` writes of one
(its exact parts as a GLB, its concepts as JSON), written here by hand, so no engine runs.
"""

from __future__ import annotations

import importlib.util
import json
import struct
import tempfile
import unittest
from pathlib import Path

import numpy as np

HAS_OMEGA = importlib.util.find_spec("omega_core") is not None
NEEDS_OMEGA = "needs omega-core (cad[omega]: macOS and Linux)"

_CORNERS = np.array([[x, y, z] for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)], dtype=np.float64)
_FACES = np.array([[0, 1, 3], [0, 3, 2], [4, 6, 7], [4, 7, 5], [0, 4, 5], [0, 5, 1],
                   [2, 3, 7], [2, 7, 6], [0, 2, 6], [0, 6, 4], [1, 5, 7], [1, 7, 3]])

# A slab 40 x 40 mm, 4 thick, its top at z = 0 in its own frame; ``t`` is ranged.
SLAB = "@scene(60)\n@range(2, 8) t = 4.0;\nslab = max(abs(p.x) - 20.0, abs(p.y) - 20.0, abs(p.z + t / 2.0) - t / 2.0);\nreturn slab;\n"
# A block 20 x 20 x 10 about its own origin.
BLOCK = "@scene(40)\n@range(5, 15) w = 10.0;\nblock = max(abs(p.x) - w, abs(p.y) - 10.0, abs(p.z) - 5.0);\nreturn block;\n"


def box(half, at=(0.0, 0.0, 0.0)):
    return _CORNERS * np.asarray(half) + np.asarray(at), _FACES


def write_glb(path: Path, bodies: dict) -> Path:
    """A binary glTF of named bodies, ``name -> (points (n, 3) mm, triangles (t, 3))``, Z up, in metres, as the
    engine writes one."""
    blob = b""
    views, accessors, meshes, nodes = [], [], [], []
    for index, (name, (points, triangles)) in enumerate(bodies.items()):
        for data, kind, component in ((np.asarray(points, np.float64) / 1000.0, "VEC3", 5126),
                                      (np.asarray(triangles).reshape(-1), "SCALAR", 5125)):
            data = np.asarray(data, "<f4" if component == 5126 else "<u4")
            views.append({"buffer": 0, "byteOffset": len(blob), "byteLength": data.nbytes})
            accessors.append({"bufferView": len(views) - 1, "componentType": component, "type": kind,
                              "count": int(len(data))})
            blob += data.tobytes()
        meshes.append({"name": name, "primitives": [{"attributes": {"POSITION": 2 * index}, "indices": 2 * index + 1}]})
        nodes.append({"mesh": index, "name": name, "extras": {"cadUpAxis": "z"}})
    document = json.dumps({"asset": {"version": "2.0"}, "buffers": [{"byteLength": len(blob)}], "bufferViews": views,
                           "accessors": accessors, "meshes": meshes, "nodes": nodes,
                           "scenes": [{"nodes": list(range(len(nodes)))}], "scene": 0}).encode()
    document += b" " * (-len(document) % 4)
    blob += b"\0" * (-len(blob) % 4)
    path.write_bytes(struct.pack("<4sII", b"glTF", 2, 28 + len(document) + len(blob))
                     + struct.pack("<I4s", len(document), b"JSON") + document
                     + struct.pack("<I4s", len(blob), b"BIN\0") + blob)
    return path


def placed(x: float = 0.0, y: float = 0.0, z: float = 0.0) -> list[float]:
    """A translation as a structure holds an instance's placement: 16 floats, column-major."""
    return [1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0, 0, x, y, z, 1.0]


class Folder(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(lambda: __import__("shutil").rmtree(self.folder, ignore_errors=True))
        self.slab = self.folder / "slab.gsl"
        self.slab.write_text(SLAB, encoding="utf-8")
        self.block = self.folder / "block.gsl"
        self.block.write_text(BLOCK, encoding="utf-8")


class Declaring(Folder):
    def test_a_concept_is_a_part_with_no_shape_that_names_its_file_and_values(self) -> None:
        from cad import gsl
        from cad.engine.declarations import CONCEPT

        part = gsl.concept(self.slab, t=6)
        self.assertEqual("slab", part.label)
        self.assertEqual([], list(part.faces()))
        held = part.__dict__[CONCEPT]
        self.assertEqual((self.slab.as_posix(), "body", {"t": 6.0}), (held["gsl"], held["role"], held["values"]))
        self.assertEqual("base", gsl.concept(self.slab, label="base").label)
        self.assertNotIn("values", gsl.concept(self.slab).__dict__[CONCEPT])

    def test_the_digest_is_the_file_s_text_as_the_model_read_it(self) -> None:
        from cad import gsl
        from cad.engine.declarations import CONCEPT

        before = gsl.concept(self.slab).__dict__[CONCEPT]["digest"]
        self.assertEqual(before, gsl.concept(self.slab).__dict__[CONCEPT]["digest"])
        self.slab.write_text(SLAB.replace("20.0", "25.0"), encoding="utf-8")
        self.assertNotEqual(before, gsl.concept(self.slab).__dict__[CONCEPT]["digest"])

    def test_a_placed_or_copied_concept_keeps_what_it_names(self) -> None:
        import build123d as bd

        from cad import gsl
        from cad.engine.declarations import CONCEPT

        part = gsl.concept(self.slab)
        self.assertEqual(part.__dict__[CONCEPT], part.moved(bd.Location((5, 0, 0))).__dict__[CONCEPT])

    def test_a_baked_part_names_its_concept_and_stays_the_part(self) -> None:
        import build123d as bd

        from cad import gsl
        from cad.engine.declarations import CONCEPT

        part = bd.Box(20, 20, 10)
        self.assertIs(part, gsl.baked(part, self.block, w=10))
        self.assertEqual(("baked", {"w": 10.0}), (part.__dict__[CONCEPT]["role"], part.__dict__[CONCEPT]["values"]))
        self.assertEqual(6, len(part.faces()))

    def test_what_is_no_concept_is_refused_by_name(self) -> None:
        import build123d as bd

        from cad import gsl

        with self.assertRaisesRegex(ValueError, r"a concept is a \.gsl file, not part\.step"):
            gsl.concept(self.folder / "part.step")
        with self.assertRaisesRegex(FileNotFoundError, "gone.gsl is not there"):
            gsl.concept(self.folder / "gone.gsl")
        with self.assertRaisesRegex(ValueError, "a finite number by its name"):
            gsl.concept(self.slab, t=float("nan"))
        with self.assertRaisesRegex(TypeError, "a build123d shape, not str"):
            gsl.baked("knob", self.block)
        assembly = bd.Compound(children=[bd.Box(1, 1, 1), bd.Box(2, 2, 2)])
        with self.assertRaisesRegex(ValueError, "is an assembly"):
            gsl.baked(assembly, self.block)


class Document(Folder):
    def device(self):
        import build123d as bd

        from cad import gsl

        board = bd.Box(30, 20, 2)
        board.label = "board"
        knob = bd.Box(20, 20, 10).moved(bd.Location((0, 0, 30)))
        knob.label = "knob"
        gsl.baked(knob, self.block)
        base = gsl.concept(self.slab, label="base", t=6).moved(bd.Location((0, 0, -1)))
        device = bd.Compound(children=[board, knob, base])
        device.label = "device"
        return device

    def saved(self) -> Path:
        from cad.engine import document

        tree = document.collect(self.device(), "device")
        path = self.folder / "device.xbf"
        document.save(document.to_xcaf(tree), path, compare=False, tree=tree)
        return path

    def test_the_document_keeps_each_concept_on_its_part_through_the_file(self) -> None:
        from cad.engine import document

        tree = document.collect(self.device(), "device")
        path = self.folder / "device.xbf"
        document.save(document.to_xcaf(tree), path, compare=False, tree=tree)
        read = document.Loaded(path).structure()
        by_name = {prototype["name"]: prototype for prototype in read["prototypes"]}
        self.assertNotIn("concept", by_name["board"])
        self.assertEqual(("baked", self.block.as_posix()), (by_name["knob"]["concept"]["role"], by_name["knob"]["concept"]["gsl"]))
        self.assertEqual(("body", {"t": 6.0}), (by_name["base"]["concept"]["role"], by_name["base"]["concept"]["values"]))
        # The part with no shape stands where the model placed it.
        base = next(instance for instance in read["instances"] if instance["path"] == "device/base")
        self.assertEqual([0.0, 0.0, -1.0], [round(value, 6) for value in base["matrix"][12:15]])
        # And the structure made from the tree in memory says the same as the file read back.
        made = document.tree_structure(tree, path)
        self.assertEqual([prototype.get("concept") for prototype in read["prototypes"]],
                         [prototype.get("concept") for prototype in made["prototypes"]])

    def test_two_placements_of_one_concept_with_other_values_are_two_parts(self) -> None:
        import build123d as bd

        from cad import gsl
        from cad.engine import document

        pair = bd.Compound(children=[gsl.concept(self.slab, label="a", t=3), gsl.concept(self.slab, label="b", t=5)])
        tree = document.collect(pair, "pair")
        self.assertEqual([{"t": 3.0}, {"t": 5.0}], [part.declared["concept"]["values"] for part in tree.parts])

    def test_concepts_that_share_one_empty_shape_stay_parts_of_their_own_in_the_file(self) -> None:
        # The engine keeps a shape by what it holds, so every part with no shape may come back as one shape:
        # the file must still hold a part for each, with its own name and concept.
        import build123d as bd

        from cad import gsl
        from cad.engine import document
        from cad.engine.declarations import CONCEPT

        first = gsl.concept(self.slab, label="base")
        parts = [first]
        for label, path, values, at in (("lid", self.block, {}, 0), ("knob", self.slab, {"t": 6}, 14)):
            shared = bd.Compound(first.wrapped).moved(bd.Location((0, 0, at)))
            shared.label = label
            shared.__dict__[CONCEPT] = gsl.concept(path, label=label, **values).__dict__[CONCEPT]
            parts.append(shared)
        tree = document.collect(bd.Compound(children=parts, label="device"), "device")
        path = self.folder / "device.xbf"
        document.save(document.to_xcaf(tree), path, compare=False, tree=tree)
        read = document.Loaded(path).structure()
        self.assertEqual([("base", "slab.gsl", None), ("lid", "block.gsl", None), ("knob", "slab.gsl", {"t": 6.0})],
                         [(read["prototypes"][instance["prototype"]]["name"],
                           Path(read["prototypes"][instance["prototype"]]["concept"]["gsl"]).name,
                           read["prototypes"][instance["prototype"]]["concept"].get("values"))
                          for instance in read["instances"]])

    def test_a_step_of_a_document_holding_a_concept_is_refused_by_the_part_s_name(self) -> None:
        from cad.engine import export

        path = self.saved()
        with self.assertRaisesRegex(export.ExportRefused, r"holds a concept with no exact shape: base \(slab\.gsl\)"):
            export.translate(str(path), None, self.folder / "device.step")
        self.assertFalse((self.folder / "device.step").exists())

    def test_a_file_of_triangles_holds_the_exact_parts_and_says_which_part_it_leaves_out(self) -> None:
        from cad.engine import export
        from cad.engine.formats.gltf import read_gltf

        heard: list[str] = []
        export.translate(str(self.saved()), None, self.folder / "device.glb", told=heard.append)
        self.assertTrue(any("not in this file: base (slab.gsl)" in line for line in heard), heard)
        read = read_gltf(self.folder / "device.glb")
        self.assertEqual({"board", "knob"}, {name for index, _matrix, name in read.placed if len(read.parts[index].triangles)})

    def test_a_snapshot_of_a_document_holding_a_concept_is_refused_before_anything_is_drawn(self) -> None:
        from cad.engine import document, snapshot

        structure = document.Loaded(self.saved()).structure()
        with self.assertRaisesRegex(snapshot.SnapshotRefused, r"holds a concept OCCT does not draw: base \(slab\.gsl\)") as refused:
            snapshot.refusals(None, structure, "device")
        self.assertEqual("source", refused.exception.part)

    def test_a_baked_part_alone_is_drawn_and_exported_as_any_exact_part(self) -> None:
        import build123d as bd

        from cad import gsl
        from cad.engine import document, export

        knob = bd.Box(20, 20, 10)
        knob.label = "knob"
        gsl.baked(knob, self.block)
        tree = document.collect(knob, "knob")
        path = self.folder / "knob.xbf"
        document.save(document.to_xcaf(tree), path, compare=False, tree=tree)
        self.assertGreater(export.translate(str(path), None, self.folder / "knob.step"), 0)


class Clock(Folder):
    def test_a_model_that_reads_time_is_said_to_and_one_that_names_it_in_a_comment_is_not(self) -> None:
        from cad.omega._shader import _timed

        self.assertFalse(_timed(self.slab))
        moving = self.folder / "pulse.gsl"
        moving.write_text("@scene(40)\nr = 5.0 + sin(time);\nreturn length(p) - r;\n", encoding="utf-8")
        self.assertTrue(_timed(moving))
        noted = self.folder / "still.gsl"
        noted.write_text("@scene(40)\n// no time here\n/* nor\n time */\nreturn length(p) - 5.0;\n", encoding="utf-8")
        self.assertFalse(_timed(noted))


class Placing(unittest.TestCase):
    def sampled(self):
        from cad.omega._fit import sample

        with tempfile.TemporaryDirectory() as folder:
            return sample(write_glb(Path(folder) / "parts.glb", {"board": box((15, 10, 1)), "knob": box((10, 10, 5), (0, 0, 30))}), density=1.0)

    def test_the_exact_surface_is_taken_into_the_concept_s_frame(self) -> None:
        from cad.omega._fit import _in_frame

        frame = np.eye(4)
        frame[:3, 3] = (0, 0, 30)
        moved = _in_frame(self.sampled(), {"frame": frame, "only": None})
        self.assertEqual(["board", "knob"], moved.names)
        knob = moved.points[moved.part == 1]
        self.assertTrue(np.allclose(np.max(np.abs(knob) / [10, 10, 5], axis=1), 1.0, atol=1e-4))  # about its own origin
        self.assertEqual(self.sampled().triangles.shape, moved.triangles.shape)

    def test_a_baked_part_is_held_alone(self) -> None:
        from cad.omega._fit import _in_frame

        frame = np.eye(4)
        frame[:3, 3] = (0, 0, 30)
        alone = _in_frame(self.sampled(), {"frame": frame, "only": {"part": "knob", "matrix": frame}})
        self.assertEqual(["knob"], alone.names)
        self.assertTrue((alone.part == 0).all())
        self.assertEqual((12, 3, 3), alone.triangles.shape)
        self.assertIsNone(_in_frame(self.sampled(), {"frame": frame, "only": {"part": "lid", "matrix": frame}}))


@unittest.skipUnless(HAS_OMEGA, NEEDS_OMEGA)
class Assembly(Folder):
    def plan(self, bodies: dict, concepts: list[dict]) -> Path:
        glb = write_glb(self.folder / "exact.glb", bodies)
        plan = self.folder / "concepts.json"
        plan.write_text(json.dumps({"document": "device", "exact": str(glb), "concepts": concepts}), encoding="utf-8")
        return plan

    def base(self, z: float, **values: float) -> dict:
        return {"part": "base", "path": "device/base", "gsl": str(self.slab), "role": "body", "values": values, "matrix": placed(z=z)}

    def knob(self, z: float) -> dict:
        return {"part": "knob", "path": "device/knob", "gsl": str(self.block), "role": "baked", "values": {}, "matrix": placed(z=z)}

    def test_fit_holds_every_exact_part_to_the_concept_where_the_assembly_places_it(self) -> None:
        from cad.gsl import fit

        # A board resting on the slab's top, which the assembly places at z = 10.
        bodies = {"board": box((15, 10, 1), (0, 0, 11))}
        result = fit(self.plan(bodies, [self.base(10)]))
        self.assertTrue(result.ok, result.findings)
        (held,) = result.measurements["concepts"]
        self.assertEqual(("base", "body", 0.0), (held["part"], held["role"], round(held["parts"][0]["clearance_mm"], 4)))
        # The same board with the slab left at the origin stands 10 mm clear of it: the placement is what is held.
        clear = fit(self.plan(bodies, [self.base(0)]))
        self.assertEqual(10.0, round(clear.measurements["concepts"][0]["parts"][0]["clearance_mm"], 4))

    def test_fit_takes_the_values_the_assembly_gives_the_concept(self) -> None:
        from cad.gsl import fit

        # A block hanging 5 mm under the slab's top: clear of a slab 4 thick, inside one 8 thick.
        bodies = {"block": box((5, 5, 0.5), (0, 0, -5.5))}
        self.assertTrue(fit(self.plan(bodies, [self.base(0)])).ok)
        thick = fit(self.plan(bodies, [self.base(0, t=8)]))
        self.assertFalse(thick.ok)
        self.assertEqual(["interference"], [finding.code for finding in thick.findings])

    def test_bake_holds_each_baked_part_to_its_own_concept_alone_in_the_part_s_frame(self) -> None:
        from cad.gsl import bake

        # The knob is the block exactly, placed 30 up; the board beside it is no part of the bake.
        bodies = {"board": box((15, 10, 1)), "knob": box((10, 10, 5), (0, 0, 30))}
        result = bake(self.plan(bodies, [self.base(-1), self.knob(30)]))
        self.assertTrue(result.ok, result.findings)
        (held,) = result.measurements["concepts"]
        self.assertEqual(("knob", ["knob"]), (held["part"], [row["part"] for row in held["parts"]]))
        self.assertLess(held["parts"][0]["max_mm"], 1e-3)
        self.assertTrue((self.folder / "block.baked.gsl").is_file())
        # And the bake is not stale until the concept moves.
        self.assertTrue(bake(self.plan(bodies, [self.knob(30)]), stale=True).ok)
        self.block.write_text(BLOCK.replace("w = 10.0", "w = 12.0"), encoding="utf-8")
        stale = bake(self.plan(bodies, [self.knob(30)]), stale=True)
        self.assertFalse(stale.ok)
        self.assertEqual({"stale"}, {finding.code for finding in stale.findings})

    def test_an_assembly_with_no_concept_of_the_kind_is_said_so(self) -> None:
        from cad.gsl import bake, fit

        bodies = {"knob": box((10, 10, 5), (0, 0, 30))}
        none = fit(self.plan(bodies, [self.knob(30)]))
        self.assertEqual(["no_concepts"], [finding.code for finding in none.findings])
        self.assertIn("no part that is a concept", none.findings[0].message)
        self.assertEqual(["no_concepts"], [finding.code for finding in bake(self.plan(bodies, [self.base(0)])).findings])

    def test_an_assembly_takes_no_value_or_contact_of_the_command_s(self) -> None:
        from cad.gsl import fit

        plan = self.plan({"board": box((15, 10, 1), (0, 0, 11))}, [self.base(10)])
        self.assertEqual(["bad_define"], [finding.code for finding in fit(plan, define=("t=6",)).findings])
        self.assertEqual(["bad_define"], [finding.code for finding in fit(plan, contact=("0,0,10",)).findings])


if __name__ == "__main__":
    unittest.main()
