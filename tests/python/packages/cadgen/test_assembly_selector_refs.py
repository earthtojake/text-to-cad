"""An assembly's refs must resolve in the namespace the tools actually hand out.

`snapshot --mode list` and the CAD Viewer enumerate instance-tree occurrences --
`#o:4b1f9e2a7c03 shoulder_yaw_yoke` -- while `inspect refs` and `snapshot --focus/--hide`
once resolved against a whole-assembly topology sidecar extracted from the COMPOSED compound,
which described any assembly as ONE occurrence. Every ref a user could pick was rejected by
every tool that could measure it.

These cover the merge itself (real package, real descriptor) and the transform arithmetic, which
is the part with a wrong answer that looks plausible. An occurrence's id is a token from the
tree, an element's a name from its component's selector table, a ref `<occurrence>/<element>`.
"""

from __future__ import annotations

import copy
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_repo_path
from tests.python.support.store_fixtures import build_view
from tests.python.support.tree_ids import leaf_id, leaf_ids, node_id

add_repo_path("packages/cadgen/src")

from build123d import Box, Compound, Pos, Rot  # noqa: E402

from cadgen import assembly_lookup, lookup  # noqa: E402
from cadgen._internal import component_package  # noqa: E402
from cadgen._internal.tree_tokens import is_occurrence_token  # noqa: E402
from cadgen.cad_ref_syntax import element_ref, split_element_ref  # noqa: E402


def _demo_compound() -> Compound:
    """Two identical boxes placed apart, a distinct one, and one ROTATED.

    The rotated occurrence is not decoration. Every other part here is placed by translation
    alone, and under a translation a box's face normals stay axis-aligned whatever the rotation
    code does -- so a transposed or dropped rotation passes unnoticed. `box_rot` is turned 90
    degrees about Z, which swaps its X and Y extents and sends its +X normal to +Y, both of
    which are wrong in a checkable way if the rotation is mishandled.
    """
    first = Pos(0, 0, 0) * Box(10, 10, 10)
    first.label = "box_a_1"
    second = Pos(40, 0, 0) * Box(10, 10, 10)
    second.label = "box_a_2"
    third = Pos(0, 40, 0) * Box(4, 6, 8)
    third.label = "box_b"
    rotated = Pos(0, -40, 0) * Rot(0, 0, 90) * Box(4, 6, 8)
    rotated.label = "box_rot"
    assembly = Compound(children=[first, second, third, rotated])
    assembly.label = "demo"
    return assembly


def setUpModule() -> None:
    global _fixture_root, _fixture_package_dir, _fixture_descriptor
    global _group_package_dir, _group_descriptor

    fixture_tmp = tempfile.TemporaryDirectory(prefix="assembly-refs-")
    unittest.addModuleCleanup(fixture_tmp.cleanup)
    _fixture_root = Path(fixture_tmp.name)
    cache_patch = mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(_fixture_root / "store")})
    cache_patch.start()
    unittest.addModuleCleanup(cache_patch.stop)
    _fixture_package_dir = _fixture_root / "__cadgen__" / "models" / "demo.py"
    build_view(_demo_compound(), package_dir=_fixture_package_dir, root_name="demo")
    _fixture_descriptor = component_package.read_package_descriptor(_fixture_package_dir)
    if not isinstance(_fixture_descriptor, dict):
        raise AssertionError("fixture package has no descriptor")

    _group_package_dir = _fixture_root / "__cadgen__" / "models" / "nested.py"
    build_view(_nested_compound(), package_dir=_group_package_dir, root_name="nested")
    _group_descriptor = component_package.read_package_descriptor(_group_package_dir)
    if not isinstance(_group_descriptor, dict):
        raise AssertionError("group fixture package has no descriptor")


class _FakeArtifact:
    """Stands in for StepArtifact: the merge only reads `kind` and `artifact_path`."""

    def __init__(self, kind: str, artifact_path: Path) -> None:
        self.kind = kind
        self.artifact_path = artifact_path


