import json
import shutil
import struct
import unittest
from pathlib import Path
from types import SimpleNamespace

from cadpy_common.assembly_composition import build_linked_assembly_composition, build_native_assembly_composition
from cadpy_common.assembly_spec import AssemblyInstanceSpec, AssemblyNodeSpec, AssemblySpec
from cadpy_common.glb import read_step_topology_manifest_from_glb
from cadpy_common.glb_topology import STEP_TOPOLOGY_SCHEMA_VERSION
from cadpy_common.render import part_glb_path
from tests.python.support.cad_test_roots import IsolatedCadRoots


IDENTITY_TRANSFORM = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]


def _pad4(payload: bytes, *, byte: bytes = b"\0") -> bytes:
    padding = (4 - (len(payload) % 4)) % 4
    return payload + (byte * padding)


def _write_topology_glb(path: Path, manifest: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    manifest_payload = json.dumps({"schemaVersion": STEP_TOPOLOGY_SCHEMA_VERSION, "profile": "index", **manifest}, separators=(",", ":")).encode("utf-8")
    display_manifest_payload = json.dumps(
        {
            "schemaVersion": STEP_TOPOLOGY_SCHEMA_VERSION,
            "profile": "surface-edges",
            "stepHash": "",
            "halfEdgesView": "surfaceHalfEdges",
            "buffers": {"views": {"surfaceHalfEdges": {"dtype": "uint32", "bufferView": 1, "byteOffset": 0, "byteLength": 0, "count": 0, "itemSize": 4}}},
        },
        separators=(",", ":"),
    ).encode("utf-8")
    display_offset = len(_pad4(manifest_payload))
    binary = _pad4(manifest_payload) + _pad4(display_manifest_payload)
    gltf = {
        "asset": {"version": "2.0"},
        "buffers": [{"byteLength": len(binary)}],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": len(manifest_payload)},
            {"buffer": 0, "byteOffset": display_offset, "byteLength": len(display_manifest_payload)},
        ],
        "extensionsUsed": ["STEP_topology"],
        "extensions": {
            "STEP_topology": {
                "schemaVersion": STEP_TOPOLOGY_SCHEMA_VERSION,
                "indexView": 0,
                "edgeView": 1,
                "entryKind": "assembly" if manifest.get("assembly") else "part",
                "encoding": "utf-8",
            }
        },
    }
    json_chunk = _pad4(json.dumps(gltf, separators=(",", ":")).encode("utf-8"), byte=b" ")
    path.write_bytes(
        b"glTF"
        + struct.pack("<II", 2, 12 + 8 + len(json_chunk) + 8 + len(binary))
        + struct.pack("<I4s", len(json_chunk), b"JSON")
        + json_chunk
        + struct.pack("<I4s", len(binary), b"BIN\0")
        + binary
    )


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
        topology_path = part_glb_path(self.temp_root / "assembly.step")
        _write_topology_glb(
            topology_path,
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
                    ]
                },
                "occurrences": rows,
            },
        )
        return topology_path

    def _assembly_mesh_path(self) -> Path:
        return part_glb_path(self.temp_root / "assembly.step")

    def _write_source_topology(self, step_path: Path) -> None:
        _write_topology_glb(
            part_glb_path(step_path),
            {
                "stats": {
                    "shapeCount": 1,
                    "faceCount": 6,
                    "edgeCount": 12,
                }
            },
        )

    def _read_topology(self, topology_path: Path) -> dict[str, object]:
        manifest = read_step_topology_manifest_from_glb(topology_path)
        self.assertIsNotNone(manifest)
        assert manifest is not None
        return manifest

    def test_native_assembly_composition_declares_self_contained_mesh(self) -> None:
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

        payload = build_native_assembly_composition(
            cad_ref="imports/assembly",
            topology_path=topology_path,
            topology_manifest=self._read_topology(topology_path),
            mesh_path=self._assembly_mesh_path(),
        )

        self.assertEqual("native", payload["mode"])
        self.assertEqual("gltf-node-extras", payload["mesh"]["addressing"])
        self.assertEqual("cadOccurrenceId", payload["mesh"]["occurrenceIdKey"])
        self.assertIn(".assembly.step.glb?v=", payload["mesh"]["url"])
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
            },
            part["topologyCounts"],
        )
        self.assertEqual("sample_component", part["displayName"])
        self.assertNotIn("assets", part)

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
        payload = build_native_assembly_composition(
            cad_ref="imports/assembly",
            topology_path=topology_path,
            topology_manifest=self._read_topology(topology_path),
            mesh_path=self._assembly_mesh_path(),
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
        payload = build_native_assembly_composition(
            cad_ref="imports/assembly",
            topology_path=topology_path,
            topology_manifest=self._read_topology(topology_path),
            mesh_path=self._assembly_mesh_path(),
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
            topology_manifest=self._read_topology(topology_path),
            assembly_spec=assembly_spec,
            mesh_path=self._assembly_mesh_path(),
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
            topology_manifest=self._read_topology(topology_path),
            assembly_spec=assembly_spec,
            mesh_path=self._assembly_mesh_path(),
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
        module_source_path.write_text("def gen_step():\n    return {'instances': []}\n", encoding="utf-8")
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
            topology_manifest=self._read_topology(topology_path),
            assembly_spec=assembly_spec,
            mesh_path=self._assembly_mesh_path(),
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
        source_topology_path = part_glb_path(source_step_path)
        _write_topology_glb(
            source_topology_path,
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
            },
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
            topology_manifest=self._read_topology(topology_path),
            assembly_spec=assembly_spec,
            mesh_path=self._assembly_mesh_path(),
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
        self.assertEqual("gltf-node-extras", payload["mesh"]["addressing"])
        self.assertEqual("o1.2", sample_module["occurrenceId"])
        self.assertEqual(["o1.2.7"], sample_module["leafPartIds"])
        self.assertEqual("o1.2.7", finger["occurrenceId"])
        self.assertNotIn("assets", finger)

    def test_linked_native_subassembly_synthesizes_source_assembly_from_occurrences(self) -> None:
        source_step_path = self._write_catalog_step("imports/vendor")
        source_topology_path = part_glb_path(source_step_path)
        _write_topology_glb(
            source_topology_path,
            {
                "stats": {
                    "shapeCount": 2,
                    "faceCount": 12,
                    "edgeCount": 24,
                },
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
                    ]
                },
                "occurrences": [
                    ["o9", "", "9", "vendor", "vendor", IDENTITY_TRANSFORM, None, 2, 12, 24],
                    [
                        "o9.1",
                        "o9",
                        "9.1",
                        "finger_a",
                        "finger_a",
                        IDENTITY_TRANSFORM,
                        {"min": [0, 0, 0], "max": [1, 1, 1]},
                        1,
                        6,
                        12,
                    ],
                    [
                        "o9.2",
                        "o9",
                        "9.2",
                        "finger_b",
                        "finger_b",
                        IDENTITY_TRANSFORM,
                        {"min": [1, 0, 0], "max": [2, 1, 1]},
                        1,
                        6,
                        12,
                    ],
                ],
            },
        )
        topology_path = self._write_topology(
            [
                ["o1", "", "1", "assembly", "assembly", IDENTITY_TRANSFORM, None, 2, 12, 24, 16],
                ["o1.2", "o1", "1.2", "sample_module", "sample_module", IDENTITY_TRANSFORM, None, 2, 12, 24, 16],
                [
                    "o1.2.1",
                    "o1.2",
                    "1.2.1",
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
                    "o1.2.2",
                    "o1.2",
                    "1.2.2",
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
            topology_manifest=self._read_topology(topology_path),
            assembly_spec=assembly_spec,
            mesh_path=self._assembly_mesh_path(),
            entries_by_step_path={
                source_step_path.resolve(): SimpleNamespace(
                    kind="part",
                    step_path=source_step_path,
                )
            },
            read_assembly_spec=lambda path: (_ for _ in ()).throw(AssertionError(path)),
        )

        sample_module = payload["root"]["children"][0]
        leaf_a, leaf_b = sample_module["children"]
        self.assertEqual("assembly", sample_module["nodeType"])
        self.assertEqual("native", sample_module["sourceKind"])
        self.assertEqual("o1.2", sample_module["occurrenceId"])
        self.assertEqual(["o1.2.1", "o1.2.2"], sample_module["leafPartIds"])
        self.assertTrue(sample_module["sourcePath"].endswith("imports/vendor.step"))
        self.assertEqual("o9", sample_module["sourceOccurrenceId"])
        self.assertEqual("o9", sample_module["sourceRootOccurrenceId"])
        self.assertEqual("o1.2", sample_module["sourceRootTargetOccurrenceId"])
        self.assertEqual("o1.2.1", leaf_a["occurrenceId"])
        self.assertEqual("o1.2.2", leaf_b["occurrenceId"])
        self.assertTrue(leaf_a["sourcePath"].endswith("imports/vendor.step"))
        self.assertEqual("o9.1", leaf_a["sourceOccurrenceId"])
        self.assertEqual("o9", leaf_a["sourceRootOccurrenceId"])
        self.assertEqual("o1.2", leaf_a["sourceRootTargetOccurrenceId"])
        self.assertNotIn("assets", leaf_a)
        self.assertNotIn("assets", leaf_b)

    def test_linked_part_with_single_source_occurrence_stays_collapsed(self) -> None:
        source_step_path = self._write_catalog_step("imports/vendor_part")
        source_topology_path = part_glb_path(source_step_path)
        _write_topology_glb(
            source_topology_path,
            {
                "stats": {
                    "shapeCount": 1,
                    "faceCount": 6,
                    "edgeCount": 12,
                },
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
                    ]
                },
                "occurrences": [
                    [
                        "o9",
                        "",
                        "9",
                        "vendor_part",
                        "vendor_part",
                        IDENTITY_TRANSFORM,
                        {"min": [0, 0, 0], "max": [1, 1, 1]},
                        1,
                        6,
                        12,
                    ]
                ],
            },
        )
        topology_path = self._write_topology(
            [
                ["o1", "", "1", "assembly", "assembly", IDENTITY_TRANSFORM, None, 1, 6, 12, 8],
                [
                    "o1.2",
                    "o1",
                    "1.2",
                    "sample_part",
                    "sample_part",
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
                    instance_id="sample_part",
                    source_path=source_step_path.resolve(),
                    path="vendor_part.step",
                    name="sample_part",
                    transform=tuple(float(value) for value in IDENTITY_TRANSFORM),
                ),
            ),
        )

        payload = build_linked_assembly_composition(
            cad_ref="assemblies/assembly",
            topology_path=topology_path,
            topology_manifest=self._read_topology(topology_path),
            assembly_spec=assembly_spec,
            mesh_path=self._assembly_mesh_path(),
            entries_by_step_path={
                source_step_path.resolve(): SimpleNamespace(
                    kind="part",
                    step_path=source_step_path,
                )
            },
            read_assembly_spec=lambda path: (_ for _ in ()).throw(AssertionError(path)),
        )

        child = payload["root"]["children"][0]
        self.assertEqual("part", child["nodeType"])
        self.assertEqual("o1.2", child["occurrenceId"])
        self.assertEqual([], child["children"])

    def test_linked_native_subassembly_handles_extra_target_wrapper(self) -> None:
        source_step_path = self._write_catalog_step("imports/vendor")
        source_topology_path = part_glb_path(source_step_path)
        _write_topology_glb(
            source_topology_path,
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
            },
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
            topology_manifest=self._read_topology(topology_path),
            assembly_spec=assembly_spec,
            mesh_path=self._assembly_mesh_path(),
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
        self.assertNotIn("assets", leaf_a)
        self.assertNotIn("assets", leaf_b)

    def test_linked_native_subassembly_renders_target_wrapper_for_wrapped_source_part(self) -> None:
        source_step_path = self._write_catalog_step("imports/vendor")
        source_topology_path = part_glb_path(source_step_path)
        _write_topology_glb(
            source_topology_path,
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
            },
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
            topology_manifest=self._read_topology(topology_path),
            assembly_spec=assembly_spec,
            mesh_path=self._assembly_mesh_path(),
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
        self.assertNotIn("assets", rendered_part)


if __name__ == "__main__":
    unittest.main()
