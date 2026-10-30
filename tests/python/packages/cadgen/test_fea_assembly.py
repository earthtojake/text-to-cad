"""``cadgen fea`` on assemblies: parts, touching faces, and the glued mesh.

The fixture is a 40 x 20 x 10 base with a 10 x 10 x 30 post standing on its
top, written to a temporary STEP as two named parts; a lifted post and a block
meeting the base only along an edge cover the cases that must NOT be contact.
Nothing under ``models/`` is read.
"""

from __future__ import annotations

import io
import json
import re
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from tests.python.support.fea_fixtures import (
    class_directory, glb_array, glb_attribute_names, glb_extras, needs_fea, quiet, reported, solve,
)
from tests.python.support.fea_fixtures import AL6061_NUMBERS, STEEL_NUMBERS  # noqa: E402

#: The materials the mixed studies name each part by, as numbers.
NUMBERS = {"steel": STEEL_NUMBERS, "6061": AL6061_NUMBERS}

TOLERANCE = 0.1
MESH = {"size_mm": 4.0}


def _box(label: str, at: tuple[float, float, float], size: tuple[float, float, float]):
    from build123d import Align, Box, Pos

    box = Pos(*at) * Box(*size, align=Align.MIN)
    box.label = label
    return box


def _export(path: Path, *children) -> Path:
    from build123d import Compound, export_step

    export_step(Compound(children=list(children)), str(path))
    return path


def _write_assembly(
    directory: Path, *, lift: float = 0.0, edge_block: bool = False, far_block: float | None = None,
    cap: bool = False, overlap_block: bool = False, corner_block: float | None = None, name: str = "assembly",
) -> Path:
    """Base at the origin, post centred on its top and lifted by ``lift``; with
    ``edge_block``, a block that meets the base only along its +X/+Y edge; with
    ``far_block``, a block that far (mm) beyond the base's +X end; with ``cap``,
    a plate on the post's top; with ``overlap_block``, a block sunk 1 mm into the base's
    +X end (they share 100 mm^3); with ``corner_block``, a block whose corner is sunk
    that far (mm) into the base's +X/+Y top corner on all three axes."""
    children = [_box("base", (0, 0, 0), (40, 20, 10)), _box("post", (15, 5, 10 + lift), (10, 10, 30))]
    if edge_block:
        children.append(_box("block", (40, 20, 0), (10, 10, 10)))
    if far_block is not None:
        children.append(_box("block", (40 + far_block, 0, 0), (10, 10, 10)))
    if overlap_block:
        children.append(_box("block", (39, 5, 0), (10, 10, 10)))
    if corner_block is not None:
        sunk = corner_block
        children.append(_box("block", (40 - sunk, 20 - sunk, 10 - sunk), (10, 10, 10)))
    if cap:
        children.append(_box("cap", (12, 2, 40 + lift), (16, 16, 5)))
    return _export(directory / f"{name}.step", *children)


def _refs(scene) -> dict[str, str]:
    return {leaf.label: leaf.ref for leaf in scene.leaves()}


def _refs_of(parts) -> dict[str, str]:
    return {part.name: part.ref for part in parts}


def _face_where(scene, part_ref: str, axis: int, value: float) -> str:
    """The ref of the part's face whose centre is at ``value`` along ``axis`` (0 = X, 2 = Z)."""
    from cadgen._internal.fea.mesh import face_area_center

    (part,) = scene.resolve(part_ref)
    for selection in part.entities("face"):
        _, centre = face_area_center(selection.shape())
        if abs(centre[axis] - value) < 1e-6:
            return selection.ref
    raise AssertionError(f"no face of {part_ref} at {'xyz'[axis]} = {value}")


def _face_at(scene, part_ref: str, z: float) -> str:
    """The ref of the part's horizontal face whose centre is at height ``z``."""
    return _face_where(scene, part_ref, 2, z)


def _scene(step: Path):
    from cadgen._internal.fea.document import read_document

    scene = read_document(step)
    return scene, _refs(scene)


def _pushed(step: Path, part: str, z: float, force: float = 1000, **extra) -> dict:
    """A 6061 study of ``step``: the base's bottom held, ``part``'s face at height ``z`` pushed along +X."""
    scene, refs = _scene(step)
    return {"material": AL6061_NUMBERS, **extra, "fixtures": [{"faces": [_face_at(scene, refs["base"], 0.0)]}],
            "loads": [{"faces": [_face_at(scene, refs[part], z)], "type": "force", "vector_N": [force, 0, 0]}]}


def _temporary(case: unittest.TestCase) -> Path:
    tmp = tempfile.TemporaryDirectory()
    case.addCleanup(tmp.cleanup)
    return Path(tmp.name)


