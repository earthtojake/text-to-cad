"""The implicit document type without cadjoint: its bytes (``cad.engine.implicit_document``: a GLB of the sampled
mesh with the engine's words in its extras), ``@implicit`` as a declaration, and ``cad.implicit`` as a type.

A tetrahedron stands in for a field's sample, so every fact is known from the construction: four
triangles, a volume of one sixth, bounds of one. A ``Field`` is stood in for by its class's name and module,
which is all the producer's matcher reads."""

from __future__ import annotations

import os
import tempfile
import textwrap
import unittest
from pathlib import Path

import numpy as np

from cad.engine import implicit_document as implicit

POSITIONS = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
TRIANGLES = np.array([[0, 2, 1], [0, 1, 3], [1, 2, 3], [0, 3, 2]])
NORMALS = np.array([[-1.0, -1.0, -1.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])


class Field:  # cad.cadjoint.field(scene, cell=...), by its class's name and module alone
    __module__ = "cad.cadjoint._field"
    digest = "f" * 32


class DocumentBytesTest(unittest.TestCase):
    def test_the_bytes_are_a_glb_carrying_the_closure_the_digest_and_the_facts(self) -> None:
        data, facts = implicit.document_bytes("tet", POSITIONS, NORMALS, TRIANGLES, closure='{"schema":"x","key":"k"}',
                                              digest="d" * 32, cell=0.5)
        self.assertTrue(implicit.is_glb(data))
        self.assertEqual(facts["triangles"], 4)
        self.assertEqual(facts["bounds"], [1.0, 1.0, 1.0])
        self.assertAlmostEqual(facts["volume"], 1 / 6, places=3)
        extras = implicit.read_extras(data)
        self.assertEqual((extras["digest"], extras["cell"], extras["closure"], extras["format"]),
                         ("d" * 32, 0.5, '{"schema":"x","key":"k"}', "glb"))
        self.assertTrue(extras["writer"].startswith("cad.engine glb ("))
        self.assertEqual(extras["facts"], facts)
        # Read back as a mesh file is: one part, the tetrahedron's four triangles, no path.
        source = implicit.source_of(data, "tet")
        self.assertEqual(len(source.structure["prototypes"]), 1)
        self.assertEqual(source.structure["tree"]["name"], "tet")
        self.assertIsNone(source.path)
        mesh = next(iter(source.meshes.values()))
        self.assertEqual(mesh.triangles, 4)
        # Its closure rewritten, its binary chunk untouched.
        again = implicit.with_extras(data, {**extras, "closure": '{"schema":"x","key":"k2"}'})
        self.assertEqual(implicit.read_extras(again)["closure"], '{"schema":"x","key":"k2"}')
        self.assertEqual(implicit.source_of(again, "tet").meshes[mesh and next(iter(source.meshes))].triangles, 4)

    def test_bytes_that_are_no_document_of_the_engines_read_as_none(self) -> None:
        self.assertIsNone(implicit.read_extras(b"not a glb"))
        self.assertFalse(implicit.is_glb(b"xbf"))
        with tempfile.TemporaryDirectory() as folder:
            from cad.engine.export import translate

            path = Path(folder) / "plain.glb"
            translate(implicit._source("plain", POSITIONS, NORMALS, TRIANGLES), "glb", path)
            self.assertIsNone(implicit.read_extras(path.read_bytes()), "a GLB with no extras of ours")


def _cube() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """A unit cube welded at its eight corners, two triangles a side wound outward, each corner's normal the
    mean of its three sides' (as a sample's vertex on a crease carries one)."""
    positions = np.array([[x, y, z] for x in (0.0, 1.0) for y in (0.0, 1.0) for z in (0.0, 1.0)])
    quads = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    triangles = np.array([tri for a, b, c, d in quads for tri in ((a, b, c), (a, c, d))])
    normals = positions - 0.5
    return positions, normals / np.linalg.norm(normals, axis=1, keepdims=True), triangles


def _sphere(rings: int = 16, segments: int = 32) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """A welded UV sphere of radius 10, its normals the exact ones: no fold anywhere."""
    theta = np.linspace(0.0, np.pi, rings + 1)[1:-1]
    phi = np.linspace(0.0, 2 * np.pi, segments, endpoint=False)
    t, f = np.meshgrid(theta, phi, indexing="ij")
    ring = np.stack([np.sin(t) * np.cos(f), np.sin(t) * np.sin(f), np.cos(t)], -1).reshape(-1, 3)
    unit = np.concatenate([[[0.0, 0.0, 1.0]], ring, [[0.0, 0.0, -1.0]]])
    at = lambda r, s: 1 + r * segments + s % segments  # noqa: E731
    triangles = [(0, at(0, s), at(0, s + 1)) for s in range(segments)]
    for r in range(rings - 2):
        for s in range(segments):
            triangles += [(at(r, s), at(r + 1, s), at(r + 1, s + 1)), (at(r, s), at(r + 1, s + 1), at(r, s + 1))]
    south = len(unit) - 1
    triangles += [(south, at(rings - 2, s + 1), at(rings - 2, s)) for s in range(segments)]
    return unit * 10.0, unit, np.array(triangles)


def _drawn(positions: np.ndarray, normals: np.ndarray, triangles: np.ndarray) -> tuple:
    """The document of a sample read back: its mesh's points, normals and triangles."""
    data, _facts = implicit.document_bytes("part", positions, normals, triangles, closure=None, digest="d" * 32, cell=0.5)
    mesh = next(iter(implicit.source_of(data, "part").meshes.values()))
    return (np.asarray(mesh.positions, np.float64), np.asarray(mesh.normals, np.float64),
            np.asarray(mesh.indices, np.int64).reshape(-1, 3))


class FoldTest(unittest.TestCase):
    """A sample's vertex on a crease carries one normal for both sides; the document has one per side."""

    def test_a_cube_is_written_with_each_corner_once_per_side_shaded_flat(self) -> None:
        positions, normals, triangles = _cube()
        points, drawn, faces = _drawn(positions, normals, triangles)
        self.assertEqual((len(points), len(faces)), (24, 12), "each of the eight corners once per side it meets")
        a, b, c = (points[faces[:, k]] for k in range(3))
        planes = np.cross(b - a, c - a)
        planes /= np.linalg.norm(planes, axis=1, keepdims=True)
        for corner in range(3):
            agree = np.degrees(np.arccos(np.clip(np.einsum("ij,ij->i", drawn[faces[:, corner]], planes), -1, 1)))
            self.assertLess(agree.max(), 1.0, "every corner's normal is its side's plane's")
        np.testing.assert_allclose(points[faces], positions[triangles], atol=1e-6, err_msg="the same corners at the same points")
        facts = implicit.facts_of(positions, triangles)
        self.assertEqual((facts["triangles"], facts["volume"]), (12, 1.0), "the facts are the welded sample's")

    def test_a_smooth_sample_keeps_its_vertices_and_the_fields_normals(self) -> None:
        positions, normals, triangles = _sphere()
        points, drawn, faces = _drawn(positions, normals, triangles)
        self.assertEqual(len(points), len(positions))
        np.testing.assert_array_equal(faces, triangles)
        np.testing.assert_allclose(drawn, normals, atol=1e-6)

    def test_the_split_reindexes_only_the_folds_vertices(self) -> None:
        positions, normals, triangles = _cube()
        split_positions, split_normals, split_triangles = implicit.split_folds(positions, normals, triangles)
        self.assertEqual(split_positions.shape, (24, 3))
        np.testing.assert_array_equal(split_positions[:8], positions, "the sample's vertices keep their indices")
        np.testing.assert_array_equal(split_positions[split_triangles], positions[triangles])
        _edges, uses = np.unique(np.sort(np.concatenate([split_triangles[:, [0, 1]], split_triangles[:, [1, 2]],
                                                         split_triangles[:, [2, 0]]]), axis=1), axis=0, return_counts=True)
        self.assertEqual((int((uses == 2).sum()), int((uses == 1).sum())), (6, 24),
                         "each side's diagonal stays shared, each fold's edge is now one per side")
        # A fold within the crease is no fold: the cube's sides part by 90 degrees.
        self.assertEqual(len(implicit.split_folds(positions, normals, triangles, crease=95.0)[0]), 8)


class DeclarationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="implicit-decl-"))
        self.addCleanup(__import__("shutil").rmtree, self.folder, True)

    def _models(self, text: str) -> dict:
        import importlib.util

        script = self.folder / f"m{abs(hash(text)) % 10**8}.py"
        script.write_text(textwrap.dedent(text), encoding="utf-8")
        spec = importlib.util.spec_from_file_location(script.stem, script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return vars(module)

    def test_implicit_declares_a_model_of_its_own_kind_and_stacks_with_nothing(self) -> None:
        from cad._internal.document_type import ImplicitType
        from cad.engine.model import Model

        import cad

        self.assertIsInstance(cad.implicit, ImplicitType)
        found = self._models("""
            from cad import implicit

            @implicit
            def part():
                return None

            @implicit(name="named")
            def other():
                return None
        """)
        self.assertIsInstance(found["part"], Model)
        self.assertEqual((found["part"].kind, found["part"].outputs, found["other"].explicit_name), ("implicit", [], "named"))
        self.assertEqual(repr(found["part"])[:10], "<implicit ")
        for first, second in (("@model", "@implicit"), ("@implicit", "@model"), ('@stl("p.stl")', "@implicit"),
                              ("@implicit", '@stl("p.stl")')):
            with self.subTest(stacked=f"{first} {second}"):
                with self.assertRaises(TypeError) as caught:
                    self._models("\n".join(["from cad import implicit, model, stl", "", first, second, "def part():",
                                            "    return None", ""]))
                self.assertIn("never two of them", str(caught.exception))
        with self.assertRaises(TypeError):
            cad.implicit(object())

    def test_check_result_holds_each_kind_to_its_producer(self) -> None:
        from cad.engine.model import check_result

        found = self._models("""
            from cad import implicit, model

            @implicit
            def part():
                return None

            @model
            def shape():
                return None
        """)
        check_result(found["part"], Field())  # a field, the cadjoint integration's producer of an implicit document
        with self.assertRaises(TypeError) as caught:
            check_result(found["shape"], Field())
        self.assertIn("no producer of model from Field", str(caught.exception))

        class Shape:
            __module__ = "build123d.topology"

        with self.assertRaises(TypeError) as caught:
            check_result(found["part"], Shape())
        self.assertIn("cad.cadjoint.field(scene, cell=...)", str(caught.exception))

    def test_a_handle_of_the_other_in_memory_type_is_refused_by_name(self) -> None:
        from cad._internal.document_type import refuse_other
        from cad.engine.api import Document

        implicit_handle = Document("part", self.folder / "m.py", {"ok": True, "id": "x", "type": "implicit"}, self.folder)
        model_handle = Document("part", self.folder / "m.py", {"ok": True, "id": "x", "type": "model"}, self.folder)
        refuse_other("implicit", implicit_handle)
        refuse_other("model", model_handle)
        with self.assertRaisesRegex(ValueError, "is an implicit document, not a model: use cad.implicit"):
            refuse_other("model", implicit_handle)
        with self.assertRaisesRegex(ValueError, "is a model document, not an implicit: use cad.model"):
            refuse_other("implicit", model_handle)
        with self.assertRaisesRegex(ValueError, "cad.implicit takes a model's handle or its document id"):
            refuse_other("implicit", os.path.join(self.folder, "part.py"))
        with self.assertRaisesRegex(TypeError, "is an implicit document: the mesh sampled from its field"):
            implicit_handle.shape  # noqa: B018 - the property is the subject


if __name__ == "__main__":
    unittest.main()
