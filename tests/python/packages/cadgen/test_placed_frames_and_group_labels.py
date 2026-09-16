"""One frame, one naming scheme: what `inspect refs` and `inspect measure` report about a
placed occurrence, and what a subassembly answers to.

Two tom-cad FEEDBACK findings, both of which produced a confident wrong answer rather than an
error:

* issue 2 -- an arc's `bounds` and `detail.center` were world-positioned while
  `detail.params.center` stayed in the component's own coordinates. `measure` reads the
  analytic centre for a circular edge, so measuring an arc against a line on the same part
  reported a 37 mm separation along an axis where they meet, and a 501 mm distance.
  ``assembly_lookup._POINT_PARAM_KEYS`` knew the spelling `origin` (plane, cylinder, cone,
  line) and not `center` (circle, ellipse, sphere, torus), so exactly the analytic types that
  spell their point `center` were left behind.
* issue 5 -- `#camera_assembly` did not resolve although `#o1.8` named the same subassembly
  and resolved its leaves, and a kinematics mate fastened to that very label. The label index
  was built from the occurrence rows, which are LEAVES; the group names sit in
  ``SelectorIndex.group_nodes``, which nothing fed to it.

The fixture is built here in a temp dir with its own store. `models/` is a manual-validation
corpus, not a test input.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from build123d import Box, Compound, Cylinder, Pos, Rot  # noqa: E402

from cadgen import analysis, assembly_lookup, lookup  # noqa: E402
from cadgen._internal import component_package  # noqa: E402
from cadgen.cli.step_inspect import inspect as refs_inspect  # noqa: E402
from tests.python.support.store_fixtures import build_view  # noqa: E402


GROUP_LABEL = "camera_assembly"
GROUP_ID = "o1.1"


def _demo_compound() -> Compound:
    """A labelled subassembly, placed away from the origin AND rotated.

    Both halves matter. The translation is what separates component-local from world, and the
    rotation is what makes a dropped or transposed placement visible: under translation alone a
    cylinder's axis stays put whatever the transform code does.

    The cylinder is the point of the part: a box has only planes and lines, whose analytic
    params spell their point `origin`, which was always placed. An arc spells it `center`.
    """
    pin = Cylinder(radius=3, height=10)
    pin.label = "camera_pin"
    plate = Pos(0, 0, 20) * Box(20, 20, 2)
    plate.label = "camera_plate"
    group = Pos(100, 50, 7) * Rot(0, 90, 0) * Compound(children=[pin, plate])
    group.label = GROUP_LABEL
    other = Pos(-60, 0, 0) * Box(5, 5, 5)
    other.label = "base_block"
    assembly = Compound(children=[group, other])
    assembly.label = "demo"
    return assembly


class _FakeArtifact:
    """Stands in for StepTopologyArtifact: composition reads `kind` and `artifact_path` only."""

    def __init__(self, kind: str, artifact_path: Path) -> None:
        self.kind = kind
        self.artifact_path = artifact_path


class PlacedPackageTestCase(unittest.TestCase):
    # One build for the class: every test only READS the index and the descriptor
    # (the same setUpModule shape as test_assembly_selector_refs). The store is
    # content-addressed and shared unless told otherwise; the fixture gets one of
    # its own for the class, and whatever the runner set is RESTORED, never popped.
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls._tmp = tempfile.TemporaryDirectory(prefix="placed-frames-")
        cls.root = Path(cls._tmp.name)
        cache_dir = cls.root / "cadgen-cache"
        cache_dir.mkdir()
        cls._previous_cache = os.environ.get("CADGEN_CACHE_DIR")
        os.environ["CADGEN_CACHE_DIR"] = str(cache_dir)
        cls.package_dir = cls.root / "view"
        build_view(_demo_compound(), package_dir=cls.package_dir, root_name="demo")
        descriptor = component_package.read_package_descriptor(cls.package_dir)
        if not isinstance(descriptor, dict):
            raise RuntimeError("fixture package has no descriptor")
        cls.descriptor = descriptor
        cls.index = assembly_lookup.index_with_assembly_occurrences(
            lookup.build_selector_index(
                {
                    "stats": {"occurrenceCount": 1},
                    "tables": {"occurrenceColumns": ["id", "name", "bbox"]},
                    "occurrences": [["o1", "demo.step", None]],
                }
            ),
            _FakeArtifact(kind="assembly", artifact_path=cls.package_dir),
        )

    @classmethod
    def tearDownClass(cls) -> None:
        if cls._previous_cache is None:
            os.environ.pop("CADGEN_CACHE_DIR", None)
        else:
            os.environ["CADGEN_CACHE_DIR"] = cls._previous_cache
        cls._tmp.cleanup()
        super().tearDownClass()

    def _circle_edge(self) -> dict:
        for row in self.index.edges:
            if str(row.get("curveType")) == "circle" and str(row.get("occurrenceId", "")).count("."):
                return row
        self.fail("fixture produced no placed circular edge")

    def _context(self) -> refs_inspect.EntryContext:
        return refs_inspect.EntryContext(
            cad_path="demo",
            kind="assembly",
            source_path=self.package_dir,
            step_path=None,
            manifest=dict(self.index.manifest),
            selector_index=self.index,
        )


class AnalyticParamsAreWorldPlacedTest(PlacedPackageTestCase):
    def test_an_arcs_analytic_centre_sits_inside_its_own_bounds(self) -> None:
        """The reported bug, as an invariant that needs no reference numbers: a circle's centre
        is on its own axis, so it lies within the box the same row reports. The shipped payload
        put the centre ~500 mm outside it."""
        row = self._circle_edge()
        centre = row["params"]["center"]
        bbox = row["bbox"]
        for axis in range(3):
            self.assertGreaterEqual(centre[axis], bbox["min"][axis] - 1e-6)
            self.assertLessEqual(centre[axis], bbox["max"][axis] + 1e-6)

    def test_the_analytic_centre_agrees_with_the_placed_row_centre(self) -> None:
        """`center` (placed) and `params.center` (not) described the same circle in two frames."""
        row = self._circle_edge()
        for placed, analytic in zip(row["center"], row["params"]["center"]):
            self.assertAlmostEqual(placed, analytic, places=6)

    def test_the_centre_moved_with_the_occurrence(self) -> None:
        """Guards the fix from the other side: a params dict left untouched would still pass the
        bounds check on an occurrence that happens to sit at the origin."""
        row = self._circle_edge()
        occurrence = self.index.occurrence_by_id[str(row["occurrenceId"])]
        translation = [occurrence["transform"][index] for index in (3, 7, 11)]
        self.assertGreater(
            max(abs(value) for value in translation), 1.0, "fixture occurrence is not displaced"
        )
        self.assertGreater(
            max(abs(value) for value in row["params"]["center"]),
            1.0,
            "params.center is still component-local",
        )

    def test_measure_reads_the_same_frame_it_reports(self) -> None:
        """What `measure --axis` actually consumes. `positioning_facts_for_row` hands a circular
        edge its analytic centre, and `positioning_point` prefers that over the bbox -- so a
        local `params.center` reached the subtraction while the other target's did not."""
        row = self._circle_edge()
        facts = analysis.positioning_facts_for_row("edge", row, self.index)
        point = analysis.positioning_point(facts)
        self.assertIsNotNone(point)
        bbox = row["bbox"]
        for axis in range(3):
            self.assertGreaterEqual(point[axis], bbox["min"][axis] - 1e-6)
            self.assertLessEqual(point[axis], bbox["max"][axis] + 1e-6)

    def test_a_radius_is_a_length_and_does_not_move(self) -> None:
        """The other half of the key-by-key rule: placing a scalar would be just as wrong."""
        self.assertAlmostEqual(3.0, float(self._circle_edge()["params"]["radius"]), places=6)

    def test_a_placed_axis_stays_a_unit_vector(self) -> None:
        """A direction that picks up the occurrence's offset stops being one."""
        axis = self._circle_edge()["params"]["axis"]
        self.assertAlmostEqual(1.0, sum(value * value for value in axis) ** 0.5, places=6)


