from __future__ import annotations

import json
import struct
import tempfile
import unittest
from pathlib import Path

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from build123d import Box, Compound, Pos

from cadgen._internal import component_package
from cadgen.coordination.lock import exclusive
from cadgen.coordination.paths import write_lock_path


def _build_package(compound, **kwargs):
    """Drive the package writer holding its write lock, as every real producer does.

    build_package_from_compound() asserts the lock at the mutation boundary (see
    require_write_lock) precisely so a producer cannot be added that writes a package
    uncoordinated -- which is the bug that made a cold `cad inspect` build invisible to
    the CAD Viewer. These unit tests call the writer directly, so they take the lock too.
    """
    with exclusive(write_lock_path(kwargs["package_dir"])):
        return component_package.build_package_from_compound(compound, **kwargs)


def _glb_json_chunk(glb_path: Path) -> dict:
    data = glb_path.read_bytes()
    json_len = struct.unpack("<I", data[12:16])[0]
    return json.loads(data[20 : 20 + json_len])


def _demo_compound() -> Compound:
    """A 3-occurrence assembly: two identical boxes (placed apart) + a distinct box.

    The two identical boxes share an unlocated TShape, so they content-address to one
    component; the distinct box is a second component -> 3 occurrences / 2 components.
    """
    box_a1 = (Pos(0, 0, 0) * Box(10, 10, 10))
    box_a1.label = "box_a_1"
    box_a2 = (Pos(50, 0, 0) * Box(10, 10, 10))
    box_a2.label = "box_a_2"
    box_b = (Pos(0, 50, 0) * Box(20, 5, 5))
    box_b.label = "box_b"
    return Compound(children=[box_a1, box_a2, box_b], label="demo")


