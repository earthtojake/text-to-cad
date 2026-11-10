#!/usr/bin/env python3

"""3D printing's measurements (``cad.trimesh._printing``) and its check (``cad.<type>.dfm(...,
process="printing")``).

Each part is built with build123d so the correct answer is known from the
construction rather than from a recorded run: a 2 mm wall is 2 mm because it
was built that way, and a 30 deg underside is below a 45 deg limit by
geometry. A regression then shows up as a disagreement with the model, not as
a diff against whatever the tool happened to print last time.
"""

from __future__ import annotations

import json
import math
import tempfile
import unittest
from pathlib import Path

import trimesh
from build123d import Align, Box, Cylinder, Polyline, Pos, Rotation, export_stl, extrude, make_face

import cad
from cad.trimesh import _printing as dfam_tool


def _stl(part, tmp: Path, name: str) -> str:
    path = tmp / f"{name}.stl"
    export_stl(part, str(path))
    return str(path)


def _wedge(angle_deg: float, length: float = 30.0, width: float = 12.0):
    """Cantilever whose underside rises at angle_deg from horizontal.

    Vertex order matters: built the other way up this is a ramp, which is
    self-supporting and tests nothing.
    """
    h = max(length * math.tan(math.radians(angle_deg)), 0.6)
    pts = [(0, 0, 0), (length, h, 0), (0, h, 0), (0, 0, 0)]
    return Rotation(90, 0, 0) * extrude(make_face(Polyline(*pts)), width)


def _hollow_box(wall: float, outer: float = 24.0, height: float = 16.0):
    inner = max(outer - 2 * wall, 0.5)
    return Box(outer, outer, height) - Pos(0, 0, wall) * Box(inner, inner, height)


