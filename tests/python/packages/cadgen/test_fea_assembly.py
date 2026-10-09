"""``cadgen fea`` on assemblies: parts, touching faces, and the glued mesh.

The fixture is a 40 x 20 x 10 base with a 10 x 10 x 30 post standing on its
top, written to a temporary STEP as two named parts; a lifted post and a block
meeting the base only along an edge cover the cases that must NOT be contact.
Nothing under ``models/`` is read.
"""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen._internal.fea.mesh import require_fea_stack  # noqa: E402

try:
    require_fea_stack()
    HAVE_FEA = True
except RuntimeError:
    HAVE_FEA = False

TOLERANCE = 0.1


def _write_assembly(
    directory: Path, *, lift: float = 0.0, edge_block: bool = False, far_block: float | None = None,
    cap: bool = False, name: str = "assembly",
) -> Path:
    """Base at the origin, post centred on its top and lifted by ``lift``; with
    ``edge_block``, a block that meets the base only along its +X/+Y edge; with
    ``far_block``, a block that far (mm) beyond the base's +X end; with ``cap``,
    a plate on the post's top."""
    from build123d import Align, Box, Compound, Pos, export_step

    base = Box(40, 20, 10, align=Align.MIN)
    base.label = "base"
    post = Pos(15, 5, 10 + lift) * Box(10, 10, 30, align=Align.MIN)
    post.label = "post"
    children = [base, post]
    if edge_block:
        block = Pos(40, 20, 0) * Box(10, 10, 10, align=Align.MIN)
        block.label = "block"
        children.append(block)
    if far_block is not None:
        block = Pos(40 + far_block, 0, 0) * Box(10, 10, 10, align=Align.MIN)
        block.label = "block"
        children.append(block)
    if cap:
        plate = Pos(12, 2, 40 + lift) * Box(16, 16, 5, align=Align.MIN)
        plate.label = "cap"
        children.append(plate)
    path = directory / f"{name}.step"
    export_step(Compound(children=children), str(path))
    return path


def _refs(scene) -> dict[str, str]:
    return {leaf.label: leaf.ref for leaf in scene.leaves()}


def _face_at(scene, part_ref: str, z: float) -> str:
    """The ref of the part's horizontal face whose centre is at height ``z``."""
    from cadgen._internal.fea.mesh import face_area_center

    for selection in scene.resolve(part_ref).entities("face"):
        _, centre = face_area_center(selection.shape())
        if abs(centre[2] - z) < 1e-6:
            return selection.ref
    raise AssertionError(f"no face of {part_ref} at z = {z}")


def _face_where(scene, part_ref: str, axis: int, value: float) -> str:
    """The ref of the part's face whose centre is at ``value`` along ``axis`` (0 = X, 2 = Z)."""
    from cadgen._internal.fea.mesh import face_area_center

    for selection in scene.resolve(part_ref).entities("face"):
        _, centre = face_area_center(selection.shape())
        if abs(centre[axis] - value) < 1e-6:
            return selection.ref
    raise AssertionError(f"no face of {part_ref} at {'xyz'[axis]} = {value}")


