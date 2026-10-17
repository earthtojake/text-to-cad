"""Geometric tokens (``cadgen._internal.geometric_tokens``): the names of the elements no
construction names are functions of rounded geometry, of nothing positional, and survive the
STEP round trip; other geometry has another name; a body's names take its lineage's where
it has them and a token for each element it does not name; and a stored body's tokens are
measured once, remembered by its bytes."""

from __future__ import annotations

import math
import tempfile
import unittest
from pathlib import Path

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from build123d import Box, Compound, Cylinder, Pos, Rot, export_step, import_step  # noqa: E402

from cadgen._internal.geometric_tokens import (  # noqa: E402
    GEOMETRIC_TOKEN_SCHEME,
    RELATIVE_QUANTUM,
    TOKEN_RE,
    component_tokens,
    element_names,
    element_tokens,
    quantum_for_extent,
)


def _topods(shape):
    return getattr(shape, "wrapped", shape)


def _roundtrip(shape, directory: Path):
    path = directory / "shape.step"
    export_step(shape, str(path))
    return import_step(str(path))


class GeometricTokenTest(unittest.TestCase):
    def test_every_element_has_a_token_by_ordinal_under_the_scheme(self) -> None:
        tokens = element_tokens(_topods(Box(10, 20, 30)))
        self.assertEqual(sorted(tokens), ["edges", "faces", "vertices"])
        self.assertEqual([len(tokens[name]) for name in ("faces", "edges", "vertices")], [6, 12, 8])
        for name, prefix in (("faces", "f"), ("edges", "e"), ("vertices", "v")):
            for token in tokens[name]:
                self.assertTrue(token.startswith(prefix + ":"), token)
                self.assertRegex(token, TOKEN_RE)
            self.assertEqual(len(set(tokens[name])), len(tokens[name]), "tokens are distinct")
        self.assertTrue(GEOMETRIC_TOKEN_SCHEME.startswith("cadgen-geometric-token-v"))

    def test_the_same_geometry_in_other_bytes_has_the_same_tokens(self) -> None:
        # Built twice, and built then read from STEP: other bytes, another order.
        self.assertEqual(element_tokens(_topods(Box(10, 20, 30))), element_tokens(_topods(Box(10, 20, 30))))
        with tempfile.TemporaryDirectory() as directory:
            original = Box(10, 20, 30) - Pos(0, 0, 10) * Cylinder(3, 20)
            read = _roundtrip(original, Path(directory))
        before, after = element_tokens(_topods(original)), element_tokens(_topods(read))
        for name in ("faces", "edges", "vertices"):
            self.assertEqual(sorted(before[name]), sorted(after[name]), f"{name} tokens survive the round trip")

    def test_other_geometry_has_other_tokens(self) -> None:
        box = set(element_tokens(_topods(Box(10, 20, 30)))["faces"])
        for other in (Box(10, 20, 31), Pos(0.1, 0, 0) * Box(10, 20, 30)):
            self.assertNotEqual(set(element_tokens(_topods(other))["faces"]), box, str(other))

    def test_elements_are_named_by_their_geometry_not_their_ordinal(self) -> None:
        from OCP.BRepAdaptor import BRepAdaptor_Surface
        from OCP.TopAbs import TopAbs_FACE
        from OCP.TopExp import TopExp
        from OCP.TopTools import TopTools_IndexedMapOfShape
        from OCP.TopoDS import TopoDS

        # The +Z cap of one box has the token of the +Z cap of another, whatever its ordinal.
        def top_token(shape):
            tokens = element_tokens(shape)
            found = TopTools_IndexedMapOfShape()
            TopExp.MapShapes_s(shape, TopAbs_FACE, found)
            for ordinal in range(1, found.Extent() + 1):
                face = TopoDS.Face_s(found.FindKey(ordinal))
                plane = BRepAdaptor_Surface(face).Plane()
                if abs(plane.Location().Z() - 15.0) < 1e-9:
                    return tokens["faces"][ordinal - 1]
            raise AssertionError("no top face")

        self.assertEqual(top_token(_topods(Box(10, 20, 30))), top_token(_topods(Rot(0, 0, 180) * Box(10, 20, 30))))

    def test_coincident_elements_are_told_apart_deterministically(self) -> None:
        # Two solids sharing a face: two faces with one geometry, two tokens, the same twice.
        pair = Compound(children=[Box(10, 10, 10), Pos(10, 0, 0) * Box(10, 10, 10)])
        first, second = element_tokens(_topods(pair)), element_tokens(_topods(pair))
        self.assertEqual(first, second)
        self.assertEqual(len(first["faces"]), 12)
        self.assertEqual(len(set(first["faces"])), 12)
        self.assertEqual(len(set(first["vertices"])), len(first["vertices"]))

    def test_an_edge_the_kernel_built_without_vertices_is_named_by_its_curve(self) -> None:
        # A closed edge made straight from its curve has no vertices (a loft or sweep
        # leaves such edges); its ends are read off the curve, not off a null vertex.
        from OCP.BRep import BRep_Builder
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
        from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt
        from OCP.Geom import Geom_Circle
        from OCP.TopoDS import TopoDS_Edge

        from cadgen._internal.geometric_tokens import _edge_facts
        from cadgen._internal.topology_extract import component_metrics

        def facts(edge):
            return _edge_facts(edge, component_metrics(edge)["edges"][0])

        circle = Geom_Circle(gp_Ax2(gp_Pnt(1, 2, 3), gp_Dir(0, 0, 1)), 5.0)
        bare = TopoDS_Edge()
        BRep_Builder().MakeEdge(bare, circle, 1e-7)
        with_vertices = BRepBuilderAPI_MakeEdge(circle).Edge()
        for bare_end, vertex_end in zip(facts(bare)["ends"], facts(with_vertices)["ends"]):
            for a, b in zip(bare_end, vertex_end):
                self.assertAlmostEqual(a, b, places=9)
        self.assertAlmostEqual(facts(bare)["length"], 2 * math.pi * 5.0, places=6)

    def test_the_quantum_is_a_power_of_two_relative_to_the_extent(self) -> None:
        for extent in (0.001, 1.0, 37.5, 1e4):
            quantum = quantum_for_extent(extent)
            self.assertEqual(math.log2(quantum), round(math.log2(quantum)), "a power of two")
            self.assertLessEqual(quantum, extent * RELATIVE_QUANTUM)
            self.assertGreater(quantum, extent * RELATIVE_QUANTUM / 2)
        self.assertEqual(quantum_for_extent(0.0), 2.0 ** -40)


