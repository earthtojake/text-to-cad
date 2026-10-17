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
* issue 5 -- `#camera_assembly` did not resolve although the subassembly's own token named
  it and resolved its leaves, and a kinematics mate fastened to that very label. The label index
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
from tests.python.support.store_fixtures import build_view  # noqa: E402
from tests.python.support.tree_ids import leaf_id, node_id  # noqa: E402


GROUP_LABEL = "camera_assembly"


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
    """Stands in for StepArtifact: composition reads `kind` and `artifact_path` only."""

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
        # The group's token is read off the tree the build minted it in.
        cls.group_id = node_id(descriptor, GROUP_LABEL)
        cls.leaves = {str(row["id"]) for row in descriptor["occurrences"]}
        cls.index = assembly_lookup.index_with_assembly_occurrences(
            lookup.build_selector_index({"tables": {"occurrenceColumns": ["id", "name", "bbox"]}, "occurrences": []}),
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
            if str(row.get("curveType")) == "circle" and row.get("occurrenceId") in self.leaves:
                return row
        self.fail("fixture produced no placed circular edge")



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

    def test_an_axis_ref_reads_the_same_frame_it_reports(self) -> None:
        """What a mate's axis ref consumes. `positioning_facts_for_row` hands a circular edge
        its analytic centre, and the axis takes that as its origin
        (`kinematics_resolve._axis_from_ref`) -- so a local `params.center` would put the axis
        in the component's frame while the row's bounds are in the world's."""
        row = self._circle_edge()
        facts = analysis.positioning_facts_for_row("edge", row, self.index)
        point = facts.get("origin") or facts.get("center") or facts.get("point")
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
    def test_a_group_label_resolves_to_the_group(self) -> None:
        from cadgen.refs import resolve

        found = resolve(f"#{GROUP_LABEL}", lookup.index_space(self.index))
        self.assertEqual(self.group_id, found.occurrence,
                         "a subassembly's authored label does not name it in the refs index")
        self.assertEqual("occurrence", found.kind)

    def test_leaf_labels_still_resolve_to_their_own_occurrence(self) -> None:
        """Additive. Adding interior nodes must not renumber or displace the leaves."""
        from cadgen.refs import resolve

        space = lookup.index_space(self.index)
        for label in ("camera_pin", "camera_plate", "base_block"):
            self.assertEqual(leaf_id(self.descriptor, label), resolve(f"#{label}", space).occurrence, label)


class GroupLabelAmbiguityTest(unittest.TestCase):
    """A group and a leaf may honestly share a name. The duplicate rule is what already covers
    that, and it must keep covering it once groups are indexed: numbered aliases, and the bare
    label refuses rather than picking one."""

    def test_a_group_and_a_leaf_sharing_a_name_become_numbered_aliases(self) -> None:
        from cadgen.label_refs import LabelResolutionError
        from cadgen.refs import Space, resolve

        group, leaf = "o:" + "3" * 12, "o:" + "4" * 12
        # Names are taken in tree order, the group before the leaf beneath it.
        space = Space({group: [leaf], leaf: [leaf]}, {"gripper": [group, leaf]})
        self.assertEqual(group, resolve("#gripper_1", space).occurrence)
        self.assertEqual(leaf, resolve("#gripper_2", space).occurrence)
        with self.assertRaises(LabelResolutionError):
            resolve("#gripper", space)


if __name__ == "__main__":
    unittest.main()