def _empty_index() -> lookup.SelectorIndex:
    """The index a document starts from: no rows of its own. Every occurrence and element
    row comes from the tree and its components, composed by ``assembly_lookup``."""
    return lookup.build_selector_index({"tables": {"occurrenceColumns": ["id", "name", "bbox"]}, "occurrences": []})


class _AssemblyDisplayFixture:
    def setUp(self) -> None:
        super().setUp()
        self.root = _fixture_root
        self.package_dir = _fixture_package_dir
        self.descriptor = copy.deepcopy(_fixture_descriptor)
        self.leaves = set(leaf_ids(self.descriptor))

    def _placed(self, rows) -> list:
        """The rows an occurrence of the fixture places."""
        return [row for row in rows if row.get("occurrenceId") in self.leaves]


class AssemblyOccurrenceRefsTest(_AssemblyDisplayFixture, unittest.TestCase):

    def test_every_ref_the_lister_hands_out_resolves(self) -> None:
        """The bug as reported: ids present in assembly.json, absent from the resolver."""
        index = assembly_lookup.merge_assembly_occurrences(_empty_index(), self.descriptor, self.package_dir)
        ids = [str(row["id"]) for row in self.descriptor["occurrences"]]
        self.assertTrue(ids, "fixture assembly declares no occurrences")
        self.assertTrue(all(is_occurrence_token(occurrence_id) for occurrence_id in ids), ids)
        for occurrence_id in ids:
            with self.subTest(occurrence=occurrence_id):
                found = lookup.find(f"#{occurrence_id}", index)
                self.assertEqual("occurrence", found[0])
                self.assertEqual(occurrence_id, found[1]["id"])

    def test_an_assembly_has_no_single_occurrence(self) -> None:
        """A bare element name (`#f:…`) names an element of a document's ONE leaf; an
        assembly has none, so the bare form resolves to nothing rather than to a guess."""
        merged = assembly_lookup.merge_assembly_occurrences(_empty_index(), self.descriptor, self.package_dir)
        entities = assembly_lookup.merge_assembly_entities(merged, self.descriptor, self.package_dir)
        _occurrence, element = split_element_ref(str(entities.faces[0]["id"]))
        with self.assertRaisesRegex(ValueError, "needs an occurrence token in an assembly"):
            lookup.find(f"#{element}", entities)

    def test_a_part_artifact_is_composed_like_any_tree(self) -> None:
        """A tree's selector tables live in its components, a part's single component
        included: skipping parts left them with the empty base index, so no face or
        edge resolved on a part and its facts counted zero faces. Only a missing
        artifact returns the index untouched."""
        flat = _empty_index()
        part = _FakeArtifact(kind="part", artifact_path=self.package_dir)
        composed = assembly_lookup.index_with_assembly_occurrences(flat, part)
        self.assertIsNot(flat, composed)
        self.assertTrue(composed.occurrence_by_id, "the part's occurrences were not composed from its tree")
        self.assertIs(flat, assembly_lookup.index_with_assembly_occurrences(flat, None))

    def test_a_missing_package_directory_is_not_an_error(self) -> None:
        flat = _empty_index()
        absent = _FakeArtifact(kind="assembly", artifact_path=self.root / "nope")
        self.assertIs(flat, assembly_lookup.index_with_assembly_occurrences(flat, absent))

    def test_occurrences_are_reported_in_world_coordinates(self) -> None:
        rows = assembly_lookup.assembly_occurrence_rows(self.descriptor, self.package_dir)
        placed = [row for row in rows if row.get("bbox")]
        self.assertTrue(placed, "no occurrence carried a bbox")
        # The two identical boxes share a component and differ ONLY by placement, so
        # component-local bboxes would make them indistinguishable. World coordinates are the
        # frame the viewer shows and `snapshot --mode list` reports.
        centres = {
            tuple(round((row["bbox"]["min"][axis] + row["bbox"]["max"][axis]) / 2, 3) for axis in range(3))
            for row in placed
        }
        self.assertEqual(len(centres), len(placed), "occurrences collapsed to one position")