@unittest.skipUnless(HAVE_FEA, "cadgen[fea] is not installed")
class DetectContactsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _contacts(self, **kwargs):
        from cadgen._internal.fea.assembly import detect_contacts, list_parts
        from cadgen.step_scene import read_scene

        scene = read_scene(_write_assembly(self.tmp, **kwargs))
        parts = list_parts(scene)
        return parts, detect_contacts(parts, TOLERANCE)

    def test_lists_each_part_with_its_name_and_volume(self):
        parts, _ = self._contacts()
        self.assertEqual([part.name for part in parts], ["base", "post"])
        self.assertAlmostEqual(parts[0].volume_mm3, 8000.0, places=3)
        self.assertAlmostEqual(parts[1].volume_mm3, 3000.0, places=3)

    def test_post_standing_on_the_base_is_one_contact_of_its_footprint(self):
        parts, contacts = self._contacts()
        self.assertEqual(len(contacts), 1)
        contact = contacts[0]
        # The smaller part first: the post is attached to the base.
        self.assertEqual((contact.a, contact.b), (parts[1].ref, parts[0].ref))
        self.assertAlmostEqual(contact.area_mm2, 100.0, places=3)
        self.assertAlmostEqual(contact.gap_mm, 0.0, places=6)

    def test_a_gap_within_the_tolerance_is_contact_with_its_gap(self):
        _, contacts = self._contacts(lift=0.1)
        self.assertEqual(len(contacts), 1)
        self.assertAlmostEqual(contacts[0].gap_mm, 0.1, places=6)
        self.assertAlmostEqual(contacts[0].area_mm2, 100.0, places=3)

    def test_a_gap_beyond_the_tolerance_is_not_contact(self):
        _, contacts = self._contacts(lift=0.5)
        self.assertEqual(contacts, [])

    def test_touching_only_along_an_edge_is_not_contact(self):
        parts, contacts = self._contacts(edge_block=True)
        block = next(part.ref for part in parts if part.name == "block")
        self.assertEqual([c for c in contacts if block in (c.a, c.b)], [])
        self.assertEqual(len(contacts), 1)


