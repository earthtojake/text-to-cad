"""A STEP file names what it holds: each part by its key, on its product, and each face
and edge by its name, on the entity written for it (``step_names``).

Any reader of the file gets those names from the file alone, on the elements they were
written on; a cold parse walked as a compile walks it names every occurrence by the token
the result names it by, and a document of one shape is that one product; and a file written
without names is the file the writer wrote before names existed, which a named file whose
plain twin is already read as its result is too, byte for byte, but for its names.
"""

from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

_KEYS = {"bracket": f"{1:064x}-v7", "mirrored": f"{2:064x}-v7", "ball": f"{3:064x}-v7"}


def _unlocated(shape):
    from OCP.TopLoc import TopLoc_Location

    return shape.wrapped.Located(TopLoc_Location())


def _elements(shape, kind):
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
    from OCP.TopExp import TopExp
    from OCP.TopTools import TopTools_IndexedMapOfShape

    found = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, TopAbs_FACE if kind == "face" else TopAbs_EDGE, found)
    return [found.FindKey(ordinal) for ordinal in range(1, found.Extent() + 1)]


def _names(label, shape):
    from cadgen._internal.step_names import ComponentNames

    return ComponentNames(
        part=_KEYS[label],
        faces=tuple(f"f:{label}.box1.{ordinal}" for ordinal in range(1, len(_elements(shape, "face")) + 1)),
        edges=tuple(f"e:{label}.box1.{ordinal}" for ordinal in range(1, len(_elements(shape, "edge")) + 1)),
    )


def _box(shape):
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape, box, False, False)
    return box.Get()


def _rig():
    """An assembly, its leaves and what names each: a bracket with a bore; its mirror
    image, every face of which OCCT's writer would rebuild on a direct surface; a sphere,
    whose seam and poles no STEP entity carries; a twin of the bracket (the same part placed
    again) and a nested group placing the sphere turned."""
    import build123d as bd

    bracket = bd.Box(4, 2, 1) - bd.Pos(1, 0, 0) * bd.Cylinder(0.4, 2)
    shapes = {"bracket": bracket, "mirrored": bracket.mirror(bd.Plane.YZ), "ball": bd.Solid.make_sphere(1)}
    names = {label: _names(label, _unlocated(shape)) for label, shape in shapes.items()}
    placed = {}
    leaves = []
    for index, (label, shape) in enumerate(shapes.items()):
        leaf = bd.Pos(6 * index, 0, 0) * shape
        leaf.label = label
        placed[id(leaf)] = names[label]
        leaves.append(leaf)
    twin = bd.Pos(0, 9, 0) * leaves[0]
    twin.label = "twin"
    placed[id(twin)] = names["bracket"]
    turned = bd.Pos(3, 3, 3) * bd.Rot(30, 45, 60) * leaves[2]
    turned.label = "turned"
    placed[id(turned)] = names["ball"]
    group = bd.Compound(children=[turned], label="nest")
    root = bd.Compound(children=[leaves[0], leaves[1], twin, group, leaves[2]], label="rig")
    return root, shapes, names, placed


def _strip_names(data: bytes) -> bytes:
    """``data`` with every element name and part key the writer added taken out, and OCCT's
    line wrapping (which a longer record moves) undone."""
    data = re.sub(rb"'[fe]:[A-Za-z_]+\.box1\.\d+'", b"''", data)
    data = re.sub(rb"'[0-9a-f]{64}-v7'", b"''", data)
    return re.sub(rb"\r?\n\s*", b"", data)


class StepNamesRoundTripTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from cadgen.step_export import export_build123d_step_file

        cls._tmp = tempfile.TemporaryDirectory(prefix="step-names-")
        tmp = Path(cls._tmp.name)
        cls.root, cls.shapes, cls.names, placed = _rig()
        cls.named = tmp / "named.step"
        cls.plain = tmp / "plain.step"
        cls.named_digest = export_build123d_step_file(cls.root, cls.named, names=lambda leaf: placed.get(id(leaf)))
        cls.plain_digest = export_build123d_step_file(cls.root, cls.plain)
        cls.placed = placed

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_each_part_reads_back_with_its_key_and_its_elements_named_where_they_were(self) -> None:
        from OCP.BRep import BRep_Tool
        from OCP.TopoDS import TopoDS

        from cadgen._internal.step_scene_loader import load_step_scene

        scene = load_step_scene(self.named)
        by_part = {names.part: (key, names) for key, names in scene.prototype_step_names.items()}
        self.assertEqual(set(by_part), set(_KEYS.values()), "one product per part, each carrying its key")
        for label, shape in self.shapes.items():
            with self.subTest(part=label):
                key, read = by_part[_KEYS[label]]
                written = self.names[label]
                source = _unlocated(shape)
                prototype = scene.prototype_shapes[key]
                self.assertEqual(sorted(filter(None, read.faces)), sorted(written.faces))
                source_faces = dict(zip(written.faces, _elements(source, "face")))
                for name, face in zip(read.faces, _elements(prototype, "face")):
                    for read_bound, source_bound in zip(_box(face), _box(source_faces[name])):
                        self.assertAlmostEqual(read_bound, source_bound, places=6, msg=f"{name} is read elsewhere")
                # Every edge the file has an entity for is read named; a sphere's seam
                # and poles have none, and are read as new and unnamed.
                source_edges = dict(zip(written.edges, _elements(source, "edge")))
                carried = {name for name, edge in source_edges.items()
                           if not BRep_Tool.Degenerated_s(TopoDS.Edge_s(edge)) and label != "ball"}
                self.assertEqual(set(filter(None, read.edges)), carried)
                for name, edge in zip(read.edges, _elements(prototype, "edge")):
                    if name is not None:
                        for read_bound, source_bound in zip(_box(edge), _box(source_edges[name])):
                            self.assertAlmostEqual(read_bound, source_bound, places=6,
                                                   msg=f"{name} is read elsewhere")

    def test_names_change_no_byte_of_the_file_but_the_names(self) -> None:
        from cadgen.step_export import export_build123d_step_file

        named, plain = self.named.read_bytes(), self.plain.read_bytes()
        self.assertNotEqual(named, plain)
        self.assertEqual(_strip_names(named), _strip_names(plain))
        self.assertNotRegex(plain, rb"'[fe]:", "a file written without names carries none")
        again = self.named.with_name("again.step")
        self.assertEqual(export_build123d_step_file(self.root, again, names=lambda leaf: self.placed.get(id(leaf))),
                         self.named_digest, "the same names write the same bytes")

    def test_a_cold_parse_names_every_occurrence_as_the_result_does(self) -> None:
        from cadgen._internal.step_scene_loader import load_step_scene
        from cadgen._internal.tree_tokens import assign_tokens
        from cadgen.store.build import _document_walk

        def transform(shape):
            from cadgen._internal.component_package import _transform_from_location

            return _transform_from_location(shape.location)

        leaves = [child for child in self.root.children if child.label != "nest"]
        nest = next(child for child in self.root.children if child.label == "nest")
        result = {"id": "rig", "name": "rig", "children": [
            *({"id": leaf.label, "name": leaf.label} for leaf in leaves[:3]),
            {"id": "nest", "name": "nest", "children": [{"id": "turned", "name": "turned"}]},
            {"id": leaves[3].label, "name": leaves[3].label},
        ]}
        occurrences = [{"id": leaf.label, "transform": transform(leaf)} for leaf in leaves]
        occurrences.append({"id": "turned", "transform": transform(nest.children[0])})
        expected = assign_tokens(result, occurrences, [], label="rig")
        walk = _document_walk(load_step_scene(self.named))
        self.assertEqual(sorted(str(row["id"]) for row in walk.occurrences),
                         sorted(expected[row["id"]] for row in occurrences))

    def test_a_document_of_one_shape_is_one_product_named_as_the_result_names_it(self) -> None:
        from OCP.gp import gp_Trsf
        from OCP.TopLoc import TopLoc_Location

        from cadgen._internal.step_scene_loader import load_step_scene
        from cadgen.step_export import export_build123d_step_file

        # A stored result's one leaf, placed as materialize places it: at a location made
        # from the identity matrix, which OCCT does not take for no location.
        shape = self.shapes["mirrored"]
        root = type(shape)(shape.wrapped.Moved(TopLoc_Location(gp_Trsf())))
        self.assertFalse(root.wrapped.Location().IsIdentity())
        root.label = "bracket_only"
        path = self.named.with_name("one.step")
        export_build123d_step_file(root, path, names=lambda leaf: self.names["mirrored"] if leaf is root else None)
        scene = load_step_scene(path)
        self.assertEqual([(node.name, node.children) for node in scene.roots], [("bracket_only", [])])
        names = scene.prototype_step_names[scene.roots[0].prototype_key]
        self.assertEqual((names.part, sorted(filter(None, names.faces))),
                         (_KEYS["mirrored"], sorted(self.names["mirrored"].faces)))
        # Named or not is the file's mode, not what it names: a root it names nothing of
        # is one product too.
        export_build123d_step_file(root, path, names=lambda leaf: None)
        self.assertEqual([(node.name, node.children) for node in load_step_scene(path).roots],
                         [("bracket_only", [])])

    def test_face_colours_survive_on_the_faces_they_were_given_where_the_writer_rebuilds_them(self) -> None:
        import build123d as bd

        from cadgen._internal.step_scene_loader import load_step_scene
        from cadgen._internal.step_scene_mesh import _face_colors_by_ordinal
        from cadgen.step_export import export_build123d_step_file

        names = self.names["mirrored"]
        for ordinal in (1, 4, 7):
            with self.subTest(face=ordinal):
                mirrored = bd.Pos(0, 0, 0) * self.shapes["mirrored"]
                mirrored.label = "mirrored"
                mirrored.cad_face_ordinal_colors = {ordinal: (1.0, 0.0, 0.0, 1.0)}
                root = bd.Compound(children=[mirrored], label="painted")
                path = self.named.with_name("painted.step")
                export_build123d_step_file(root, path, names=lambda leaf: names if leaf is mirrored else None)
                scene = load_step_scene(path)
                ((key, shape),) = scene.prototype_shapes.items()
                colours = _face_colors_by_ordinal(shape, scene.prototype_face_colors[key])
                read_names = scene.prototype_step_names[key].faces
                self.assertEqual({read_names[read - 1]: colour for read, colour in colours.items()},
                                 {names.faces[ordinal - 1]: (1.0, 0.0, 0.0, 1.0)})

    def test_the_writer_refuses_names_that_do_not_fit_and_writes_nothing(self) -> None:
        import dataclasses

        from cadgen.step_export import export_build123d_step_file

        good = self.names["bracket"]
        cases = {
            "an edge name for a face": dataclasses.replace(good, faces=("e:bracket.box1.1",) + good.faces[1:]),
            "a name given twice": dataclasses.replace(good, faces=(good.faces[1],) + good.faces[1:]),
            "a name short": dataclasses.replace(good, faces=good.faces[1:]),
            "a part key misspelled": dataclasses.replace(good, part="bracket"),
            "a part key without its version": dataclasses.replace(good, part="0" * 64),
        }
        bracket = self.root.children[0]
        for case, names in cases.items():
            with self.subTest(case=case):
                path = self.named.with_name("refused.step")
                with self.assertRaises(ValueError):
                    export_build123d_step_file(self.root, path,
                                               names=lambda leaf, names=names: names if leaf is bracket else None)
                self.assertFalse(path.exists())


