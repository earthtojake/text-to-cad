"""An assembly's refs must resolve in the namespace the tools actually hand out.

Issue 0b (tom-cad FEEDBACK.md): `snapshot --mode list` and the CAD Viewer enumerate instance-tree
occurrences -- `#o1.12 shoulder_yaw_yoke` -- while `inspect refs` and `snapshot --focus/--hide`
resolved against the whole-assembly topology sidecar, which is extracted from the COMPOSED
compound and therefore describes any assembly as ONE occurrence. Every ref a user could pick was
rejected by every tool that could measure it, and `--facts` reported `occurrenceCount: 1` for a
160-part assembly.

These cover the merge itself (real package, real descriptor) and the transform arithmetic, which
is the part with a wrong answer that looks plausible.
"""

from __future__ import annotations

from tests.python.support.store_fixtures import build_view

import tempfile
import unittest
from unittest import mock
from pathlib import Path

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from build123d import Box, Compound, Pos, Rot  # noqa: E402

from cadgen import assembly_lookup, lookup  # noqa: E402
from cadgen._internal import component_package  # noqa: E402
from cadgen.coordination.lock import exclusive  # noqa: E402
from cadgen.coordination.paths import write_lock_path  # noqa: E402


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


class _FakeArtifact:
    """Stands in for StepTopologyArtifact: the merge only reads `kind` and `artifact_path`."""

    def __init__(self, kind: str, artifact_path: Path) -> None:
        self.kind = kind
        self.artifact_path = artifact_path


class AssemblyOccurrenceRefsTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="assembly-refs-")
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.package_dir = self.root / "__cadgen__" / "models" / "demo.py"
        with exclusive(write_lock_path(self.package_dir)):
            build_view(
                _demo_compound(), package_dir=self.package_dir, root_name="demo"
            )
        descriptor = component_package.read_package_descriptor(self.package_dir)
        self.assertIsInstance(descriptor, dict, "fixture package has no descriptor")
        self.descriptor = descriptor

    def _flat_index(self) -> lookup.SelectorIndex:
        """A stand-in for the composed-compound sidecar: one occurrence, as the real one has."""
        manifest = {
            "stats": {"occurrenceCount": 1, "shapeCount": 3},
            "tables": {"occurrenceColumns": ["id", "name", "bbox"]},
            "occurrences": [["o1", "demo.step", None]],
        }
        return lookup.build_selector_index(manifest)

    def test_every_ref_the_lister_hands_out_resolves(self) -> None:
        """The bug as reported: ids present in assembly.json, absent from the resolver."""
        index = assembly_lookup.merge_assembly_occurrences(
            self._flat_index(), self.descriptor, self.package_dir
        )
        ids = [str(row["id"]) for row in self.descriptor["occurrences"]]
        self.assertTrue(ids, "fixture assembly declares no occurrences")
        for occurrence_id in ids:
            with self.subTest(occurrence=occurrence_id):
                found = lookup.lookup_selector(f"#{occurrence_id}", index)
                self.assertIsNotNone(found, f"{occurrence_id} did not resolve")
                self.assertEqual("occurrence", found[0])

    def test_the_flat_namespace_still_resolves(self) -> None:
        """The merge is ADDITIVE. `#o1` and bare-ordinal refs are what every existing caller
        and test uses; fixing instance refs must not cost them."""
        flat = self._flat_index()
        merged = assembly_lookup.merge_assembly_occurrences(
            flat, self.descriptor, self.package_dir
        )
        self.assertIsNotNone(lookup.lookup_selector("#o1", merged))
        self.assertEqual(flat.single_occurrence_id, merged.single_occurrence_id)

    def test_the_reported_occurrence_count_stops_saying_one(self) -> None:
        merged = assembly_lookup.merge_assembly_occurrences(
            self._flat_index(), self.descriptor, self.package_dir
        )
        summary = lookup.entry_summary(merged)
        self.assertGreater(
            int(summary["occurrenceCount"]),
            1,
            "`inspect refs --facts` reported occurrenceCount 1 for a whole assembly",
        )

    def test_a_non_assembly_artifact_is_returned_untouched(self) -> None:
        """The guardrail. Part entries are the common path and must not notice this change."""
        flat = self._flat_index()
        part = _FakeArtifact(kind="part", artifact_path=self.package_dir)
        self.assertIs(flat, assembly_lookup.index_with_assembly_occurrences(flat, part))
        self.assertIs(flat, assembly_lookup.index_with_assembly_occurrences(flat, None))

    def test_a_missing_package_directory_is_not_an_error(self) -> None:
        flat = self._flat_index()
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