class MeshFactsTest(unittest.TestCase):
    def test_solid_box_is_watertight_single_body(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            mesh = dfam_tool._load(_stl(Box(20, 20, 15), tmp, "box"))
            facts = dfam_tool._mesh_facts(mesh)

        self.assertTrue(facts["watertight"])
        self.assertEqual(facts["body_count"], 1)
        self.assertEqual(facts["euler_number"], 2)
        self.assertAlmostEqual(facts["volume_mm3"], 6000.0, delta=1.0)


def _cracked_box(tmp: Path) -> str:
    """A 10 mm cube's STL as an exporter leaves one: triangle soup, a collapsed triangle, and a T-junction
    whose sliver crack is 0.001 mm wide."""
    import numpy as np

    box = trimesh.creation.box((10, 10, 10))
    vertices, faces = np.asarray(box.vertices, dtype=float), np.asarray(box.faces)
    a, b, c = (int(v) for v in faces[0])  # split edge a-b of the first triangle at a point just off it
    middle = (vertices[a] + vertices[b]) / 2 + 0.001 * (vertices[c] - (vertices[a] + vertices[b]) / 2) / 5
    vertices = np.vstack([vertices, middle])
    m = len(vertices) - 1
    faces = np.vstack([[[a, m, c], [m, b, c]], faces[1:], [[a, a, b]]])
    soup = trimesh.Trimesh(vertices[faces].reshape(-1, 3), np.arange(3 * len(faces)).reshape(-1, 3), process=False)
    path = tmp / "cracked.stl"
    soup.export(path)
    return str(path)


class MeshCleanTest(unittest.TestCase):
    def test_a_welded_mesh_with_a_crack_closed_is_one_watertight_body(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            raw = trimesh.load(_cracked_box(Path(td)), force="mesh")
            self.assertFalse(raw.is_watertight, "read as written, the cube is open")
            mesh = dfam_tool._load(_cracked_box(Path(td)))
        facts = dfam_tool._mesh_facts(mesh)
        self.assertTrue(facts["watertight"])
        self.assertEqual(facts["body_count"], 1)
        self.assertAlmostEqual(facts["volume_mm3"], 1000.0, delta=0.5)
        self.assertEqual((facts["degenerate_faces_dropped"], facts["cracks_closed"]), (1, 1))

    def test_a_crack_closes_beside_two_openings_that_share_a_corner(self) -> None:
        import numpy as np

        from cad.trimesh import _mesh

        with tempfile.TemporaryDirectory() as td:
            mesh = trimesh.load(_cracked_box(Path(td)), force="mesh", process=False)
        mesh.merge_vertices()
        faces = [set(face) for face in np.asarray(mesh.faces).tolist()]
        edges = np.sort(np.concatenate([mesh.faces[:, [0, 1]], mesh.faces[:, [1, 2]], mesh.faces[:, [2, 0]]]), axis=1)
        unique, counts = np.unique(edges, axis=0, return_counts=True)
        crack = set(unique[counts == 1].ravel().tolist())  # the T-junction's corners
        # two triangles away from the crack meeting at one corner alone: their openings' loops share it
        first, second = next((i, j) for i in range(len(faces)) for j in range(i + 1, len(faces))
                             if len(faces[i] & faces[j]) == 1 and not (faces[i] | faces[j]) & crack)
        mesh.update_faces(np.isin(np.arange(len(faces)), [first, second], invert=True))
        _mesh.clean(mesh)
        self.assertEqual(mesh.metadata["cracks_closed"], 1, "the sliver crack, whatever the other loops")
        self.assertFalse(mesh.is_watertight, "the two openings stay open")

    def test_an_opening_stays_open_and_its_body_is_named(self) -> None:
        import numpy as np

        from cad.trimesh import _mesh

        box = trimesh.creation.box((10, 10, 10))
        box.update_faces(np.arange(len(box.faces)) >= 2)  # one side's two triangles gone: a 10 mm opening
        facts = _mesh.facts(_mesh.prepared(box.copy()))
        self.assertFalse(facts["watertight"])
        self.assertEqual(facts["open_body_count"], 1)
        self.assertEqual(facts["open_bodies"][0]["boundary_edges"], 4)
        self.assertIsNone(facts["volume_mm3"])
        # two bodies sharing a face are each closed, and the face's two copies cancel in the volume
        touching = trimesh.util.concatenate([trimesh.creation.box((10, 10, 10)),
                                             trimesh.creation.box((10, 10, 10)).apply_translation((10, 0, 0))])
        facts = _mesh.facts(_mesh.prepared(touching))
        self.assertEqual((facts["watertight"], facts["volume_mm3"]), (True, 2000.0))

    def test_an_opening_in_one_of_two_touching_bodies_is_not_repaired_shut_for_printing(self) -> None:
        import numpy as np

        far = trimesh.creation.box((10, 10, 10)).apply_translation((10, 0, 0))
        side = np.nonzero(far.face_normals[:, 0] > 0.5)[0][0]
        far.update_faces(np.arange(len(far.faces)) != side)  # one triangle of the far side gone
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "open.stl"
            trimesh.util.concatenate([trimesh.creation.box((10, 10, 10)), far]).export(str(path))
            result = cad.stl.dfm(path, process="printing", material="pla")
        self.assertIn("not_watertight", {finding.code for finding in result.findings})
        self.assertEqual(result.measurements["mesh"]["open_body_count"], 1)

    def test_slivers_doubled_on_an_edge_are_dropped_and_none_that_closes_the_shell(self) -> None:
        """An exporter's collapsed chord left as slivers on an edge (a gear's 3MF: 95 of them, the mesh open
        and split into 25 bodies): a pair wound against each other is dropped; of three on a T-junction, the
        one that closes it, wound as its neighbours, stays."""
        import numpy as np

        from cad.trimesh import _mesh

        box = trimesh.creation.box((10, 10, 10))
        vertices, faces = np.asarray(box.vertices, dtype=float), np.asarray(box.faces)
        a, b, c = (int(v) for v in faces[0])
        middle = len(vertices)
        vertices = np.vstack([vertices, (vertices[a] + vertices[b]) / 2])
        doubled = np.vstack([faces, [[a, middle, b], [b, middle, a]]])
        split = np.vstack([[[a, middle, c], [middle, b, c]], faces[1:], [[a, b, middle]] * 2, [[middle, b, a]]])
        for faces_given in (doubled, split):
            mesh = _mesh.prepared(trimesh.Trimesh(vertices.copy(), faces_given, process=False))
            self.assertTrue(mesh.is_watertight and mesh.is_winding_consistent)
            self.assertEqual((mesh.body_count, mesh.metadata["degenerate_faces_dropped"]), (1, 2))
            self.assertAlmostEqual(float(mesh.volume), 1000.0, places=6)


class FoldTest(unittest.TestCase):
    """A fan folded back over itself in one plane (an exporter's, wrapping a concave boundary) is laid flat."""

    @staticmethod
    def _notched_prism(height: float = 5.0) -> trimesh.Trimesh:
        # a square notched from the top (E is its reflex corner); both caps fanned from A, so the fan's middle
        # triangle (A, C, E) winds against its neighbours: a fold in each cap
        outline = [(0, 0), (4, 0), (4, 4), (2, 1), (0, 4)]
        n = len(outline)
        vertices = [(x, y, 0.0) for x, y in outline] + [(x, y, height) for x, y in outline]
        faces = [(0, 2, 1), (0, 3, 2), (0, 4, 3)]  # the bottom, seen from below
        faces += [(n, n + 1, n + 2), (n, n + 2, n + 3), (n, n + 3, n + 4)]  # the top
        for k in range(n):
            a, b = k, (k + 1) % n
            faces += [(a, b, n + b), (a, n + b, n + a)]
        return trimesh.Trimesh(vertices, faces, process=False)

    def test_a_folded_fan_is_laid_flat_and_reads_no_ceiling(self) -> None:
        from cad.trimesh import _mesh

        mesh = _mesh.prepared(self._notched_prism())
        self.assertEqual(mesh.metadata["folds_laid_flat"], 2)
        normals = mesh.face_normals[mesh.face_adjacency]
        self.assertGreater(float(min((a @ b) for a, b in normals)), _mesh.FOLD_DOT)
        self.assertTrue(mesh.is_watertight)
        self.assertAlmostEqual(float(mesh.volume), (16 - 0.5 * 4 * 3) * 5.0, places=6)  # the notch is 6 mm2
        top = mesh.triangles_center[:, 2] > 4.999
        self.assertTrue((mesh.face_normals[top][:, 2] > 0.999).all())  # no triangle of the top looks down

    def test_a_mesh_with_no_fold_is_not_changed(self) -> None:
        from cad.trimesh import _mesh

        box = trimesh.creation.box((10, 20, 30))
        before = box.faces.copy()
        mesh = _mesh.prepared(box.copy())
        self.assertEqual(mesh.metadata["folds_laid_flat"], 0)
        self.assertTrue((mesh.faces == before).all())


class OverhangTest(unittest.TestCase):
    def test_a_round_on_the_plates_edge_is_no_overhang_as_on_exact_geometry(self) -> None:
        from build123d import Axis, fillet

        part = Box(30, 20, 6, align=(Align.CENTER, Align.CENTER, Align.MIN))
        part = fillet(part.edges().group_by(Axis.Z)[0], 0.6)
        with tempfile.TemporaryDirectory() as td:
            result = cad.stl.dfm(_stl(part, Path(td), "rounded"), process="printing")
        overhangs = result.measurements["overhangs"]
        self.assertEqual(overhangs["down_facing_area_below_limit_mm2"], 0.0)
        self.assertEqual({item["kind"] for item in overhangs["items"]}, {"plate_edge"})
        self.assertNotIn("printing.overhang_angle", [finding.code for finding in result.findings])

    def test_underside_below_limit_is_flagged_above_limit_is_not(self) -> None:
        """A 30 deg underside is a violation at 45 deg and clear at 20 deg."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            path = _stl(_wedge(30.0), tmp, "wedge30")
            mesh = dfam_tool._load(path)
            strict = dfam_tool._overhang_facts(mesh, 45.0)
            lenient = dfam_tool._overhang_facts(mesh, 20.0)

        self.assertGreater(strict["down_facing_area_below_limit_mm2"], 0.0)
        self.assertEqual(lenient["down_facing_area_below_limit_mm2"], 0.0)
        self.assertEqual(strict["angle_limit_used_deg"], 45.0)

    def test_face_resting_on_plate_is_not_counted(self) -> None:
        """The base is carried by the bed, so a plain box needs no support."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            mesh = dfam_tool._load(_stl(Box(20, 20, 15), tmp, "box"))
            facts = dfam_tool._overhang_facts(mesh, 45.0)

        self.assertEqual(facts["down_facing_area_below_limit_mm2"], 0.0)
        self.assertEqual(facts["face_count_below_limit"], 0)


class WallThicknessTest(unittest.TestCase):
    def test_measured_wall_matches_constructed_wall(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            mesh = dfam_tool._load(_stl(_hollow_box(2.0), tmp, "wall2"))
            facts = dfam_tool._wall_facts(mesh, samples=600)

        self.assertAlmostEqual(facts["median_mm"], 2.0, delta=0.4)

    def test_a_wall_is_measured_from_the_surface_not_from_the_ray_s_nudge(self) -> None:
        # each ray starts 1e-4 off its triangle: its length is the surface's, so a 2 mm wall reads 2, not 1.9999,
        # and SLA's 0.5 mm shell passes its 0.5 mm minimum on the mesh as on the B-rep
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            facts = dfam_tool._wall_facts(dfam_tool._load(_stl(_hollow_box(2.0), tmp, "wall2")), samples=600)
            shell = Box(40, 40, 30, align=(Align.CENTER, Align.CENTER, Align.MIN)) - \
                Pos(0, 0, 0.5) * Box(39, 39, 30, align=(Align.CENTER, Align.CENTER, Align.MIN))
            result = cad.stl.dfm(_stl(shell, tmp, "shell"), process="printing", technology="sla")
        self.assertEqual(facts["min_mm"], 2.0)
        self.assertFalse([f.code for f in result.findings if f.code.startswith("printing.wall")])
        self.assertEqual(result.measurements["wall_thickness"]["min_mm"], 0.5)

    def test_thinner_wall_measures_thinner(self) -> None:
        """Ordering must hold even where absolute sampling error does not."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            thin = dfam_tool._wall_facts(
                dfam_tool._load(_stl(_hollow_box(0.8), tmp, "wall08")), samples=600
            )
            thick = dfam_tool._wall_facts(
                dfam_tool._load(_stl(_hollow_box(3.0), tmp, "wall30")), samples=600
            )

        self.assertLess(thin["median_mm"], thick["median_mm"])

    def test_a_coarse_mesh_is_sampled_all_over_its_surface(self) -> None:
        """A plate thinning from 6 mm to 0.6 mm, meshed as a dozen large triangles: every ray asked for is cast,
        each from anywhere on the surface, so the thin end is measured. Rays from the triangles' centres, at most
        one a triangle, found the plate's thinnest place 2.4 mm thick."""
        plate = extrude(make_face(Polyline((0, 0, 0), (60, 0, 0), (60, 0.6, 0), (0, 6, 0), (0, 0, 0))), 30)
        with tempfile.TemporaryDirectory() as td:
            mesh = dfam_tool._load(_stl(plate, Path(td), "ramp"))
            facts = dfam_tool._wall_facts(mesh, samples=2000)

        self.assertLess(len(mesh.faces), 20)
        self.assertGreater(facts["samples_valid"], 1900)
        self.assertLess(facts["min_mm"], 1.0)

    def test_a_corner_is_no_wall(self) -> None:
        """A block 10 mm tall whose sides lean out 10 degrees: a ray from its top face by an edge leaves through the
        side after a hair, past a corner, not across a wall, and is not counted, so the block measures its own
        size."""
        block = extrude(make_face(Polyline((5, 0, 0), (15, 0, 0), (16.76, 10, 0), (3.24, 10, 0), (5, 0, 0))), 30)
        with tempfile.TemporaryDirectory() as td:
            facts = dfam_tool._wall_facts(dfam_tool._load(_stl(block, Path(td), "flared")), samples=2000)

        self.assertGreater(facts["min_mm"], 9.0)


    def test_one_fin_is_one_wall(self) -> None:
        """A 0.5 mm fin is one wall, read from its two sides: one item, as on its exact geometry."""
        part = Box(40, 30, 5, align=(Align.CENTER, Align.CENTER, Align.MIN)) \
            + Pos(0, 0, 5) * Box(30, 0.5, 15, align=(Align.CENTER, Align.CENTER, Align.MIN))
        with tempfile.TemporaryDirectory() as td:
            facts = dfam_tool._wall_facts(dfam_tool._load(_stl(part, Path(td), "fin")), samples=2000)
        thin = [item for item in facts["items"] if item["thickness_mm"] < 0.8]
        self.assertEqual(len(thin), 1)
        self.assertAlmostEqual(thin[0]["thickness_mm"], 0.5, delta=1e-3)

    def test_the_figures_are_of_the_rays_the_items_are(self) -> None:
        """min_mm is the thinnest item, on one body and on several: the summary never says a thinner wall is not
        there (a knob read "walls min 1.2" beside its 0.277 mm web)."""
        part = Box(20, 20, 10) - Pos(0, 0, 4.0) * Box(16, 16, 1)
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            for path in (_stl(part, tmp, "sealed"), MultiBodyWallTest()._assembly(tmp)):
                facts = dfam_tool._wall_facts(dfam_tool._load(path), samples=400)
                with self.subTest(path=Path(path).name):
                    self.assertAlmostEqual(facts["min_mm"], min(i["thickness_mm"] for i in facts["items"]), delta=1e-3)
                    self.assertTrue(facts["cover"])

    def test_a_mesh_over_the_cover_cap_is_measured_by_its_random_rays(self) -> None:
        mesh = trimesh.creation.icosphere(subdivisions=4, radius=10.0)
        self.assertGreater(len(mesh.faces), dfam_tool.COVER_MAX_TRIANGLES)
        facts = dfam_tool._wall_facts(mesh, samples=400)
        self.assertFalse(facts["cover"])
        self.assertIn("no ray from every triangle", facts["method"])
        self.assertEqual(facts["samples_valid"], sum(item["samples"] for item in facts["items"]))
        self.assertGreater(facts["min_mm"], 1.0)


class MeshDefectTest(unittest.TestCase):
    def test_a_fold_is_no_knife_and_the_walls_are_still_measured(self) -> None:
        """A ridge whose flanks meet at 0.3 deg -- two triangles doubled back, as a tessellation folds -- is no
        knife edge (its thin depth would reach 150 mm and wipe every wall ray), and the walls are measured."""
        ridge = Polyline((0, 0, 0), (30, 0, 0), (30, 4, 0), (15.005, 4, 0), (15, 6, 0), (14.995, 4, 0), (0, 4, 0),
                         (0, 0, 0))
        with tempfile.TemporaryDirectory() as td:
            result = cad.stl.dfm(_stl(extrude(make_face(ridge), 20), Path(td), "fold"), process="printing")
        report = result.measurements
        self.assertEqual(report["knife_edges"]["count"], 0)
        self.assertNotIn("error", report["wall_thickness"])
        self.assertGreater(report["wall_thickness"]["samples_valid"], 1000)
        self.assertNotIn("printing.knife_edge", [finding.code for finding in result.findings])

    def test_an_acute_crease_is_no_gap(self) -> None:
        """A groove of two arcs meeting at its root at 52 degrees: rays from one flank near the root land on the
        other at a few tenths of a millimetre -- the crease's angle, not a slot (the exact path skips the face
        beside its own alike, and reads no gap there)."""
        lens = (Pos(-9, 0, 30) * Rotation(90, 0, 0) * Cylinder(10, 40)) & (Pos(9, 0, 30) * Rotation(90, 0, 0) * Cylinder(10, 40))
        part = Box(40, 30, 30, align=(Align.CENTER, Align.CENTER, Align.MIN)) - lens
        with tempfile.TemporaryDirectory() as td:
            result = cad.stl.dfm(_stl(part, Path(td), "lens"), process="printing")
        self.assertEqual(result.measurements["gaps"]["items"], [])
        self.assertNotIn("printing.gap", [finding.code for finding in result.findings])

    def test_faces_lying_on_faces_are_the_meshs_defect_said_once_not_a_gap(self) -> None:
        part = Box(20, 20, 10) - Pos(0, 0, 5) * Box(0.005, 30, 5, align=(Align.CENTER, Align.CENTER, Align.MAX))
        with tempfile.TemporaryDirectory() as td:
            result = cad.stl.dfm(_stl(part, Path(td), "slit"), process="printing")
        codes = [finding.code for finding in result.findings]
        self.assertEqual(codes.count("mesh_overlap"), 1)
        self.assertNotIn("printing.gap", codes)
        self.assertLess(result.measurements["gaps"]["overlap"]["gap_mm"], dfam_tool.GAP_DEFECT_MM)


class OrientationTest(unittest.TestCase):
    def test_flipping_a_wedge_removes_its_support_requirement(self) -> None:
        """The same wedge is self-supporting once turned over.

        This is the whole point of ranking orientations, so if it stops
        holding, the ranking is not doing anything useful.
        """
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            mesh = dfam_tool._load(_stl(_wedge(30.0), tmp, "wedge30"))
            facts = dfam_tool._orientation_facts(mesh, 45.0)

        candidates = facts["candidates"]
        self.assertEqual(len(candidates), 6)

        current = next(c for c in candidates if c["orientation"] == "current_plus_z")
        best = min(candidates, key=lambda c: c["support_area_mm2"])

        self.assertGreater(current["support_area_mm2"], 0.0)
        self.assertEqual(best["support_area_mm2"], 0.0)
        for candidate in candidates:
            self.assertGreater(candidate["build_height_mm"], 0.0)


class FormatCoverageTest(unittest.TestCase):
    """Every 3D mesh type's check reads its file as the viewer does (millimetres, Z up), and the
    Python API measures any mesh trimesh reads (an .obj, a .ply).

    A format that is claimed but unreadable is worse than one that is not
    claimed, because the failure surfaces at the user rather than here.
    """

    def test_each_mesh_type_loads_and_measures(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            stl = _stl(Box(20, 20, 15), tmp, "box")
            cad.stl.export(stl, tmp / "box.3mf", tmp / "box.glb")
            for kind, path in (("stl", stl), ("threemf", tmp / "box.3mf"), ("glb", tmp / "box.glb")):
                with self.subTest(kind=kind):
                    result = getattr(cad, kind).dfm(path, process="printing")
                    facts = result.measurements["mesh"]
                    self.assertTrue(result.ok)
                    self.assertAlmostEqual(facts["volume_mm3"], 6000.0, delta=1.0)
                    self.assertEqual(facts["bbox_mm"], [20.0, 20.0, 15.0], "Z up, in millimetres")
            source = trimesh.load(stl, force="mesh")
            for suffix in (".obj", ".ply"):
                with self.subTest(fmt=suffix):
                    path = tmp / f"box{suffix}"
                    source.export(str(path))
                    facts = cad.trimesh.printing(trimesh.load(str(path), force="mesh"))["mesh"]
                    self.assertAlmostEqual(facts["volume_mm3"], 6000.0, delta=1.0)
                    self.assertEqual(facts["body_count"], 1)


class DegenerateMeshTest(unittest.TestCase):
    def test_zero_area_mesh_reports_instead_of_dividing_by_zero(self) -> None:
        """Area weighting needs a positive total; say so rather than crash."""
        mesh = trimesh.Trimesh(
            vertices=[[0, 0, 0], [1, 0, 0], [2, 0, 0]],
            faces=[[0, 1, 2]],
            process=False,
        )
        facts = dfam_tool._wall_facts(mesh, samples=100)

        self.assertEqual(facts["samples"], 0)
        self.assertIn("degenerate", facts["note"])


def _checked(path, **options) -> tuple[bool, dict]:
    """Check the way a skill run does: whether it passed, and what it measured."""
    result = cad.stl.dfm(path, process="printing", **options)
    return result.ok, result.measurements


def _measured(path, **options) -> dict:
    return _checked(path, **options)[1]


class OpenMeshTest(unittest.TestCase):
    def test_an_open_mesh_is_still_measured_and_says_it_is_open(self) -> None:
        # a 0.4 mm-walled cup missing one triangle: trimesh's split would repair the open piece through
        # networkx (not a dependency) and lose the walls; measured as it is, the thin wall still fails
        import numpy as np

        cup = _hollow_box(0.4)
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            mesh = trimesh.load(_stl(cup, tmp, "cup"))
            mesh.update_faces(np.arange(len(mesh.faces)) != int(np.argmax(mesh.area_faces)))
            path = tmp / "open.stl"
            mesh.export(path)
            result = cad.stl.dfm(path, process="printing", technology="fdm")
        codes = [finding.code for finding in result.findings]
        self.assertFalse(result.measurements.get("partial"), result.measurements.get("partial_sections"))
        self.assertEqual(codes[0], "not_watertight", "said first: every figure after it is of an open surface")
        self.assertEqual(result.findings[0].severity, "error", "an open surface has no inside to print")
        self.assertIn("1 open body(ies)", result.findings[0].message)
        self.assertFalse(result.ok)
        self.assertNotIn("measurement_failed", codes)
        self.assertNotIn("internal_void", codes, "an open mesh's voxel voids are its holes")
        walls = [o for o in result.measurements["rules"]["outcomes"]
                 if o["rule"].startswith("printing.wall") and o["status"] == "failed"]
        self.assertTrue(walls, "the cup's walls are still measured, and fail")
        self.assertAlmostEqual(min(f["value"] for o in walls for f in o["failures"]), 0.4, delta=0.01)

    def test_an_open_mesh_s_holes_are_no_escape_holes(self) -> None:
        # a sealed 2 mm box missing one triangle of its inside: on SLS the cavity's "opening" is the mesh's hole,
        # neither an escape hole nor none -- not measured
        import numpy as np

        box = Box(24, 24, 16) - Box(20, 20, 12)
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            mesh = trimesh.load(_stl(box, tmp, "box"))
            inner = np.flatnonzero(np.abs(mesh.triangles_center).max(axis=1) < 10.01)
            mesh.update_faces(np.arange(len(mesh.faces)) != int(inner[0]))
            path = tmp / "open.stl"
            mesh.export(path)
            result = cad.stl.dfm(path, process="printing", technology="sls")
        codes = {finding.code for finding in result.findings}
        self.assertIn("not_watertight", codes)
        self.assertFalse(codes & {"printing.escape_holes", "printing.escape_hole_diameter"})
        trapped = result.measurements["trapped_volumes"]
        self.assertIn("openings_not_measured", trapped)
        self.assertTrue(all(item["escape_holes"] is None for item in trapped["items"]))


def _written(mesh: trimesh.Trimesh, tmp: Path, name: str) -> str:
    path = tmp / f"{name}.stl"
    mesh.export(path)
    return str(path)


class GateTest(unittest.TestCase):
    """One gate ahead of the families: a mesh with no inside is one finding, never a family's exception; what is
    unambiguous is repaired, and said."""

    def test_a_file_with_nothing_to_read_is_one_finding(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            for name, content in (("empty", b""), ("cut-off", b"solid x\nfacet normal 0 0 0\nouter loop\nvertex 0 0 nan\n")):
                path = Path(td) / f"{name}.stl"
                path.write_bytes(content)
                result = cad.stl.dfm(path, process="printing")
                with self.subTest(file=name):
                    self.assertFalse(result.ok)
                    [found] = result.findings
                    self.assertEqual(found.severity, "error")
                    self.assertIn(found.code, ("mesh_empty", "mesh_unreadable"))

    def test_a_mesh_with_no_surface_or_a_broken_corner_is_refused(self) -> None:
        import numpy as np

        from cad._internal.dfm import Unmeasured
        from cad.trimesh import _mesh

        line = trimesh.Trimesh(vertices=[[0, 0, 0], [1, 0, 0], [2, 0, 0]], faces=[[0, 1, 2]], process=False)
        broken = trimesh.creation.box((10, 10, 10))
        vertices = np.array(broken.vertices)
        vertices[0, 2] = np.nan
        broken = trimesh.Trimesh(vertices, broken.faces, process=False)
        # a sheet doubled back on itself: closed by its edges, with no inside
        sheet = trimesh.Trimesh([[0, 0, 0], [10, 0, 0], [10, 10, 0], [0, 10, 0]],
                                [[0, 1, 2], [0, 2, 3], [0, 2, 1], [0, 3, 2]], process=False)
        # a band with a half turn: one-sided, no winding of its triangles is consistent
        count, band = 24, []
        for k in range(count):
            turn = 2 * math.pi * k / count
            across = np.array([math.cos(turn) * math.cos(turn / 2), math.sin(turn) * math.cos(turn / 2), math.sin(turn / 2)])
            centre = 10 * np.array([math.cos(turn), math.sin(turn), 0.0])
            band += [centre - 2 * across, centre + 2 * across]
        faces = []
        for k in range(count):
            a, b = 2 * k, 2 * k + 1
            c, d = (2 * (k + 1), 2 * (k + 1) + 1) if k + 1 < count else (1, 0)  # the turn: the ends meet crossed
            faces += [[a, c, b], [b, c, d]]
        one_sided = trimesh.Trimesh(band, faces, process=False)
        for mesh, code in ((line, "mesh_empty"), (broken, "mesh_unreadable"), (sheet, "mesh_no_volume"),
                           (one_sided, "inconsistent_normals")):
            with self.subTest(code=code), self.assertRaises(Unmeasured) as refused:
                _mesh.prepared(mesh)
            self.assertEqual(refused.exception.code, code)

    def test_triangles_wound_wrongly_are_turned_and_said(self) -> None:
        import numpy as np

        box = trimesh.creation.box((20, 20, 20))
        mixed = box.copy()
        faces = np.array(mixed.faces)
        faces[:5] = faces[:5, ::-1]
        mixed.faces = faces
        inside_out = box.copy()
        inside_out.invert()
        twice = trimesh.util.concatenate([box, box.copy()])
        with tempfile.TemporaryDirectory() as td:
            for name, mesh, said in (("mixed", mixed, "5 triangle(s) wound against their neighbours turned"),
                                     ("inside-out", inside_out, "1 closed shell(s) wound inside out turned"),
                                     ("twice", twice, "12 triangle(s) doubled in place dropped")):
                result = cad.stl.dfm(_written(mesh, Path(td), name), process="printing")
                with self.subTest(mesh=name):
                    [repaired] = [f for f in result.findings if f.code == "mesh_repaired"]
                    self.assertEqual(repaired.severity, "warning")
                    self.assertIn(said, repaired.message)
                    self.assertTrue(result.ok, "the cube it stands for prints")
                    self.assertEqual(result.measurements["mesh"]["volume_mm3"], 8000.0)
                    self.assertEqual(result.measurements["mesh"]["body_count"], 1)
                    self.assertEqual(result.measurements["wall_thickness"]["min_mm"], 20.0)
                    self.assertFalse({"internal_void", "measurement_failed", "printing.bridge_length"}
                                     & {f.code for f in result.findings}, "no figure of a surface read inside out")
            # a void's shell is wound inward and stays so: a cavity, not a repair
            hollow = trimesh.util.concatenate([box, trimesh.creation.box((8, 8, 8)).copy()])
            faces = np.array(hollow.faces)
            faces[12:] = faces[12:, ::-1]
            hollow.faces = faces
            sealed = cad.stl.dfm(_written(hollow, Path(td), "hollow"), process="printing", technology="sls")
            self.assertNotIn("mesh_repaired", {f.code for f in sealed.findings})
            [void] = sealed.measurements["trapped_volumes"]["items"]
            self.assertEqual((void["exact"], void["sealed"], void["volume_mm3"]), (True, True, 512.0))

    def test_bodies_that_pass_through_each_other_are_said(self) -> None:
        box = trimesh.creation.box((20, 20, 20))
        with tempfile.TemporaryDirectory() as td:
            for shift, crossing in (((10, 0, 0), True), ((20, 20, 0), False)):  # half through; touching along an edge
                other = trimesh.creation.box((20, 20, 20), transform=trimesh.transformations.translation_matrix(shift))
                result = cad.stl.dfm(_written(trimesh.util.concatenate([box, other]), Path(td), "two"),
                                     process="printing")
                found = {f.code: f for f in result.findings}
                with self.subTest(shift=shift):
                    self.assertEqual("bodies_intersect" in found, crossing)
                    self.assertEqual("printing.clearance" in found, not crossing, "one finding a pair")
                    if crossing:
                        self.assertEqual(found["bodies_intersect"].severity, "warning")
                        self.assertIn("the bodies' sum", found["bodies_intersect"].message)

    def test_a_body_inside_another_is_found_and_counted_once_and_a_captive_ball_is_no_overlap(self) -> None:
        import numpy as np

        def sphere(radius: float, inside_out: bool = False) -> trimesh.Trimesh:
            ball = trimesh.creation.icosphere(subdivisions=3, radius=radius)
            if inside_out:
                ball.invert()
            return ball

        with tempfile.TemporaryDirectory() as td:
            # a 5 mm cube deep in a 20 mm cube's material: far from its surface, so read before any distance
            nested = trimesh.util.concatenate([trimesh.creation.box((20, 20, 20)), trimesh.creation.box((5, 5, 5))])
            result = cad.stl.dfm(_written(nested, Path(td), "nested"), process="printing")
            found = [f for f in result.findings if f.code == "bodies_intersect"]
            self.assertEqual(len(found), 1)
            self.assertIn("lies wholly inside", found[0].message)
            self.assertAlmostEqual(result.measurements["mesh"]["volume_mm3"], 8000.0, delta=1.0)
            self.assertEqual(result.measurements["mesh"]["bodies_inside_another"], 1)
            # a ball loose in a hollow shell (print-in-place): the void is the shell's, though the ball holds its
            # centre -- so the shell's own 0.3 mm wall is measured, the 0.5 mm clearance judged, and nothing
            # passes through anything
            captive = trimesh.util.concatenate([sphere(10.0), sphere(10.5, inside_out=True), sphere(10.8)])
            result = cad.stl.dfm(_written(captive, Path(td), "captive"), process="printing", technology="sla")
            codes = [f.code for f in result.findings]
            self.assertNotIn("bodies_intersect", codes)
            self.assertEqual(result.measurements["mesh"]["body_count"], 2)
            self.assertAlmostEqual(result.measurements["wall_thickness"]["min_mm"], 0.3, delta=0.02)
            self.assertIn("printing.wall_supported", codes)
            [gap] = result.measurements["clearances"]["items"]
            self.assertAlmostEqual(gap["distance_mm"], 0.5, delta=0.02)
            self.assertTrue(gap["exact"])
            self.assertAlmostEqual(result.measurements["mesh"]["volume_mm3"],
                                   float(captive.volume), delta=1.0)
            self.assertTrue(np.isfinite(gap["distance_mm"]))

    def test_a_mesh_over_the_ceiling_is_refused_before_it_is_read(self) -> None:
        from unittest import mock

        from cad.trimesh import _mesh

        with tempfile.TemporaryDirectory() as td, mock.patch.object(_mesh, "MAX_TRIANGLES", 10):
            result = cad.stl.dfm(_written(trimesh.creation.box((20, 20, 20)), Path(td), "box"), process="printing")
        self.assertEqual([(f.severity, f.code) for f in result.findings], [("error", "mesh_too_large")])
        self.assertIn("12 triangles, over the 10", result.findings[0].message)
        self.assertIn("decimate it", result.findings[0].message)


class BoundedTest(unittest.TestCase):
    def test_a_ray_costs_the_triangles_near_it_not_the_mesh(self) -> None:
        """82 000 triangles, 2000 rays: every ray lands, and the cast's tables stay within megabytes (trimesh's
        own engine without embree held 2.4 GB on this mesh, and ran out of memory on 1.3 million triangles)."""
        import tracemalloc

        import numpy as np

        from cad._internal import meshops_printing as mo

        sphere = trimesh.creation.icosphere(subdivisions=6, radius=30.0)
        vertices, faces = np.asarray(sphere.vertices, dtype=float), np.asarray(sphere.faces, dtype=int)
        origins, on = trimesh.sample.sample_surface(sphere, 2000, seed=1)
        directions = -sphere.face_normals[on]
        tracemalloc.start()
        caster = mo.Caster(vertices, faces)
        distance, hit = caster.first(origins + directions * 1e-4, directions)
        peak = tracemalloc.get_traced_memory()[1]
        tracemalloc.stop()
        self.assertEqual(len(faces), 81920)
        self.assertTrue((hit >= 0).all())
        np.testing.assert_allclose(distance, 60.0, atol=0.05, err_msg="across the sphere, through its middle")
        self.assertLess(peak, 250e6)
        # the same crossings as every ray against every triangle, on a small soup
        rng = np.random.default_rng(5)
        soup = rng.uniform(-10, 10, (300, 1, 3)) + rng.uniform(-2, 2, (300, 3, 3))
        few = mo.Caster(soup.reshape(-1, 3), np.arange(900).reshape(-1, 3))
        start, way = rng.uniform(-12, 12, (200, 3)), rng.normal(size=(200, 3))
        way /= np.linalg.norm(way, axis=1, keepdims=True)
        found, which = few.first(start, way)
        e1, e2 = soup[:, 1] - soup[:, 0], soup[:, 2] - soup[:, 0]
        p = np.cross(way[:, None, :], e2[None])
        det = np.einsum("tj,rtj->rt", e1, p)
        s0 = start[:, None, :] - soup[None, :, 0]
        u = np.einsum("rtj,rtj->rt", s0, p) / det
        q = np.cross(s0, e1[None])
        v = np.einsum("rj,rtj->rt", way, q) / det
        t = np.einsum("tj,rtj->rt", e2, q) / det
        every = np.where((u >= 0) & (v >= 0) & (u + v <= 1) & (t > 0), t, np.inf).min(axis=1)
        np.testing.assert_allclose(found, every, rtol=1e-9)
        self.assertEqual(int((which >= 0).sum()), int(np.isfinite(every).sum()))


    def test_the_clearances_are_bounded_and_a_distance_the_budget_cut_short_is_no_pass(self) -> None:
        """A ball 0.3 mm inside a shell, 61 000 triangles: every point of each is as near the other as any, the
        case trimesh's closest-point query held 767 MB on (and ran out of 4 GB at 246 000 triangles). Each body
        is read as a few points a triangle, in a tree; with the budget of exact distances cut to nothing the
        distance stands with how much less it may be, and a limit between the two is not judged: not checked."""
        import tracemalloc
        from unittest import mock

        def sphere(radius: float, inside_out: bool = False, subdivisions: int = 5) -> trimesh.Trimesh:
            ball = trimesh.creation.icosphere(subdivisions=subdivisions, radius=radius)
            if inside_out:
                ball.invert()
            return ball

        nested = dfam_tool._mesh.prepared(trimesh.util.concatenate([sphere(30.0), sphere(30.3, True), sphere(32.0)]))
        self.assertEqual(len(nested.faces), 61440)
        tracemalloc.start()
        found = dfam_tool._clearance_facts(nested)
        peak = tracemalloc.get_traced_memory()[1]
        tracemalloc.stop()
        [gap] = found["items"]
        self.assertLess(peak, 300e6)
        self.assertAlmostEqual(gap["distance_mm"], 0.3, delta=0.01)
        self.assertEqual((gap["kind"], gap["exact"]), ("gap", True))
        # 1 mm apart, the budget cut: the points alone say 1 mm or up to their spacing less, and FDM's 0.762 mm
        # limit lies between
        loose = trimesh.util.concatenate([sphere(30.0, False, 4), sphere(31.0, True, 4), sphere(33.0, False, 4)])
        with tempfile.TemporaryDirectory() as td, mock.patch.object(dfam_tool, "CLEARANCE_PAIRS", 1):
            result = cad.stl.dfm(_written(loose, Path(td), "loose"), process="printing", technology="fdm")
        [gap] = result.measurements["clearances"]["items"]
        self.assertFalse(gap["exact"])
        self.assertIsNone(gap["distance_mm"], "the limit lies between the least found and its bound")
        self.assertGreater(gap["distance_at_most_mm"], 0.99)
        self.assertGreater(gap["uncertainty_mm"], 0.24)
        self.assertEqual(result.status, "not_checked")
        self.assertIn("clearance_bounded", [f.code for f in result.findings])

    def test_a_scan_s_underside_is_one_overhang_and_its_spans_are_bounded(self) -> None:
        """A sphere with every corner moved a little (a scan's noise): its underside's triangles under the limit
        are hundreds of islands, one overhang -- and no span is read of a slope. With the spans' budget cut to
        nothing a part of flat undersides says they were not measured: not checked, never passed."""
        import numpy as np
        from unittest import mock

        ball = trimesh.creation.icosphere(subdivisions=5, radius=30.0)
        ball.vertices = ball.vertices + ball.vertex_normals * np.random.default_rng(7).normal(0, 0.05, (len(ball.vertices), 1))
        with tempfile.TemporaryDirectory() as td:
            result = cad.stl.dfm(_written(ball, Path(td), "scan"), process="printing")
            self.assertEqual(len([f for f in result.findings if f.code == "printing.overhang_angle"]), 1)
            self.assertNotIn("measurement_failed", [f.code for f in result.findings])
            table = _stl(Box(30, 10, 10) - Pos(0, 0, -2) * Box(20, 10, 6), Path(td), "table")
            with mock.patch.object(dfam_tool, "SPAN_PAIRS", 0):
                unread = cad.stl.dfm(table, process="printing")
            self.assertEqual(unread.measurements["bridges"]["spans_not_measured"], 1)
            self.assertEqual(unread.status, "not_checked")
            self.assertIn("bridges", [f.location for f in unread.findings if f.code == "measurement_failed"])
            self.assertIn("printing.bridge_length", [f.code for f in cad.stl.dfm(table, process="printing").findings])


class MeshAccuracyTest(unittest.TestCase):
    """A triangle is a chord of the surface: what is read off it is the surface's within the mesh's own turn."""

    def test_every_triangle_of_a_45_degree_cone_reads_45_within_its_own_tolerance(self) -> None:
        import numpy as np
        from build123d import Cone

        from cad._internal import meshops_printing as mo

        with tempfile.TemporaryDirectory() as td:
            for tolerance, angular in ((0.01, 0.1), (0.01, 0.2), (0.1, 0.4)):
                path = Path(td) / f"cone-{angular}.stl"
                export_stl(Cone(5, 15, 10), str(path), tolerance=tolerance, angular_tolerance=angular)
                mesh = dfam_tool._load(str(path))
                surface = dfam_tool._smooth(mesh)
                tilt, slack = mo.angles(surface.normals), surface.slopes()
                side = (surface.normals[:, 2] < -0.1) & (np.abs(tilt - 45.0) < 10.0)
                with self.subTest(angular=angular):
                    self.assertGreater(int(side.sum()), 50)
                    self.assertGreater(float(np.abs(tilt[side] - 45.0).max()), 0.2, "the chords do read off 45")
                    self.assertTrue((np.abs(tilt[side] - 45.0) <= slack[side]).all(),
                                    "each reading's tolerance holds the cone's 45 deg")
                    self.assertLess(float(slack[side].max()), 5.0, "a tolerance, not a licence")
            # a plane has none but its coordinates' noise: a wedge turned 37 deg about Z reads 45 as exactly
            path = Path(td) / "wedge.stl"
            export_stl(Rotation(0, 0, 37) * _wedge(45.0), str(path))
            flat = dfam_tool._smooth(dfam_tool._load(str(path))).slopes()
            self.assertLess(float(flat.max()), 1e-3)
            self.assertGreater(float(flat.max()), 0.0)

    def test_a_cavity_s_throat_is_measured_on_the_triangles(self) -> None:
        # 40 x 40 x 6 mm of air behind a 2 mm vent, and behind one of 3.5 mm -- the limit, which its polygon of
        # chords reads a hair under: the hole's own diameter within its chords' sag, a warning and none
        block = Box(50, 50, 16) - Box(40, 40, 6)
        with tempfile.TemporaryDirectory() as td:
            for diameter, warned in ((2.0, True), (3.5, False)):
                part = block - Pos(0, 0, 5) * Cylinder(diameter / 2, 8)
                result = cad.stl.dfm(_stl(part, Path(td), f"vent{diameter}"), process="printing", technology="sls")
                [cavity] = result.measurements["trapped_volumes"]["items"]
                with self.subTest(vent=diameter):
                    self.assertEqual((cavity["sealed"], cavity["escape_holes"]), (False, 1))
                    self.assertLess(cavity["min_escape_hole_mm"], diameter, "a polygon inside its circle")
                    self.assertLessEqual(diameter - cavity["min_escape_hole_mm"], cavity["escape_hole_uncertainty_mm"])
                    self.assertLess(cavity["escape_hole_uncertainty_mm"], 0.1)
                    self.assertAlmostEqual(cavity["volume_mm3"], 9600.0, delta=0.05 * 9600)
                    self.assertEqual("printing.escape_hole_diameter" in {f.code for f in result.findings}, warned)
                    self.assertEqual(cavity["escape_at_limit"], not warned)

    def test_one_hole_is_one_gap(self) -> None:
        # a 0.4 mm hole through 30 mm: a mesh has no axis to call it a hole, and reads it as a gap -- once
        part = Box(40, 30, 30) - Pos(-10, 0, 0) * Cylinder(0.2, 30)
        with tempfile.TemporaryDirectory() as td:
            result = cad.stl.dfm(_stl(part, Path(td), "hole"), process="printing", technology="sls")
        gaps = result.measurements["gaps"]
        self.assertEqual(gaps["count"], 1)
        self.assertAlmostEqual(gaps["items"][0]["gap_mm"], 0.4, delta=0.01)
        self.assertEqual([f.code for f in result.findings if f.code == "printing.gap"], ["printing.gap"])


class CheckTest(unittest.TestCase):
    def test_the_check_emits_every_fact_family(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            path = _stl(Box(20, 20, 15), tmp, "box")
            payload = _measured(path, angle_limit=45.0)

        self.assertGreaterEqual(set(payload), {"mesh", "overhangs", "wall_thickness", "support_volume"})

    def test_a_wall_at_its_limit_within_the_mesh_s_chords_is_a_warning(self) -> None:
        """A 0.5 mm tube is at SLA's 0.5 mm limit exactly; its STL's chords read it a few microns thin. Within the
        mesh's own deviation (read from its curvature and edge lengths) that is the limit, a warning saying so; on
        FDM (0.8 mm) the same wall is still an error."""
        tube = Cylinder(10, 40) - Cylinder(9.5, 41)
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "tube.stl"
            export_stl(tube, str(path), tolerance=0.01, angular_tolerance=0.1)
            sla = cad.stl.dfm(str(path), process="printing", technology="sla")
            fdm = cad.stl.dfm(str(path), process="printing", technology="fdm")
        # a tube's wall is joined all round (a ring): supported, read off the mesh as off the exact tube
        walls = [f for f in sla.findings if f.code == "printing.wall_supported"]
        self.assertTrue(walls and all(f.severity == "warning" for f in walls), [f.message for f in walls])
        self.assertIn("within the mesh's accuracy", walls[0].message)
        thinnest = min(sla.measurements["wall_thickness"]["items"], key=lambda item: item["thickness_mm"])
        self.assertTrue(thinnest["at_limit"])
        self.assertTrue(thinnest["supported"])
        self.assertGreater(thinnest["chord_mm"], 0.5 - thinnest["thickness_mm"])
        self.assertIn(("error", "printing.wall_supported"), {(f.severity, f.code) for f in fdm.findings})
        # a 0.75 mm tube on FDM (0.8), coarsely meshed: its two rows of chords lie alike and cancel, so the
        # reading's own error is small and the wall is under its limit -- an error, not "at the limit"
        thin = Cylinder(5, 20) - Cylinder(4.25, 21)
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "thin.stl"
            export_stl(thin, str(path), tolerance=0.1, angular_tolerance=0.5)
            coarse = cad.stl.dfm(str(path), process="printing", technology="fdm")
        least = min(coarse.measurements["wall_thickness"]["items"], key=lambda item: item["thickness_mm"])
        self.assertLess(least["chord_mm"], 0.8 - least["thickness_mm"])
        self.assertIn(("error", "printing.wall_supported"), {(f.severity, f.code) for f in coarse.findings})
        # a box's flat walls have no chords to depart: none is at a limit
        with tempfile.TemporaryDirectory() as td:
            flat = cad.stl.dfm(_stl(_hollow_box(0.45), Path(td), "box"), process="printing", technology="sla")
        self.assertIn(("error", "printing.wall_supported"), {(f.severity, f.code) for f in flat.findings})

    def test_angle_limit_is_echoed_back(self) -> None:
        """The limit used has to travel with the numbers it produced."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            path = _stl(Box(20, 20, 15), tmp, "box")
            payload = _measured(path, angle_limit=30.0)

        self.assertEqual(payload["overhangs"]["angle_limit_used_deg"], 30.0)

    def test_candidates_rank_the_orientations_beside_the_parts_own_figures(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            path = _stl(_wedge(30.0), tmp, "wedge30")
            result = cad.stl.dfm(path, process="printing", candidates=True)

        self.assertEqual(len(result.measurements["orientations"]["candidates"]), 6)
        self.assertIn("orientations ranked", result.summary)

    def test_an_overhang_is_said_where_it_is(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            result = cad.stl.dfm(_stl(_wedge(30.0), Path(td), "wedge30"), process="printing")

        # the overhang's area is a fact: printing.overhang_angle judges the face (one cause, one finding), the sum
        # names it; its 30 deg tip is a knife edge, a warning (the tip prints rounded)
        self.assertIn(("warning", "printing.knife_edge"), {(f.severity, f.code) for f in result.findings})
        self.assertIn(("warning", "printing.overhang_angle"), {(f.severity, f.code) for f in result.findings})
        overhang = next(f for f in result.findings if f.code == "overhangs")
        self.assertEqual(overhang.severity, "info")
        self.assertEqual(len(overhang.location.split(", ")), 3)


class MultiBodyWallTest(unittest.TestCase):
    """A mating clearance is not a wall.

    Cast against a whole assembly, a ray can leave one body, cross the fit gap
    and land on its neighbour, recording the gap as wall thickness. Measuring
    per body makes that impossible.
    """

    def _assembly(self, tmp: Path) -> str:
        socket = Box(10, 10, 10) - Box(6.6, 6.6, 20)     # 1.7 mm wall
        peg = Box(6.0, 6.0, 8)                           # 0.3 mm clearance a side
        export_stl(socket, str(tmp / "socket.stl"))
        export_stl(peg, str(tmp / "peg.stl"))
        merged = trimesh.util.concatenate([
            trimesh.load(str(tmp / "socket.stl"), force="mesh"),
            trimesh.load(str(tmp / "peg.stl"), force="mesh"),
        ])
        path = tmp / "mating.stl"
        merged.export(str(path))
        return str(path)

    def test_each_body_is_measured_against_itself(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            facts = dfam_tool._wall_facts(dfam_tool._load(self._assembly(tmp)), samples=2000)

        self.assertEqual(facts["body_count"], 2)
        self.assertTrue(facts["measured_per_body"])

        thinnest = min(b["min_mm"] for b in facts["per_body"] if b["min_mm"] is not None)
        # 0.3 mm is the fit gap; the thinnest real wall is the 1.7 mm socket.
        self.assertGreater(thinnest, 1.0)

    def test_a_sealed_cavity_is_its_bodys_and_its_skin_a_wall(self) -> None:
        """A groove that stops short of the top (the macropad's knob) is a sealed void inside one solid: one
        body, with the void said, and the 0.5 mm skin over it measured as one of its walls."""
        with tempfile.TemporaryDirectory() as td:
            part = Box(20, 20, 10) - Pos(0, 0, 4.0) * Box(16, 16, 1)   # its top at 4.5, the box's at 5
            result = cad.stl.dfm(_stl(part, Path(td), "sealed"), process="printing", samples=4000)

        self.assertEqual((result.measurements["mesh"]["body_count"], result.measurements["mesh"]["internal_void_count"]),
                         (1, 1))
        codes = {finding.code for finding in result.findings}
        self.assertIn("internal_void", codes)  # FDM prints it as infill; a resin or powder process traps material
        self.assertNotIn("several_bodies", codes)
        self.assertAlmostEqual(result.measurements["wall_thickness"]["min_mm"], 0.5, delta=0.01)

    def test_a_body_resting_on_another_is_closed_and_measured(self) -> None:
        """A two-material print: a 10 mm baffle standing on a 2 mm diffuser shares the diffuser's top, so the
        whole's edges there are used four times. Each body is closed again as the bodies are split (no edge of
        it a boundary, the hole the face it shares is filled: trimesh's ``fill_holes``, which needs networkx,
        the trimesh extra carries it), judged watertight per body, and measured against itself: the diffuser's
        2 mm wall too."""
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "two.stl"
            diffuser = trimesh.creation.box((20, 20, 2))
            baffle = trimesh.creation.box((20, 20, 10))
            baffle.apply_translation((0, 0, 6))
            trimesh.util.concatenate([diffuser, baffle]).export(str(path))
            result = cad.stl.dfm(path, process="printing", samples=400)

        self.assertTrue(result.ok, [(finding.code, finding.message) for finding in result.findings])
        self.assertTrue(result.measurements["mesh"]["watertight"], "each body is closed")
        self.assertAlmostEqual(result.measurements["mesh"]["volume_mm3"], 4800.0, delta=1.0)
        walls = sorted(body["min_mm"] for body in result.measurements["wall_thickness"]["per_body"] if body["min_mm"])
        self.assertEqual([round(wall, 3) for wall in walls], [2.0, 10.0])

    def test_per_body_carries_p05_for_the_same_judgement_rule_as_pooled(self) -> None:
        """The printing reference judges walls on p05_mm (min_mm alone is a
        small thin place) and attributes a violation to its own body rather
        than the pooled figure. Both rules only hold together if p05_mm is
        present per body, not only in the pooled result.
        """
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            facts = dfam_tool._wall_facts(dfam_tool._load(self._assembly(tmp)), samples=2000)

        for body in facts["per_body"]:
            self.assertIn("p05_mm", body)
            self.assertIsNotNone(body["p05_mm"])

    def test_internal_arrays_never_reach_the_payload(self) -> None:
        """The pooled arrays are numpy and would not survive json.dumps."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            for path in (self._assembly(tmp), _stl(Box(20, 20, 15), tmp, "solid")):
                facts = dfam_tool._wall_facts(dfam_tool._load(path), samples=400)
                leaked = [k for k in facts if k.startswith("_")]
                self.assertEqual(leaked, [], f"{path} leaked {leaked}")
                json.dumps(facts)

    def test_single_body_keeps_the_flat_result_shape(self) -> None:
        """One body must not acquire per-body keys, and must stay accurate.

        Uses a hollow box because a solid box has a bimodal thickness field
        (15 mm through the flats, 20 mm through the sides), so asserting a
        single median would only be testing the triangulation.
        """
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            path = _stl(_hollow_box(2.0), tmp, "hollow_single")
            facts = dfam_tool._wall_facts(dfam_tool._load(path), samples=800)

        self.assertNotIn("body_count", facts)
        self.assertNotIn("per_body", facts)
        self.assertAlmostEqual(facts["median_mm"], 2.0, delta=0.4)


class ResilienceTest(unittest.TestCase):
    def test_one_failing_family_does_not_lose_the_others(self) -> None:
        """A planar mesh kills convex_hull; the rest of the report survives."""
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "planar.stl"
            trimesh.Trimesh(
                vertices=[[0, 0, 0], [10, 0, 0], [0, 10, 0]],
                faces=[[0, 1, 2]],
                process=False,
            ).export(str(path))
            result = cad.stl.dfm(path, process="printing")
        payload = result.measurements

        self.assertIn("error", payload["support_volume"])
        self.assertNotIn("error", payload["overhangs"])
        self.assertNotIn("error", payload["mesh"])

        # A degraded report is not a clean one. Without these, a report missing
        # wall thickness because a dependency is absent reads exactly like a
        # report from a part that has no thin walls.
        self.assertTrue(payload["partial"])
        self.assertIn("support_volume", payload["partial_sections"])
        self.assertFalse(result.ok)
        self.assertIn(("error", "measurement_failed", "support_volume"),
                      [(f.severity, f.code, f.location) for f in result.findings])

    def test_a_complete_report_is_not_partial(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = _stl(Box(20, 20, 15), Path(td), "box")
            ok, payload = _checked(path)

        self.assertFalse(payload["partial"])
        self.assertNotIn("partial_sections", payload)
        self.assertTrue(ok)
        json.dumps(payload, allow_nan=False)


class ScaleHintTest(unittest.TestCase):
    """Sub-millimetre bbox means wrong units, not a flawless part."""

    def test_meters_scale_mesh_is_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            small = dfam_tool._load(_stl(Box(0.05, 0.02, 0.04), tmp, "meters"))
            big = dfam_tool._load(_stl(Box(20, 20, 15), tmp, "mm"))

        self.assertTrue(dfam_tool._scale_hint(small)["units_suspect"])
        self.assertFalse(dfam_tool._scale_hint(big)["units_suspect"])

    def test_scale_appears_in_both_reports(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            path = _stl(Box(20, 20, 15), tmp, "box")
            self.assertIn("scale", _measured(path))
            self.assertIn("scale", _measured(path, candidates=True))

    def test_units_scale_an_stl_to_millimetres(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            facts = _measured(_stl(Box(2, 2, 1.5), Path(td), "cm"), units="cm")["mesh"]

        self.assertAlmostEqual(facts["volume_mm3"], 6000.0, delta=1.0)


if __name__ == "__main__":
    unittest.main()