def _named_parts(*shapes):
    """A document placing each of ``shapes`` (label, shape) apart, every element of each
    named, and what names each: by the leaf, and by its part key."""
    import build123d as bd

    from cadgen._internal.step_names import ComponentNames

    leaves, by_leaf = [], {}
    for index, (label, shape) in enumerate(shapes):
        leaf = shape.moved(bd.Location((20 * index, 0, 0))) if index else shape
        leaf.label = label
        unlocated = _unlocated(leaf)
        by_leaf[id(leaf)] = ComponentNames(
            part=f"{index + 10:064x}-v7",
            faces=tuple(f"f:{label}.make1.{n}" for n in range(1, len(_elements(unlocated, "face")) + 1)),
            edges=tuple(f"e:{label}.make1.{n}" for n in range(1, len(_elements(unlocated, "edge")) + 1)),
        )
        leaves.append(leaf)
    return bd.Compound(children=leaves, label="kinds"), leaves, by_leaf


class ComponentKindsTest(unittest.TestCase):
    """Every component a stored result can hold is named as far as a file can carry it:
    named export never fails where plain export succeeds, and a reader takes back every name
    the file carries, through the transfer's own map from entities to shapes."""

    def write(self, root, names):
        from cadgen._internal.step_scene_loader import load_step_scene
        from cadgen.step_export import export_build123d_step_file

        tmp = tempfile.TemporaryDirectory(prefix="step-kinds-")
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "kinds.step"
        export_build123d_step_file(root, path, names=names)
        return load_step_scene(path)

    def read_by_part(self, scene):
        return {names.part: (key, names) for key, names in scene.prototype_step_names.items()}

    def test_a_component_that_is_one_face_is_named_on_that_face(self) -> None:
        import build123d as bd

        root, leaves, by_leaf = _named_parts(("body", bd.Box(4, 4, 4)), ("plate", bd.Face.make_rect(10, 20)))
        read = self.read_by_part(self.write(root, lambda leaf: by_leaf.get(id(leaf))))
        plate = by_leaf[id(leaves[1])]
        self.assertEqual(read[plate.part][1].faces, plate.faces)
        self.assertEqual(sorted(filter(None, read[plate.part][1].edges)), sorted(plate.edges))

        face = bd.Face.make_rect(3, 3)
        face.label = "sheet"
        names = by_leaf[id(leaves[1])]
        only = self.write(face, lambda leaf: names if leaf is face else None)
        ((key, read_names),) = only.prototype_step_names.items()
        self.assertEqual((read_names.part, read_names.faces), (names.part, names.faces))

    def test_a_component_with_nothing_in_it_carries_its_key(self) -> None:
        import build123d as bd

        root, leaves, by_leaf = _named_parts(("body", bd.Box(4, 4, 4)), ("nothing", bd.Compound([])))
        read = self.read_by_part(self.write(root, lambda leaf: by_leaf.get(id(leaf))))
        self.assertEqual(set(read), {names.part for names in by_leaf.values()})

    def test_every_name_the_file_carries_reads_back_on_its_element(self) -> None:
        """Faces of an internal void, and free edges a file writes on curve sets, which a
        reader's sub-shape expansion does not reach."""
        import build123d as bd

        hollow = bd.Box(10, 10, 10) - bd.Box(4, 4, 4)
        axis = bd.Compound([bd.Solid.make_box(1, 1, 1), bd.Edge.make_line((3, 0, 0), (6, 0, 0)),
                            bd.Edge.make_circle(1, bd.Plane.XY.offset(4))])
        root, leaves, by_leaf = _named_parts(("hollow", hollow), ("axis", axis))
        scene = self.write(root, lambda leaf: by_leaf.get(id(leaf)))
        read = self.read_by_part(scene)
        for leaf in leaves:
            written = by_leaf[id(leaf)]
            with self.subTest(part=leaf.label):
                key, names = read[written.part]
                self.assertEqual(sorted(filter(None, names.faces)), sorted(written.faces))
                self.assertEqual(sorted(filter(None, names.edges)), sorted(written.edges))
                source = _unlocated(leaf)
                for kind, given, got in (("face", written.faces, names.faces), ("edge", written.edges, names.edges)):
                    where = dict(zip(given, _elements(source, kind)))
                    for name, element in zip(got, _elements(scene.prototype_shapes[key], kind)):
                        for read_bound, source_bound in zip(_box(element), _box(where[name])):
                            self.assertAlmostEqual(read_bound, source_bound, places=6, msg=name)

    def test_names_change_no_byte_of_a_file_of_every_kind_but_the_names(self) -> None:
        import build123d as bd

        from cadgen.step_export import export_build123d_step_file

        root, _leaves, by_leaf = _named_parts(
            ("plate", bd.Face.make_rect(10, 20)), ("nothing", bd.Compound([])),
            ("hollow", bd.Box(10, 10, 10) - bd.Box(4, 4, 4)),
            ("axis", bd.Compound([bd.Solid.make_box(1, 1, 1), bd.Edge.make_line((3, 0, 0), (6, 0, 0)),
                                  bd.Wire.make_polygon([(3, 2, 0), (5, 2, 0), (5, 4, 0)])])))
        with tempfile.TemporaryDirectory(prefix="step-kinds-bytes-") as tmp:
            named, plain = Path(tmp) / "named.step", Path(tmp) / "plain.step"
            export_build123d_step_file(root, named, names=lambda leaf: by_leaf.get(id(leaf)))
            export_build123d_step_file(root, plain)
            strip = re.compile(rb"'[fe]:[A-Za-z_]+\.make1\.\d+'|'[0-9a-f]{64}-v7'")
            self.assertEqual(re.sub(rb"\r?\n\s*", b"", strip.sub(b"''", named.read_bytes())),
                             re.sub(rb"\r?\n\s*", b"", plain.read_bytes()))

    def test_what_a_file_cannot_name_is_known_by_construction(self) -> None:
        """STEP has no entity for a degenerate edge, OCCT writes a face bounded by one seam
        alone (a whole sphere) with its natural bounds and no edges, and a free wire as one
        curve set: those edges and no others go unnamed, and the writer names every other."""
        import build123d as bd
        from OCP.BRep import BRep_Tool
        from OCP.TopoDS import TopoDS

        from cadgen._internal.step_names import unnameable

        sphere = bd.Solid.make_sphere(2)
        shapes = {
            "sphere": sphere,
            "hemisphere": sphere - bd.Pos(0, 0, -5) * bd.Box(10, 10, 10),
            "cylinder": bd.Cylinder(1, 2),
            "cone": bd.Cone(2, 0, 3),
            "torus": bd.Torus(3, 1),
            "wired": bd.Compound([bd.Solid.make_box(1, 1, 1), bd.Wire.make_polygon([(3, 0, 0), (5, 0, 0), (5, 2, 0)])]),
        }
        root, leaves, by_leaf = _named_parts(*shapes.items())
        read = self.read_by_part(self.write(root, lambda leaf: by_leaf.get(id(leaf))))
        expected_unnamed = {"sphere": {1, 2, 3}, "hemisphere": "degenerate", "cylinder": set(), "cone": "degenerate",
                            "torus": set(), "wired": {13, 14, 15}}
        for leaf in leaves:
            written = by_leaf[id(leaf)]
            source = _unlocated(leaf)
            faces, edges = unnameable(source)
            with self.subTest(part=leaf.label):
                wanted = expected_unnamed[leaf.label]
                if wanted == "degenerate":
                    wanted = {ordinal for ordinal, edge in enumerate(_elements(source, "edge"), start=1)
                              if BRep_Tool.Degenerated_s(TopoDS.Edge_s(edge))}
                    self.assertTrue(wanted)
                self.assertEqual((faces, edges), (frozenset(), frozenset(wanted)))
                _key, names = read[written.part]
                carried = [name for ordinal, name in enumerate(written.edges, start=1) if ordinal not in edges]
                self.assertEqual(sorted(filter(None, names.edges)), sorted(carried))
                self.assertEqual(sorted(filter(None, names.faces)), sorted(written.faces))