@needs_fea
class DetectContactsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = _temporary(self)

    def _parts(self, **kwargs):
        from cadgen._internal.fea.assembly import list_parts
        from cadgen._internal.fea.document import read_document

        return list_parts(read_document(_write_assembly(self.tmp, **kwargs)))

    def _contacts(self, **kwargs):
        from cadgen._internal.fea.assembly import detect_contacts

        parts = self._parts(**kwargs)
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

    def test_two_boxes_that_overlap_by_a_millimetre_share_a_hundred_cubic_millimetres(self):
        from cadgen._internal.fea.assembly import detect_contacts, detect_overlaps

        parts = self._parts(overlap_block=True, name="sunk")
        (overlap,) = detect_overlaps(parts)
        refs = _refs_of(parts)
        self.assertEqual({overlap.a, overlap.b}, {refs["base"], refs["block"]})
        self.assertAlmostEqual(overlap.volume_mm3, 100.0, places=3)
        self.assertEqual(overlap.a, refs["block"])  # the smaller part first
        # The overlapping pair is for the caller to leave out of contacts.
        skip = {frozenset((overlap.a, overlap.b))}
        self.assertEqual([c for c in detect_contacts(parts, TOLERANCE, skip=skip) if refs["block"] in (c.a, c.b)], [])

    def test_an_overlap_no_thicker_than_the_tolerance_is_an_interference_to_bond(self):
        from cadgen._internal.fea.assembly import detect_overlaps, interferences

        parts = self._parts(lift=-0.01, name="pressed")
        refs = _refs_of(parts)
        (overlap,) = detect_overlaps(parts)
        self.assertAlmostEqual(overlap.thickness_mm, 0.01, delta=1e-4)
        (contact,), left = interferences([overlap], TOLERANCE)
        self.assertEqual(left, [])
        self.assertEqual((contact.a, contact.b), (refs["post"], refs["base"]))
        self.assertEqual(contact.gap_mm, 0.0)
        self.assertAlmostEqual(contact.interference_mm, 0.01, delta=1e-4)
        self.assertAlmostEqual(contact.area_mm2, 100.0, delta=1.0)
        # A flat press fit stays an interference up to the tolerance.
        for depth in (0.05, 0.09):
            with self.subTest(depth=depth):
                (overlap,) = detect_overlaps(self._parts(lift=-depth, name=f"pressed{depth}"))
                (contact,), left = interferences([overlap], TOLERANCE)
                self.assertEqual(left, [])
                self.assertAlmostEqual(contact.interference_mm, depth, delta=1e-4)

    def test_an_overlap_thicker_than_the_tolerance_stays_an_overlap(self):
        from cadgen._internal.fea.assembly import detect_overlaps, interferences

        (overlap,) = detect_overlaps(self._parts(overlap_block=True, name="sunk"))
        self.assertAlmostEqual(overlap.thickness_mm, 1.0, places=6)  # 1 x 10 x 10 mm: its volume over its largest face
        self.assertEqual(interferences([overlap], TOLERANCE), ([], [overlap]))
        # A corner sunk on every axis: a 0.25 mm cube in common, which 2 V / A alone reads as a third of its depth
        # (0.083 mm), inside the tolerance.
        (overlap,) = detect_overlaps(self._parts(corner_block=0.25, name="corner"))
        self.assertAlmostEqual(overlap.volume_mm3, 0.25**3, places=6)
        self.assertAlmostEqual(overlap.thickness_mm, 0.25, places=6)
        self.assertEqual(interferences([overlap], TOLERANCE), ([], [overlap]))

    def test_parts_that_only_touch_do_not_overlap(self):
        from cadgen._internal.fea.assembly import detect_overlaps

        self.assertEqual(detect_overlaps(self._parts()), [])

    def test_a_row_of_parts_is_checked_only_between_neighbours(self):
        from cadgen._internal.fea.assembly import detect_contacts, list_parts
        from cadgen._internal.fea.document import read_document

        path = _export(self.tmp / "row.step", *(_box(f"box{n}", (10 * n, 0, 0), (10, 10, 10)) for n in range(12)))
        parts = list_parts(read_document(path))
        said = []
        contacts = detect_contacts(parts, TOLERANCE, log=said.append)
        self.assertEqual(len(contacts), 11)
        self.assertEqual(said, ["checking 11 close part pairs for touching faces"])  # not 66 pairs


@needs_fea
class MeshAssemblyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = class_directory(cls)

    def _glued(self, lift: float = 0.0):
        from cadgen._internal.fea.assembly import detect_contacts, list_parts
        from cadgen._internal.fea.mesh import mesh_assembly
        from cadgen._internal.fea.document import read_document

        scene = read_document(_write_assembly(self.tmp, lift=lift, name=f"lift{lift}"))
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
        self.assertTrue(all(ref.startswith((base + "/face ", post + "/face ")) for ref in volume.faces))
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


