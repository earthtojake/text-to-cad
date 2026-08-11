import json
import tempfile
import unittest
from pathlib import Path

import build123d
from build123d import Compound, Location

from cadgen.instances import compound_from_instances
from cadgen._internal.component_package import (
    build_package_from_compound as _RAW_BUILD_PACKAGE,
)


def _build_package(compound, **kwargs):
    """Drive the package writer holding its write lock, as every real producer does.

    _build_package() asserts the lock at the mutation boundary (see
    cadgen.coordination.require_write_lock) so a producer cannot be added that writes a
    package uncoordinated. These tests call the writer directly, so they take it too.
    """
    from cadgen.coordination.lock import exclusive
    from cadgen.coordination.paths import write_lock_path

    with exclusive(write_lock_path(kwargs["package_dir"])):
        return _RAW_BUILD_PACKAGE(compound, **kwargs)


def _labeled(shape, label):
    shape.label = label
    return shape


def _engine_prototype() -> Compound:
    bell = _labeled(build123d.Cylinder(radius=4, height=6), "bell")
    pump = _labeled(build123d.Box(3, 3, 5).moved(Location((6, 0, 0))), "pump")
    return Compound(obj=[bell, pump], children=[bell, pump], label="engine")


def _descriptor_summary(descriptor: dict) -> tuple[set, set, int]:
    occurrences = descriptor["occurrences"]
    names = {occ["name"] for occ in occurrences}
    cids = set(descriptor["components"].keys())
    return names, cids, len(occurrences)


class CompoundFromInstancesTests(unittest.TestCase):
    def _build(self, shape, tmp: Path, key: str) -> dict:
        package_dir = tmp / "__cadgen__" / "models" / key
        _build_package(
            shape,
            package_dir=package_dir,
            root_name=key,
            linear_deflection=0.5,
            angular_deflection=0.4,
        )
        return json.loads((package_dir / "assembly.json").read_text())

    def test_nested_instance_compound_matches_moved_composition(self) -> None:
        proto = _engine_prototype()
        placements = [
            (Location((0, 0, 0), (0, 0, 0)), "engine_center"),
            (Location((20, 0, 0), (0, 0, 45)), "engine_outer"),
        ]
        cluster = compound_from_instances(
            "cluster", [(proto, loc, name) for loc, name in placements]
        )
        deck = _labeled(build123d.Box(40, 40, 2).moved(Location((0, 0, -4))), "deck")
        via_instances = Compound(obj=[deck, cluster], children=[deck, cluster], label="rig")

        proto_b = _engine_prototype()
        moved_children = []
        for loc, name in placements:
            inst = proto_b.moved(loc)
            inst.label = name
            moved_children.append(inst)
        deck_b = _labeled(build123d.Box(40, 40, 2).moved(Location((0, 0, -4))), "deck")
        cluster_b = Compound(obj=moved_children, children=moved_children, label="cluster")
        via_moved = Compound(obj=[deck_b, cluster_b], children=[deck_b, cluster_b], label="rig")

        with tempfile.TemporaryDirectory() as tmp:
            desc_a = self._build(via_instances, Path(tmp), "a.step.py")
            desc_b = self._build(via_moved, Path(tmp), "b.step.py")

        names_a, cids_a, count_a = _descriptor_summary(desc_a)
        names_b, cids_b, count_b = _descriptor_summary(desc_b)
        self.assertEqual(count_a, count_b)
        self.assertEqual(names_a, names_b)
        # NOTE: cid VALUES differ between the two compositions — .moved()'s
        # BRepBuilderAPI_Copy serializes to different BREP bytes than the
        # original geometry — but the dedup STRUCTURE must match: same number
        # of unique components, engines shared across instances either way.
        self.assertEqual(len(cids_a), len(cids_b))
        # engine inner-part labels survive through the occurrence tree
        self.assertIn("bell", names_a)
        self.assertIn("pump", names_a)
        # world transforms agree pairwise (sorted by name)
        by_name_a = {o["name"]: o["transform"] for o in desc_a["occurrences"]}
        by_name_b = {o["name"]: o["transform"] for o in desc_b["occurrences"]}
        _ = by_name_a, by_name_b  # duplicate names across instances; compare sorted transform sets
        transforms_a = sorted(tuple(round(v, 6) for v in o["transform"]) for o in desc_a["occurrences"])
        transforms_b = sorted(tuple(round(v, 6) for v in o["transform"]) for o in desc_b["occurrences"])
        self.assertEqual(transforms_a, transforms_b)

    def test_root_level_instance_compound_builds_package(self) -> None:
        proto = _engine_prototype()
        root = compound_from_instances(
            "cluster",
            [(proto, Location((0, 0, 0)), "e1"), (proto, Location((15, 0, 0)), "e2")],
        )
        with tempfile.TemporaryDirectory() as tmp:
            descriptor = self._build(root, Path(tmp), "root.step.py")
        names, cids, count = _descriptor_summary(descriptor)
        self.assertEqual(4, count)  # 2 instances x 2 leaf parts
        self.assertEqual(2, len(cids))  # bell + pump geometry, shared across instances
        tree_names = {c["name"] for c in descriptor["assembly"]["root"]["children"]}
        self.assertEqual({"e1", "e2"}, tree_names)

    def test_empty_instances_raise(self) -> None:
        with self.assertRaises(RuntimeError):
            compound_from_instances("empty", [])


if __name__ == "__main__":
    unittest.main()
