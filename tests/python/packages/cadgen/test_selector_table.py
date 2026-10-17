"""The per-component selector table: every fact a ref resolves to, under its element's name.

Tiny generated BREPs, built here: a box (every edge and face alone), a box with
its vertical edges filleted (tangent groups), and an extruded slot (a chain of
lines and arcs). The table is derived from the exact BREP and its topology
facts, so each expectation is a fact of the shape, not of a tessellation.
"""

from __future__ import annotations

import json
import unittest

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from build123d import Axis, Box, BuildPart, BuildSketch, Plane, SlotOverall, extrude, fillet  # noqa: E402

from cadgen._internal.geometric_tokens import element_names, element_tokens  # noqa: E402
from cadgen._internal.glb_topology import STEP_EDGE_FLAGS  # noqa: E402
from cadgen.cad_ref_syntax import is_element_name  # noqa: E402
from cadgen._internal.selector_table import (  # noqa: E402
    SELECTOR_TABLE_SCHEMA_VERSION,
    build_selector_table,
    read_selector_table,
    selector_table_bytes,
)
from cadgen._internal.topology_extract import extract_topology_facts  # noqa: E402


def _table(part, lineage=None):
    """The part's table as a derivation builds it: from its facts, its names and its display
    mesh's boxes."""
    from cadgen._internal.tessellate import mesh_component
    from cadgen.tessellation_policy import DISPLAY_TESSELLATION

    shape = part.wrapped
    facts = extract_topology_facts(shape)
    boxes = mesh_component(shape, facts, {}, part="0" * 64 + "-v1", chord=DISPLAY_TESSELLATION["chordTolerance"],
                           angle=DISPLAY_TESSELLATION["angleTolerance"]).boxes
    return build_selector_table(shape, facts, element_names(lineage, shape), boxes=boxes)


def _rows(table, name):
    key = {"shapes": "shapeColumns", "faces": "faceColumns", "edges": "edgeColumns", "vertices": "vertexColumns"}[name]
    return [dict(zip(table["tables"][key], row)) for row in table[name]]


def _slot():
    with BuildPart() as slot:
        with BuildSketch(Plane.XY):
            SlotOverall(30, 10)
        extrude(amount=5)
    return slot.part


class BoxTableTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.table = _table(Box(10, 20, 30))

    def test_rows_carry_the_names_of_the_elements_by_ordinal(self) -> None:
        table = self.table
        self.assertEqual(table["schemaVersion"], SELECTOR_TABLE_SCHEMA_VERSION)
        self.assertEqual(table["stats"], {"occurrenceCount": 1, "leafOccurrenceCount": 1, "shapeCount": 1,
                                          "faceCount": 6, "edgeCount": 12, "vertexCount": 8})
        # No lineage: every element goes by its geometric token.
        tokens = element_tokens(Box(10, 20, 30).wrapped)
        for name, kind in (("faces", "face"), ("edges", "edge"), ("vertices", "vertex")):
            rows = _rows(table, name)
            # The ordinal is the mesh join; the name is what a ref names. Both columns lead.
            columns = table["tables"][{"faces": "faceColumns", "edges": "edgeColumns", "vertices": "vertexColumns"}[name]]
            self.assertEqual(columns[:2], ["name", "ordinal"])
            self.assertEqual([row["ordinal"] for row in rows], list(range(1, len(rows) + 1)))
            self.assertEqual([row["name"] for row in rows], tokens[name])
            for row in rows:
                self.assertTrue(is_element_name(row["name"], kind), row["name"])
                self.assertEqual(row["shape"], 1)
            self.assertEqual(len(set(row["name"] for row in rows)), len(rows), "names are distinct")
        for row in _rows(table, "shapes"):
            self.assertEqual(row["ordinal"], 1)
            self.assertNotIn("name", row, "a shape has no name: a ref never names one")

    def test_a_lineage_names_the_rows_it_names(self) -> None:
        lineage = {"faces": [f"f:part.make_box1.{n}" for n in range(1, 7)],
                   "edges": [None, *[f"e:part.make_box1.{n}" for n in range(2, 13)]],
                   "vertices": [f"v:part.make_box1.{n}" for n in range(1, 9)]}
        table = _table(Box(10, 20, 30), lineage)
        self.assertEqual([row["name"] for row in _rows(table, "faces")], lineage["faces"])
        edges = [row["name"] for row in _rows(table, "edges")]
        self.assertEqual(edges[1:], lineage["edges"][1:])
        self.assertEqual(edges[0], element_tokens(Box(10, 20, 30).wrapped)["edges"][0])

    def test_every_edge_and_face_stands_alone(self) -> None:
        # At a box corner each edge end has two continuations and neither runs on through it.
        edges = _rows(self.table, "edges")
        self.assertEqual(sorted(row["chain"] for row in edges), list(range(1, 13)))
        self.assertEqual(sorted(row["tangentGroup"] for row in _rows(self.table, "faces")), list(range(1, 7)))

    def test_vertices_and_their_adjacency(self) -> None:
        table = self.table
        vertices = _rows(table, "vertices")
        self.assertEqual({tuple(abs(v) for v in row["center"]) for row in vertices}, {(5.0, 10.0, 15.0)})
        edges = _rows(table, "edges")
        for row in vertices:
            self.assertEqual(row["edgeCount"], 3)
            touching = table["relations"]["vertexEdgeRows"][row["edgeStart"]:row["edgeStart"] + row["edgeCount"]]
            for edge_row in touching:
                edge = edges[edge_row]
                ends = table["relations"]["edgeVertexRows"][edge["vertexStart"]:edge["vertexStart"] + edge["vertexCount"]]
                self.assertIn(vertices.index(row), ends, f"{edge['name']} ends at {row['name']}")
        for edge in edges:
            self.assertEqual(edge["vertexCount"], 2)
            self.assertEqual(edge["faceCount"], 2)
        faces = _rows(table, "faces")
        for face in faces:
            self.assertEqual(face["edgeCount"], 4)
            self.assertIsNotNone(face["normal"], "a plane carries its normal")
        self.assertEqual(table["bbox"], {"min": [-5.0, -10.0, -15.0], "max": [5.0, 10.0, 15.0]})

    def test_the_bytes_read_as_written_and_a_foreign_payload_is_refused(self) -> None:
        payload = selector_table_bytes(self.table)
        self.assertEqual(read_selector_table(payload), json.loads(payload))
        damaged = json.loads(payload)
        damaged["faces"][0][0] = "f7"  # an ordinal is not a name
        with self.assertRaises(ValueError):
            read_selector_table(json.dumps(damaged).encode())
        twice = json.loads(payload)
        twice["edges"][1][0] = twice["edges"][0][0]
        with self.assertRaises(ValueError):
            read_selector_table(json.dumps(twice).encode())
        gap = json.loads(payload)
        gap["vertices"][2][1] = 9
        with self.assertRaises(ValueError):
            read_selector_table(json.dumps(gap).encode())
        with self.assertRaises(ValueError):
            read_selector_table(json.dumps({**json.loads(payload), "schemaVersion": 99}).encode())
        with self.assertRaises(ValueError):
            read_selector_table(b"not json")


class FilletedBoxTableTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.table = _table(fillet(Box(10, 20, 30).edges().filter_by(Axis.Z), 2))

    def test_tangent_groups_join_the_fillets_to_the_walls(self) -> None:
        faces = _rows(self.table, "faces")
        wrapped = {row["ordinal"] for row in faces if row["surfaceType"] == "cylinder"}
        self.assertEqual(len(wrapped), 4)
        groups = {row["ordinal"]: row["tangentGroup"] for row in faces}
        band = {groups[ordinal] for ordinal in wrapped}
        self.assertEqual(len(band), 1, "the four fillets wrap one band of faces")
        band_id = band.pop()
        walls = [row for row in faces if row["surfaceType"] == "plane" and groups[row["ordinal"]] == band_id]
        self.assertEqual(len(walls), 4, "the four side walls join the fillets")
        caps = [row for row in faces if groups[row["ordinal"]] != band_id]
        self.assertEqual(len(caps), 2)
        self.assertNotEqual(groups[caps[0]["ordinal"]], groups[caps[1]["ordinal"]])

    def test_a_chain_runs_round_each_cap_through_the_tangent_arcs(self) -> None:
        edges = _rows(self.table, "edges")
        by_chain: dict[int, list[dict]] = {}
        for row in edges:
            by_chain.setdefault(row["chain"], []).append(row)
        loops = [members for members in by_chain.values() if len(members) > 1]
        self.assertEqual(len(loops), 2, "one chain per cap")
        for members in loops:
            self.assertEqual(sorted(row["curveType"] for row in members), ["circle"] * 4 + ["line"] * 4)
            self.assertEqual(len({round(row["center"][2], 6) for row in members}), 1, "a loop lies in one plane")
        # The vertical tangent edges between a fillet and a wall are chains of their own.
        singles = [members[0] for members in by_chain.values() if len(members) == 1]
        self.assertEqual(len(singles), 8)
        self.assertTrue(all(row["visibilityClass"] == "tangent" for row in singles))


class SlotChainTest(unittest.TestCase):
    def test_lines_and_arcs_chain_where_they_meet_tangentially(self) -> None:
        table = _table(_slot())
        edges = _rows(table, "edges")
        by_chain: dict[int, list[dict]] = {}
        for row in edges:
            by_chain.setdefault(row["chain"], []).append(row)
        loops = sorted((members for members in by_chain.values() if len(members) > 1), key=lambda m: m[0]["center"][2])
        self.assertEqual([len(members) for members in loops], [4, 4])
        for members in loops:
            self.assertEqual(sorted(row["curveType"] for row in members), ["circle", "circle", "line", "line"])
        # The vertical edges meet each loop at a right angle: they continue nothing.
        verticals = [row for row in edges if row["curveType"] == "line" and abs(row["bbox"]["max"][2] - row["bbox"]["min"][2]) > 4]
        self.assertEqual(len(verticals), 4)
        self.assertTrue(all(len(by_chain[row["chain"]]) == 1 for row in verticals))
        # A circular edge's params carry its sweep, so no reader re-derives it from the curve.
        for row in edges:
            if row["curveType"] == "circle":
                self.assertAlmostEqual(row["params"]["sweepRadians"], 3.141592653589793, places=6)


class MeasuredWhereReadTest(unittest.TestCase):
    def test_a_face_row_carries_no_area_and_an_edge_its_length_and_relevance(self) -> None:
        # A face's area and centroid are measured where a view asks (``store.parts.measure_face``).
        table = _table(Box(1, 2, 3))
        self.assertFalse({"area", "center", "relevance", "flags"} & set(table["tables"]["faceColumns"]))
        self.assertNotIn("area", table["tables"]["shapeColumns"])
        edges = _rows(table, "edges")
        self.assertEqual(sorted(round(row["length"], 9) for row in edges), [1.0] * 4 + [2.0] * 4 + [3.0] * 4)
        self.assertTrue(all(row["relevance"] > 0 and not row["flags"] & STEP_EDGE_FLAGS["NOT_REFERENCEABLE"]
                            for row in edges))


if __name__ == "__main__":
    unittest.main()