class AssemblyEntityRefsTest(_AssemblyDisplayFixture, unittest.TestCase):
    """Phase 2: the refs users actually pick. `#o:…/f:…` is the face of that occurrence's
    component that the name names -- the same name in the part's own table and in every
    occurrence of the part."""

    def _merged(self) -> lookup.SelectorIndex:
        return assembly_lookup.merge_assembly_entities(_empty_index(), self.descriptor, self.package_dir)

    def _first_face(self, merged: lookup.SelectorIndex, occurrence_id: str) -> dict:
        (row,) = [row for row in merged.faces if row["occurrenceId"] == occurrence_id and int(row["ordinal"]) == 1]
        return row

    def test_entity_refs_inside_an_occurrence_resolve(self) -> None:
        merged = self._merged()
        occurrence_id = str(self.descriptor["occurrences"][0]["id"])
        ref = element_ref(occurrence_id, str(self._first_face(merged, occurrence_id)["name"]))
        found = lookup.find(f"#{ref}", merged)
        self.assertEqual("face", found[0])
        self.assertEqual(ref, found[1]["id"])

    def test_a_face_keeps_its_component_name_and_ordinal(self) -> None:
        """The assembly ref carries the name the PART's own table uses, so a ref picked on
        one occurrence names the same face of every occurrence of that part; the ordinal is
        kept beside it as the mesh join."""
        merged = self._merged()
        twins = [leaf_id(self.descriptor, name) for name in ("box_a_1", "box_a_2")]
        rows = {str(row["id"]): row for row in self.descriptor["occurrences"]}
        self.assertEqual(rows[twins[0]]["component"], rows[twins[1]]["component"],
                         "the fixture's two identical boxes share one component")
        first, second = (self._first_face(merged, occurrence_id) for occurrence_id in twins)
        self.assertEqual(first["name"], second["name"])
        self.assertEqual((1, 1), (int(first["ordinal"]), int(second["ordinal"])))
        self.assertNotEqual(first["id"], second["id"], "each occurrence's ref names its own placement")
        self.assertEqual((twins[0], first["name"]), split_element_ref(str(first["id"])))

    def test_geometry_is_placed_and_rigid_invariants_survive(self) -> None:
        merged = self._merged()
        rows = self._placed(merged.faces)
        self.assertTrue(rows, "no placed faces were merged")
        # The two identical boxes differ ONLY by placement, so component-local boxes would be
        # identical. Distinct centres prove the occurrence transform was applied.
        centres = {tuple(round((row["bbox"]["min"][axis] + row["bbox"]["max"][axis]) / 2, 6) for axis in range(3))
                   for row in rows}
        self.assertGreater(len(centres), 1, "faces collapsed to one position")
        for row in self._placed(merged.edges):
            self.assertGreater(float(row["length"]), 0.0, "a rigid placement must preserve length")

    def test_a_normal_is_rotated_not_translated(self) -> None:
        """The silent failure: putting a direction through the full matrix makes it absorb the
        occurrence's offset, so it stops being a unit vector and points somewhere false."""
        merged = self._merged()
        placed = [row for row in self._placed(merged.faces) if row.get("normal")]
        self.assertTrue(placed)
        for row in placed:
            length = sum(component * component for component in row["normal"]) ** 0.5
            self.assertAlmostEqual(1.0, length, places=6, msg=f"{row['id']} normal is not unit")