@needs_fea
class FeaPartsVerbTest(unittest.TestCase):
    def setUp(self):
        self.tmp = _temporary(self)

    def _parts(self, **kwargs):
        from cadgen import fea

        with quiet():
            return fea.parts(_write_assembly(self.tmp, **kwargs))

    def test_lists_parts_and_their_bonded_pair(self):
        result = self._parts()
        self.assertEqual([part.name for part in result.parts], ["base", "post"])
        self.assertEqual(len(result.pairs), 1)
        pair = result.pairs[0]
        self.assertEqual(pair.between, ("post", "base"))
        self.assertEqual(pair.type, "bonded")
        self.assertIn("post ↔ base · 100 mm² · bonded", result.human_lines())

    def test_it_says_each_stage_at_default_verbosity(self):
        from cadgen.cli.fea_parts import main

        err = io.StringIO()
        with redirect_stderr(err), redirect_stdout(io.StringIO()):
            main([str(_write_assembly(self.tmp))])
        lines = err.getvalue().splitlines()
        self.assertTrue(any(line.endswith("reading the parts") for line in lines), lines)
        self.assertTrue(any("read 2 parts" in line for line in lines), lines)
        self.assertTrue(any("checking 1 close part pairs" in line for line in lines), lines)
        self.assertTrue(any("found 1 touching or near pairs" in line for line in lines), lines)

    def test_an_overlap_is_listed_with_its_volume_and_is_not_a_touching_pair(self):
        result = self._parts(overlap_block=True)
        self.assertEqual([(pair.type, pair.between) for pair in result.pairs], [("bonded", ("post", "base")), ("overlapping", ("block", "base"))])
        self.assertAlmostEqual(result.pairs[1].overlap_mm3, 100.0, places=3)
        self.assertTrue(result.human_lines()[0].endswith(": 3 parts, 1 touching pairs, 1 overlapping"))
        self.assertIn("block ↔ base · overlapping · 100 mm³", result.human_lines())

    def test_a_corner_sunk_on_every_axis_is_listed_as_overlapping(self):
        result = self._parts(corner_block=0.25, name="corner")
        self.assertIn(("overlapping", ("block", "base")), [(pair.type, pair.between) for pair in result.pairs])

    def test_an_interference_within_the_tolerance_is_listed_as_bonded(self):
        result = self._parts(lift=-0.01)
        (pair,) = result.pairs
        self.assertEqual((pair.type, pair.between, pair.gap_mm), ("bonded", ("post", "base"), 0.0))
        self.assertAlmostEqual(pair.interference_mm, 0.01, delta=1e-4)
        self.assertTrue(result.human_lines()[0].endswith(": 2 parts, 1 touching pairs"))
        self.assertTrue(any(line.startswith("post ↔ base · ") and line.endswith(" · interference 0.01 mm · bonded") for line in result.human_lines()))

    def test_a_near_miss_is_listed_as_not_connected_and_not_counted_as_a_touching_pair(self):
        result = self._parts(lift=0.3)
        self.assertTrue(result.human_lines()[0].endswith(": 2 parts, 0 touching pairs, 1 near miss"), result.human_lines()[0])
        self.assertEqual([pair.type for pair in result.pairs], ["not_connected"])
        self.assertIn("post ↔ base · gap 0.3 mm · not connected", result.human_lines())

    def test_it_needs_only_what_contact_detection_needs_not_netgen(self):
        import builtins
        from unittest import mock

        real = builtins.__import__

        def refuse(name, *args, **kwargs):
            if name.split(".")[0] == "netgen":
                raise ImportError(name)
            return real(name, *args, **kwargs)

        with mock.patch("builtins.__import__", refuse):
            result = self._parts()
        self.assertEqual([pair.type for pair in result.pairs], ["bonded"])

    def test_json_output(self):
        from cadgen.cli.fea_parts import main

        out = io.StringIO()
        with redirect_stdout(out), quiet():
            code = main([str(_write_assembly(self.tmp)), "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue().strip().splitlines()[-1])
        self.assertTrue(payload["ok"])
        self.assertEqual([part["name"] for part in payload["parts"]], ["base", "post"])
        self.assertEqual(payload["pairs"][0]["type"], "bonded")
        self.assertAlmostEqual(payload["pairs"][0]["area_mm2"], 100.0, places=2)


@needs_fea
class DuplicateNamesTest(unittest.TestCase):
    """A base with two posts that are both called ``bar``: the study has to say which."""

    @classmethod
    def setUpClass(cls):
        from cadgen._internal.fea.document import read_document

        cls.tmp = class_directory(cls)
        cls.step = _export(cls.tmp / "bars.step", _box("base", (0, 0, 0), (40, 20, 10)),
                           *(_box("bar", (x, 5, 10), (10, 10, 30)) for x in (2, 26)))
        cls.scene = read_document(cls.step)
        cls.base, cls.first, cls.second = [leaf.ref for leaf in cls.scene.leaves()]

    def study(self, **extra) -> dict:
        return {
            "material": AL6061_NUMBERS,
            "fixtures": [{"faces": [_face_at(self.scene, self.base, 0.0)]}],
            "loads": [{"faces": [_face_at(self.scene, self.first, 40.0)], "type": "force", "vector_N": [500, 0, 0]}],
            "mesh": MESH,
            **extra,
        }

    def test_the_listing_tells_the_two_bars_apart_by_their_refs(self):
        from cadgen import fea

        with quiet():
            lines = fea.parts(self.step).human_lines()
        self.assertIn(f"bar ({self.first}) ↔ base · 100 mm² · bonded", lines)
        self.assertIn(f"bar ({self.second}) ↔ base · 100 mm² · bonded", lines)

    def test_a_study_can_name_each_bar_by_its_ref(self):
        study = self.study(parts={self.first: {"material": STEEL_NUMBERS}, self.second: {"material": AL6061_NUMBERS}, "base": {"material": AL6061_NUMBERS}})
        result = solve(self.step, self.tmp / "refs.glb", study)
        self.assertIsNotNone(result.glb)  # solved; ok is the part's verdict (a bar yields under this load)
        names = [part["name"] for part in result.summary["parts"]]
        self.assertEqual(names, ["base", f"bar ({self.first})", f"bar ({self.second})"])
        materials = {part["ref"]: part["material"] for part in result.summary["parts"]}
        self.assertTrue(materials[self.first].startswith("Steel"))  # the ref chose the material

    def test_sentences_name_a_shared_name_with_its_ref(self):
        # Neither the study nor the model gives the first bar a material: refused, naming it by its ref too.
        study = {key: value for key, value in self.study(parts={"base": {"material": AL6061_NUMBERS}}).items()
                 if key != "material"}
        with self.assertRaisesRegex(ValueError, rf"'bar' \({re.escape(self.first)}\) has no material"):
            solve(self.step, self.tmp / "default.glb", study)

    def test_a_name_both_bars_share_is_an_error_naming_the_refs(self):
        with self.assertRaisesRegex(ValueError, rf"parts\['bar'\]: 'bar' names 2 parts \({self.first}, {self.second}\); use a ref"):
            solve(self.step, self.tmp / "ambiguous.glb", self.study(parts={"bar": {"material": STEEL_NUMBERS}}))
        connections = [{"between": ["bar", "base"], "type": "free"}]
        with self.assertRaisesRegex(ValueError, rf"connections\[0\].between: 'bar' names 2 parts \({self.first}, {self.second}\); use a ref"):
            solve(self.step, self.tmp / "ambiguous.glb", self.study(connections=connections))

    def test_a_connection_can_name_a_bar_by_its_ref_and_the_other_part_by_name(self):
        # Freeing the second bar from the base leaves it unheld, and the error says which bar.
        result = solve(self.step, self.tmp / "free.glb", self.study(connections=[{"between": [self.second, "base"], "type": "free"}]))
        self.assertFalse(result.ok)
        (finding,) = result.findings
        self.assertEqual(finding["type"], "not_connected")
        self.assertTrue(finding["summary"].startswith(f"'bar' ({self.second}) isn't connected"), finding["summary"])


class AssemblyStudyFileTest(unittest.TestCase):
    """The study's assembly keys parse without the FEA stack."""

    BASE = {
        "material": AL6061_NUMBERS,
        "fixtures": [{"faces": ["base/face 1"]}],
        "loads": [{"faces": ["post/face 2"], "type": "force", "vector_N": [1, 0, 0]}],
    }

    def _parse(self, **extra):
        from cadgen._internal.fea.study import parse_study

        return parse_study({**self.BASE, **extra})

    def test_parts_connections_and_tolerance_parse(self):
        parsed = self._parse(
            parts={"post": {"material": STEEL_NUMBERS}},
            connections=[{"between": ["post", "base"], "type": "free"}],
            contact_tolerance_mm=0.2,
        )
        self.assertEqual(parsed.parts["post"].yield_strength, 250.0)
        self.assertEqual((parsed.connections[0].between, parsed.connections[0].type), (("post", "base"), "free"))
        self.assertEqual(parsed.contact_tolerance_mm, 0.2)

    def test_the_tolerance_is_set_in_the_study_alone(self):
        # The study is the document of record: `fea parts` lists against the default and takes no tolerance of its own.
        import inspect

        from cadgen import fea
        from cadgen.cli.fea_parts import build_parser

        self.assertNotIn("contact_tolerance_mm", inspect.signature(fea.parts).parameters)
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            build_parser().parse_args(["a.step", "--contact-tolerance-mm", "0.2"])

    def test_a_study_without_them_is_a_one_part_study(self):
        parsed = self._parse()
        self.assertEqual((parsed.parts, parsed.connections, parsed.contact_tolerance_mm), ({}, (), 0.1))

    def test_the_errors_name_the_field(self):
        for extra, message in (
            ({"connections": [{"between": ["post"], "type": "free"}]}, r"connections\[0\]\.between"),
            ({"connections": [{"between": ["a", "b"], "type": "glued"}]}, r"connections\[0\]\.type"),
            ({"parts": {"post": {}}}, r"parts\['post'\]"),
            ({"contact_tolerance_mm": -1}, "contact_tolerance_mm"),
        ):
            with self.subTest(extra=extra), self.assertRaisesRegex(ValueError, message):
                self._parse(**extra)


@needs_fea
class SolveAssemblyTest(unittest.TestCase):
    """Base 6061 plus a steel post, base bottom fixed, 1000 N along +X on the post's top."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = class_directory(cls)
        cls.step = _write_assembly(cls.tmp)
        cls.scene, cls.refs = _scene(cls.step)
        cls.fixed = _face_at(cls.scene, cls.refs["base"], 0.0)
        cls.load = _face_at(cls.scene, cls.refs["post"], 40.0)
        # The post alone: held at its foot, pushed at its top.
        cls.alone = {"material": STEEL_NUMBERS, "fixtures": [{"faces": [_face_at(cls.scene, cls.refs["post"], 10.0)]}],
                     "loads": [{"faces": [cls.load], "type": "force", "vector_N": [1000, 0, 0]}], "mesh": MESH}
        with quiet():
            # Its checks: the stress check and one displacement check over a face of each part, both passing.
            cls.mixed = cls.solve_parts({"base": "6061", "post": "steel"}, name="mixed", checks=[
                {"kind": "stress"}, {"kind": "displacement", "limit_mm": 100.0, "faces": [cls.load, cls.fixed], "label": "Post and base"}])
            cls.steel = cls.solve_parts({"base": "steel", "post": "steel"}, name="steel")
            cls.aluminium = cls.solve_parts({"base": "6061", "post": "6061"}, name="aluminium")

    @classmethod
    def study(cls, materials: dict | None, **extra) -> dict:
        return {
            "material": AL6061_NUMBERS,
            **({"parts": {name: {"material": NUMBERS[material]} for name, material in materials.items()}} if materials else {}),
            "fixtures": [{"faces": [cls.fixed]}],
            "loads": [{"faces": [cls.load], "type": "force", "vector_N": [1000, 0, 0]}],
            "mesh": MESH,
            **extra,
        }

    @classmethod
    def solve_parts(cls, materials, name, **extra):
        """The study of the base and post solved, its progress lines left on stderr."""
        from cadgen import fea

        return fea.solve(cls.step, cls.tmp / f"{name}.glb", study=cls.study(materials, **extra))

    def _types(self, result) -> list[str]:
        return [finding["type"] for finding in result.findings]

    def test_a_study_says_its_planning_stages_at_default_verbosity(self):
        err = io.StringIO()
        with redirect_stderr(err):
            self.solve_parts({"base": "6061", "post": "steel"}, name="quiet")
        text = err.getvalue()
        for stage in ("reading the parts", "found 1 touching pairs", "gluing 1 bonded pairs of 2 parts", "meshing the glued shape"):
            self.assertIn(stage, text)

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
        # The weakest part's numbers are one scope: its peak, its yield and its factor agree.
        self.assertEqual(summary["weakest_part_peak_MPa"], weakest["peak_MPa"])
        self.assertEqual(summary["weakest_part_peak_at_mm"], weakest["peak_at_mm"])
        self.assertAlmostEqual(summary["safety_factor"], summary["yield_MPa"] / summary["weakest_part_peak_MPa"], delta=0.002)
        self.assertGreaterEqual(summary["max_von_mises_MPa"], summary["weakest_part_peak_MPa"])
        lines = self.mixed.human_lines()
        peak = summary["weakest_part_peak_MPa"]
        from cadgen._internal.fea.checks import safety_factor_text

        self.assertIn(
            f"weakest part 'post': peak {peak} MPa, yield 250.0 MPa, safety factor {safety_factor_text(summary['safety_factor'])}",
            lines,
        )
        self.assertTrue(any(line.startswith(f"assembly peak von Mises {summary['max_von_mises_MPa']} MPa") for line in lines))
        self.assertTrue(any(line.startswith("  'base' (Aluminum 6061-T6): peak ") for line in lines))

    def test_the_stress_check_is_the_weakest_parts_and_a_displacement_check_may_span_parts(self):
        stress, both = self.mixed.summary["checks"]
        summary = self.mixed.summary
        self.assertEqual((stress["part"], stress["value"], stress["limit"]), ("post", summary["weakest_part_peak_MPa"], 250.0))
        self.assertEqual(stress["ratio"], round(1 / summary["safety_factor"], 6))
        self.assertEqual(stress["status"], "fails" if summary["safety_factor"] < 1 else "close" if summary["safety_factor"] < 2 else "passes")
        # The post's loaded top moves the most of the two faces; the fixed base face not at all.
        self.assertEqual(both["faces"], [self.fixed, self.load])
        self.assertEqual(both["where"]["ref"], self.load)
        self.assertAlmostEqual(both["value"], summary["max_displacement_mm"], delta=0.05 * summary["max_displacement_mm"])
        self.assertEqual(both["status"], "passes")
        self.assertEqual(glb_extras(self.mixed.glb)["checks"], summary["checks"])

    def test_each_part_that_falls_short_is_named_in_its_findings(self):
        (yields,) = [f for f in self.mixed.findings if f["type"] == "yields"]
        self.assertTrue(yields["summary"].startswith("'post' yields: peak stress "), yields["summary"])
        self.assertEqual(self.mixed.findings[0], yields)
        (low,) = [f for f in self.mixed.findings if f["type"] == "low_margin"]
        self.assertTrue(low["summary"].startswith("'base' holds, but only 1."), low["summary"])

    def test_a_peak_at_the_foot_of_a_joint_is_the_edge_of_the_bonded_joint(self):
        edges = {f["summary"].split(":")[0]: f for f in self.mixed.findings if f["type"] == "bonded_edge_peak"}
        self.assertEqual(set(edges), {"In 'post'", "In 'base'"})
        self.assertIn("the edge of the bonded joint with 'base'", edges["In 'post'"]["summary"])
        self.assertEqual(edges["In 'post'"]["severity"], "warning")

    def test_a_part_with_no_material_anywhere_is_refused(self):
        # The study names the post's alone and gives no material of its own, and the model gives the base none: no
        # default stands in for it.
        study = {key: value for key, value in self.study({"post": "steel"}).items() if key != "material"}
        with self.assertRaisesRegex(ValueError, r"'base' has no material: set part.material in its model"):
            solve(self.step, self.tmp / "nothing.glb", study)
        self.assertFalse((self.tmp / "nothing.glb").exists())

    def test_the_result_records_the_joint(self):
        written = reported(self.mixed)
        (joint,) = written["connections"]
        self.assertEqual((joint["between"], joint["type"]), (["post", "base"], "bonded"))
        self.assertAlmostEqual(joint["area_mm2"], 100.0, places=3)
        self.assertEqual(written["summary"]["parts"], self.mixed.summary["parts"])

    def test_the_glb_tags_every_vertex_with_its_part(self):
        import numpy as np

        glb = self.mixed.glb
        part = glb_array(glb, "_PART")[:, 0]
        position = glb_array(glb, "POSITION", 3)  # glTF metres, Y up: CAD z is glTF y
        self.assertEqual(set(np.unique(part)), {0.0, 1.0})
        height = position[:, 1] * 1000.0
        # The tip moves under load, never by as much as a part's own height.
        self.assertTrue((height[part == 1.0] > 10 - 1.0).all())
        self.assertTrue((height[part == 0.0] < 10 + 1.0).all())
        self.assertGreater((height[part == 1.0] > 10 + 1.0).sum(), 0)
        extras = glb_extras(glb)
        self.assertEqual([p["name"] for p in extras["parts"]], ["base", "post"])
        self.assertEqual(extras["parts"][1]["ref"], self.refs["post"])

    def test_every_vertexs_face_belongs_to_its_part(self):
        extras = glb_extras(self.mixed.glb)
        part = glb_array(self.mixed.glb, "_PART")[:, 0].astype(int)
        face = glb_array(self.mixed.glb, "_FACE")[:, 0].astype(int)
        for part_index, face_index in set(zip(part.tolist(), face.tolist())):
            self.assertTrue(
                extras["faces"][face_index].startswith(extras["parts"][part_index]["ref"] + "/face "),
                (extras["faces"][face_index], extras["parts"][part_index]["ref"]),
            )

    def test_a_joints_faces_come_in_the_glbs_face_order(self):
        extras = glb_extras(self.mixed.glb)
        (joint,) = extras["connections"]
        self.assertEqual(joint["faces"], sorted(joint["faces"], key=extras["faces"].index))

    def test_the_glb_parts_match_the_result(self):
        extras = glb_extras(self.mixed.glb)
        summary = reported(self.mixed)["summary"]
        keys = ("ref", "name", "material", "yield_MPa", "peak_MPa", "safety_factor", "max_displacement_mm")
        self.assertEqual(extras["parts"], [{k: part[k] for k in keys} for part in summary["parts"]])
        self.assertEqual(extras["weakest_part"], "post")
        self.assertEqual(extras["weakest_part_peak_MPa"], summary["weakest_part_peak_MPa"])
        self.assertEqual(extras["safety_factor"], summary["safety_factor"])
        self.assertEqual(extras["max_displacement_mm"], summary["max_displacement_mm"])

    def test_the_glb_connection_lists_the_interface_faces_of_both_sides(self):
        extras = glb_extras(self.mixed.glb)
        (joint,) = extras["connections"]
        self.assertEqual(joint["between"], [self.refs["post"], self.refs["base"]])
        self.assertEqual((joint["names"], joint["type"]), (["post", "base"], "bonded"))
        self.assertAlmostEqual(joint["area_mm2"], 100.0, places=3)
        self.assertEqual(joint["gap_mm"], 0.0)
        # The post's bottom and the base's top, as the GLB's own face list names them.
        self.assertEqual(set(joint["faces"]), {_face_at(self.scene, self.refs["post"], 10.0), _face_at(self.scene, self.refs["base"], 10.0)})
        self.assertTrue(set(joint["faces"]) <= set(extras["faces"]))
        self.assertEqual(reported(self.mixed)["connections"][0]["faces"], joint["faces"])

    def test_solve_picks_no_part_and_sizes_no_mesh(self):
        # A part on its own is its own model (law 22), and the mesh's size is the study's: the options that did either
        # are gone, and refused as any argument the command never had (law 15).
        from cadgen.cli.fea_solve import main

        for option, value in (("--occurrence", self.refs["post"]), ("--mesh-size", "2")):
            with self.subTest(option=option), redirect_stderr(io.StringIO()) as said, self.assertRaises(SystemExit):
                main([str(self.step), str(self.tmp / "cli.glb"), "--study", json.dumps(self.alone), option, value])
            self.assertIn(f"unrecognized arguments: {option}", said.getvalue())
        self.assertFalse((self.tmp / "cli.glb").exists())

    def _first_solve_only(self, name):
        """The mixed study solved once at the first mesh size, with the outcome and the mesh it was solved on."""
        from unittest import mock

        from cadgen._internal.fea import solve as solve_module

        seen = []
        real = solve_module.solve_linear_static

        def spy(volume, *args, **kwargs):
            outcome = real(volume, *args, **kwargs)
            seen.append((volume, outcome))
            return outcome

        with mock.patch("cadgen._internal.fea.checks.needs_finer", return_value=False), \
                mock.patch("cadgen._internal.fea.solve.solve_linear_static", spy), quiet():
            result = self.solve_parts({"base": "6061", "post": "steel"}, name)
        (volume, outcome), = seen
        return result, volume, outcome

    def test_each_part_has_its_own_stress_field_that_jumps_across_the_joint(self):
        import numpy as np

        result, volume, outcome = self._first_solve_only("once")
        self.assertIsNone(reported(result)["refined"])
        fields = outcome.von_mises_parts
        # A node in the middle of the joint: z = 10, inside the post's footprint.
        at = outcome.dof_locations
        joint = np.flatnonzero((abs(at[:, 2] - 10) < 1e-6) & (at[:, 0] > 16) & (at[:, 0] < 24) & (at[:, 1] > 6) & (at[:, 1] < 14))
        self.assertGreater(len(joint), 0)
        base, post = fields[0, joint], fields[1, joint]
        self.assertTrue((abs(base - post) > 0.01 * np.maximum(base, post)).any())
        # Each part's peak is the maximum of its own field over its own elements.
        for index, part in enumerate(result.summary["parts"]):
            own = np.unique(outcome.element_dofs[volume.domain == index])
            self.assertEqual(part["peak_MPa"], round(float(fields[index][own].max()), 4))
        # The field is zero where the part is not.
        self.assertEqual(fields[1][np.unique(outcome.element_dofs[volume.domain == 0]).tolist()].min(), 0.0)
        # The assembly-wide peak is the larger of the two.
        self.assertEqual(result.summary["max_von_mises_MPa"], round(float(fields.max()), 4))

    def test_a_close_call_is_solved_again_and_the_record_compares_one_part_with_itself(self):
        from cadgen._internal.fea.checks import _number

        coarse, _, _ = self._first_solve_only("coarse")
        before = {part["name"]: part["peak_MPa"] for part in coarse.summary["parts"]}
        weakest = coarse.summary["weakest_part"]
        refined = reported(self.mixed)["refined"]
        self.assertEqual(refined["part"], weakest)
        self.assertEqual(refined["from_max_von_mises_MPa"], before[weakest])
        after = {part["name"]: part["peak_MPa"] for part in self.mixed.summary["parts"]}
        self.assertEqual(refined["max_von_mises_MPa"], after[weakest])
        self.assertEqual(refined["size_mm"], 2.0)
        # Each part's convergence finding quotes that part's own coarser and finer peaks.
        moved = {f["summary"].split(":")[0]: f["summary"] for f in self.mixed.findings if f["type"] == "mesh_not_converged"}
        for name in ("base", "post"):
            self.assertIn(f"({_number(before[name])} to {_number(after[name])} MPa)", moved[f"In '{name}'"])

    def test_a_result_that_stopped_before_the_solve_serializes_through_the_cli(self):
        from unittest import mock

        from cadgen.cli.fea_solve import main

        step = _write_assembly(self.tmp, far_block=20.0, name="stopped")
        study = {
            "material": AL6061_NUMBERS,
            "fixtures": [{"faces": [self.fixed]}],
            "loads": [{"faces": [self.load], "type": "force", "vector_N": [1000, 0, 0]}],
        }
        out = io.StringIO()
        with mock.patch("cadgen._internal.fea.solve.solve_linear_static", side_effect=AssertionError("solved")), redirect_stdout(out), quiet():
            code = main([str(step), str(self.tmp / "stopped.glb"), "--study", json.dumps(study), "--json"])
        self.assertEqual(code, 1)
        payload = json.loads(out.getvalue().strip().splitlines()[-1])
        self.assertFalse(payload["ok"])
        self.assertIsNone(payload["glb"])
        self.assertEqual(payload["findings"][0]["type"], "not_connected")

    def _closed(self, lift: float, name: str, **extra):
        """The post lifted (or, below 0, pressed into the base) by ``lift``, glued anyway: the study solves."""
        step = _write_assembly(self.tmp, lift=lift, name=name)
        result = solve(step, self.tmp / f"{name}.glb", _pushed(step, "post", 40.0 + lift, mesh=MESH, **extra))
        (finding,) = [f for f in result.findings if f["type"] == "gap_closed"]
        self.assertAlmostEqual(result.summary["reaction_force_N"][0], -1000.0, delta=0.5)
        return result, finding["summary"]

    def test_a_gap_that_is_closed_to_bond_is_said(self):
        _, said = self._closed(0.08, "lifted", parts={"base": {"material": AL6061_NUMBERS}, "post": {"material": STEEL_NUMBERS}})
        self.assertEqual(said, "Closed a 0.08 mm gap between 'post' and 'base' to bond them")

    def test_an_interference_that_is_closed_to_bond_is_said(self):
        result, said = self._closed(-0.01, "pressed", parts={"base": {"material": AL6061_NUMBERS}, "post": {"material": STEEL_NUMBERS}})
        self.assertIsNotNone(result.glb)  # solved; ok is the part's verdict
        self.assertNotIn("overlapping_parts", self._types(result))
        self.assertEqual(said, "Closed a 0.01 mm interference between 'post' and 'base' to bond them")
        (joint,) = reported(result)["connections"]
        self.assertEqual(joint["type"], "bonded")

    def test_a_press_fit_just_inside_the_tolerance_is_closed_to_bond(self):
        result, said = self._closed(-0.09, "pressed-deep")
        self.assertIsNotNone(result.glb)  # solved; ok is the part's verdict
        self.assertEqual(said, "Closed a 0.09 mm interference between 'post' and 'base' to bond them")

    def test_a_corner_sunk_on_every_axis_is_refused_as_an_overlap(self):
        step = _write_assembly(self.tmp, corner_block=0.25, name="corner")
        (error,) = self._not_solved(step, _pushed(step, "block", 19.75, mesh=MESH)).findings
        self.assertEqual(error["type"], "not_connected")
        self.assertEqual(
            error["summary"],
            "'block' isn't connected to anything that is held: it overlaps 'base' by 0.0156 mm³ instead of touching it, "
            "so it isn't bonded to it; fix the geometry or move them apart",
        )

    def test_parts_the_glue_would_fuse_are_named_in_a_study_error(self):
        from cadgen._internal.fea.assembly import Contact, list_parts
        from cadgen._internal.fea.mesh import mesh_assembly
        from cadgen._internal.fea.document import read_document

        scene = read_document(_write_assembly(self.tmp, corner_block=0.25, name="corner-forced"))
        refs = _refs_of(list_parts(scene))
        # Bonded by hand, as the old 2 V / A estimate did: gluing fuses the corner into one solid.
        forced = Contact(a=refs["block"], b=refs["base"], area_mm2=0.19, gap_mm=0.0, interference_mm=0.083)
        with self.assertRaisesRegex(ValueError, r"'base' and 'block' share a solid after gluing: they overlap"):
            mesh_assembly(scene, [refs["base"], refs["block"]], [forced], TOLERANCE, 4.0)

    def _not_solved(self, step, study):
        from unittest import mock

        with mock.patch("cadgen._internal.fea.solve.solve_linear_static", side_effect=AssertionError("solved")):
            result = solve(step, self.tmp / "none.glb", study)
        self.assertFalse(result.ok)
        self.assertIsNone(result.glb)
        self.assertFalse((self.tmp / "none.glb").exists())
        return result

    def test_a_floating_part_stops_the_study_before_the_solve(self):
        step = _write_assembly(self.tmp, far_block=20.0, name="floating")
        result = self._not_solved(step, _pushed(step, "post", 40.0))
        (finding,) = result.findings
        self.assertEqual((finding["severity"], finding["type"]), ("error", "not_connected"))
        self.assertEqual(
            finding["summary"], "'block' isn't connected to anything that is held: nearest part 'base' is 20 mm away"
        )
        self.assertEqual(finding["items"][0]["ref"], _scene(step)[1]["block"])
        self.assertIn("error: 'block' isn't connected", result.human_lines()[1])

    def _with_sunk_block(self, held_block: bool, **extra):
        step = _write_assembly(self.tmp, overlap_block=True, name=f"sunk{held_block}")
        study = _pushed(step, "post", 40.0, mesh=MESH, **extra)
        if held_block:
            scene, refs = _scene(step)
            study["fixtures"][0]["faces"].append(_face_at(scene, refs["block"], 0.0))
        return step, study

    def test_overlapping_parts_are_not_bonded_and_the_study_suggests_fixing_them(self):
        step, study = self._with_sunk_block(held_block=True)
        result = solve(step, self.tmp / "sunk.glb", study)
        (finding,) = [f for f in result.findings if f["type"] == "overlapping_parts"]
        self.assertEqual(finding["severity"], "warning")
        self.assertEqual(
            finding["summary"],
            "'block' and 'base' overlap by 100 mm³: real parts can't, so the model may be wrong; fix the geometry or mark them free",
        )
        written = reported(result)
        self.assertEqual([c["between"] for c in written["connections"]], [["post", "base"]])
        self.assertEqual([o["between"] for o in written["overlaps"]], [["block", "base"]])

    def test_marking_an_overlapping_pair_free_silences_the_suggestion(self):
        step, study = self._with_sunk_block(held_block=True, connections=[{"between": ["block", "base"], "type": "free"}])
        result = solve(step, self.tmp / "sunk-free.glb", study)
        self.assertNotIn("overlapping_parts", self._types(result))

    def test_an_overlap_cannot_be_bonded(self):
        step, study = self._with_sunk_block(held_block=True, connections=[{"between": ["block", "base"], "type": "bonded"}])
        with self.assertRaisesRegex(ValueError, r"overlap by 100 mm³, so they can't be bonded"):
            solve(step, self.tmp / "sunk-bonded.glb", study)

    def test_a_part_an_overlap_leaves_unheld_says_so(self):
        result = self._not_solved(*self._with_sunk_block(held_block=False))
        (finding,) = result.findings
        self.assertEqual(finding["type"], "not_connected")
        self.assertEqual(
            finding["summary"],
            "'block' isn't connected to anything that is held: it overlaps 'base' by 100 mm³ instead of touching it, "
            "so it isn't bonded to it; fix the geometry or move them apart",
        )

    def test_a_part_set_free_of_the_only_held_part_is_not_connected(self):
        study = self.study({"base": "6061", "post": "steel"}, connections=[{"between": ["post", "base"], "type": "free"}])
        result = self._not_solved(self.step, study)
        (finding,) = result.findings
        self.assertEqual(finding["type"], "not_connected")
        self.assertEqual(
            finding["summary"], "'post' isn't connected to anything that is held: it touches 'base' but isn't bonded to it"
        )

    def test_a_fixture_or_load_on_a_face_wholly_a_joint_is_a_study_error(self):
        joint = _face_at(self.scene, self.refs["post"], 10.0)
        study = self.study(None, loads=[{"faces": [joint], "type": "force", "vector_N": [0, 0, -1]}])
        with self.assertRaisesRegex(ValueError, rf"{joint} is where 'post' is bonded to 'base'"):
            solve(self.step, self.tmp / "joint.glb", study)

    def test_a_face_partly_covered_by_a_joint_loads_its_exposed_area(self):
        study = self.study(None, loads=[{"faces": [_face_at(self.scene, self.refs["base"], 10.0)], "type": "force", "vector_N": [0, 0, -100]}])
        result = solve(self.step, self.tmp / "exposed.glb", study)
        self.assertEqual(result.summary["applied_force_N"], [0.0, 0.0, -100.0])
        self.assertAlmostEqual(result.summary["reaction_force_N"][2], 100.0, delta=0.1)

    def test_the_parts_the_study_names_must_exist(self):
        with self.assertRaisesRegex(ValueError, r"parts\['lid'\]: no part named 'lid'; the parts are 'base', 'post'"):
            solve(self.step, self.tmp / "lid.glb", self.study({"lid": "steel"}))
        far = _write_assembly(self.tmp, far_block=20.0, name="far")
        with self.assertRaisesRegex(ValueError, "don't touch within 0.1 mm"):
            solve(far, self.tmp / "far.glb", self.study(None, connections=[{"between": ["block", "base"], "type": "bonded"}]))

    def _two_posts(self, name: str, right_x: float) -> Path:
        """Posts 'left' at x = 0 and 'right' at ``right_x`` side by side on the base: both bonded to it."""
        return _export(self.tmp / f"{name}.step", _box("base", (0, 0, 0), (40, 20, 10)),
                       _box("left", (0, 5, 10), (10, 10, 30)), _box("right", (right_x, 5, 10), (10, 10, 30)))

    def test_one_joint_cannot_be_freed_inside_a_bonded_group(self):
        step = self._two_posts("two-posts", 10)
        study = _pushed(step, "right", 40.0, 100, connections=[{"between": ["left", "right"], "type": "free"}])
        with self.assertRaisesRegex(ValueError, "'left' and 'right' are also joined through other bonded parts"):
            solve(step, self.tmp / "two.glb", study)

    def test_a_free_joint_that_splits_the_assembly_glues_each_group_apart(self):
        step = _write_assembly(self.tmp, cap=True, name="capped")
        scene, refs = _scene(step)
        study = {
            "material": AL6061_NUMBERS,
            "parts": {name: {"material": AL6061_NUMBERS} for name in ("base", "post", "cap")},
            "fixtures": [
                {"faces": [_face_at(scene, refs["base"], 0.0)]},
                {"faces": [_face_at(scene, refs["cap"], 45.0)]},
            ],
            "loads": [{"faces": [_face_where(scene, refs["post"], 0, 25.0)], "type": "force", "vector_N": [100, 0, 0]}],
            "connections": [{"between": ["cap", "post"], "type": "free"}],
            "mesh": MESH,
        }
        result = solve(step, self.tmp / "capped.glb", study)
        self.assertTrue(result.ok)
        self.assertNotIn("not_connected", self._types(result))
        self.assertEqual({c["between"][0]: c["type"] for c in reported(result)["connections"]}, {"post": "bonded", "cap": "free"})
        # The 100 N is held by the base alone: the cap carries nothing across the free joint.
        self.assertAlmostEqual(result.summary["reaction_force_N"][0], -100.0, delta=0.5)

    def test_two_parts_that_overlap_and_are_bonded_through_a_third_are_refused(self):
        step = self._two_posts("overlapping-posts", 8)  # right 2 mm into left
        study = _pushed(step, "right", 40.0, 100, mesh=MESH)
        for connections in ([], [{"between": ["left", "right"], "type": "free"}]):
            with self.assertRaisesRegex(ValueError, r"'left' and 'right' overlap by .* mm³ and are joined through 'base'"):
                solve(step, self.tmp / "overlapping.glb", {**study, "connections": connections})

    def test_gluing_refuses_a_solid_two_parts_both_became(self):
        from cadgen._internal.fea.assembly import glue

        from build123d import Align, Box

        one, same = Box(10, 10, 10, align=Align.MIN).wrapped, Box(10, 10, 10, align=Align.MIN).wrapped
        with self.assertRaisesRegex(RuntimeError, "parts 0 and 1 share a solid"):
            glue([one, same], [(0, 1, 0.0)], TOLERANCE)

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


@needs_fea
class RoundPartTest(unittest.TestCase):
    """A cylinder pin bonded onto a plate: the curved part's volume is what the mesher's linear tets undercount."""

    def test_a_round_pin_on_a_plate_is_meshed_and_solved(self):
        from build123d import Align, Cylinder, Pos

        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            pin = Pos(20, 20, 10) * Cylinder(5, 30, align=(Align.CENTER, Align.CENTER, Align.MIN))
            pin.label = "pin"
            step = _export(tmp / "pin.step", _box("plate", (0, 0, 0), (40, 40, 10)), pin)
            scene, refs = _scene(step)
            study = {
                "material": AL6061_NUMBERS,
                "fixtures": [{"faces": [_face_at(scene, refs["plate"], 0.0)]}],
                "loads": [{"faces": [_face_at(scene, refs["pin"], 40.0)], "type": "force", "vector_N": [100, 0, 0]}],
                "mesh": MESH,
            }
            result = solve(step, tmp / "pin.glb", study)
        self.assertTrue(result.ok)
        self.assertAlmostEqual(result.summary["reaction_force_N"][0], -100.0, delta=0.5)


if __name__ == "__main__":
    unittest.main()