@unittest.skipUnless(HAVE_FEA, "cadgen[fea] is not installed")
class MeshAssemblyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.tmp = Path(cls._tmp.name)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _glued(self, lift: float = 0.0):
        from cadgen._internal.fea.assembly import detect_contacts, list_parts
        from cadgen._internal.fea.mesh import mesh_assembly
        from cadgen.step_scene import read_scene

        scene = read_scene(_write_assembly(self.tmp, lift=lift, name=f"lift{lift}"))
        parts = list_parts(scene)
        contacts = detect_contacts(parts, TOLERANCE)
        refs = [part.ref for part in parts]
        volume = mesh_assembly(scene, refs, contacts, TOLERANCE, 4.0)
        return scene, refs, volume

    @staticmethod
    def _components(volume) -> int:
        import numpy as np
        import scipy.sparse as sparse
        from scipy.sparse.csgraph import connected_components

        corners = volume.tets[:, :4]
        rows = np.repeat(np.arange(len(corners)), 4)
        incidence = sparse.coo_matrix(
            (np.ones(corners.size), (rows, corners.ravel())), shape=(len(corners), len(volume.nodes))
        ).tocsr()
        count, _ = connected_components(incidence @ incidence.T, directed=False)
        return count

    def test_glued_parts_are_one_conforming_mesh_with_a_domain_per_part(self):
        import numpy as np

        scene, refs, volume = self._glued()
        self.assertEqual(self._components(volume), 1)
        self.assertEqual(volume.domain.shape, (len(volume.tets),))
        self.assertEqual(sorted(np.unique(volume.domain)), [0, 1])
        # Each domain is its own part: the base below z = 10, the post above.
        centroid_z = volume.nodes[volume.tets[:, :4]].mean(axis=1)[:, 2]
        self.assertLess(centroid_z[volume.domain == 0].max(), 10.0)
        self.assertGreater(centroid_z[volume.domain == 1].min(), 10.0)
        # The two parts share nodes, and only on the post's footprint at z = 10.
        shared = np.intersect1d(volume.tets[volume.domain == 0], volume.tets[volume.domain == 1])
        self.assertGreater(len(shared), 0)
        at = volume.nodes[shared]
        np.testing.assert_allclose(at[:, 2], 10.0, atol=1e-6)
        self.assertTrue(((at[:, 0] >= 15 - 1e-6) & (at[:, 0] <= 25 + 1e-6)).all())
        self.assertTrue(((at[:, 1] >= 5 - 1e-6) & (at[:, 1] <= 15 + 1e-6)).all())

    def test_every_part_face_keeps_its_ref_and_lands_where_it_was(self):
        scene, refs, volume = self._glued()
        base, post = refs
        base_bottom, post_top = _face_at(scene, base, 0.0), _face_at(scene, post, 40.0)
        self.assertEqual(len(volume.faces), 12)
        self.assertTrue(all(ref.startswith((base + ".f", post + ".f")) for ref in volume.faces))
        positions = list(volume.faces)
        for ref, z in ((base_bottom, 0.0), (post_top, 40.0)):
            rows = volume.boundary_ordinal == positions.index(ref) + 1
            self.assertGreater(rows.sum(), 0, ref)
            self.assertAlmostEqual(volume.faces[ref].center[2], z)
            self.assertTrue((abs(volume.nodes[volume.boundary[rows]][..., 2] - z) < 1e-6).all(), ref)
        # Every outer triangle is on some part's face.
        self.assertTrue((volume.boundary_ordinal > 0).all())

    def test_the_faces_of_a_bonded_joint_are_marked(self):
        scene, refs, volume = self._glued()
        base, post = refs
        self.assertEqual(volume.interface_faces, {_face_at(scene, base, 10.0), _face_at(scene, post, 10.0)})

    def test_the_joint_is_not_a_boundary_of_either_part(self):
        import numpy as np

        scene, refs, volume = self._glued()
        base, post = refs
        positions = list(volume.faces)

        def area(triangles):
            c = volume.nodes[triangles[:, :3]]
            return float(np.linalg.norm(np.cross(c[:, 1] - c[:, 0], c[:, 2] - c[:, 0]), axis=1).sum() / 2)

        top = volume.boundary[volume.boundary_ordinal == positions.index(_face_at(scene, base, 10.0)) + 1]
        self.assertAlmostEqual(area(top), 40 * 20 - 100, places=3)
        self.assertEqual((volume.boundary_ordinal == positions.index(_face_at(scene, post, 10.0)) + 1).sum(), 0)
        corners = volume.nodes[volume.boundary[:, :3]]
        inside = (
            (abs(corners[..., 2] - 10) < 1e-6).all(axis=1)
            & ((corners[..., 0] > 15 + 1e-6) & (corners[..., 0] < 25 - 1e-6) & (corners[..., 1] > 5 + 1e-6) & (corners[..., 1] < 15 - 1e-6)).all(axis=1)
        )
        self.assertFalse(inside.any())
        self.assertEqual(list(volume.interface_triangles), [(0, 1)])
        self.assertAlmostEqual(area(volume.interface_triangles[(0, 1)]), 100.0, places=3)

    def test_a_swapped_domain_mapping_is_caught(self):
        from cadgen._internal.fea.assembly import list_parts
        from cadgen._internal.fea.mesh import check_domains

        scene, refs, volume = self._glued()
        parts = list_parts(scene)
        check_domains(volume.nodes, volume.tets, volume.domain, parts)
        with self.assertRaisesRegex(RuntimeError, "do not follow the parts"):
            check_domains(volume.nodes, volume.tets, 1 - volume.domain, parts)

    def test_a_gap_within_the_tolerance_is_closed_to_glue_the_parts(self):
        import numpy as np

        _, _, volume = self._glued(lift=0.1)
        self.assertEqual(self._components(volume), 1)
        self.assertEqual(sorted(np.unique(volume.domain)), [0, 1])
        self.assertEqual(len(volume.interface_faces), 2)