class AssemblyEntityRefsTest(AssemblyOccurrenceRefsTest):
    """Phase 2: the refs users actually pick. `#o1.12.f19` is face 19 of that occurrence's
    component, which is the translation they were doing by hand -- and which the flat
    whole-assembly namespace cannot express, since its numbering does not agree with the
    component's ("the assembly's f18 is the wall's face; the part's f18 is a cylinder")."""

    def _merged(self) -> lookup.SelectorIndex:
        return assembly_lookup.merge_assembly_entities(
            self._flat_index(), self.descriptor, self.package_dir
        )

    def test_entity_refs_inside_an_occurrence_resolve(self) -> None:
        merged = self._merged()
        occurrence_id = str(self.descriptor["occurrences"][0]["id"])
        found = lookup.lookup_selector(f"#{occurrence_id}.f1", merged)
        self.assertIsNotNone(found, f"{occurrence_id}.f1 did not resolve")
        self.assertEqual("face", found[0])

    def test_a_face_keeps_its_component_ordinal(self) -> None:
        """The assembly ref carries the number the PART's own namespace uses, so a translated
        ref stays checkable by hand against the part file."""
        merged = self._merged()
        occurrence_id = str(self.descriptor["occurrences"][0]["id"])
        kind, row = lookup.lookup_selector(f"#{occurrence_id}.f1", merged)
        self.assertEqual(1, int(row["ordinal"]))
        self.assertEqual(occurrence_id, str(row["occurrenceId"]))

    def test_geometry_is_placed_and_rigid_invariants_survive(self) -> None:
        merged = self._merged()
        rows = [row for row in merged.faces if str(row.get("occurrenceId", "")).count(".") >= 1]
        self.assertTrue(rows, "no placed faces were merged")
        # The two identical boxes differ ONLY by placement, so component-local centres would be
        # identical. Distinct centres prove the occurrence transform was applied.
        centres = {tuple(round(value, 6) for value in row["center"]) for row in rows}
        self.assertGreater(len(centres), 1, "faces collapsed to one position")
        for row in rows:
            self.assertGreater(float(row["area"]), 0.0, "a rigid placement must preserve area")

    def test_a_normal_is_rotated_not_translated(self) -> None:
        """The silent failure: putting a direction through the full matrix makes it absorb the
        occurrence's offset, so it stops being a unit vector and points somewhere false."""
        merged = self._merged()
        placed = [row for row in merged.faces if row.get("normal") and row.get("occurrenceId")]
        self.assertTrue(placed)
        for row in placed:
            length = sum(component * component for component in row["normal"]) ** 0.5
            self.assertAlmostEqual(1.0, length, places=6, msg=f"{row['id']} normal is not unit")

    def test_adjacency_stays_inside_the_occurrence(self) -> None:
        """Relation rows index their own component's tables and are re-based as they merge.
        Without that, adjacency returns confident wrong neighbours -- worse than none."""
        merged = self._merged()
        occurrence_id = str(self.descriptor["occurrences"][0]["id"])
        _, face = lookup.lookup_selector(f"#{occurrence_id}.f1", merged)
        neighbours = lookup.face_adjacent_edge_selectors(face, merged)
        self.assertTrue(neighbours, "a solid's face has adjacent edges")
        for selector in neighbours:
            self.assertTrue(
                selector.startswith(f"{occurrence_id}."),
                f"{selector} escaped {occurrence_id} -- relation offsets are wrong",
            )

    def test_the_flat_entity_namespace_still_resolves(self) -> None:
        """Additive, again: a bare `#f1` still canonicalizes through single_occurrence_id into
        the composed-compound namespace, which is what every part-shaped caller relies on."""
        flat = self._flat_index()
        merged = self._merged()
        self.assertEqual(flat.single_occurrence_id, merged.single_occurrence_id)


