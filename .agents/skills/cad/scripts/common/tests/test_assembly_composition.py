import json
import shutil
import unittest
from pathlib import Path
from types import SimpleNamespace

from common.assembly_composition import build_linked_assembly_composition, build_native_assembly_composition
from common.assembly_spec import AssemblyInstanceSpec, AssemblyNodeSpec, AssemblySpec
from common.render import part_selector_manifest_path
from tests.cad_test_roots import IsolatedCadRoots


IDENTITY_TRANSFORM = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]


class NativeAssemblyCompositionTests(unittest.TestCase):
    def setUp(self) -> None:
        self._isolated_roots = IsolatedCadRoots(self, prefix="assembly-composition-")
        tempdir = self._isolated_roots.temporary_cad_directory(prefix="tmp-assembly-composition-")
        self._tempdir = tempdir
        self.temp_root = Path(tempdir.name)

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_root, ignore_errors=True)
        self._tempdir.cleanup()

    def _write_step(self, name: str) -> Path:
        step_path = self.temp_root / f"{name}.step"
        step_path.write_text("ISO-10303-21; END-ISO-10303-21;\n", encoding="utf-8")
        return step_path

    def _write_catalog_step(self, cad_ref: str) -> Path:
        step_path = self._isolated_roots.cad_root / f"{cad_ref}.step"
        step_path.parent.mkdir(parents=True, exist_ok=True)
        step_path.write_text("ISO-10303-21; END-ISO-10303-21;\n", encoding="utf-8")
        return step_path

    def _write_topology(self, rows: list[list[object]]) -> Path:
        topology_path = self.temp_root / ".assembly.step" / "topology.json"
        topology_path.parent.mkdir(parents=True, exist_ok=True)
        topology_path.write_text(
            json.dumps(
                {
                    "tables": {
                        "occurrenceColumns": [
                            "id",
                            "parentId",
                            "path",
                            "name",
                            "sourceName",
                            "transform",
                            "bbox",
                            "shapeCount",
                            "faceCount",
                            "edgeCount",
                            "vertexCount",
                        ]
                    },
                    "occurrences": rows,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return topology_path

    def _write_component_mesh(self, occurrence_id: str) -> Path:
        mesh_path = self.temp_root / ".assembly.step" / "components" / f"{occurrence_id}.glb"
        mesh_path.parent.mkdir(parents=True, exist_ok=True)
        mesh_path.write_bytes(b"glb component")
        return mesh_path

    def _write_source_topology(self, step_path: Path) -> None:
        topology_path = part_selector_manifest_path(step_path)
        topology_path.parent.mkdir(parents=True, exist_ok=True)
        topology_path.write_text(
            json.dumps(
                {
                    "stats": {
                        "shapeCount": 1,
                        "faceCount": 6,
                        "edgeCount": 12,
                        "vertexCount": 8,
                    }
                }
            )
            + "\n",
            encoding="utf-8",
        )

    def test_native_assembly_composition_embeds_component_mesh_assets(self) -> None:
        self._write_step("assembly")
        topology_path = self._write_topology(
            [
                ["o1", "", "1", "root", "root", IDENTITY_TRANSFORM, None, 0, 0, 0, 0],
                [
                    "o1.1",
                    "o1",
                    "1.1",
                    "sample_component",
                    "SAMPLE_COMPONENT",
                    IDENTITY_TRANSFORM,
                    {"min": [0, 0, 0], "max": [1, 1, 1]},
                    1,
                    6,
                    12,
                    8,
                ],
            ]
        )
        mesh_path = self._write_component_mesh("o1.1")

        payload = build_native_assembly_composition(
            cad_ref="imports/assembly",
            topology_path=topology_path,
            topology_manifest=json.loads(topology_path.read_text(encoding="utf-8")),
            component_mesh_paths={"o1.1": mesh_path},
        )

        self.assertEqual("native", payload["mode"])
        root = payload["root"]
        self.assertEqual("assembly", root["displayName"])
        self.assertEqual(1, len(root["children"]))
        part = root["children"][0]
        self.assertEqual("part", part["nodeType"])
        self.assertEqual(["o1.1"], root["leafPartIds"])
        self.assertEqual(
            {
                "shapes": 1,
                "faces": 6,
                "edges": 12,
                "vertices": 8,
            },
            part["topologyCounts"],
        )
        self.assertEqual("sample_component", part["displayName"])
        self.assertTrue(part["assets"]["glb"]["url"].startswith("components/"))
        self.assertIn("components/o1.1.glb?v=", part["assets"]["glb"]["url"])

    def test_native_assembly_composition_falls_back_to_single_component(self) -> None:
        self._write_step("assembly")
        topology_path = self._write_topology(
            [
                [
                    "o1",
                    "",
                    "1",
                    "vendor-assembly",
                    "vendor-assembly",
                    IDENTITY_TRANSFORM,
                    {"min": [0, 0, 0], "max": [2, 2, 2]},
                    1,
                    12,
                    24,
                    16,
                ],
            ]
        )
        mesh_path = self._write_component_mesh("o1")

        payload = build_native_assembly_composition(
            cad_ref="imports/assembly",
            topology_path=topology_path,
            topology_manifest=json.loads(topology_path.read_text(encoding="utf-8")),
            component_mesh_paths={"o1": mesh_path},
        )

        root = payload["root"]
        self.assertEqual(1, len(root["children"]))
        part = root["children"][0]
        self.assertEqual("o1", part["occurrenceId"])
        self.assertEqual("vendor-assembly", part["displayName"])

    def test_native_assembly_composition_prefers_source_name_for_anonymous_step_occurrence(self) -> None:
        self._write_step("assembly")
        topology_path = self._write_topology(
            [
                ["o1", "", "1", "assembly", "assembly", IDENTITY_TRANSFORM, None, 1, 6, 12, 8],
                [
                    "o1.1",
                    "o1",
                    "1.1",
                    "=>[0:1:1:54]",
                    "sample_component",
                    IDENTITY_TRANSFORM,
                    {"min": [0, 0, 0], "max": [1, 1, 1]},
                    1,
                    6,
                    12,
                    8,
                ],
            ]
        )
        mesh_path = self._write_component_mesh("o1.1")

        payload = build_native_assembly_composition(
            cad_ref="imports/assembly",
            topology_path=topology_path,
            topology_manifest=json.loads(topology_path.read_text(encoding="utf-8")),
            component_mesh_paths={"o1.1": mesh_path},
        )

        part = payload["root"]["children"][0]
        self.assertEqual("sample_component", part["displayName"])

    def test_linked_assembly_matches_build123d_component_source_names(self) -> None:
        leaf_step_path = self._write_catalog_step("parts/leaf")
        self._write_source_topology(leaf_step_path)
        topology_path = self._write_topology(
            [
                ["o1", "", "1", "assembly", "assembly", IDENTITY_TRANSFORM, None, 1, 6, 12, 8],
                [
                    "o1.1",
                    "o1",
                    "1.1",
                    "=>[0:1:1:2]",
                    "leaf",
                    IDENTITY_TRANSFORM,
                    {"min": [0, 0, 0], "max": [1, 1, 1]},
                    1,
                    6,
                    12,
                    8,
                ],
                [
                    "o1.1.1",
                    "o1.1",
                    "1.1.1",
                    "=>[0:1:1:3]",
                    "=>[0:1:1:3]",
                    IDENTITY_TRANSFORM,
                    {"min": [0, 0, 0], "max": [1, 1, 1]},
                    1,
                    6,
                    12,
                    8,
                ],
            ]
        )
        assembly_spec = AssemblySpec(
            assembly_path=self.temp_root / "assembly.py",
            instances=(
                AssemblyInstanceSpec(
                    instance_id="leaf",
                    source_path=leaf_step_path.resolve(),
                    path="leaf.step",
                    name="leaf",
                    transform=tuple(float(value) for value in IDENTITY_TRANSFORM),
                    use_source_colors=False,
                ),
            ),
        )

        payload = build_linked_assembly_composition(
            cad_ref="assemblies/assembly",
            topology_path=topology_path,
            topology_manifest=json.loads(topology_path.read_text(encoding="utf-8")),
            assembly_spec=assembly_spec,
            entries_by_step_path={
                leaf_step_path.resolve(): SimpleNamespace(
                    kind="part",
                    step_path=leaf_step_path,
                )
            },
            read_assembly_spec=lambda path: (_ for _ in ()).throw(AssertionError(path)),
        )

        child = payload["root"]["children"][0]
        self.assertEqual("linked", payload["mode"])
        self.assertEqual("o1.1", child["occurrenceId"])
        self.assertEqual("leaf", child["displayName"])
        self.assertFalse(child["useSourceColors"])
        self.assertEqual(
            {
                "shapes": 1,
                "faces": 6,
                "edges": 12,
                "vertices": 8,
            },
            child["topologyCounts"],
        )

    def test_linked_assembly_prefers_instance_name_over_source_step_stem(self) -> None:
        leaf_step_path = self._write_catalog_step("parts/leaf")
        self._write_source_topology(leaf_step_path)
        topology_path = self._write_topology(
            [
                ["o1", "", "1", "assembly", "assembly", IDENTITY_TRANSFORM, None, 1, 6, 12, 8],
                [
                    "o1.1",
                    "o1",
                    "1.1",
                    "=>[0:1:1:2]",
                    "custom_leaf_instance",
                    IDENTITY_TRANSFORM,
                    {"min": [0, 0, 0], "max": [1, 1, 1]},
                    1,
                    6,
                    12,
                    8,
                ],
            ]
        )
        assembly_spec = AssemblySpec(
            assembly_path=self.temp_root / "assembly.py",
            instances=(
                AssemblyInstanceSpec(
                    instance_id="custom_leaf_instance",
                    source_path=leaf_step_path.resolve(),
                    path="custom_leaf_instance.step",
                    name="custom_leaf_instance",
                    transform=tuple(float(value) for value in IDENTITY_TRANSFORM),
                    use_source_colors=False,
                ),
            ),
        )

        payload = build_linked_assembly_composition(
            cad_ref="assemblies/assembly",
            topology_path=topology_path,
            topology_manifest=json.loads(topology_path.read_text(encoding="utf-8")),
            assembly_spec=assembly_spec,
            entries_by_step_path={
                leaf_step_path.resolve(): SimpleNamespace(
                    kind="part",
                    step_path=leaf_step_path,
                )
            },
            read_assembly_spec=lambda path: (_ for _ in ()).throw(AssertionError(path)),
        )

        child = payload["root"]["children"][0]
        self.assertEqual("custom_leaf_instance", child["displayName"])

    def test_linked_generated_subassembly_expands_to_descendant_leaf_nodes(self) -> None:
        module_step_path = self._write_catalog_step("assemblies/module")
        module_source_path = module_step_path.with_suffix(".py")
        module_source_path.write_text("def gen_step():\n    return {'instances': [], 'step_output': 'module.step'}\n", encoding="utf-8")
        leaf_step_path = self._write_catalog_step("parts/leaf")
        self._write_source_topology(leaf_step_path)
        topology_path = self._write_topology(
            [
                ["o1", "", "1", "assembly", "assembly", IDENTITY_TRANSFORM, None, 1, 6, 12, 8],
                ["o1.1", "o1", "1.1", "module", "module", IDENTITY_TRANSFORM, None, 1, 6, 12, 8],
                [
                    "o1.1.1",
                    "o1.1",
                    "1.1.1",
                    "=>[0:1:1:3]",
                    "module__leaf",
                    IDENTITY_TRANSFORM,
                    {"min": [0, 0, 0], "max": [1, 1, 1]},
                    1,
                    6,
                    12,
                    8,
                ],
            ]
        )
        assembly_spec = AssemblySpec(
            assembly_path=self.temp_root / "assembly.py",
            instances=(),
            children=(
                AssemblyNodeSpec(
                    instance_id="module",
                    name="module",
                    source_path=module_step_path.resolve(),
                    path="module.step",
                    transform=tuple(float(value) for value in IDENTITY_TRANSFORM),
                ),
            ),
        )
        module_spec = AssemblySpec(
            assembly_path=module_source_path,
            instances=(
                AssemblyInstanceSpec(
                    instance_id="leaf",
                    source_path=leaf_step_path.resolve(),
                    path="leaf.step",
                    name="leaf",
                    transform=tuple(float(value) for value in IDENTITY_TRANSFORM),
                ),
            ),
        )

        payload = build_linked_assembly_composition(
            cad_ref="assemblies/assembly",
            topology_path=topology_path,
            topology_manifest=json.loads(topology_path.read_text(encoding="utf-8")),
            assembly_spec=assembly_spec,
            entries_by_step_path={
                module_step_path.resolve(): SimpleNamespace(
                    kind="assembly",
                    step_path=module_step_path,
                    source_path=module_source_path,
                    script_path=module_source_path,
                ),
                leaf_step_path.resolve(): SimpleNamespace(
                    kind="part",
                    step_path=leaf_step_path,
                ),
            },
            read_assembly_spec=lambda path: module_spec,
        )

        module = payload["root"]["children"][0]
        leaf = module["children"][0]
        self.assertEqual("assembly", module["nodeType"])
        self.assertEqual("o1.1", module["occurrenceId"])
        self.assertEqual(["o1.1.1"], module["leafPartIds"])
        self.assertEqual("part", leaf["nodeType"])
        self.assertEqual("o1.1.1", leaf["occurrenceId"])

    def test_linked_native_subassembly_uses_target_occurrence_ids_for_descendants(self) -> None:
        source_step_path = self._write_catalog_step("imports/vendor")
        source_topology_path = part_selector_manifest_path(source_step_path)
        source_topology_path.parent.mkdir(parents=True, exist_ok=True)
        source_topology_path.write_text(
            json.dumps(
                {
                    "assembly": {
                        "root": {
                            "id": "o9",
                            "occurrenceId": "o9",
                            "nodeType": "assembly",
                            "children": [
                                {
                                    "id": "o9.3",
                                    "occurrenceId": "o9.3",
                                    "nodeType": "part",
                                    "displayName": "finger",
                                    "topologyCounts": {
                                        "shapes": 1,
                                        "faces": 6,
                                        "edges": 12,
                                        "vertices": 8,
                                    },
                                    "assets": {
                                        "glb": {
                                            "url": "components/o9.3.glb?v=abc",
                                            "hash": "abc",
                                        }
                                    },
                                    "children": [],
                                }
                            ],
                        }
                    }
                }
            )
            + "\n",
            encoding="utf-8",
        )
        topology_path = self._write_topology(
            [
                ["o1", "", "1", "assembly", "assembly", IDENTITY_TRANSFORM, None, 1, 6, 12, 8],
                ["o1.2", "o1", "1.2", "sample_module", "sample_module", IDENTITY_TRANSFORM, None, 1, 6, 12, 8],
                [
                    "o1.2.7",
                    "o1.2",
                    "1.2.7",
                    "finger",
                    "finger",
                    IDENTITY_TRANSFORM,
                    {"min": [0, 0, 0], "max": [1, 1, 1]},
                    1,
                    6,
                    12,
                    8,
                ],
            ]
        )
        assembly_spec = AssemblySpec(
            assembly_path=self.temp_root / "assembly.py",
            instances=(
                AssemblyInstanceSpec(
                    instance_id="sample_module",
                    source_path=source_step_path.resolve(),
                    path="vendor.step",
                    name="sample_module",
                    transform=tuple(float(value) for value in IDENTITY_TRANSFORM),
                ),
            ),
        )

        payload = build_linked_assembly_composition(
            cad_ref="assemblies/assembly",
            topology_path=topology_path,
            topology_manifest=json.loads(topology_path.read_text(encoding="utf-8")),
            assembly_spec=assembly_spec,
            entries_by_step_path={
                source_step_path.resolve(): SimpleNamespace(
                    kind="part",
                    step_path=source_step_path,
                )
            },
            read_assembly_spec=lambda path: (_ for _ in ()).throw(AssertionError(path)),
        )

        sample_module = payload["root"]["children"][0]
        finger = sample_module["children"][0]
        self.assertEqual("assembly", sample_module["nodeType"])
        self.assertEqual("o1.2", sample_module["occurrenceId"])
        self.assertEqual(["o1.2.7"], sample_module["leafPartIds"])
        self.assertEqual("o1.2.7", finger["occurrenceId"])
        self.assertIn("components/o9.3.glb?v=abc", finger["assets"]["glb"]["url"])

    def test_linked_native_subassembly_handles_extra_target_wrapper(self) -> None:
        source_step_path = self._write_catalog_step("imports/vendor")
        source_topology_path = part_selector_manifest_path(source_step_path)
        source_topology_path.parent.mkdir(parents=True, exist_ok=True)
        source_topology_path.write_text(
            json.dumps(
                {
                    "assembly": {
                        "root": {
                            "id": "o9",
                            "occurrenceId": "o9",
                            "nodeType": "assembly",
                            "children": [
                                {
                                    "id": "o9.1",
                                    "occurrenceId": "o9.1",
                                    "nodeType": "part",
                                    "displayName": "finger_a",
                                    "topologyCounts": {
                                        "shapes": 1,
                                        "faces": 6,
                                        "edges": 12,
                                        "vertices": 8,
                                    },
                                    "assets": {
                                        "glb": {
                                            "url": "components/o9.1.glb?v=aaa",
                                            "hash": "aaa",
                                        }
                                    },
                                    "children": [],
                                },
                                {
                                    "id": "o9.2",
                                    "occurrenceId": "o9.2",
                                    "nodeType": "part",
                                    "displayName": "finger_b",
                                    "topologyCounts": {
                                        "shapes": 1,
                                        "faces": 6,
                                        "edges": 12,
                                        "vertices": 8,
                                    },
                                    "assets": {
                                        "glb": {
                                            "url": "components/o9.2.glb?v=bbb",
                                            "hash": "bbb",
                                        }
                                    },
                                    "children": [],
                                },
                            ],
                        }
                    }
                }
            )
            + "\n",
            encoding="utf-8",
        )
        topology_path = self._write_topology(
            [
                ["o1", "", "1", "assembly", "assembly", IDENTITY_TRANSFORM, None, 2, 12, 24, 16],
                ["o1.2", "o1", "1.2", "sample_module", "sample_module", IDENTITY_TRANSFORM, None, 2, 12, 24, 16],
                ["o1.2.1", "o1.2", "1.2.1", "wrapper", "wrapper", IDENTITY_TRANSFORM, None, 2, 12, 24, 16],
                [
                    "o1.2.1.1",
                    "o1.2.1",
                    "1.2.1.1",
                    "finger_a",
                    "finger_a",
                    IDENTITY_TRANSFORM,
                    {"min": [0, 0, 0], "max": [1, 1, 1]},
                    1,
                    6,
                    12,
                    8,
                ],
                [
                    "o1.2.1.2",
                    "o1.2.1",
                    "1.2.1.2",
                    "finger_b",
                    "finger_b",
                    IDENTITY_TRANSFORM,
                    {"min": [1, 0, 0], "max": [2, 1, 1]},
                    1,
                    6,
                    12,
                    8,
                ],
            ]
        )
        assembly_spec = AssemblySpec(
            assembly_path=self.temp_root / "assembly.py",
            instances=(
                AssemblyInstanceSpec(
                    instance_id="sample_module",
                    source_path=source_step_path.resolve(),
                    path="vendor.step",
                    name="sample_module",
                    transform=tuple(float(value) for value in IDENTITY_TRANSFORM),
                ),
            ),
        )

        payload = build_linked_assembly_composition(
            cad_ref="assemblies/assembly",
            topology_path=topology_path,
            topology_manifest=json.loads(topology_path.read_text(encoding="utf-8")),
            assembly_spec=assembly_spec,
            entries_by_step_path={
                source_step_path.resolve(): SimpleNamespace(
                    kind="part",
                    step_path=source_step_path,
                )
            },
            read_assembly_spec=lambda path: (_ for _ in ()).throw(AssertionError(path)),
        )

        wrapper = payload["root"]["children"][0]["children"][0]
        leaf_a, leaf_b = wrapper["children"]
        self.assertEqual("assembly", wrapper["nodeType"])
        self.assertEqual("o1.2.1", wrapper["occurrenceId"])
        self.assertEqual("o1.2.1.1", leaf_a["occurrenceId"])
        self.assertEqual("o1.2.1.2", leaf_b["occurrenceId"])
        self.assertIn("components/o9.1.glb?v=aaa", leaf_a["assets"]["glb"]["url"])
        self.assertIn("components/o9.2.glb?v=bbb", leaf_b["assets"]["glb"]["url"])

    def test_linked_native_subassembly_renders_target_wrapper_for_wrapped_source_part(self) -> None:
        source_step_path = self._write_catalog_step("imports/vendor")
        source_topology_path = part_selector_manifest_path(source_step_path)
        source_topology_path.parent.mkdir(parents=True, exist_ok=True)
        source_topology_path.write_text(
            json.dumps(
                {
                    "assembly": {
                        "root": {
                            "id": "o9",
                            "occurrenceId": "o9",
                            "nodeType": "assembly",
                            "children": [
                                {
                                    "id": "o9.1",
                                    "occurrenceId": "o9.1",
                                    "nodeType": "part",
                                    "displayName": "compound_part",
                                    "topologyCounts": {
                                        "shapes": 2,
                                        "faces": 10,
                                        "edges": 20,
                                        "vertices": 12,
                                    },
                                    "assets": {
                                        "glb": {
                                            "url": "components/o9.1.glb?v=wrapped",
                                            "hash": "wrapped",
                                        }
                                    },
                                    "children": [],
                                }
                            ],
                        }
                    }
                }
            )
            + "\n",
            encoding="utf-8",
        )
        topology_path = self._write_topology(
            [
                ["o1", "", "1", "assembly", "assembly", IDENTITY_TRANSFORM, None, 2, 10, 20, 12],
                ["o1.2", "o1", "1.2", "sample_module", "sample_module", IDENTITY_TRANSFORM, None, 2, 10, 20, 12],
                ["o1.2.1", "o1.2", "1.2.1", "compound_part", "compound_part", IDENTITY_TRANSFORM, None, 2, 10, 20, 12],
                [
                    "o1.2.1.1",
                    "o1.2.1",
                    "1.2.1.1",
                    "subshape_a",
                    "subshape_a",
                    IDENTITY_TRANSFORM,
                    {"min": [0, 0, 0], "max": [1, 1, 1]},
                    1,
                    5,
                    10,
                    6,
                ],
                [
                    "o1.2.1.2",
                    "o1.2.1",
                    "1.2.1.2",
                    "subshape_b",
                    "subshape_b",
                    IDENTITY_TRANSFORM,
                    {"min": [1, 0, 0], "max": [2, 1, 1]},
                    1,
                    5,
                    10,
                    6,
                ],
            ]
        )
        assembly_spec = AssemblySpec(
            assembly_path=self.temp_root / "assembly.py",
            instances=(
                AssemblyInstanceSpec(
                    instance_id="sample_module",
                    source_path=source_step_path.resolve(),
                    path="vendor.step",
                    name="sample_module",
                    transform=tuple(float(value) for value in IDENTITY_TRANSFORM),
                ),
            ),
        )

        payload = build_linked_assembly_composition(
            cad_ref="assemblies/assembly",
            topology_path=topology_path,
            topology_manifest=json.loads(topology_path.read_text(encoding="utf-8")),
            assembly_spec=assembly_spec,
            entries_by_step_path={
                source_step_path.resolve(): SimpleNamespace(
                    kind="part",
                    step_path=source_step_path,
                )
            },
            read_assembly_spec=lambda path: (_ for _ in ()).throw(AssertionError(path)),
        )

        rendered_part = payload["root"]["children"][0]["children"][0]
        self.assertEqual("part", rendered_part["nodeType"])
        self.assertEqual("o1.2.1", rendered_part["occurrenceId"])
        self.assertEqual(["o1.2.1"], rendered_part["leafPartIds"])
        self.assertEqual([], rendered_part["children"])
        self.assertIn("components/o9.1.glb?v=wrapped", rendered_part["assets"]["glb"]["url"])


if __name__ == "__main__":
    unittest.main()
