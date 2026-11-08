"""The cadquery integration's bridge: a CadQuery value described portably, and the engine's reading of it.

CadQuery runs on an OCP build of its own, so ``model(value, name=...)`` in a CadQuery program sends the
engine a description -- the reader's header and one BinTools dump (``cad.cadquery._bridge.portable``) -- which
a kernel process of the engine's reads back into a build123d tree and makes the document of
(``cad.engine.portable``). Here the values are stand-ins with CadQuery's class names and attributes on
build123d's shapes (``tests/python/support/cadquery_like.py``): the matcher reads names alone, the bridge
packs with whatever OCP it runs on, and the reading side is the real one. The real CadQuery round trip is the
``cadquery`` job's (``tests/python/packages/cadquery``).
"""

from __future__ import annotations

import unittest

from tests.python.support import cadquery_like as cq
from tests.python.support.paths import add_sources

add_sources()

from cad import registry  # noqa: E402
from cad.cadquery import _bridge  # noqa: E402
from cad.engine import portable  # noqa: E402


def _box(x: float, y: float, z: float):
    import build123d as bd

    return bd.Box(x, y, z)


class TheMatcherReadsNamesAlone(unittest.TestCase):
    def test_cadquery_s_four_kinds_are_told_by_their_class_s_ancestry(self) -> None:
        self.assertEqual(_bridge.kind_of(cq.Workplane()), "Workplane")
        self.assertEqual(_bridge.kind_of(cq.Compound(None)), "Shape", "a subclass is the Shape it descends from")
        self.assertEqual(_bridge.kind_of(cq.Sketch(None)), "Sketch")
        self.assertEqual(_bridge.kind_of(cq.Assembly()), "Assembly")
        self.assertIsNone(_bridge.kind_of(cq.Vector()), "a CadQuery value that is no shape is not handed over")
        self.assertIsNone(_bridge.kind_of(_box(1, 1, 1)), "a build123d shape is the kernel's own")
        self.assertIsNone(_bridge.kind_of(object()))

    def test_the_registry_hands_a_cadquery_value_over_and_writes_no_file_of_it(self) -> None:
        found = registry.producer_for("model", cq.Workplane(cq.Shape(_box(1, 1, 1).wrapped)))
        self.assertEqual((found.integration, found.portable, found.writer),
                         ("cadquery", True, "cad.cadquery._bridge.portable"))
        for kind in ("step", "xbf", "stl"):
            with self.subTest(kind=kind), self.assertRaises(TypeError) as caught:
                registry.producer_for(kind, cq.Assembly(), where="model m.py::m")
            self.assertIn(f"the cadquery integration has no producer of {kind} from Assembly", str(caught.exception))
        self.assertIn("model(value, name=...) handing over a CadQuery Workplane, Shape, Sketch or Assembly (cadquery:",
                      registry.help_text("model"))
        from cad._internal import integrations

        self.assertEqual(integrations.for_module("cadquery.cq"), "cadquery")
        self.assertEqual(integrations.for_distribution("CadQuery"), "cadquery")


class TheDescription(unittest.TestCase):
    def test_a_shape_is_one_part_named_by_its_label_or_the_document_s_name(self) -> None:
        header, shapes, locations = _bridge.describe(cq.Shape(_box(2, 3, 4).wrapped, label="lid"), "part")
        self.assertEqual([product["name"] for product in header["products"]], ["lid"])
        self.assertEqual((len(shapes), len(locations), header["roots"][0]["product"]), (1, 1, 0))
        self.assertTrue(locations[0].IsIdentity())
        header, _shapes, _locations = _bridge.describe(cq.Shape(_box(2, 3, 4).wrapped), "part")
        self.assertEqual(header["products"][0]["name"], "part", "no label: the document's name")

    def test_a_workplane_s_stack_is_one_part_and_a_stack_with_no_shape_is_refused(self) -> None:
        header, shapes, _locations = _bridge.describe(
            cq.Workplane(cq.Shape(_box(1, 1, 1).wrapped), cq.Vector(), cq.Shape(_box(2, 2, 2).wrapped)), "pair")
        self.assertEqual(len(shapes), 1, "several shapes make one compound")
        self.assertEqual(header["products"][0]["name"], "pair")
        with self.assertRaisesRegex(ValueError, "the Workplane's stack holds Vector, and no shape"):
            _bridge.describe(cq.Workplane(cq.Vector()), "points")
        with self.assertRaisesRegex(ValueError, "the Workplane's stack is empty, and no shape"):
            _bridge.describe(cq.Workplane(), "nothing")
        with self.assertRaisesRegex(ValueError, "the Sketch has no faces"):
            _bridge.describe(cq.Sketch(None), "sketch")

    def test_an_assembly_is_its_tree_with_names_colours_and_placements(self) -> None:
        header, shapes, locations = _bridge.describe(cq.bracket_assembly(), "bracket")
        kinds = [(product["name"], product["assembly"], product["color"]) for product in header["products"]]
        self.assertEqual(kinds, [("bracket_assembly", True, None), ("plate", False, [0.3, 0.5, 0.8, 1.0]),
                                 ("peg", False, [1.0, 0.0, 0.0, 1.0])])
        root = header["products"][0]
        self.assertEqual([component["product"] for component in root["components"]], [1, 2])
        self.assertEqual(len(shapes), 2)
        peg_location = locations[root["components"][1]["location"]]
        self.assertEqual([round(peg_location.Transformation().TranslationPart().Coord(axis), 6) for axis in (1, 2, 3)],
                         [10.0, 0.0, 8.0])
        self.assertTrue(locations[header["roots"][0]["location"]].IsIdentity())
        # A node with children and a shape of its own: the shape a part component named as the node.
        parent = cq.Assembly(cq.plate(), name="base", color=cq.Color(0.1, 0.2, 0.3))
        parent.add(cq.peg(), loc=cq.at(0, 0, 6), name="pin")
        header, shapes, _locations = _bridge.describe(parent, "nested")
        self.assertEqual([(product["name"], product["assembly"]) for product in header["products"]],
                         [("base", True), ("base", False), ("pin", False)])
        with self.assertRaisesRegex(ValueError, "empty holds no shape"):
            _bridge.describe(cq.Assembly(name="empty"), "empty")