class GroupLabelsResolveTest(PlacedPackageTestCase):
    def test_the_group_carries_a_label_alias(self) -> None:
        self.assertEqual(
            GROUP_ID, self.index.label_aliases["aliases"].get(GROUP_LABEL),
            "a subassembly's authored label is not in the refs label index",
        )

    def test_a_group_label_canonicalizes_to_the_group_id(self) -> None:
        self.assertEqual(GROUP_ID, lookup.canonicalize_selector(f"#{GROUP_LABEL}", self.index))

    def test_a_group_label_expands_to_exactly_what_its_id_expands_to(self) -> None:
        """The reported asymmetry: `#o1.8` answered with its leaves and `#camera_assembly` did
        not resolve at all. They are the same node, so they are the same answer."""
        context = self._context()
        by_label = refs_inspect._group_expanded_selectors(f"#{GROUP_LABEL}", context)
        by_id = refs_inspect._group_expanded_selectors(f"#{GROUP_ID}", context)
        self.assertEqual(by_id, by_label)
        self.assertGreater(len(by_label), 1, "the fixture group holds more than one leaf")

    def test_refs_reports_the_groups_leaves_for_a_label(self) -> None:
        result = refs_inspect.inspect_cad_refs(
            "demo", f"#{GROUP_LABEL}", detail=True, context_provider=lambda *_: self._context()
        )
        self.assertEqual([], result["errors"], "a group label must resolve")
        selections = result["tokens"][0]["selections"]
        self.assertTrue(selections)
        for selection in selections:
            self.assertEqual("resolved", selection["status"])
            self.assertEqual(GROUP_LABEL, selection.get("fromGroup"))

    def test_leaf_labels_still_resolve_to_their_own_occurrence(self) -> None:
        """Additive. Adding interior nodes must not renumber or displace the leaves."""
        aliases = self.index.label_aliases["aliases"]
        self.assertEqual("o1.1.1", aliases.get("camera_pin"))
        self.assertEqual("o1.1.2", aliases.get("camera_plate"))
        self.assertEqual("o1.2", aliases.get("base_block"))

    def test_an_entity_ref_under_a_group_label_is_not_treated_as_a_group(self) -> None:
        """`#camera_assembly.f3` names a face, and a group owns no geometry, so it must reach
        the ordinary resolver (and fail there) rather than silently expand to the subtree."""
        self.assertEqual(
            [f"#{GROUP_LABEL}.f3"],
            refs_inspect._group_expanded_selectors(f"#{GROUP_LABEL}.f3", self._context()),
        )


class GroupLabelAmbiguityTest(unittest.TestCase):
    """A group and a leaf may honestly share a name. The duplicate rule is what already covers
    that, and it must keep covering it once groups are indexed: numbered aliases, and the bare
    label refuses rather than picking one."""

    def test_a_group_and_a_leaf_sharing_a_name_become_numbered_aliases(self) -> None:
        from cadgen.label_refs import LabelResolutionError, build_label_aliases, resolve_label_selectors

        built = build_label_aliases(
            [{"id": "o1.3.1", "name": "gripper"}, {"id": "o1.3", "name": "gripper"}]
        )
        self.assertEqual({"gripper_1": "o1.3", "gripper_2": "o1.3.1"}, built["aliases"])
        with self.assertRaises(LabelResolutionError):
            resolve_label_selectors(["gripper"], built)


if __name__ == "__main__":
    unittest.main()