class MergedRowsAreInternallyConsistentTest(AssemblyOccurrenceRefsTest):
    """Every id and every RANGE a merged row carries must point somewhere true.

    A component's rows index that component's own tables. Copied across unchanged they all still
    RESOLVE -- against the wrong thing, which is worse than not resolving at all, because the
    caller gets a confident answer. `#o1.12.f19` used to report `shapeId s1`, and `s1` in the
    merged index is a solid 40 mm away from the face claiming it.
    """

    def _merged(self) -> lookup.SelectorIndex:
        occurrences = assembly_lookup.merge_assembly_occurrences(
            self._flat_index(), self.descriptor, self.package_dir
        )
        return assembly_lookup.merge_assembly_entities(
            occurrences, self.descriptor, self.package_dir
        )

    def test_a_face_names_a_shape_that_exists_and_contains_it(self) -> None:
        merged = self._merged()
        checked = 0
        for face in merged.faces:
            occurrence_id = str(face.get("occurrenceId") or "")
            if not occurrence_id or occurrence_id == "o1":
                continue
            shape_id = str(face.get("shapeId") or "")
            self.assertTrue(
                shape_id.startswith(f"{occurrence_id}."),
                f"{face['id']} names {shape_id}, which belongs to another occurrence",
            )
            shape = merged.shape_by_id.get(shape_id)
            self.assertIsNotNone(shape, f"{face['id']} names a shape that does not resolve")
            # Geometric consistency, not just naming: a face has to lie inside its own solid.
            for axis in range(3):
                self.assertGreaterEqual(
                    face["bbox"]["min"][axis], shape["bbox"]["min"][axis] - 1e-6,
                    f"{face['id']} sits outside {shape_id}",
                )
                self.assertLessEqual(
                    face["bbox"]["max"][axis], shape["bbox"]["max"][axis] + 1e-6,
                    f"{face['id']} sits outside {shape_id}",
                )
            checked += 1
        self.assertGreater(checked, 0, "no placed faces were checked")

    def test_shape_refs_resolve_and_slice_their_own_faces(self) -> None:
        merged = self._merged()
        checked = 0
        for shape in merged.shapes:
            occurrence_id = str(shape.get("occurrenceId") or "")
            if not occurrence_id or occurrence_id == "o1":
                continue
            self.assertIsNotNone(lookup.lookup_selector(f"#{shape['id']}", merged))
            start = int(shape.get("faceStart") or 0)
            count = int(shape.get("faceCount") or 0)
            self.assertGreater(count, 0)
            for face in merged.faces[start : start + count]:
                self.assertEqual(
                    shape["id"], str(face.get("shapeId")),
                    "a shape's face range must contain exactly its own faces",
                )
            checked += 1
        self.assertGreater(checked, 0, "no placed shapes were checked")

    def test_an_occurrence_range_slices_its_own_entities(self) -> None:
        merged = self._merged()
        checked = 0
        for occurrence_id, row in merged.occurrence_by_id.items():
            if occurrence_id == "o1" or not int(row.get("faceCount") or 0):
                continue
            start = int(row["faceStart"])
            faces = merged.faces[start : start + int(row["faceCount"])]
            self.assertTrue(faces, f"{occurrence_id} has an empty face range")
            for face in faces:
                self.assertEqual(occurrence_id, str(face.get("occurrenceId")))
            checked += 1
        self.assertGreater(checked, 0, "no occurrence ranges were checked")

    def test_the_index_it_was_handed_is_left_alone(self) -> None:
        """SelectorIndex is a frozen dataclass -- a value. `replace()` makes a new one, but the
        ROW DICTS are shared, so writing occurrence ranges in place left the caller's index
        claiming slices of lists it does not have."""
        occurrences = assembly_lookup.merge_assembly_occurrences(
            self._flat_index(), self.descriptor, self.package_dir
        )
        occurrence_id = str(self.descriptor["occurrences"][0]["id"])
        before = dict(occurrences.occurrence_by_id[occurrence_id])
        merged = assembly_lookup.merge_assembly_entities(
            occurrences, self.descriptor, self.package_dir
        )
        self.assertEqual(
            before, occurrences.occurrence_by_id[occurrence_id],
            "the input index's occurrence row was rewritten in place",
        )
        self.assertGreater(
            int(merged.occurrence_by_id[occurrence_id]["faceCount"]), 0,
            "the merged index should carry the ranges instead",
        )

    def test_buffer_offsets_are_dropped_rather_than_carried_stale(self) -> None:
        """These index the COMPONENT's proxy buffers. The merged index holds the flat
        assembly's, so a copied start points into unrelated data -- silently, and only for
        whoever renders a highlight from it. Absent makes that a KeyError instead."""
        merged = self._merged()
        for rows in (merged.faces, merged.edges):
            for row in rows:
                if not str(row.get("occurrenceId") or "").count("."):
                    continue
                for field in ("triangleStart", "segmentStart", "surfaceHalfEdgeStart"):
                    self.assertNotIn(field, row, f"{row['id']} carries a stale {field}")

    def test_adjacency_rows_stay_in_range(self) -> None:
        """Every relation row is an index into a list we concatenated into. An un-rebased one
        still lands somewhere -- on another occurrence's edge."""
        merged = self._merged()
        for face in merged.faces:
            occurrence_id = str(face.get("occurrenceId") or "")
            if not occurrence_id or occurrence_id == "o1":
                continue
            for selector in lookup.face_adjacent_edge_selectors(face, merged):
                self.assertTrue(
                    selector.startswith(f"{occurrence_id}."),
                    f"{face['id']} is adjacent to {selector}, which is not its own",
                )