class MergedRowsAreInternallyConsistentTest(_AssemblyDisplayFixture, unittest.TestCase):
    """Every id a merged row carries must point somewhere true.

    A component's rows index that component's own tables. Copied across unchanged they would
    still RESOLVE -- against the wrong thing, which is worse than not resolving at all, because
    the caller gets a confident answer. A face's ref names the occurrence that places it, and
    the face lies inside that occurrence's own box.
    """

    def _merged(self) -> lookup.SelectorIndex:
        occurrences = assembly_lookup.merge_assembly_occurrences(_empty_index(), self.descriptor, self.package_dir)
        return assembly_lookup.merge_assembly_entities(occurrences, self.descriptor, self.package_dir)

    def test_a_face_names_the_occurrence_that_contains_it(self) -> None:
        merged = self._merged()
        checked = 0
        for face in self._placed(merged.faces):
            occurrence_id, element = split_element_ref(str(face["id"]))
            self.assertEqual(occurrence_id, face["occurrenceId"])
            self.assertEqual(element, face["name"])
            occurrence = merged.occurrence_by_id[occurrence_id]
            # Geometric consistency, not just naming: a face has to lie inside its own solid.
            for axis in range(3):
                self.assertGreaterEqual(
                    face["bbox"]["min"][axis], occurrence["bbox"]["min"][axis] - 1e-6,
                    f"{face['id']} sits outside {occurrence_id}",
                )
                self.assertLessEqual(
                    face["bbox"]["max"][axis], occurrence["bbox"]["max"][axis] + 1e-6,
                    f"{face['id']} sits outside {occurrence_id}",
                )
            checked += 1
        self.assertGreater(checked, 0, "no placed faces were checked")

    def test_a_shape_carries_no_ref_of_its_own(self) -> None:
        """The occurrence names a body: its solids are listed, placed, for the facts a solid
        gives, under no id a selector could spell."""
        merged = self._merged()
        shapes = self._placed(merged.shapes)
        self.assertTrue(shapes, "no placed shapes were merged")
        for shape in shapes:
            self.assertNotIn("id", shape)
            with self.assertRaises(ValueError):
                lookup.find(f"#{shape['shapeId']}", merged)


class DormantPathsTest(unittest.TestCase):
    """Vertex placement in isolation, and geometry that cannot be placed.

    A synthetic one-edge component, so the placement of a vertex can be checked
    against numbers chosen here rather than read off a kernel's ordinals.
    """

    F1, E1, V1, V2 = "f:part.extrude1.1", "e:part.extrude1.1", "v:part.extrude1.1", "v:" + "4" * 12

    def _fake_table(self):
        """A component's own selector table (schema 3): element rows lead with their name
        and ordinal, and carry no id of their own."""
        return {
            "tables": {
                "occurrenceColumns": ["id", "name", "bbox"],
                "shapeColumns": ["ordinal", "bbox"],
                "faceColumns": ["name", "ordinal", "shape", "center", "edgeStart", "edgeCount"],
                "edgeColumns": ["name", "ordinal", "shape", "center", "vertexStart", "vertexCount"],
                "vertexColumns": ["name", "ordinal", "center", "edgeStart", "edgeCount"],
            },
            "occurrences": [["o:" + "0" * 12, "part", None]],
            "shapes": [[1, None]],
            "faces": [[self.F1, 1, 1, [0.0, 0.0, 0.0], 0, 1]],
            "edges": [[self.E1, 1, 1, [0.0, 0.0, 0.0], 0, 2]],
            "vertices": [
                [self.V1, 1, [0.0, 0.0, 0.0], 0, 1],
                [self.V2, 2, [1.0, 0.0, 0.0], 1, 1],
            ],
        }

    def test_every_occurrence_gets_its_own_placed_vertices(self) -> None:
        a, b = "o:" + "a" * 12, "o:" + "b" * 12
        descriptor = {
            "occurrences": [
                {"id": a, "name": "a", "component": "c", "transform": None},
                {"id": b, "name": "b", "component": "c",
                 "transform": [1, 0, 0, 100, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]},
            ]
        }
        with mock.patch.object(assembly_lookup, "_read_component_table", return_value=self._fake_table()):
            merged = assembly_lookup.merge_assembly_entities(_empty_index(), descriptor, Path("."))

        for occurrence_id in (a, b):
            for element in (self.V1, self.V2):
                found = lookup.find(f"#{element_ref(occurrence_id, element)}", merged)
                self.assertEqual("vertex", found[0])
                self.assertEqual(occurrence_id, found[1]["occurrenceId"])
                self.assertEqual(element, found[1]["name"])
        # ...and the second occurrence is genuinely 100 mm away, not a shared row.
        self.assertEqual(100.0, merged.vertex_by_id[element_ref(b, self.V1)]["center"][0])
        self.assertEqual(0.0, merged.vertex_by_id[element_ref(a, self.V1)]["center"][0])

    def test_geometry_that_cannot_be_placed_is_dropped_not_left_local(self) -> None:
        """A field kept unplaced would be a component-local number in an otherwise world-space
        row, shared by every occurrence of that component."""
        placed = assembly_lookup._place_entity_row(
            assembly_lookup._matrix([1, 0, 0, 5, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]),
            {"name": "x", "center": "not-a-point", "normal": None, "bbox": {"min": [0, 0, 0]}},
        )
        for field in ("center", "normal", "bbox"):
            self.assertNotIn(field, placed, f"{field} survived unplaced")
        self.assertEqual("x", placed["name"], "non-geometry fields are untouched")


