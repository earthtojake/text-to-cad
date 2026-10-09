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


def _write_assembly(directory: Path, *, lift: float = 0.0, edge_block: bool = False, name: str = "assembly") -> Path:
    """Base at the origin, post centred on its top and lifted by ``lift``; with
    ``edge_block``, a block that meets the base only along its +X/+Y edge."""
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


if __name__ == "__main__":
    unittest.main()