class ElementNamesTest(unittest.TestCase):
    def test_a_lineage_names_what_it_names_and_a_token_the_rest(self) -> None:
        box = _topods(Box(10, 20, 30))
        tokens = element_tokens(box)
        lineage = {"faces": ["f:part.make_box1.1", None, *[f"f:part.make_box1.{n}" for n in range(3, 7)]],
                   "edges": [f"e:part.make_box1.{n}" for n in range(1, 13)],
                   "vertices": [f"v:part.make_box1.{n}" for n in range(1, 9)]}
        names = element_names(lineage, box)
        self.assertEqual(names["faces"][1], tokens["faces"][1])
        self.assertEqual(names["faces"][0], "f:part.make_box1.1")
        self.assertEqual(names["edges"], lineage["edges"])
        self.assertEqual(element_names(None, box), tokens, "no lineage: every element by its token")

    def test_a_lineage_that_names_every_element_measures_nothing(self) -> None:
        from unittest import mock

        lineage = {"faces": [f"f:a.b1.{n}" for n in range(1, 7)], "edges": [f"e:a.b1.{n}" for n in range(1, 13)],
                   "vertices": [f"v:a.b1.{n}" for n in range(1, 9)]}
        with mock.patch("cadgen._internal.geometric_tokens.element_tokens", side_effect=AssertionError("measured")):
            self.assertEqual(element_names(lineage, _topods(Box(1, 2, 3)))["faces"], lineage["faces"])

    def test_a_lineage_of_another_body_is_refused(self) -> None:
        lineage = {"faces": [None], "edges": [], "vertices": []}
        with self.assertRaisesRegex(ValueError, "does not describe this shape"):
            element_names(lineage, _topods(Box(1, 2, 3)))


class RememberedTokensTest(unittest.TestCase):
    def test_a_stored_bodys_tokens_are_measured_once_by_its_bytes(self) -> None:
        """Asked again -- by this process or another -- for the body a component's codec and
        BREP object name, the tokens are the store's, and nothing is measured."""
        import os
        from unittest import mock

        from cadgen.store import bounds

        box = _topods(Box(10, 20, 30))
        with tempfile.TemporaryDirectory() as store, mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": store}):
            component = ("bintools-v4", "a" * 64)
            measured = component_tokens(box, component)
            self.assertEqual(measured, element_tokens(box))
            bounds.clear()
            with mock.patch("cadgen._internal.geometric_tokens.element_tokens",
                            side_effect=AssertionError("measured again")):
                self.assertEqual(component_tokens(box, component), measured)


if __name__ == "__main__":
    unittest.main()