@unittest.skipUnless(HAVE_FEA, "cadgen[fea] is not installed")
class FeaPartsVerbTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_lists_parts_and_their_bonded_pair(self):
        from cadgen import fea

        result = fea.parts(_write_assembly(self.tmp))
        self.assertEqual([part.name for part in result.parts], ["base", "post"])
        self.assertEqual(len(result.pairs), 1)
        pair = result.pairs[0]
        self.assertEqual(pair.between, ("post", "base"))
        self.assertEqual(pair.type, "bonded")
        self.assertIn("post ↔ base · 100 mm² · bonded", result.human_lines())

    def test_a_near_miss_is_listed_as_not_connected(self):
        from cadgen import fea

        result = fea.parts(_write_assembly(self.tmp, lift=0.3))
        self.assertEqual([pair.type for pair in result.pairs], ["not_connected"])
        self.assertIn("post ↔ base · gap 0.3 mm · not connected", result.human_lines())

    def test_json_output(self):
        from cadgen.cli.fea_parts import main

        path = _write_assembly(self.tmp)
        out = io.StringIO()
        with redirect_stdout(out):
            code = main([str(path), "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue().strip().splitlines()[-1])
        self.assertTrue(payload["ok"])
        self.assertEqual([part["name"] for part in payload["parts"]], ["base", "post"])
        self.assertEqual(payload["pairs"][0]["type"], "bonded")
        self.assertAlmostEqual(payload["pairs"][0]["area_mm2"], 100.0, places=2)


class AssemblyStudyFileTest(unittest.TestCase):
    """The study's assembly keys parse without the FEA stack."""

    BASE = {
        "material": "6061",
        "fixtures": [{"faces": ["#o1.1.f1"]}],
        "loads": [{"faces": ["#o1.2.f2"], "type": "force", "vector_N": [1, 0, 0]}],
    }

    def _parse(self, **extra):
        from cadgen._internal.fea.study import parse_study

        return parse_study({**self.BASE, **extra})

    def test_parts_connections_and_tolerance_parse(self):
        parsed = self._parse(
            parts={"post": {"material": "steel"}},
            connections=[{"between": ["post", "base"], "type": "free"}],
            contact_tolerance_mm=0.2,
        )
        self.assertEqual(parsed.parts["post"].yield_strength, 250.0)
        self.assertEqual((parsed.connections[0].between, parsed.connections[0].type), (("post", "base"), "free"))
        self.assertEqual(parsed.contact_tolerance_mm, 0.2)

    def test_a_study_without_them_is_a_one_part_study(self):
        parsed = self._parse()
        self.assertEqual((parsed.parts, parsed.connections, parsed.contact_tolerance_mm), ({}, (), 0.1))

    def test_bolt_and_contact_are_not_yet(self):
        for kind in ("bolt", "contact"):
            with self.assertRaisesRegex(ValueError, rf"connections\[0\]\.type: '{kind}' connections are not yet supported"):
                self._parse(connections=[{"between": ["post", "base"], "type": kind}])

    def test_the_errors_name_the_field(self):
        for extra, message in (
            ({"connections": [{"between": ["post"], "type": "free"}]}, r"connections\[0\]\.between"),
            ({"connections": [{"between": ["a", "b"], "type": "glued"}]}, r"connections\[0\]\.type"),
            ({"parts": {"post": {}}}, r"parts\['post'\]"),
            ({"contact_tolerance_mm": -1}, "contact_tolerance_mm"),
        ):
            with self.subTest(extra=extra), self.assertRaisesRegex(ValueError, message):
                self._parse(**extra)


@unittest.skipUnless(HAVE_FEA, "cadgen[fea] is not installed")
class SolveAssemblyTest(unittest.TestCase):
    """Base 6061 plus a steel post, base bottom fixed, 1000 N along +X on the post's top."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.tmp = Path(cls._tmp.name)
        from cadgen.step_scene import read_scene

        cls.step = _write_assembly(cls.tmp)
        scene = read_scene(cls.step)
        cls.refs = _refs(scene)
        cls.fixed = _face_at(scene, cls.refs["base"], 0.0)
        cls.load = _face_at(scene, cls.refs["post"], 40.0)
        cls.scene = scene
        cls.mixed = cls.solve(cls.step, {"base": "6061", "post": "steel"}, name="mixed")
        cls.steel = cls.solve(cls.step, {"base": "steel", "post": "steel"}, name="steel")
        cls.aluminium = cls.solve(cls.step, {"base": "6061", "post": "6061"}, name="aluminium")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    @classmethod
    def study(cls, materials: dict | None, **extra) -> dict:
        return {
            "material": "6061",
            **({"parts": {name: {"material": material} for name, material in materials.items()}} if materials else {}),
            "fixtures": [{"faces": [cls.fixed]}],
            "loads": [{"faces": [cls.load], "type": "force", "vector_N": [1000, 0, 0]}],
            "mesh": {"size_mm": 4.0},
            **extra,
        }

    @classmethod
    def solve(cls, step, materials, name, **extra):
        from cadgen import fea

        return fea.solve(step, cls.tmp / f"{name}.glb", study=cls.study(materials, **extra))

    def _types(self, result) -> list[str]:
        return [finding["type"] for finding in result.findings]

    def test_the_reactions_balance_the_load(self):
        self.assertEqual(self.mixed.warnings, ())
        np_sum = self.mixed.summary["reaction_force_N"]
        self.assertAlmostEqual(np_sum[0], -1000.0, delta=0.5)
        self.assertAlmostEqual(np_sum[1], 0.0, delta=0.5)
        self.assertAlmostEqual(np_sum[2], 0.0, delta=0.5)
        self.assertEqual(self.mixed.summary["applied_force_N"][0], 1000.0)

    def test_the_tip_moves_between_all_steel_and_all_aluminium(self):
        stiff, soft = self.steel.summary["max_displacement_mm"], self.aluminium.summary["max_displacement_mm"]
        self.assertLess(stiff, self.mixed.summary["max_displacement_mm"])
        self.assertLess(self.mixed.summary["max_displacement_mm"], soft)

    def test_each_part_has_its_own_peak_and_safety_factor_against_its_own_yield(self):
        parts = {part["name"]: part for part in self.mixed.summary["parts"]}
        self.assertEqual(set(parts), {"base", "post"})
        self.assertEqual((parts["base"]["yield_MPa"], parts["post"]["yield_MPa"]), (276.0, 250.0))
        for part in parts.values():
            self.assertAlmostEqual(part["safety_factor"], part["yield_MPa"] / part["peak_MPa"], delta=0.002)
        self.assertEqual(parts["post"]["material"], "Steel (structural, generic)")
        self.assertEqual(parts["base"]["ref"], self.refs["base"])
        self.assertGreater(parts["post"]["peak_MPa"], parts["base"]["peak_MPa"])

    def test_the_headline_is_the_weakest_part(self):
        summary = self.mixed.summary
        weakest = min(summary["parts"], key=lambda part: part["safety_factor"])
        self.assertEqual(summary["weakest_part"], weakest["name"])
        self.assertEqual(summary["weakest_part"], "post")
        self.assertEqual(summary["safety_factor"], weakest["safety_factor"])
        self.assertEqual(summary["yield_MPa"], weakest["yield_MPa"])
        self.assertIn("weakest part: post", self.mixed.human_lines())

    def test_each_part_that_falls_short_is_named_in_its_findings(self):
        (yields,) = [f for f in self.mixed.findings if f["type"] == "yields"]
        self.assertTrue(yields["summary"].startswith("The post yields: peak stress "), yields["summary"])
        self.assertEqual(self.mixed.findings[0], yields)
        (low,) = [f for f in self.mixed.findings if f["type"] == "low_margin"]
        self.assertTrue(low["summary"].startswith("'base' holds, but only 1."), low["summary"])

    def test_a_peak_at_the_foot_of_a_joint_is_the_edge_of_the_bonded_joint(self):
        edges = {f["summary"].split(":")[0]: f for f in self.mixed.findings if f["type"] == "bonded_edge_peak"}
        self.assertEqual(set(edges), {"In 'post'", "In 'base'"})
        self.assertIn("the edge of the bonded joint with 'base'", edges["In 'post'"]["summary"])
        self.assertEqual(edges["In 'post'"]["severity"], "warning")

    def test_a_part_the_study_does_not_name_uses_the_default_material(self):
        result = self.solve(self.step, {"post": "steel"}, "default")
        (finding,) = [f for f in result.findings if f["type"] == "default_material"]
        self.assertEqual(finding["summary"], "'base' uses the default material (Aluminum 6061-T6): is that right?")
        self.assertNotIn("default_material", self._types(self.mixed))

    def test_the_sidecar_records_the_joint(self):
        sidecar = json.loads(self.mixed.sidecar.read_text(encoding="utf-8"))
        (joint,) = sidecar["connections"]
        self.assertEqual((joint["between"], joint["type"]), (["post", "base"], "bonded"))
        self.assertAlmostEqual(joint["area_mm2"], 100.0, places=3)
        self.assertEqual(sidecar["summary"]["parts"], self.mixed.summary["parts"])

    def test_a_gap_that_is_closed_to_bond_is_said(self):
        from cadgen import fea
        from cadgen.step_scene import read_scene

        step = _write_assembly(self.tmp, lift=0.08, name="lifted")
        scene = read_scene(step)
        refs = _refs(scene)
        study = {
            "material": "6061",
            "parts": {"base": {"material": "6061"}, "post": {"material": "steel"}},
            "fixtures": [{"faces": [_face_at(scene, refs["base"], 0.0)]}],
            "loads": [{"faces": [_face_at(scene, refs["post"], 40.08)], "type": "force", "vector_N": [1000, 0, 0]}],
            "mesh": {"size_mm": 4.0},
        }
        result = fea.solve(step, self.tmp / "lifted.glb", study=study)
        (finding,) = [f for f in result.findings if f["type"] == "gap_closed"]
        self.assertEqual(finding["summary"], "Closed a 0.08 mm gap between 'post' and 'base' to bond them")
        self.assertAlmostEqual(result.summary["reaction_force_N"][0], -1000.0, delta=0.5)

    def _not_solved(self, step, study):
        from unittest import mock

        from cadgen import fea

        with mock.patch("cadgen._internal.fea.solve.solve_linear_static", side_effect=AssertionError("solved")):
            result = fea.solve(step, self.tmp / "none.glb", study=study)
        self.assertFalse(result.ok)
        self.assertIsNone(result.glb)
        self.assertFalse((self.tmp / "none.glb").exists())
        return result

    def test_a_floating_part_stops_the_study_before_the_solve(self):
        from cadgen.step_scene import read_scene

        step = _write_assembly(self.tmp, far_block=20.0, name="floating")
        scene = read_scene(step)
        refs = _refs(scene)
        study = {
            "material": "6061",
            "fixtures": [{"faces": [_face_at(scene, refs["base"], 0.0)]}],
            "loads": [{"faces": [_face_at(scene, refs["post"], 40.0)], "type": "force", "vector_N": [1000, 0, 0]}],
        }
        result = self._not_solved(step, study)
        (finding,) = result.findings
        self.assertEqual((finding["severity"], finding["type"]), ("error", "not_connected"))
        self.assertEqual(
            finding["summary"], "'block' isn't connected to anything that is held: nearest part 'base' is 20 mm away"
        )
        self.assertEqual(finding["items"][0]["ref"], refs["block"])
        self.assertIn("error: 'block' isn't connected", result.human_lines()[1])

    def test_a_part_set_free_of_the_only_held_part_is_not_connected(self):
        study = self.study({"base": "6061", "post": "steel"}, connections=[{"between": ["post", "base"], "type": "free"}])
        result = self._not_solved(self.step, study)
        (finding,) = result.findings
        self.assertEqual(finding["type"], "not_connected")
        self.assertEqual(
            finding["summary"], "'post' isn't connected to anything that is held: it touches 'base' but isn't bonded to it"
        )

    def test_a_fixture_or_load_on_a_joint_is_a_study_error(self):
        from cadgen import fea

        joint = _face_at(self.scene, self.refs["base"], 10.0)
        study = self.study(None)
        study["loads"] = [{"faces": [joint], "type": "force", "vector_N": [0, 0, -1]}]
        with self.assertRaisesRegex(ValueError, rf"{joint} is where 'base' is bonded to 'post'"):
            fea.solve(self.step, self.tmp / "joint.glb", study=study)

    def test_bolt_is_not_yet(self):
        from cadgen import fea

        with self.assertRaisesRegex(ValueError, "not yet supported"):
            fea.solve(self.step, self.tmp / "bolt.glb", study=self.study(None, connections=[{"between": ["post", "base"], "type": "bolt"}]))

    def test_the_parts_the_study_names_must_exist(self):
        from cadgen import fea

        with self.assertRaisesRegex(ValueError, r"parts\['lid'\]: no part named 'lid'; the parts are 'base', 'post'"):
            fea.solve(self.step, self.tmp / "lid.glb", study=self.study({"lid": "steel"}))
        with self.assertRaisesRegex(ValueError, "don't touch within 0.1 mm"):
            far = _write_assembly(self.tmp, far_block=20.0, name="far")
            fea.solve(far, self.tmp / "far.glb", study=self.study(None, connections=[{"between": ["block", "base"], "type": "bonded"}]))

    def test_one_joint_cannot_be_freed_inside_a_bonded_group(self):
        from cadgen import fea
        from cadgen.step_scene import read_scene

        from build123d import Align, Box, Compound, Pos, export_step

        base = Box(40, 20, 10, align=Align.MIN)
        base.label = "base"
        left = Pos(0, 5, 10) * Box(10, 10, 30, align=Align.MIN)
        left.label = "left"
        right = Pos(10, 5, 10) * Box(10, 10, 30, align=Align.MIN)
        right.label = "right"
        step = self.tmp / "two-posts.step"
        export_step(Compound(children=[base, left, right]), str(step))
        scene = read_scene(step)
        refs = _refs(scene)
        study = {
            "material": "6061",
            "fixtures": [{"faces": [_face_at(scene, refs["base"], 0.0)]}],
            "loads": [{"faces": [_face_at(scene, refs["right"], 40.0)], "type": "force", "vector_N": [100, 0, 0]}],
            "connections": [{"between": ["left", "right"], "type": "free"}],
        }
        with self.assertRaisesRegex(ValueError, "'left' and 'right' are also joined through other bonded parts"):
            fea.solve(step, self.tmp / "two.glb", study=study)

    def test_a_free_joint_that_splits_the_assembly_glues_each_group_apart(self):
        from cadgen import fea
        from cadgen.step_scene import read_scene

        step = _write_assembly(self.tmp, cap=True, name="capped")
        scene = read_scene(step)
        refs = _refs(scene)
        study = {
            "material": "6061",
            "parts": {name: {"material": "6061"} for name in ("base", "post", "cap")},
            "fixtures": [
                {"faces": [_face_at(scene, refs["base"], 0.0)]},
                {"faces": [_face_at(scene, refs["cap"], 45.0)]},
            ],
            "loads": [{"faces": [_face_where(scene, refs["post"], 0, 25.0)], "type": "force", "vector_N": [100, 0, 0]}],
            "connections": [{"between": ["cap", "post"], "type": "free"}],
            "mesh": {"size_mm": 4.0},
        }
        result = fea.solve(step, self.tmp / "capped.glb", study=study)
        self.assertTrue(result.ok)
        self.assertNotIn("not_connected", [f["type"] for f in result.findings])
        sidecar = json.loads(result.sidecar.read_text(encoding="utf-8"))
        self.assertEqual({c["between"][0]: c["type"] for c in sidecar["connections"]}, {"post": "bonded", "cap": "free"})
        # The 100 N is held by the base alone: the cap carries nothing across the free joint.
        self.assertAlmostEqual(result.summary["reaction_force_N"][0], -100.0, delta=0.5)

    def test_a_part_the_glue_leaves_apart_is_found_in_the_mesh(self):
        import numpy as np

        from cadgen._internal.fea.assembly import detect_contacts, list_parts
        from cadgen._internal.fea.mesh import mesh_assembly
        from cadgen._internal.fea.run import _unheld_after_meshing

        parts = list_parts(self.scene)
        refs = [part.ref for part in parts]
        joined = mesh_assembly(self.scene, refs, detect_contacts(parts, TOLERANCE), TOLERANCE, 4.0)
        apart = mesh_assembly(self.scene, refs, [], TOLERANCE, 4.0)
        ordinal = list(joined.faces).index(self.fixed) + 1
        self.assertEqual(_unheld_after_meshing(joined, {ordinal}, 2), [])
        self.assertEqual(_unheld_after_meshing(apart, {ordinal}, 2), [[1]])


if __name__ == "__main__":
    unittest.main()