class DormantPathsTest(unittest.TestCase):
    """Vertices, and geometry that cannot be placed.

    No model in this repo carries vertices -- every component bundle reports vertexCount 0 -- so
    the vertex rebasing is dead code that will wake up the first time a package has one. That is
    exactly when nobody will be looking at it, so it is driven here with a synthetic component.
    """

    def _fake_component(self):
        manifest = {
            "tables": {
                "occurrenceColumns": ["id", "name", "bbox"],
                "shapeColumns": ["id", "occurrenceId", "ordinal", "bbox"],
                "faceColumns": ["id", "occurrenceId", "shapeId", "ordinal", "center", "edgeStart", "edgeCount"],
                "edgeColumns": ["id", "occurrenceId", "shapeId", "ordinal", "center", "vertexStart", "vertexCount"],
                "vertexColumns": ["id", "occurrenceId", "ordinal", "center", "edgeStart", "edgeCount"],
            },
            "occurrences": [["o1", "part", None]],
            "shapes": [["o1.s1", "o1", 1, None]],
            "faces": [["o1.f1", "o1", "o1.s1", 1, [0.0, 0.0, 0.0], 0, 1]],
            "edges": [["o1.e1", "o1", "o1.s1", 1, [0.0, 0.0, 0.0], 0, 2]],
            "vertices": [
                ["o1.v1", "o1", 1, [0.0, 0.0, 0.0], 0, 1],
                ["o1.v2", "o1", 2, [1.0, 0.0, 0.0], 1, 1],
            ],
            "relations": {
                "faceEdgeRows": [0],
                "edgeFaceRows": [0],
                "edgeVertexRows": [0, 1],
                "vertexEdgeRows": [0, 0],
            },
        }
        return lookup.build_selector_index(manifest)

    def test_vertex_ranges_are_rebased_for_every_occurrence(self) -> None:
        component = self._fake_component()
        descriptor = {
            "occurrences": [
                {"id": "o1.1", "name": "a", "component": "c", "transform": None},
                {"id": "o1.2", "name": "b", "component": "c",
                 "transform": [1, 0, 0, 100, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]},
            ]
        }
        flat = lookup.build_selector_index(
            {"tables": {"occurrenceColumns": ["id"]}, "occurrences": [["o1"]]}
        )
        with mock.patch.object(assembly_lookup, "_component_index", return_value=component):
            merged = assembly_lookup.merge_assembly_entities(flat, descriptor, Path("."))

        for occurrence_id in ("o1.1", "o1.2"):
            edge = merged.edge_by_id[f"{occurrence_id}.e1"]
            neighbours = lookup.edge_adjacent_vertex_selectors(edge, merged)
            self.assertEqual(
                [f"{occurrence_id}.v1", f"{occurrence_id}.v2"], neighbours,
                f"{occurrence_id}.e1 reached another occurrence's vertices",
            )
            vertex = merged.vertex_by_id[f"{occurrence_id}.v2"]
            self.assertEqual(
                [f"{occurrence_id}.e1"], lookup.vertex_adjacent_edge_selectors(vertex, merged),
            )
        # ...and the second occurrence is genuinely 100 mm away, not a shared row.
        self.assertEqual(100.0, merged.vertex_by_id["o1.2.v1"]["center"][0])
        self.assertEqual(0.0, merged.vertex_by_id["o1.1.v1"]["center"][0])

    def test_geometry_that_cannot_be_placed_is_dropped_not_left_local(self) -> None:
        """A field kept unplaced would be a component-local number in an otherwise world-space
        row, shared by every occurrence of that component."""
        placed = assembly_lookup._place_entity_row(
            assembly_lookup._matrix([1, 0, 0, 5, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]),
            {"id": "x", "center": "not-a-point", "normal": None, "bbox": {"min": [0, 0, 0]}},
        )
        for field in ("center", "normal", "bbox"):
            self.assertNotIn(field, placed, f"{field} survived unplaced")
        self.assertEqual("x", placed["id"], "non-geometry fields are untouched")


