"""Verifying a written STEP against the result it was written from (``step_verify``).

A file verifies when a compile of it names every occurrence by the result's token and
gives it the result's part, and every part it holds has the result's faces and edges, each
named as the result names it and where the result has it within the display tolerance,
its faces drawn in the result's colours. Every other file differs, and the routine says
where: which occurrence or which part, and what.
"""

from __future__ import annotations

import dataclasses
import tempfile
import unittest
from pathlib import Path

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

_KEYS = {"bracket": f"{1:064x}-v7", "ball": f"{3:064x}-v7"}


def verify_step(path, expected, occurrences=None, colors=None, *, named=True):
    """``step_verify.verify_scene`` of a parse of the file at ``path``, read as the verify
    job reads a file (``load_step_scene``)."""
    from cadgen._internal.step_scene_loader import load_step_scene
    from cadgen._internal.step_verify import verify_scene

    return verify_scene(load_step_scene(Path(path)), expected, occurrences, colors, named=named)


def _expected(shape, label, part):
    """The component ``shape`` places, keyed ``part``, every face and edge named."""
    from OCP.TopLoc import TopLoc_Location

    from cadgen._internal.step_names import ComponentNames
    from cadgen._internal.step_verify import edge_boxes, expected_component, face_boxes

    unlocated = shape.wrapped.Located(TopLoc_Location())
    faces, edges = face_boxes(unlocated), edge_boxes(unlocated)
    names = ComponentNames(part=part, faces=tuple(f"f:{label}.make1.{n}" for n in range(1, len(faces) + 1)),
                           edges=tuple(f"e:{label}.make1.{n}" for n in range(1, len(edges) + 1)))
    return expected_component(unlocated, names)


def _tokens(label, leaves):
    """Each leaf's token in a root ``label`` holding ``leaves``, by the leaf's label."""
    from cadgen._internal.component_package import _transform_from_location
    from cadgen._internal.tree_tokens import assign_tokens

    tree = {"id": label, "name": label, "children": [{"id": leaf.label, "name": leaf.label} for leaf in leaves]}
    return assign_tokens(tree, [{"id": leaf.label, "transform": _transform_from_location(leaf.location)}
                                for leaf in leaves], [], label=label)


class VerifyStepTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        import build123d as bd

        from cadgen._internal.step_names import ComponentNames
        from cadgen.step_export import export_build123d_step_file

        shapes = {"bracket": bd.Box(4, 2, 1) - bd.Pos(1, 0, 0) * bd.Cylinder(0.4, 2), "ball": bd.Solid.make_sphere(1)}
        cls.components = {label: _expected(shape, label, _KEYS[label]) for label, shape in shapes.items()}
        bracket = bd.Pos(0, 0, 0) * shapes["bracket"]
        bracket.label = "bracket"
        cls.bracket_shape = shapes["bracket"]
        twin = bd.Pos(0, 8, 0) * bd.Rot(0, 0, 30) * shapes["bracket"]
        twin.label = "twin"
        ball = bd.Pos(9, 0, 2) * shapes["ball"]
        ball.label = "ball"
        leaves = [bracket, twin, ball]
        parts = {"bracket": "bracket", "twin": "bracket", "ball": "ball"}
        names = {id(leaf): cls.components[parts[leaf.label]].names for leaf in leaves}
        root = bd.Compound(children=leaves, label="rig")
        tokens = _tokens("rig", leaves)
        cls.named_tokens = tokens
        cls.occurrences = {tokens[leaf.label]: _KEYS[parts[leaf.label]] for leaf in leaves}
        cls._tmp = tempfile.TemporaryDirectory(prefix="step-verify-")
        tmp = Path(cls._tmp.name)
        cls.named = tmp / "named.step"
        cls.plain = tmp / "plain.step"
        export_build123d_step_file(root, cls.named, names=lambda leaf: names.get(id(leaf)))
        export_build123d_step_file(root, cls.plain)
        key_only = bd.Compound(children=[bracket], label="keyed")
        cls.keyed = tmp / "keyed.step"
        key = ComponentNames(part=_KEYS["bracket"])
        export_build123d_step_file(key_only, cls.keyed, names=lambda leaf: key if leaf is bracket else None)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def verify(self, path, components=None, occurrences=...):

        return verify_step(path, (self.components if components is None else components).values(),
                           self.occurrences if occurrences is ... else occurrences)

    def messages(self, mismatches):
        return [(mismatch.occurrence, mismatch.part, mismatch.message) for mismatch in mismatches]

    def test_a_file_written_from_the_result_verifies(self) -> None:
        self.assertEqual(self.verify(self.named), [])

    def test_a_file_written_without_names_holds_no_part_of_the_result(self) -> None:
        found = self.messages(self.verify(self.plain))
        self.assertEqual(sum(message.endswith("carries no part key") for _o, _p, message in found), 2)
        self.assertEqual({part for _o, part, message in found if message == "the file does not hold this part"},
                         set(_KEYS.values()))
        self.assertEqual({occurrence for occurrence, _p, message in found if "holds part None" in message},
                         set(self.occurrences))

    def test_a_file_written_without_names_is_verified_by_its_occurrences(self) -> None:
        """A plain file claims no part and no element: each occurrence holds the faces and
        edges of the part the result places there, wherever they are named."""

        self.assertEqual(verify_step(self.plain, self.components.values(), self.occurrences, named=False), [])
        from cadgen._internal.step_names import ComponentNames

        # Where the result places the ball, a bracket.
        swapped = {**self.components, "ball": dataclasses.replace(self.components["bracket"],
                                                                  names=ComponentNames(part=_KEYS["ball"]))}
        found = self.messages(verify_step(self.plain, swapped.values(), self.occurrences, named=False))
        self.assertTrue(found and all(part == _KEYS["ball"] for _occurrence, part, _message in found), found)
        with self.assertRaises(ValueError):
            verify_step(self.plain, self.components.values(), named=False)

    def test_names_that_differ_are_reported_on_their_part(self) -> None:
        bracket = self.components["bracket"]
        renamed = dataclasses.replace(bracket.names, faces=("f:bracket.make2.1",) + bracket.names.faces[1:],
                                      edges=("e:bracket.make2.1",) + bracket.names.edges[1:])
        found = self.messages(self.verify(self.named, {**self.components,
                                                       "bracket": dataclasses.replace(bracket, names=renamed)}))
        self.assertEqual(found, [
            (None, _KEYS["bracket"], "face names missing from the file: f:bracket.make2.1"),
            (None, _KEYS["bracket"], "face names the result does not have: f:bracket.make1.1"),
            (None, _KEYS["bracket"], "edge names missing from the file: e:bracket.make2.1"),
            (None, _KEYS["bracket"], "edge names the result does not have: e:bracket.make1.1"),
        ])

    def test_an_element_is_where_the_result_has_it_within_the_display_tolerance(self) -> None:
        import math

        from cadgen.tessellation_policy import DISPLAY_TESSELLATION

        bracket = self.components["bracket"]
        boxes = [box for box in bracket.face_boxes if box is not None]
        diagonal = math.dist([min(box[axis] for box in boxes) for axis in range(3)],
                             [max(box[axis + 3] for box in boxes) for axis in range(3)])
        tolerance = DISPLAY_TESSELLATION["chordTolerance"] * diagonal
        for kind in ("face", "edge"):
            for shift, reported in ((0.5 * tolerance, False), (2 * tolerance, True)):
                with self.subTest(kind=kind, shift=shift):
                    boxes = getattr(bracket, f"{kind}_boxes")
                    # Boxes given without a shape are not measured again.
                    moved = dataclasses.replace(bracket, shape=None,
                                                **{f"{kind}_boxes": ((boxes[0][0] + shift, *boxes[0][1:]),)
                                                   + boxes[1:]})
                    found = self.messages(self.verify(self.named, {**self.components, "bracket": moved}))
                    message = (f"{kind}s off their place by more than {tolerance:.3g} and their own tolerance: "
                               f"{kind[0]}:bracket.make1.1")
                    self.assertEqual(found, [(None, _KEYS["bracket"], message)] if reported else [])

    def test_a_body_the_file_trims_otherwise_does_not_verify(self) -> None:
        """An ellipsoid cap fused with two side boxes: OCCT reads the cap back as its
        complement, with as many faces and the body's box unchanged; the cap's own box tells."""
        import build123d as bd

        from cadgen.step_export import export_build123d_step_file

        sphere = bd.Rot(90, 0, 0) * bd.Rot(0, 0, -90) * bd.Sphere(1)
        ellipsoid = sphere.transform_geometry(bd.Matrix([[2.7, 0, 0, 0], [0, 2.7, 0, 0], [0, 0, 1.4, 0], [0, 0, 0, 1]]))
        cap = (bd.Pos(0, 0, 5.4) * ellipsoid) - (bd.Pos(0, 0, 4.15 - 10) * bd.Box(30, 30, 20))
        body = cap + bd.Pos(-5, 0, 5) * bd.Box(1, 6, 10) + bd.Pos(5, 0, 5) * bd.Box(1, 6, 10)
        body.label = "capped"
        component = _expected(body, "capped", _KEYS["bracket"])
        path = Path(self._tmp.name) / "capped.step"
        export_build123d_step_file(body, path, names=lambda leaf: component.names)
        found = [message for _o, _p, message in self.messages(self.verify(path, {"capped": component}, None))]
        self.assertFalse([message for message in found if message.endswith(f"faces where the result has "
                                                                           f"{len(component.face_boxes)}")],
                         "the premise: the file has as many faces")
        self.assertTrue([message for message in found if message.startswith("faces off their place")], found)

    def test_a_face_one_sides_search_measures_short_is_measured_again(self) -> None:
        """A tight box is the kernel's search for each extreme. On an ellipsoid -- a sphere
        scaled into a B-spline -- the search stops 0.8 mm short of the far side on the
        result, and not on the file, whose parameters keep fewer digits: the face is
        measured again on both sides, by a mesh of it, before it is called moved --
        whether its name pairs it or its place."""
        import build123d as bd
        from OCP.TopAbs import TopAbs_FACE
        from OCP.TopExp import TopExp
        from OCP.TopTools import TopTools_IndexedMapOfShape

        from cadgen._internal.step_names import ComponentNames
        from cadgen._internal.step_scene_loader import load_step_scene
        from cadgen._internal.step_verify import face_boxes, measured_again
        from cadgen.step_export import export_build123d_step_file

        rock = bd.scale(bd.Sphere(90), by=(1.0, 0.82, 0.62))
        rock.label = "rock"
        component = _expected(rock, "rock", _KEYS["ball"])
        named = Path(self._tmp.name) / "rock.step"
        export_build123d_step_file(rock, named, names=lambda leaf: component.names)
        ((_key, read),) = load_step_scene(named).prototype_shapes.items()
        self.assertGreater(abs(face_boxes(read)[0][0] - component.face_boxes[0][0]), 0.5,
                           "the premise: one side's search stops short of the far side")
        faces = TopTools_IndexedMapOfShape()
        TopExp.MapShapes_s(component.shape, TopAbs_FACE, faces)
        self.assertLess(abs(measured_again(faces.FindKey(1), 0.05)[0] + 90.0), 0.1)
        self.assertEqual(verify_step(named, [component]), [])
        keyed = Path(self._tmp.name) / "rock-keyed.step"
        export_build123d_step_file(rock, keyed, names=lambda leaf: ComponentNames(part=_KEYS["ball"]))
        unnamed = dataclasses.replace(component, names=ComponentNames(part=_KEYS["ball"]))
        self.assertEqual(verify_step(keyed, [unnamed]), [])

    def test_a_face_measured_again_is_bounded_by_the_face_not_its_surface(self) -> None:
        """A face measured again is the face as trimmed, never its surface over the
        parameters its edges span: a sphere with a hole through it is no wider than the
        hole's rims, though its surface is, and reaches its own extent within the mesh's
        deflection. A box reaching past a face as its surface does (a fillet's beyond its
        trim, which a reader trims again otherwise) would call it moved, or call a moved
        one in place."""
        import build123d as bd
        from OCP.GeomAbs import GeomAbs_Sphere
        from OCP.BRepAdaptor import BRepAdaptor_Surface
        from OCP.TopoDS import TopoDS

        from cadgen._internal.step_verify import measured_again

        holed = bd.Sphere(20) - bd.Rot(0, 90, 0) * bd.Cylinder(12, 60)
        (face,) = [face for face in holed.faces()
                   if BRepAdaptor_Surface(TopoDS.Face_s(face.wrapped), False).GetType() == GeomAbs_Sphere]
        for deflection in (0.2, 0.02):
            with self.subTest(deflection=deflection):
                box = measured_again(face.wrapped, deflection)
                # The rims are at x = +-16, which the surface passes by 4; the face reaches y = +-20.
                self.assertEqual((round(box[0], 6), round(box[3], 6)), (-16.0, 16.0))
                self.assertTrue(-20.0 <= box[1] <= -20.0 + deflection and 20.0 - deflection <= box[4] <= 20.0, box)

    def test_a_degenerate_edge_a_reader_adds_is_no_difference(self) -> None:
        """A reader's healing gives a fillet's corner patches degenerate edges the result's
        faces have none of: points, with no place and no name, which neither side counts or
        pairs -- whether names pair the other edges or their places do."""
        import build123d as bd

        from cadgen._internal.step_names import ComponentNames
        from cadgen._internal.step_scene_loader import load_step_scene
        from cadgen._internal.step_verify import degenerate_edges
        from cadgen.step_export import export_build123d_step_file

        # A twisted blade lofted through three sections, trimmed by a hub and filleted along
        # every edge that is not flat.
        sections = [
            [(11.1171, 22.9968, 29.65), (10.4829, -8.4968, 2.45), (10.4829, -8.4968, -0.35), (11.1171, 22.9968, 26.85)],
            [(43.4823, 17.5098, 23.3467), (35.3177, -12.9136, 7.3533), (35.3177, -12.9136, 4.5533),
             (43.4823, 17.5098, 20.5467)],
            [(73.7461, 7.4144, 18.15), (62.2539, -21.9144, 11.15), (62.2539, -21.9144, 8.35), (73.7461, 7.4144, 15.35)],
        ]
        body = bd.loft([bd.Face.make_surface(bd.Wire.make_polygon(points, close=True)) for points in sections])
        body -= bd.Pos(0, 0, -45) * bd.Cylinder(29, 120, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
        blade = bd.fillet([edge for edge in body.edges() if min(edge.bounding_box().size) > 0.2], radius=0.55)
        blade.label = "blade"
        component = _expected(blade, "blade", _KEYS["ball"])
        named = Path(self._tmp.name) / "blade.step"
        export_build123d_step_file(blade, named, names=lambda leaf: component.names)
        ((_key, read),) = load_step_scene(named).prototype_shapes.items()
        self.assertFalse(component.degenerate_edges)
        self.assertTrue(degenerate_edges(read), "the premise: the reader adds degenerate edges")
        self.assertEqual(verify_step(named, [component]), [])
        keyed = Path(self._tmp.name) / "blade-keyed.step"
        export_build123d_step_file(blade, keyed, names=lambda leaf: ComponentNames(part=_KEYS["ball"]))
        self.assertEqual(verify_step(keyed, [dataclasses.replace(component, names=ComponentNames(part=_KEYS["ball"]))]),
                         [])

    def test_a_face_is_drawn_in_the_results_colour(self) -> None:
        bracket = self.components["bracket"]
        coloured = dataclasses.replace(bracket, face_colors={"1": (1.0, 0.0, 0.0, 1.0)})
        found = self.messages(self.verify(self.named, {**self.components, "bracket": coloured}))
        placed = {self.named_tokens[label]: label for label in ("bracket", "twin")}
        self.assertEqual(sorted(found), sorted(
            (token, _KEYS["bracket"],
             f"the occurrence {label} draws f:bracket.make1.1 in no colour where the result draws (1, 0, 0, 1)")
            for token, label in placed.items()))
        unplaced = self.messages(self.verify(self.named, {**self.components, "bracket": coloured}, None))
        self.assertEqual(unplaced, [(None, _KEYS["bracket"],
                                     "the part draws f:bracket.make1.1 in no colour where the result draws (1, 0, 0, 1)")])

    def test_a_placements_colour_on_every_face_is_drawn_as_the_placement(self) -> None:
        """A coloured compound's colour comes back on each of its faces: drawn alike where
        every occurrence of it is placed in that colour, and not otherwise."""
        import build123d as bd

        from cadgen.step_export import export_build123d_step_file

        panel = bd.Compound(obj=[bd.Box(4, 4, 1), bd.Pos(6, 0, 0) * bd.Box(4, 4, 1)])
        panel.label = "panel"
        panel.color = (0.2, 0.3, 0.4, 1.0)
        cube = bd.Pos(0, 9, 0) * bd.Box(2, 2, 2)
        cube.label = "cube"
        components = {"panel": _expected(panel, "panel", _KEYS["bracket"]),
                      "cube": _expected(cube, "cube", _KEYS["ball"])}
        path = Path(self._tmp.name) / "panels.step"
        export_build123d_step_file(bd.Compound(children=[panel, cube], label="panels"), path,
                                   names=lambda leaf: components[leaf.label].names)
        tokens = _tokens("panels", [panel, cube])
        occurrences = {tokens[label]: component.names.part for label, component in components.items()}

        def verified(color):
            colors = None if color is None else {tokens["panel"]: color}
            return [mismatch.message for mismatch in verify_step(path, components.values(), occurrences, colors)]

        self.assertEqual(verified(panel.color), [])
        faces = ", ".join(f"f:panel.make1.{n}" for n in range(1, 6)) + " and 7 more"
        self.assertEqual(verified((0.2, 0.3, 0.5, 1.0)), [
            f"the occurrence panel draws {faces} in (0.2, 0.3, 0.4, 1) where the result draws (0.2, 0.3, 0.5, 1)"])
        self.assertEqual(verified(None), [
            f"the occurrence panel draws {faces} in (0.2, 0.3, 0.4, 1) where the result draws no colour"])

    def test_a_face_the_result_does_not_have_is_reported(self) -> None:
        bracket = self.components["bracket"]
        more = dataclasses.replace(bracket, names=dataclasses.replace(bracket.names, faces=()),
                                   face_boxes=bracket.face_boxes + (bracket.face_boxes[0],), shape=None)
        found = self.messages(self.verify(self.named, {**self.components, "bracket": more}))
        count = len(bracket.face_boxes)
        self.assertIn((None, _KEYS["bracket"], f"the file has {count} faces where the result has {count + 1}"), found)
        self.assertIn((None, _KEYS["bracket"], "face names the result does not have: "
                       + ", ".join(sorted(bracket.names.faces)[:5]) + f" and {count - 5} more"), found)

    def test_faces_neither_side_names_are_matched_by_their_place(self) -> None:
        bracket = self.components["bracket"]
        unnamed = dataclasses.replace(bracket, names=dataclasses.replace(bracket.names, faces=(), edges=()))
        self.assertEqual(self.verify(self.keyed, {"bracket": unnamed}, None), [])
        first = bracket.face_boxes[0]
        moved = dataclasses.replace(unnamed, face_boxes=((first[0] + 1.0, *first[1:]),) + bracket.face_boxes[1:],
                                    shape=None)
        found = self.messages(self.verify(self.keyed, {"bracket": moved}, None))
        self.assertEqual(len(found), 1)
        self.assertTrue(found[0][2].startswith("1 faces not paired by name have no counterpart within"), found)

    def test_a_sphere_verifies_though_its_seam_and_poles_carry_no_name(self) -> None:
        ball = self.components["ball"]
        self.assertEqual(len(ball.names.edges), 3)
        self.assertEqual(self.verify(self.named, {"ball": ball, "bracket": self.components["bracket"]}), [])

    def test_occurrences_are_compared_by_token_and_part(self) -> None:
        tokens = sorted(self.occurrences)
        expected = dict(self.occurrences)
        dropped = expected.pop(tokens[0])
        expected["o:000000000000"] = dropped
        expected[tokens[1]] = _KEYS["ball"] if expected[tokens[1]] == _KEYS["bracket"] else _KEYS["bracket"]
        found = self.messages(self.verify(self.named, occurrences=expected))
        self.assertIn(("o:000000000000", dropped, "the file has no occurrence with this token"), found)
        extra = {occurrence for occurrence, _p, message in found
                 if message.startswith("the file has an occurrence") and message.endswith("the result does not")}
        self.assertIn(tokens[0], extra)
        self.assertIn(tokens[1], {occurrence for occurrence, _p, message in found if " holds part " in message})
        self.assertEqual(len(found), 3)

    def test_a_name_the_file_gives_two_faces_is_reported(self) -> None:
        tampered = self.named.with_name("tampered.step")
        tampered.write_bytes(self.named.read_bytes().replace(b"'f:bracket.make1.2'", b"'f:bracket.make1.1'"))
        found = self.messages(self.verify(tampered))
        self.assertEqual(found, [
            (None, _KEYS["bracket"], "face names missing from the file: f:bracket.make1.2"),
            (None, _KEYS["bracket"], "face names on more than one face: f:bracket.make1.1"),
        ])

    def test_a_name_the_file_could_carry_is_missing_whatever_element_it_names(self) -> None:
        """A cylinder's seam has an entity like any edge, so the file must carry its name;
        only what no file can name is let go, and that is known from the result alone."""
        from OCP.BRep import BRep_Tool
        from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
        from OCP.TopExp import TopExp
        from OCP.TopLoc import TopLoc_Location
        from OCP.TopoDS import TopoDS
        from OCP.TopTools import TopTools_IndexedDataMapOfShapeListOfShape, TopTools_IndexedMapOfShape

        bracket = self.components["bracket"]
        edges = TopTools_IndexedMapOfShape()
        source = self.bracket_shape.wrapped.Located(TopLoc_Location())
        TopExp.MapShapes_s(source, TopAbs_EDGE, edges)
        faces = TopTools_IndexedDataMapOfShapeListOfShape()
        TopExp.MapShapesAndAncestors_s(source, TopAbs_EDGE, TopAbs_FACE, faces)
        seam = next(ordinal for ordinal in range(1, edges.Extent() + 1)
                    if any(BRep_Tool.IsClosed_s(TopoDS.Edge_s(edges.FindKey(ordinal)), TopoDS.Face_s(face))
                           for face in faces.FindFromKey(edges.FindKey(ordinal))))
        name = bracket.names.edges[seam - 1]
        tampered = self.named.with_name("seamless.step")
        tampered.write_bytes(self.named.read_bytes().replace(f"'{name}'".encode(), b"''"))
        self.assertEqual(self.messages(self.verify(tampered)),
                         [(None, _KEYS["bracket"], f"edge names missing from the file: {name}")])
        self.assertEqual(self.components["ball"].unnameable_edges, frozenset({1, 2, 3}))

    def test_an_occurrence_is_drawn_in_the_results_colour(self) -> None:
        import re

        import build123d as bd

        from cadgen.step_export import export_build123d_step_file

        green = (0.1, 0.8, 0.2, 1.0)
        knob = bd.Pos(0, 0, 2) * bd.Cylinder(0.5, 1)
        knob.label, knob.color = "knob", bd.Color(*green)
        base = bd.Box(2, 2, 2)
        base.label = "base"
        components = {"knob": _expected(knob, "knob", _KEYS["bracket"]), "base": _expected(base, "base", _KEYS["ball"])}
        path = Path(self._tmp.name) / "knob.step"
        export_build123d_step_file(bd.Compound(children=[base, knob], label="kid"), path,
                                   names=lambda leaf: components[leaf.label].names)
        tokens = _tokens("kid", [base, knob])
        occurrences = {tokens[label]: component.names.part for label, component in components.items()}

        def found(path, colors):
            return [(mismatch.occurrence, mismatch.message)
                    for mismatch in verify_step(path, components.values(), occurrences, colors)]

        self.assertEqual(found(path, {tokens["knob"]: green}), [])
        self.assertEqual([occurrence for occurrence, _message in found(path, None)], [tokens["knob"]])
        magenta = path.with_name("magenta.step")
        magenta.write_text(re.sub(r"COLOUR_RGB\('([^']*)',[^)]*\)", r"COLOUR_RGB('\1',1.,0.,1.)",
                                  path.read_text(encoding="utf-8")), encoding="utf-8")
        self.assertEqual([occurrence for occurrence, _message in found(magenta, {tokens["knob"]: green})],
                         [tokens["knob"]])

    def test_an_elements_bound_is_the_display_tolerance_and_its_own(self) -> None:
        """The kernel takes geometry within an element's tolerance as coincident: a reader
        that heals or re-approximates within it has not changed the shape."""
        import build123d as bd
        from OCP.BRep import BRep_Builder
        from OCP.TopAbs import TopAbs_FACE, TopAbs_VERTEX
        from OCP.TopExp import TopExp
        from OCP.TopLoc import TopLoc_Location
        from OCP.TopoDS import TopoDS
        from OCP.TopTools import TopTools_IndexedMapOfShape

        from cadgen.step_export import export_build123d_step_file

        block = bd.Solid.make_box(4, 2, 1)
        vertices = TopTools_IndexedMapOfShape()
        TopExp.MapShapes_s(block.wrapped, TopAbs_VERTEX, vertices)
        BRep_Builder().UpdateVertex(TopoDS.Vertex_s(vertices.FindKey(1)), 0.05)
        block.label = "block"
        component = _expected(block, "block", _KEYS["bracket"])
        loose = next(index for index, tolerance in enumerate(component.face_tolerances) if tolerance >= 0.05)
        tight = next(index for index, tolerance in enumerate(component.face_tolerances) if tolerance < 1e-3)
        path = Path(self._tmp.name) / "block.step"
        export_build123d_step_file(block, path, names=lambda leaf: component.names)
        faces = TopTools_IndexedMapOfShape()
        TopExp.MapShapes_s(block.wrapped.Located(TopLoc_Location()), TopAbs_FACE, faces)
        for index, shift, reported in ((loose, 0.02, False), (loose, 0.08, True), (tight, 0.02, True)):
            with self.subTest(face=index + 1, shift=shift):
                boxes = list(component.face_boxes)
                boxes[index] = (boxes[index][0] + shift, *boxes[index][1:])
                moved = dataclasses.replace(component, face_boxes=tuple(boxes), shape=None)
                found = [mismatch.message for mismatch in verify_step(path, [moved])]
                self.assertEqual(any(message.startswith("faces off their place") for message in found), reported, found)

    def test_a_face_is_drawn_in_its_own_colour_and_else_in_its_occurrences(self) -> None:
        """What is compared is the colour a face is drawn in -- its own where the part gives
        it one, its occurrence's elsewhere -- not how the file states it: OCCT writes the
        occurrence's colour onto each face of a compound part without one of its own."""
        import build123d as bd

        from cadgen.step_export import export_build123d_step_file

        red, blue = (1.0, 0.0, 0.0, 1.0), (0.2, 0.4, 0.6, 1.0)
        pair = bd.Compound([bd.Solid.make_box(2, 2, 2), bd.Pos(4, 0, 0) * bd.Solid.make_box(2, 2, 2)])
        pair.label, pair.color = "pair", bd.Color(*blue)
        pair.cad_face_ordinal_colors = {1: red}
        cube = bd.Pos(0, 9, 0) * bd.Box(2, 2, 2)
        cube.label = "cube"
        components = {"pair": dataclasses.replace(_expected(pair, "pair", _KEYS["bracket"]), face_colors={1: red}),
                      "cube": _expected(cube, "cube", _KEYS["ball"])}
        path = Path(self._tmp.name) / "pair.step"
        export_build123d_step_file(bd.Compound(children=[pair, cube], label="pairs"), path,
                                   names=lambda leaf: components[leaf.label].names)
        tokens = _tokens("pairs", [pair, cube])
        occurrences = {tokens[label]: component.names.part for label, component in components.items()}
        colors = {tokens["pair"]: blue}
        self.assertEqual(verify_step(path, components.values(), occurrences, colors), [])
        green = dataclasses.replace(components["pair"], face_colors={1: (0.0, 1.0, 0.0, 1.0)})
        found = [(mismatch.occurrence, mismatch.message)
                 for mismatch in verify_step(path, [green, components["cube"]], occurrences, colors)]
        self.assertEqual(found, [(tokens["pair"], "the occurrence pair draws f:pair.make1.1 in (1, 0, 0, 1) "
                                                  "where the result draws (0, 1, 0, 1)")])

    def test_an_edge_no_file_can_name_is_checked_through_its_faces(self) -> None:
        """A whole ellipsoid made by transforming a sphere keeps its poles' degenerate edges on
        the sphere's curves, a third of the way off its poles; a reader makes them again at
        the poles. Such an edge has no entity in any file and no place of its own to check."""
        import build123d as bd
        from OCP.TopLoc import TopLoc_Location

        from cadgen._internal.step_scene_loader import load_step_scene
        from cadgen._internal.step_verify import edge_boxes
        from cadgen.step_export import export_build123d_step_file

        sphere = bd.Sphere(1)
        ellipsoid = sphere.transform_geometry(bd.Matrix([[2.7, 0, 0, 0], [0, 2.7, 0, 0], [0, 0, 1.4, 0], [0, 0, 0, 1]]))
        ellipsoid.label = "egg"
        component = _expected(ellipsoid, "egg", _KEYS["bracket"])
        path = Path(self._tmp.name) / "egg.step"
        export_build123d_step_file(ellipsoid, path, names=lambda leaf: component.names)
        ((_key, read),) = load_step_scene(path).prototype_shapes.items()
        written = {round(box[2], 3) for box in edge_boxes(ellipsoid.wrapped.Located(TopLoc_Location())) if box}
        self.assertNotEqual(written, {round(box[2], 3) for box in edge_boxes(read) if box},
                            "the premise: the file's edges are not where the result's are")
        self.assertEqual(verify_step(path, [component]), [])

    def test_a_wire_answers_for_its_body_by_its_place(self) -> None:
        """A body without faces has only its edges to answer for it, and a free wire's carry no
        name in any file: they are compared by their place, so two wires of as many edges
        never verify as each other."""
        import build123d as bd

        from cadgen.step_export import export_build123d_step_file

        written = bd.Wire.make_polygon([(0, 0, 0), (5, 0, 0), (5, 2, 0)])
        written.label = "wire"
        other = bd.Wire.make_polygon([(0, 0, 0), (6, 0, 0), (6, 3, 0)])
        component = _expected(written, "wire", _KEYS["ball"])
        path = Path(self._tmp.name) / "wire.step"
        export_build123d_step_file(written, path, names=lambda leaf: component.names)
        self.assertEqual(verify_step(path, [component]), [])
        ((occurrence, part, message),) = self.messages(verify_step(path, [_expected(other, "wire", _KEYS["ball"])]))
        self.assertEqual((None, _KEYS["ball"]), (occurrence, part))
        self.assertTrue(message.startswith("3 edges not paired by name have no counterpart within"), message)

    def test_the_result_names_each_component_by_one_part_key(self) -> None:

        bracket = self.components["bracket"]
        with self.assertRaises(ValueError):
            verify_step(self.named, [bracket, bracket])
        with self.assertRaises(ValueError):
            verify_step(self.named, [dataclasses.replace(bracket, names=dataclasses.replace(bracket.names, part=None))])


if __name__ == "__main__":
    unittest.main()