class TheEngineReadsItBack(unittest.TestCase):
    def test_the_portable_description_is_a_tree_and_a_document_in_the_engine_s_kernel(self) -> None:
        import build123d as bd

        header, data = _bridge.portable(cq.bracket_assembly(), "bracket")
        self.assertEqual((header["format"], header["integration"], header["shapes"], header["locations"]),
                         (portable.FORMAT, "cadquery", 2, 3))
        self.assertTrue(header["kernel"].startswith("cadquery-ocp"), header["kernel"])
        self.assertIsInstance(data, bytes)
        root = portable.tree(header, data)
        self.assertIsInstance(root, bd.Compound)
        self.assertEqual(root.label, "bracket_assembly")
        self.assertEqual([child.label for child in root.children], ["plate", "peg"])
        peg = root.children[1]
        self.assertAlmostEqual(peg.bounding_box().center().Z, 8.0, places=6, msg="placed where the assembly put it")
        rgb = peg.color.wrapped.GetRGB()
        self.assertEqual([round(channel, 3) for channel in (rgb.Red(), rgb.Green(), rgb.Blue(), peg.color.wrapped.Alpha())],
                         [1.0, 0.0, 0.0, 1.0])
        from cad.engine import document, reader

        doc = document.read_bytes(portable.document_bytes(header, data, "bracket"))
        described, shapes, _locations = reader.describe(doc, False)
        self.assertEqual(sorted(product["name"] for product in described["products"]), ["bracket_assembly", "peg", "plate"])
        self.assertEqual(len(shapes), 2)

    def test_a_description_is_checked_before_anything_is_read(self) -> None:
        header, data = _bridge.portable(cq.plate(), "plate")
        for broken, said in (({**header, "format": "portable/0"}, "format 'portable/0' is not portable/1"),
                             ({**header, "products": None}, "names its products and its roots"),
                             ({**header, "shapes": "2"}, "counts its shapes"),
                             ({**header, "locations": -1}, "counts its locations"),
                             ({**header, "roots": []}, "places at least one root"),
                             ({**header, "roots": [{"product": 3, "location": 0}]}, "root 0 names product 3 of 1"),
                             ({**header, "roots": [{"product": 0, "location": 1}]}, "root 0 names location 1 of 1"),
                             ({**header, "products": [{"name": "p", "assembly": False, "shape": 4}]},
                              "product 0 names shape 4 of 1"),
                             ("not a header", "is a JSON object")):
            with self.subTest(said=said), self.assertRaisesRegex(ValueError, said):
                portable.tree(broken, data)
        with self.assertRaisesRegex(ValueError, "the dump holds 2 shapes and locations, and its description counts 1 and 2"):
            portable.tree({**header, "locations": 2}, data)


class TheHandOverTakesItAndRefusesTheRest(unittest.TestCase):
    def test_a_value_no_producer_takes_is_refused_naming_what_is_taken(self) -> None:
        from cad.engine import api

        with self.assertRaises(TypeError) as caught:
            api.hand_over({"not": "a shape"}, "thing")
        said = str(caught.exception)
        self.assertIn("model() takes a function to declare, or a shape and its name=", said)
        self.assertIn("a build123d Shape a model returns or a CadQuery Workplane, Shape, Sketch or Assembly", said)
        self.assertIn("not dict", said)
        with self.assertRaisesRegex(TypeError, "animations= goes with a build123d shape; a CadQuery .* takes none"):
            api.hand_over(cq.plate(), "plate", animations=[object()])


if __name__ == "__main__":
    unittest.main()