class ForeignNamesTest(unittest.TestCase):
    def test_names_another_writer_gave_are_not_read_as_names(self) -> None:
        """A face named ``Face1`` or a product described in words is some other writer's
        naming: the file names nothing the reader takes for an element name or a part key."""
        import build123d as bd
        from OCP.TCollection import TCollection_ExtendedString
        from OCP.TDataStd import TDataStd_Name
        from OCP.XCAFDoc import XCAFDoc_DocumentTool

        from cadgen._internal.step_scene_loader import load_step_scene
        from cadgen.step_export import create_bin_xcaf_doc, write_xcaf_doc_step_file

        doc = create_bin_xcaf_doc()
        tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
        shape = bd.Solid.make_box(1, 2, 3).wrapped
        label = tool.AddShape(shape, False)
        TDataStd_Name.Set_s(label, TCollection_ExtendedString("block"))
        for ordinal, face in enumerate(_elements(shape, "face"), start=1):
            TDataStd_Name.Set_s(tool.AddSubShape(label, face), TCollection_ExtendedString(f"Face{ordinal}"))
        tool.GetNamedProperties(label, True).SetString(TCollection_ExtendedString("Description"),
                                                       TCollection_ExtendedString("a block"))
        with tempfile.TemporaryDirectory(prefix="step-foreign-names-") as tmp:
            path = Path(tmp) / "foreign.step"
            write_xcaf_doc_step_file(doc, path)
            text = path.read_text(encoding="utf-8")
            self.assertIn("'Face1'", text)
            self.assertIn("'a block'", text)
            self.assertEqual(load_step_scene(path).prototype_step_names, {})


if __name__ == "__main__":
    unittest.main()