class PlacementAgainstAnalyticGeometryTest(_AssemblyDisplayFixture, unittest.TestCase):
    """Placement checked against geometry we KNOW, not against our own arithmetic.

    The other tests here compare what the merge produced with what `transform_point` says it
    should be -- which is circular, since the merge calls `transform_point`. They pin that the
    right matrix reached the right field; they cannot pin the matrix CONVENTION, because both
    sides of the comparison share it.

    The fixture's boxes are placed by build123d at coordinates chosen here, so their world
    extents and face centres are known in advance by arithmetic no code in this repo performs.
    Measured against a column-major misread of the transform: these fail 3 assertions and name
    the wrong coordinates, where the circular tests fail 1 and only report that two occurrences
    landed on top of each other. Both notice; only this one says what is wrong.
    """

    # (label, half-extents, placement) -> the world box build123d must produce.
    _EXPECTED_BOXES = {
        "box_a_1": ((5.0, 5.0, 5.0), (0.0, 0.0, 0.0)),
        "box_a_2": ((5.0, 5.0, 5.0), (40.0, 0.0, 0.0)),
        "box_b": ((2.0, 3.0, 4.0), (0.0, 40.0, 0.0)),
        # rotated 90 deg about Z: the 4 mm X extent and 6 mm Y extent trade places.
        "box_rot": ((3.0, 2.0, 4.0), (0.0, -40.0, 0.0)),
    }

    def _expected_box(self, half, centre):
        return (
            [centre[axis] - half[axis] for axis in range(3)],
            [centre[axis] + half[axis] for axis in range(3)],
        )

    def test_occurrence_extents_match_geometry_placed_by_build123d(self) -> None:
        rows = {
            str(row["name"]): row
            for row in assembly_lookup.assembly_occurrence_rows(self.descriptor, self.package_dir)
        }
        checked = 0
        for label, (half, centre) in self._EXPECTED_BOXES.items():
            row = rows.get(label)
            if row is None or not row.get("bbox"):
                continue
            low, high = self._expected_box(half, centre)
            for axis in range(3):
                self.assertAlmostEqual(
                    low[axis], row["bbox"]["min"][axis], places=4,
                    msg=f"{label} min[{axis}] is not where build123d put it",
                )
                self.assertAlmostEqual(
                    high[axis], row["bbox"]["max"][axis], places=4,
                    msg=f"{label} max[{axis}] is not where build123d put it",
                )
            checked += 1
        self.assertEqual(len(self._EXPECTED_BOXES), checked, "not every fixture box was checked")

    def test_face_centres_land_on_the_box_faces_they_belong_to(self) -> None:
        """A box's six faces sit at its face midpoints, the middles of their boxes. Those are
        known numbers, so a placed face can be checked without asking the placement code where
        it should be."""
        merged = assembly_lookup.merge_assembly_entities(_empty_index(), self.descriptor, self.package_dir)
        by_occurrence: dict[str, list] = {}
        for row in self._placed(merged.faces):
            by_occurrence.setdefault(str(row["occurrenceId"]), []).append(row)
        names = {str(row["id"]): str(row.get("name")) for row in self.descriptor["occurrences"]}

        checked = 0
        for occurrence_id, faces in by_occurrence.items():
            expected = self._EXPECTED_BOXES.get(names.get(occurrence_id, ""))
            if expected is None:
                continue
            half, centre = expected
            wanted = set()
            for axis in range(3):
                for sign in (-1, 1):
                    point = list(centre)
                    point[axis] = centre[axis] + sign * half[axis]
                    wanted.add(tuple(round(value, 4) for value in point))
            found = {tuple(round((row["bbox"]["min"][axis] + row["bbox"]["max"][axis]) / 2, 4) for axis in range(3))
                     for row in faces}
            self.assertEqual(
                wanted, found, f"{occurrence_id} ({names.get(occurrence_id)}) faces are misplaced"
            )
            checked += 1
        self.assertEqual(len(self._EXPECTED_BOXES), checked, "not every fixture box was checked")