class PlacementAgainstAnalyticGeometryTest(AssemblyOccurrenceRefsTest):
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
        """A box's six faces sit at its face midpoints. Those are known numbers, so a placed
        face centre can be checked without asking the placement code where it should be."""
        merged = assembly_lookup.merge_assembly_entities(
            self._flat_index(), self.descriptor, self.package_dir
        )
        by_occurrence: dict[str, list] = {}
        for row in merged.faces:
            occurrence_id = str(row.get("occurrenceId") or "")
            if occurrence_id and occurrence_id != "o1":
                by_occurrence.setdefault(occurrence_id, []).append(row)
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
            found = {tuple(round(value, 4) for value in row["center"]) for row in faces}
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

    Flat fixtures cannot exercise a group at all: `o1.1`, `o1.2` are leaves there. This
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
        self._tmp = tempfile.TemporaryDirectory(prefix="assembly-groups-")
        self.addCleanup(self._tmp.cleanup)
        self.package_dir = Path(self._tmp.name) / "__cadgen__" / "models" / "nested.py"
        with exclusive(write_lock_path(self.package_dir)):
            build_view(
                _nested_compound(), package_dir=self.package_dir, root_name="nested"
            )
        self.descriptor = component_package.read_package_descriptor(self.package_dir)
        self.assertIsInstance(self.descriptor, dict, "fixture package has no descriptor")

    def test_interior_nodes_are_reported_with_their_labels(self) -> None:
        nodes = assembly_lookup.assembly_group_nodes(self.descriptor)
        names = {node_id: entry["name"] for node_id, entry in nodes.items()}
        self.assertIn("o1.1", names, f"the branch is missing from {sorted(nodes)}")
        self.assertEqual("bar_pair", names["o1.1"])
        self.assertEqual(2, nodes["o1.1"]["childCount"])
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

    def test_the_merged_index_carries_the_group_nodes(self) -> None:
        manifest = {
            "stats": {"occurrenceCount": 1, "shapeCount": 3},
            "tables": {"occurrenceColumns": ["id", "name", "bbox"]},
            "occurrences": [["o1", "nested.step", None]],
        }
        merged = assembly_lookup.merge_assembly_occurrences(
            lookup.build_selector_index(manifest), self.descriptor, self.package_dir
        )
        self.assertEqual("bar_pair", merged.group_nodes["o1.1"]["name"])
        # And the count stays a LEAF count: a group resolves by expanding to leaves that
        # are already in it.
        self.assertEqual(
            len(merged.occurrence_by_id), int(lookup.entry_summary(merged)["occurrenceCount"])
        )


if __name__ == "__main__":
    unittest.main()