class ComponentPackageTests(unittest.TestCase):
    def test_build_from_compound_dedups_and_self_describes(self) -> None:
        compound = _demo_compound()
        with tempfile.TemporaryDirectory() as tmp:
            package_dir = Path(tmp) / "__cadgen__" / "models" / "demo.step"
            stats = _build_package(
                compound, package_dir=package_dir, root_name="demo"
            )
            self.assertEqual(stats["occurrences"], 3)
            self.assertEqual(stats["unique_components"], 2)
            self.assertEqual(stats["components_built"], 2)
            self.assertEqual(stats["components_reused"], 0)

            descriptor = json.loads((package_dir / "assembly.json").read_text())
            self.assertEqual(descriptor["kind"], component_package.PACKAGE_KIND)
            self.assertEqual(
                descriptor["packageSchemaVersion"], component_package.PACKAGE_SCHEMA_VERSION
            )
            self.assertEqual(len(descriptor["occurrences"]), 3)
            self.assertEqual(len(descriptor["components"]), 2)

            # A lightweight geometry summary lets a whole-entry inspect read the
            # descriptor directly (no full topology extraction): a world bbox + counts.
            bbox = descriptor["bbox"]
            self.assertEqual(len(bbox["min"]), 3)
            self.assertEqual(len(bbox["max"]), 3)
            self.assertTrue(all(lo <= hi for lo, hi in zip(bbox["min"], bbox["max"])))
            self.assertEqual(descriptor["stats"]["occurrenceCount"], 3)
            self.assertEqual([o["id"] for o in descriptor["occurrences"]], ["o1.1", "o1.2", "o1.3"])
            # Each occurrence carries a 16-float row-major transform.
            for occurrence in descriptor["occurrences"]:
                self.assertEqual(len(occurrence["transform"]), 16)

            # The two identical boxes resolve to the SAME component cid.
            comp_by_occ = {o["name"]: o["component"] for o in descriptor["occurrences"]}
            self.assertEqual(comp_by_occ["box_a_1"], comp_by_occ["box_a_2"])
            self.assertNotEqual(comp_by_occ["box_a_1"], comp_by_occ["box_b"])

            # Component GLBs exist and embed local STEP topology (self-describing).
            for cid, entry in descriptor["components"].items():
                glb_path = package_dir / entry["glb"]
                self.assertTrue(glb_path.is_file(), f"missing component GLB {cid}")
                extensions = _glb_json_chunk(glb_path).get("extensions") or {}
                self.assertIn("STEP_topology", extensions, f"{cid} GLB lacks embedded topology")

    def test_rebuild_reuses_content_addressed_components(self) -> None:
        compound = _demo_compound()
        with tempfile.TemporaryDirectory() as tmp:
            package_dir = Path(tmp) / "__cadgen__" / "models" / "demo.step"
            _build_package(
                compound, package_dir=package_dir, root_name="demo"
            )
            # A second build over an unchanged compound reuses every component GLB.
            stats = _build_package(
                compound, package_dir=package_dir, root_name="demo"
            )
            self.assertEqual(stats["components_built"], 0)
            self.assertEqual(stats["components_reused"], 2)

    def test_force_rebuilds_all_components(self) -> None:
        compound = _demo_compound()
        with tempfile.TemporaryDirectory() as tmp:
            package_dir = Path(tmp) / "__cadgen__" / "models" / "demo.step"
            _build_package(
                compound, package_dir=package_dir, root_name="demo"
            )
            # force ignores the content-addressed cache (mesh/selector code changed,
            # not the geometry) and rebuilds every component.
            stats = _build_package(
                compound, package_dir=package_dir, root_name="demo", force=True
            )
            self.assertEqual(stats["components_built"], 2)
            self.assertEqual(stats["components_reused"], 0)

    def test_assembly_package_current_tracks_descriptor_and_components(self) -> None:
        compound = _demo_compound()
        with tempfile.TemporaryDirectory() as tmp:
            # render_package_dir derives the package path from a STEP path; emit the
            # package there so the freshness check sees a real descriptor + components.
            step_path = Path(tmp) / "demo.step"
            package_dir = component_package.render_package_dir(step_path)
            self.assertFalse(component_package.assembly_package_current(step_path))

            _build_package(
                compound, package_dir=package_dir, root_name="demo"
            )
            self.assertTrue(component_package.assembly_package_current(step_path))

            # Deleting a referenced component GLB invalidates the package.
            descriptor = json.loads((package_dir / "assembly.json").read_text())
            first = next(iter(descriptor["components"].values()))
            (package_dir / first["glb"]).unlink()
            self.assertFalse(component_package.assembly_package_current(step_path))

    def test_components_are_clean_and_byte_deterministic(self) -> None:
        from cadgen._internal.glb import read_step_topology_manifest_from_glb

        compound = _demo_compound()
        with tempfile.TemporaryDirectory() as tmp_a, tempfile.TemporaryDirectory() as tmp_b:
            pkg_a = Path(tmp_a) / ".demo.step.glb"
            pkg_b = Path(tmp_b) / ".demo.step.glb"
            provenance = {"schemaVersion": 2, "sourceKind": "python", "stepHash": "abc"}
            _build_package(
                compound, package_dir=pkg_a, root_name="demo", provenance=provenance
            )
            _build_package(
                compound, package_dir=pkg_b, root_name="demo", provenance=provenance, force=True
            )

            descriptor_a = json.loads((pkg_a / "assembly.json").read_text())
            cid, entry = next(iter(descriptor_a["components"].items()))
            glb = (pkg_a / entry["glb"]).resolve()
            # No source provenance leaks into the embedded component topology.
            manifest = read_step_topology_manifest_from_glb(glb) or {}
            for key in component_package.COMPONENT_PROVENANCE_KEYS:
                self.assertNotIn(key, manifest, f"{key} leaked into a clean component")
            self.assertNotIn("timingMs", manifest.get("stats", {}))

            # Same geometry -> byte-identical component GLB (content-addressable by file).
            glb_b = (pkg_b / json.loads((pkg_b / "assembly.json").read_text())["components"][cid]["glb"]).resolve()
            self.assertEqual(glb.read_bytes(), glb_b.read_bytes())

            # The model-level provenance lives on the descriptor instead.
            descriptor = json.loads((pkg_a / "assembly.json").read_text())
            self.assertEqual("python", descriptor.get("sourceKind"))
            self.assertEqual("abc", descriptor.get("stepHash"))


    def test_components_are_emitted_in_local_frame(self) -> None:
        """Every component GLB must be in its LOCAL frame (identity glTF node): world placement
        comes solely from the descriptor occurrence transform. If the node baked the placement,
        the renderer would double-place it, and a shared (deduped) component could only ever sit
        at its first occurrence's position. The two identical boxes here share one component but
        sit at different x, so that component MUST be local."""
        compound = _demo_compound()
        with tempfile.TemporaryDirectory() as tmp:
            package_dir = Path(tmp) / "__cadgen__" / "models" / "demo.step"
            _build_package(
                compound, package_dir=package_dir, root_name="demo"
            )
            descriptor = json.loads((package_dir / "assembly.json").read_text())

            for cid, entry in descriptor["components"].items():
                data = (package_dir / entry["glb"]).read_bytes()
                json_len = struct.unpack("<I", data[12:16])[0]
                gltf = json.loads(data[20 : 20 + json_len])
                for node in gltf.get("nodes", []):
                    matrix = node.get("matrix")
                    if matrix:
                        self.assertAlmostEqual(0.0, matrix[12], places=6, msg=f"{cid} node x-placed")
                        self.assertAlmostEqual(0.0, matrix[13], places=6, msg=f"{cid} node y-placed")
                        self.assertAlmostEqual(0.0, matrix[14], places=6, msg=f"{cid} node z-placed")
                    translation = node.get("translation")
                    if translation:
                        self.assertEqual([0.0, 0.0, 0.0], [float(v) for v in translation])

            # The two box_a occurrences share one component yet carry distinct placements: dedup
            # only works because the component is local and each occurrence transform places it.
            by_name = {o["name"]: o for o in descriptor["occurrences"]}
            self.assertEqual(by_name["box_a_1"]["component"], by_name["box_a_2"]["component"])
            self.assertNotEqual(by_name["box_a_1"]["transform"][3], by_name["box_a_2"]["transform"][3])


    def test_nested_subassembly_emits_hierarchy_and_leaf_occurrences(self) -> None:
        """A composed compound with a nested sub-assembly must emit LEAF occurrences for the
        sub-parts (with world transforms accumulated down the path) plus a nested
        ``assembly.root`` — so the viewer structure tree can drill into / select / isolate the
        sub-assembly's parts (parity with a monolithic STEP), not collapse it to one component."""
        from build123d import Box, Compound, Location, Pos

        loose = Pos(0, 0, 0) * Box(5, 5, 5)
        loose.label = "loose"
        sub_a = Pos(0, 0, 0) * Box(3, 3, 3)
        sub_a.label = "sub_a"
        sub_b = Pos(10, 0, 0) * Box(3, 3, 3)
        sub_b.label = "sub_b"
        sub = Compound(children=[sub_a, sub_b])
        sub.label = "subassembly"
        sub.location = Location((0, 0, 20))
        compound = Compound(children=[loose, sub])
        compound.label = "root"

        with tempfile.TemporaryDirectory() as tmp:
            package_dir = Path(tmp) / "__cadgen__" / "models" / "demo.step"
            _build_package(
                compound, package_dir=package_dir, root_name="demo"
            )
            descriptor = json.loads((package_dir / "assembly.json").read_text())

            # Occurrences are the LEAVES: loose (o1.1) + the sub-assembly's two parts (o1.2.1/.2).
            self.assertEqual(["o1.1", "o1.2.1", "o1.2.2"], [o["id"] for o in descriptor["occurrences"]])

            # The descriptor carries the nested hierarchy.
            root = descriptor["assembly"]["root"]
            self.assertEqual("assembly", root["nodeType"])
            self.assertEqual(2, len(root["children"]))
            sub_node = next(c for c in root["children"] if c["nodeType"] == "subassembly")
            self.assertEqual("subassembly", sub_node["name"])
            self.assertEqual(["o1.2.1", "o1.2.2"], [c["id"] for c in sub_node["children"]])
            self.assertEqual(["o1.2.1", "o1.2.2"], sub_node["leafPartIds"])

            by_name = {o["name"]: o for o in descriptor["occurrences"]}
            # Accumulated world transforms: the sub-assembly sits at z=20, so its parts inherit it.
            self.assertAlmostEqual(20.0, by_name["sub_a"]["transform"][11], places=3)
            self.assertAlmostEqual(10.0, by_name["sub_b"]["transform"][3], places=3)
            self.assertAlmostEqual(20.0, by_name["sub_b"]["transform"][11], places=3)


if __name__ == "__main__":
    unittest.main()