class TransformArithmeticTest(unittest.TestCase):
    """A box transformed by its min/max alone keeps its diagonal and loses its extent. Every
    occurrence in a posed assembly is rotated, so this is the failure mode that matters."""

    def test_a_rotated_box_is_transformed_by_its_corners(self) -> None:
        # 90 degrees about Z: x -> y, y -> -x.
        matrix = [
            0.0, -1.0, 0.0, 0.0,
            1.0, 0.0, 0.0, 0.0,
            0.0, 0.0, 1.0, 0.0,
            0.0, 0.0, 0.0, 1.0,
        ]
        box = {"min": [0.0, 0.0, 0.0], "max": [2.0, 6.0, 1.0]}
        placed = assembly_lookup.transform_bbox(matrix, box)
        self.assertIsNotNone(placed)
        for axis, (low, high) in enumerate(zip([-6.0, 0.0, 0.0], [0.0, 2.0, 1.0])):
            self.assertAlmostEqual(low, placed["min"][axis], places=6)
            self.assertAlmostEqual(high, placed["max"][axis], places=6)

    def test_translation_moves_the_box(self) -> None:
        matrix = [
            1.0, 0.0, 0.0, 5.0,
            0.0, 1.0, 0.0, -3.0,
            0.0, 0.0, 1.0, 0.0,
            0.0, 0.0, 0.0, 1.0,
        ]
        placed = assembly_lookup.transform_bbox(
            matrix, {"min": [0.0, 0.0, 0.0], "max": [1.0, 1.0, 1.0]}
        )
        self.assertEqual([5.0, -3.0, 0.0], placed["min"])
        self.assertEqual([6.0, -2.0, 1.0], placed["max"])

    def test_a_malformed_transform_falls_back_to_identity(self) -> None:
        box = {"min": [0.0, 0.0, 0.0], "max": [1.0, 2.0, 3.0]}
        rows = assembly_lookup.transform_bbox(assembly_lookup._matrix("nonsense"), box)
        self.assertEqual(box["min"], rows["min"])
        self.assertEqual(box["max"], rows["max"])

    def test_a_direction_ignores_the_translation_column(self) -> None:
        matrix = [
            1.0, 0.0, 0.0, 100.0,
            0.0, 1.0, 0.0, -50.0,
            0.0, 0.0, 1.0, 7.0,
            0.0, 0.0, 0.0, 1.0,
        ]
        self.assertEqual([0.0, 0.0, 1.0], assembly_lookup.transform_direction(matrix, [0, 0, 1]))
        # ...while a POINT under the same matrix does move.
        self.assertEqual([100.0, -50.0, 8.0], assembly_lookup.transform_point(matrix, [0, 0, 1]))

    def test_params_move_by_key_not_wholesale(self) -> None:
        """`origin` is a point, `axis`/`direction` are directions, `radius` is a length a rigid
        transform does not change. Leaving params local while center is placed would put one
        payload in two frames."""
        matrix = [
            1.0, 0.0, 0.0, 10.0,
            0.0, 1.0, 0.0, 0.0,
            0.0, 0.0, 1.0, 0.0,
            0.0, 0.0, 0.0, 1.0,
        ]
        placed = assembly_lookup._transform_params(
            matrix, {"origin": [1.0, 2.0, 3.0], "axis": [0.0, 0.0, 1.0], "radius": 3.0}
        )
        self.assertEqual([11.0, 2.0, 3.0], placed["origin"])
        self.assertEqual([0.0, 0.0, 1.0], placed["axis"])
        self.assertEqual(3.0, placed["radius"])

    def test_a_missing_bbox_is_none_rather_than_a_crash(self) -> None:
        self.assertIsNone(assembly_lookup.transform_bbox(assembly_lookup._matrix(None), None))
        self.assertIsNone(assembly_lookup.transform_bbox(assembly_lookup._matrix(None), {"min": [0, 0, 0]}))


def _nested_compound() -> Compound:
    """A branch with two parts under it, beside a loose part.

    Flat fixtures cannot exercise a group at all: every node there is a leaf. This
    one has a real interior node, which is what the viewer copies, what a kinematics mate
    names, and what `inspect` now accepts.
    """
    left = Pos(0, 0, 0) * Box(2, 2, 2)
    left.label = "bar_left"
    right = Pos(4, 0, 0) * Box(2, 2, 2)
    right.label = "bar_right"
    branch = Compound(children=[left, right])
    branch.label = "bar_pair"
    post = Pos(0, 0, 10) * Box(2, 2, 2)
    post.label = "post"
    assembly = Compound(children=[branch, post])
    assembly.label = "nested"
    return assembly


class AssemblyGroupNodesTest(unittest.TestCase):
    """The instance tree's INTERIOR nodes, which the occurrences table does not hold.

    The table is leaves only, because only a leaf owns geometry -- so a subassembly's
    NAME, the thing a person recognises the branch by, lives in the descriptor's
    `assembly` tree and nowhere else a selector index could reach.
    """

    def setUp(self) -> None:
        super().setUp()
        self.package_dir = _group_package_dir
        self.descriptor = copy.deepcopy(_group_descriptor)
        self.branch = node_id(self.descriptor, "bar_pair")

    def test_interior_nodes_are_reported_with_their_labels(self) -> None:
        nodes = assembly_lookup.assembly_group_nodes(self.descriptor)
        names = {node_id: entry["name"] for node_id, entry in nodes.items()}
        self.assertIn(self.branch, names, f"the branch is missing from {sorted(nodes)}")
        self.assertEqual("bar_pair", names[self.branch])
        self.assertEqual(2, nodes[self.branch]["childCount"])
        # Leaves are NOT interior nodes: their rows are in the occurrences table.
        leaf_ids = {str(row["id"]) for row in self.descriptor["occurrences"]}
        self.assertFalse(leaf_ids & set(nodes), "a leaf was reported as a group")

    def test_no_interior_node_carries_a_transform_today(self) -> None:
        # Pins the reason `inspect frame` reports a group's EXTENT rather than a matrix:
        # group placement is baked into each leaf's absolute transform, so the descriptor
        # writes no node transform and there is nothing to read. If a packager ever
        # records one, this fails and the frame payload starts carrying it -- which is
        # exactly the moment to notice.
        nodes = assembly_lookup.assembly_group_nodes(self.descriptor)
        self.assertTrue(nodes)
        self.assertFalse(
            [node_id for node_id, entry in nodes.items() if "transform" in entry],
            "a subassembly node now records a transform; teach frame to report it",
        )

    def test_the_merged_index_carries_the_group_nodes_and_their_members(self) -> None:
        merged = assembly_lookup.merge_assembly_occurrences(_empty_index(), self.descriptor, self.package_dir)
        self.assertEqual("bar_pair", merged.group_nodes[self.branch]["name"])
        # A group ref covers the leaves beneath it, by token.
        self.assertEqual(
            [leaf_id(self.descriptor, "bar_left"), leaf_id(self.descriptor, "bar_right")],
            merged.members[self.branch],
        )


if __name__ == "__main__":
    unittest.main()
